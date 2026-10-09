"""Captions: splitting words into captions, storage, .srt, drawing them into the video.

Speech recognition itself is replaced by a stand-in here (the real model is a download);
everything around it is real.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

import itertools
import types
from pathlib import Path

import pytest

from listo.core import captions
from listo.core.captions import Cue, Transcript, Word, for_output, split_cues, to_srt, wrap
from listo.core.engine import Conversion
from listo.core.presets import Settings
from listo.core.probe import probe
from listo.core.tools import capabilities

from .helpers import HAS_FFMPEG, ff

WORDS = [
    Word(i * 0.4, i * 0.4 + 0.3, w)
    for i, w in enumerate(["so", "we", "drove", "out", "to", "the", "border", "at", "night."])
]
WORDS += [Word(6.0 + i * 0.4, 6.3 + i * 0.4, w) for i, w in enumerate(["Nobody", "said", "a", "word."])]


def test_split_respects_length_pauses_and_sentences():
    cues = split_cues(WORDS, words_per_line=3, lines=2)
    assert [c.text for c in cues] == ["so we drove out to the", "border at night.", "Nobody said a word."]
    assert all(c.end <= n.start for c, n in itertools.pairwise(cues))  # never overlap


def test_wrap_balances_lines():
    assert wrap("one two three four five", 3) == ["one two three", "four five"]
    assert wrap("one two three four", 3) == ["one two", "three four"]


def test_trim_shifts_and_clips_captions():
    cues = [Cue(1.0, 3.0, "a"), Cue(4.0, 6.0, "b"), Cue(9.0, 10.0, "c")]
    assert for_output(cues, 2.0, 5.0) == [Cue(0.0, 1.0, "a"), Cue(2.0, 4.0, "b")]


def test_srt_format():
    srt = to_srt([Cue(0.5, 2.25, "Hola, ¿qué tal? Muy bien")], 3)
    assert srt.startswith("1\n00:00:00,500 --> 00:00:02,250\nHola, ¿qué tal?\nMuy bien\n")


def test_store_round_trip(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(captions, "data_dir", lambda: tmp_path)
    clip = tmp_path / "a.mov"
    clip.write_bytes(b"x")
    t = Transcript(
        str(clip), "small", "es", WORDS, split_cues(WORDS, 7, 2), edited=True, reviewed=True, layout=(7, 2)
    )
    captions.save(t)
    back = captions.load(clip)
    assert back == t
    clip.write_bytes(b"changed")  # a different file now: its old captions don't apply
    assert captions.load(clip) is None


def test_edited_captions_are_kept_when_layout_changes():
    t = Transcript("x", words=WORDS, cues=split_cues(WORDS, 7, 2), layout=(7, 2))
    assert len(t.cues_for(2, 1)) > 3  # re-split from the words
    t.cues = [Cue(0, 2, "fixed text")]
    t.edited = True
    assert [c.text for c in t.cues_for(7, 2)] == ["fixed text"]


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_transcribe_with_a_stand_in_model(tmp_path: Path, monkeypatch):
    clip = tmp_path / "talk.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=2", "-f", "lavfi", "-i", "sine=d=2", "-shortest",
       "-c:v", "libx264", "-c:a", "aac", str(clip))  # fmt: skip

    class FakeModel:
        def transcribe(self, audio, **kw):
            assert audio.dtype.name == "float32" and len(audio) > 16000  # real samples from ffmpeg
            assert kw["word_timestamps"] and kw["multilingual"]
            w = [
                types.SimpleNamespace(start=0.1, end=0.5, word=" Hola"),
                types.SimpleNamespace(start=0.6, end=1.0, word=" mundo."),
            ]
            return iter([types.SimpleNamespace(end=1.0, words=w)]), types.SimpleNamespace(language="es")

    monkeypatch.setattr(captions, "_model", lambda name, on_status: FakeModel())
    seen = []
    t = captions.transcribe(str(clip), probe(clip), on_progress=seen.append)
    assert [c.text for c in t.cues] == ["Hola mundo."] and t.language == "es" and seen


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize(("style", "box"), [("clean", True), ("vhs", True), ("vhs", False)])
def test_captions_burn_in_and_srt(tmp_path: Path, style, box):
    clip = tmp_path / "talk.mov"
    ff("-f", "lavfi", "-i", "color=c=gray:s=640x360:d=3", "-f", "lavfi", "-i", "sine=d=3", "-shortest",
       "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip))  # fmt: skip
    cues = [Cue(0.2, 1.4, "First line of the caption here"), Cue(1.6, 2.8, "Second one")]
    s = Settings(
        video_preset="h264", captions=True, caption_style=style, caption_box=box, caption_srt=True,
        burn_style="vhs", burn_timecode=True, aspect="2.35:1", aspect_fit="matte", naming="{name}_cc",
    )  # fmt: skip
    r = Conversion(str(clip), probe(clip), s, capabilities(), set(), captions=cues, trim=(0.5, 3.0)).run()
    assert r.status == "done", r.message
    assert any("Captions added" in n for n in r.notes)
    srt = r.output.with_suffix(".srt").read_text()
    assert srt.startswith("1\n00:00:00,000 --> 00:00:00,900\n")  # shifted for the trim
    from PIL import Image

    png = tmp_path / "f.png"
    ff("-ss", "0.5", "-i", str(r.output), "-frames:v", "1", str(png))
    im = Image.open(png).convert("L")
    bar_top = 360 - 52  # 2.35:1 bars on 640×360 are 52 px tall
    over_bar = [im.getpixel((x, y)) for x in range(160, 480, 2) for y in range(bar_top + 2, 352)]
    assert max(over_bar) > 200  # white caption text drawn over the bottom cinema bar


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_convert_makes_then_checks_captions_first(tmp_path: Path, monkeypatch):
    """Convert -> captions are made -> the editor opens -> accepted -> the clip converts with them."""
    import os
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QDialog

    import listo.ui.caption_editor as ed
    import listo.ui.main_window as mw
    import listo.ui.sidebar as sb

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    monkeypatch.setattr(captions, "data_dir", lambda: tmp_path / "data")

    class FakeModel:
        def transcribe(self, audio, **kw):
            w = [
                types.SimpleNamespace(start=0.2, end=0.6, word=" Hello"),
                types.SimpleNamespace(start=0.7, end=1.1, word=" there."),
            ]
            return iter([types.SimpleNamespace(end=1.1, words=w)]), types.SimpleNamespace(language="en")

    monkeypatch.setattr(captions, "_model", lambda name, on_status: FakeModel())
    opened = []

    def fake_exec(self):
        opened.append([c[0] for c in self.clips])
        self.cues[0][0].text = "Hello there, fixed."
        self.changed.add(0)
        self._accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ed.CaptionEditor, "exec", fake_exec)
    app = QApplication.instance() or QApplication([])
    clip = tmp_path / "talk.mov"
    ff("-f", "lavfi", "-i", "color=c=gray:s=320x240:d=2", "-f", "lavfi", "-i", "sine=d=2", "-shortest",
       "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip))  # fmt: skip
    w = mw.MainWindow()
    w.settings.captions, w.settings.caption_srt, w.settings.verify = True, True, False
    w.settings.naming = "{name}_cc"
    w.add_paths([str(clip)])

    def wait(cond, timeout=60):
        end = time.monotonic() + timeout
        while not cond() and time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)
        return cond()

    assert wait(lambda: all(it.state == "ready" for it in w.items.values()))
    w.start()
    assert wait(lambda: any(it.state == "done" for it in w.items.values()))
    assert opened == [["talk.mov"]]
    srt = (tmp_path / "talk_cc.srt").read_text()
    assert "Hello there, fixed." in srt
    assert captions.load(clip).reviewed
    w.close()
    app.processEvents()


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_preview_task_draws_captions(tmp_path: Path):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from listo.ui.workers import PreviewSignals, PreviewTask

    app = QApplication.instance() or QApplication([])
    clip = tmp_path / "c.mov"
    ff("-f", "lavfi", "-i", "color=c=gray:s=320x240:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip))
    got = []
    sig = PreviewSignals()
    sig.done.connect(lambda seq, data, err: got.append((data, err)))
    s = Settings(video_preset="h264", captions=True)
    PreviewTask(1, str(clip), probe(clip), s, 0.5, False, sig, captions=[Cue(0.0, 2.0, "Hello")]).run()
    app.processEvents()
    assert got and got[0][0] and not got[0][1]
