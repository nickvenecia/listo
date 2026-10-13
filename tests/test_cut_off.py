"""Words are never cut off: every screen and dialog, at the size it opens at and at the smallest it allows,
shows each piece of text whole (wrapped, or ended with "…" and the whole text in its tooltip).
tests/cut_off.py does the finding. A new screen or dialog gets a line here."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QWidget

from tests.cut_off import cut_off
from tests.helpers import HAS_FFMPEG, ff

LONG = "A sentence much too long for a box only sixty pixels wide"


def _release_text() -> str:
    """This version's release text, as the update window gets it (CHANGELOG entries + the download table)."""
    import importlib.util

    from listo import __version__

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("release_notes", root / "scripts" / "release_notes.py")
    rn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rn)
    return rn.notes(rn.CHANGELOG.read_text(encoding="utf-8"), __version__)


def _wait(app, ms: int) -> None:
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def _gone(app, w: QWidget) -> None:
    """Close a window for good (its dialogs go with it), so later tests don't restyle it at every look change."""
    w.close()
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _until(app, cond, timeout: float = 30.0) -> bool:
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
    return cond()


class Looker:
    """Looks at windows and keeps what doesn't fit, named by where it was seen."""

    def __init__(self, app):
        from listo.ui.style import tokens

        self.app = app
        self.settle_ms = max(tokens.DOCK_MS, tokens.FADE_MS) + 120  # slides and fades finish first
        self.found: list[str] = []

    def look(self, win: QWidget, where: str) -> None:
        _wait(self.app, self.settle_ms)
        self.found += [f"{where}: {problem}" for problem in cut_off(win)]

    def sizes(self, win: QWidget, where: str, normal: tuple[int, int] | None = None) -> None:
        """At the size it opens at (or `normal`), then at the smallest it allows; then back."""
        was = win.size()
        if normal:
            win.resize(*normal)
        self.look(win, where)
        win.resize(1, 1)  # Qt stops at the window's minimum size
        self.look(win, f"{where} (smallest)")
        win.resize(was)


@pytest.fixture
def looker(qapp, monkeypatch):
    """Dialogs that would wait for a click (exec) are looked at, then closed, instead."""
    found = Looker(qapp)

    def look_instead(self):
        self.show()
        found.sizes(self, f"{type(self).__name__} {self.windowTitle()!r}")
        self.close()
        return 0  # as if cancelled

    monkeypatch.setattr(QDialog, "exec", look_instead)
    return found


@pytest.fixture
def files(tmp_path):
    """Two videos with sound, a photo, a sound file and a file Listo can't convert."""
    a = tmp_path / "A001_C001_0915XY_001.mov"
    b = tmp_path / "A001_C002_0915XY_001 with a much longer name from the camera card.mov"
    for c in (a, b):
        ff("-f", "lavfi", "-i", "testsrc2=s=320x180:d=2", "-f", "lavfi", "-i", "sine=d=2", "-shortest",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(c))  # fmt: skip
    still = tmp_path / "still.png"
    ff("-f", "lavfi", "-i", "color=c=teal:s=64x64", "-frames:v", "1", str(still))
    sound = tmp_path / "room tone.wav"
    ff("-f", "lavfi", "-i", "sine=d=1", str(sound))
    note = tmp_path / "notes.txt"
    note.write_text("not a picture")
    return [a, b, still, sound, note]


def test_the_checker_finds_words_cut_off(qapp):
    label, button = QLabel(LONG), QPushButton(LONG)
    for w in (label, button):
        w.setFixedWidth(60)
        w.show()
    _wait(qapp, 50)
    assert len(cut_off(label)) == 1 and len(cut_off(button)) == 1
    label.setWordWrap(True)  # more lines, and room for them: fine
    label.setFixedHeight(label.heightForWidth(60))
    assert cut_off(label) == []
    from listo.ui.components.widgets import ElidedLabel

    short = ElidedLabel(LONG)  # cut short with "…" on purpose, the whole text in its tooltip: fine
    short.setFixedWidth(60)
    short.show()
    _wait(qapp, 50)
    assert short.text().endswith("…") and short.toolTip() and cut_off(short) == []
    for w in (label, button, short):
        w.close()


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_no_words_cut_off_in_the_window(qapp, looker, files, monkeypatch):
    import listo.ui.window.jobs as wk
    from listo.ui.style import tokens
    from listo.ui.window.main_window import MainWindow
    from tests import speech_standin

    monkeypatch.setattr(wk.TranscribeThread, "target", staticmethod(speech_standin.serve))
    w = MainWindow()
    w._restored = True
    w.resize(*tokens.WINDOW_SIZE)
    w.show()

    def look(state: str) -> None:
        looker.sizes(w, state, tokens.WINDOW_SIZE)

    try:
        look("first launch: the start tiles")
        w._show_update_button("12.10.0")
        look("an update waiting")
        w.btn_update.hide()

        w.add_paths([str(p) for p in files])
        assert _until(qapp, lambda: all(it.state != "probing" for it in w.items.values()))
        w._refresh_now()
        look("the list, Convert To open")
        w.convert.open_groups(True)
        w.export_panel.adv.set_open(True)
        look("every fold open")

        w.settings.apply(
            {
                "burn_timecode": True,
                "burn_filename": True,
                "burn_datetime": True,
                "burn_style": "vhs",
                "tape_glitches": "often",
                "tape_blue": True,
                "captions": True,
                "caption_srt": True,
                "aspect": "2.39",
                "aspect_fit": "matte",
                "destination": "subfolder",
                "naming": "{date}_{name}_{preset}_{res}",
                "join": True,
                "collision": "replace",
                "keep_dates": False,
                "verify": False,
                "parallel": True,
            }
        )
        w.convert.reload()
        w.export_panel.reload()
        w._settings_changed()
        w._refresh_now()
        assert _until(qapp, lambda: w.btn_check.isEnabled())  # (captions made by the stand-in)
        w._refresh_now()
        w._select(set(w.order[:2]))
        look("everything switched on, two files picked")
        w.convert.open_groups(False)
        w.export_panel.adv.set_open(False)
        look("every fold closed, saying what's on")

        w.go("done")
        look("a place with nothing in it")
        w.go("attention")
        look("Need a Look")
        w.go("all")
        w.show_panel(False)
        look("Convert To closed")
        w.show_panel(True)

        w._convert_after_captions = True
        w._refresh_footer()
        look("waiting for captions")
        w._convert_after_captions = False
        w.running, w.batch = True, list(w.order)  # as if converting (no files are made)
        w._refresh_footer()
        look("converting")
        w.paused = True
        w._refresh_footer()
        look("paused")
        w.running, w.paused = False, False
        w._last_summary = (120, 30, 20, 10)  # converted, failed, skipped, to check
        w.btn_show.show()
        w._refresh_footer(finished=True)
        look("finished, some failed")
    finally:
        w.running = False
        _gone(qapp, w)
    assert looker.found == [], "words cut off:\n" + "\n".join(looker.found)


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_no_words_cut_off_in_any_dialog(qapp, looker, files, monkeypatch):
    import listo.ui.window.jobs as wk
    from listo.core import storage, update
    from listo.core.engine import Result
    from listo.ui.dialogs.settings import SettingsDialog
    from listo.ui.window.main_window import MainWindow
    from tests import speech_standin

    monkeypatch.setattr(wk.TranscribeThread, "target", staticmethod(speech_standin.serve))
    w = MainWindow()
    w._restored = True
    w.show()
    try:
        for pane in ("general", "shortcuts", "data"):
            w.open_settings(pane)
        w.open_feedback()
        w._about()
        w.ask_link()
        w._missing_ffmpeg()
        w.convert._save_recipe()
        w.latest = update.parse_release({"tag_name": "v12.10.0", "body": _release_text()})
        w.open_update()

        for k in storage.kinds():  # something in every kind, so each can be deleted
            k.paths[0].mkdir(parents=True, exist_ok=True)
            (k.paths[0] / "kept.bin").write_bytes(b"1234")
        d = SettingsDialog(w, "data")
        d.storage.refresh()
        d.storage._delete([k.key for k in storage.kinds()])  # its alert
        d.close()

        w.add_paths([str(p) for p in files])
        assert _until(qapp, lambda: all(it.state != "probing" for it in w.items.values()))
        w.settings.captions = True
        w.convert.reload()
        w._settings_changed()
        assert _until(qapp, lambda: w.btn_check.isEnabled())
        first, long_name = w.order[:2]
        w._select({long_name})
        w.remove_selected()
        w._select(set(w.order))
        w.remove_selected()
        w.clear_all()
        w.trim_item(first)
        w.open_preview()
        w.check_captions()

        it = w.items[first]
        it.state = "done"
        it.result = Result(
            "done",
            output=Path(it.path).with_name("A001_C001_0915XY_001_ProRes 422 HQ.mov"),
            notes=["Double-checked: plays to the end, same length as the original."],
            log="frame=   48 fps=0.0 q=-0.0 Lsize=    1024kB time=00:00:02.00 bitrate=4194.3kbits/s speed=9.1x",
            command=[
                "ffmpeg",
                "-hide_banner",
                "-i",
                it.path,
                "-c:v",
                "prores_ks",
                "-profile:v",
                "3",
                "out.mov",
            ],
        )
        w.show_details(first)
        it.state, it.message = "failed", "ffmpeg stopped: Invalid data found when processing input."
        w.show_details(first)
    finally:
        _gone(qapp, w)
    assert looker.found == [], "words cut off:\n" + "\n".join(looker.found)
