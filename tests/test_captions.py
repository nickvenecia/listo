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
def test_convert_waits_for_captions_then_converts(tmp_path: Path, monkeypatch):
    """Convert -> captions are still being made -> Listo waits, then converts with them (no check forced)."""
    import os
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QDialog

    import listo.ui.dialogs.captions as ed
    import listo.ui.panels.convert as sb
    import listo.ui.window.main_window as mw

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    monkeypatch.setattr(captions, "data_dir", lambda: tmp_path / "data")

    import listo.ui.window.jobs as wk
    from tests import speech_standin

    monkeypatch.setattr(wk.TranscribeThread, "target", staticmethod(speech_standin.serve))
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
    assert opened == []  # checking is its own button now
    srt = (tmp_path / "talk_cc.srt").read_text()
    assert "Hello there." in srt
    w.close()
    app.processEvents()


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_captions_are_made_in_the_background_before_convert(tmp_path: Path, monkeypatch):
    """Captions start on their own as soon as the clip is in the list (no Convert needed)."""
    import os
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QDialog

    import listo.ui.dialogs.captions as ed
    import listo.ui.panels.convert as sb
    import listo.ui.window.main_window as mw

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    monkeypatch.setattr(captions, "data_dir", lambda: tmp_path / "data")

    import listo.ui.window.jobs as wk
    from tests import speech_standin

    monkeypatch.setattr(wk.TranscribeThread, "target", staticmethod(speech_standin.serve))
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
    assert wait(lambda: all(it.transcript is not None for it in w.items.values()))
    assert not opened and not w.running  # nothing popped up, nothing converted
    assert wait(lambda: "1 New" in w.btn_check.text())
    assert w.btn_check.isVisibleTo(w)
    w.check_captions()  # the Check Captions button
    assert opened == [["talk.mov"]]
    assert captions.load(clip).reviewed
    assert "1 New" not in w.btn_check.text()
    w.close()
    app.processEvents()


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_preview_task_draws_captions(tmp_path: Path):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from listo.ui.window.jobs import PreviewSignals, PreviewTask

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


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_worker_process_round_trip_and_stop(tmp_path: Path):
    """The real hand-off: clips go to a separate process and come back as transcripts; Stop ends it."""
    import time

    from PySide6.QtCore import QCoreApplication, Qt

    import listo.ui.window.jobs as wk
    from tests import speech_standin

    app = QCoreApplication.instance() or QCoreApplication([])
    clip = tmp_path / "talk.wav"
    ff("-f", "lavfi", "-i", "sine=d=1", str(clip))
    s = Settings()
    got = []
    th = wk.TranscribeThread([(1, str(clip), None, s)])
    th.target = speech_standin.serve
    th.done.connect(lambda i, t, e: got.append((i, t, e)), Qt.ConnectionType.DirectConnection)
    th.start()
    end = time.monotonic() + 60
    while th.isRunning() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
    assert got and got[0][1] is not None, got
    assert [w.text for w in got[0][1].words] == ["Hello", "there."]

    slow = wk.TranscribeThread([(2, str(clip), None, s)])
    slow.target = speech_standin.serve_slowly
    slow.start()
    time.sleep(3)  # let the process start and get stuck "loading the model"
    t0 = time.monotonic()
    slow.cancel()
    assert slow.wait(10_000)
    assert time.monotonic() - t0 < 5


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_caption_check_plays_and_lights_up_the_caption_on_screen(tmp_path: Path, monkeypatch):
    import os
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    import listo.ui.dialogs.captions as ed

    if not ed.HAS_PLAYER:
        pytest.skip("Qt's media player isn't installed")
    monkeypatch.setattr(captions, "data_dir", lambda: tmp_path / "data")
    app = QApplication.instance() or QApplication([])
    clip = tmp_path / "talk.mov"
    ff("-f", "lavfi", "-i", "color=c=gray:s=320x240:d=3", "-f", "lavfi", "-i", "sine=d=3", "-shortest",
       "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip))  # fmt: skip
    words = [
        Word(0.1, 0.5, "First"),
        Word(0.6, 0.9, "line."),
        Word(1.5, 1.9, "Second"),
        Word(2.0, 2.4, "one."),
    ]
    t = Transcript(str(clip), words=words, cues=[Cue(0.1, 1.0, "First line."), Cue(1.5, 2.6, "Second one.")])
    t.edited = True
    s = Settings(captions=True, caption_style="vhs")
    d = ed.CaptionEditor([("talk.mov", str(clip), probe(clip), s, t)])

    def wait(cond, timeout=20):
        end = time.monotonic() + timeout
        while not cond() and time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)
        return cond()

    assert not d.player.is_open()  # nothing opens in Qt's player until Play
    d.player.seek(1.8)
    assert wait(lambda: d.current == 1)
    assert d.edits[1].property("current") and not d.edits[0].property("current")
    assert not d.player.overlay.pixmap().isNull()  # the caption is drawn over the picture
    d.times[0].clicked.emit()  # click a time: jump there
    assert wait(lambda: d.current == 0)
    d.edits[0].setPlainText("")  # a cleared line shows nothing
    assert wait(lambda: d.player.overlay.pixmap().isNull())
    d._row_focused(d.edits[1])  # clicking a line jumps there
    assert wait(lambda: d.current == 1)
    d.player.seek(2.65)  # a gap after the last caption: add one there
    assert wait(lambda: d.current is None)
    d.add_caption()
    assert len(d.cues[0]) == 3 and abs(d.cues[0][2].start - 2.65) < 0.05
    d.edits[2].setPlainText("Added.")
    d.player.seek(1.6)
    d.player.play()  # the first Play opens the clip, from where you are
    assert wait(lambda: d.player.is_playing())
    assert d.player.position() >= 1.5
    d.player.pause()
    d._accept()
    assert [c.text for c in captions.load(clip).cues] == ["Second one.", "Added."]


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_changing_accuracy_redoes_the_captions(tmp_path: Path, monkeypatch):
    """Fast / Balanced / Most Accurate actually matter: switching redoes captions made the other way.
    Hand-edited ones are only redone if you say so."""
    import os
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    import listo.ui.panels.convert as sb
    import listo.ui.window.jobs as wk
    import listo.ui.window.main_window as mw
    from tests import speech_standin

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    monkeypatch.setattr(captions, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(wk.TranscribeThread, "target", staticmethod(speech_standin.serve))
    answers = []
    monkeypatch.setattr(mw, "confirm", lambda *a, **k: answers.pop(0))
    app = QApplication.instance() or QApplication([])
    a, b = tmp_path / "a.mov", tmp_path / "b.mov"
    for c in (a, b):
        ff("-f", "lavfi", "-i", "color=c=gray:s=320x240:d=2", "-f", "lavfi", "-i", "sine=d=2", "-shortest",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(c))  # fmt: skip
    w = mw.MainWindow()
    w.settings.captions = True

    def wait(cond, timeout=60):
        end = time.monotonic() + timeout
        while not cond() and time.monotonic() < end:
            app.processEvents()
            time.sleep(0.02)
        return cond()

    w.add_paths([str(a), str(b)])
    its = lambda: sorted(w.items.values(), key=lambda it: it.path)  # noqa: E731
    assert wait(lambda: all(it.transcript is not None for it in w.items.values()))
    assert {it.transcript.model for it in w.items.values()} == {"small"}  # Balanced
    first, second = its()
    first.transcript.edited = True  # you fixed this one by hand
    answers.append(False)
    w.settings.caption_model = "fast"
    w._settings_changed()
    assert wait(lambda: second.transcript.model == "base")  # redone with Fast
    assert first.transcript.model == "small" and not answers  # asked, kept your fixes
    answers.append(True)
    w.settings.caption_model = "best"
    w._settings_changed()
    assert wait(
        lambda: first.transcript.model == "large-v3-turbo" and second.transcript.model == "large-v3-turbo"
    )
    w.close()
    app.processEvents()
