"""A link downloads only when Convert is pressed; Move Originals to the Trash."""

from __future__ import annotations

import shutil
import threading
import time

import pytest
from PySide6.QtCore import QThread, Signal

from tests.helpers import ff


def _wait(app, cond, timeout=30.0) -> bool:
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
    return cond()


@pytest.fixture
def clip(tmp_path):
    c = tmp_path / "A001_C001.mov"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x180:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(c))
    return c


@pytest.fixture
def downloads(monkeypatch, tmp_path, clip):
    """Stand-in for the downloader: "downloads" a copy of the clip once it's let go. Returns the
    threads started, and the switch that lets them finish."""
    from listo.ui.window import main_window

    started, go = [], threading.Event()

    class _Job:
        def __init__(self):
            self.canceled = False

        def cancel(self):
            self.canceled = True

    class _Download(QThread):
        progress = Signal(int, float, str)
        titled = Signal(int, str)
        done = Signal(int, str, str)

        def __init__(self, item_id: int, url: str):
            super().__init__()
            self.item_id, self.job = item_id, _Job()
            started.append(self)

        def run(self):
            while not go.is_set() and not self.job.canceled:
                time.sleep(0.01)
            if self.job.canceled:
                self.done.emit(self.item_id, "", "Canceled")
                return
            saved = tmp_path / "saved" / f"Video {self.item_id}.mov"
            saved.parent.mkdir(exist_ok=True)
            shutil.copy(clip, saved)
            self.done.emit(self.item_id, str(saved), "")

    monkeypatch.setattr(main_window, "DownloadThread", _Download)
    return started, go


def _window():
    from listo.ui.window.main_window import MainWindow

    w = MainWindow()
    w._restored = True
    w.show()
    return w


def test_a_link_downloads_only_when_convert_is_pressed(qapp, downloads):
    started, go = downloads
    w = _window()
    try:
        w.add_links(["https://example.com/watch?v=abc"])
        w._refresh_now()
        it = next(iter(w.items.values()))
        assert it.state == "linked" and not started and not w.downloads  # nothing fetched yet
        assert it.card.status == "Ready" and "Convert" in it.card.meta
        assert w.btn_start.isEnabled() and w.btn_start.text() == "Convert 1 File"
        assert w._place_counts["todo"] == 1
        assert w.dock.opened and w.convert._kind_key[0][0] == 1  # its settings can be changed first

        w.start()
        assert len(started) == 1 and it.state == "downloading" and w.running
        w.stop()  # Stop: the link waits again, nothing half-done in the list
        assert _wait(qapp, lambda: it.state == "linked" and not w.downloads)
        assert not w.running

        go.set()
        w.start()
        assert _wait(qapp, lambda: it.state == "done"), (it.state, it.message)
        assert len(started) == 2 and it.result.output.is_file()
    finally:
        w.shutdown()
        w.close()


def test_joining_waits_for_the_links_then_converts_by_itself(qapp, downloads, clip):
    started, go = downloads
    w = _window()
    try:
        w.add_paths([str(clip)])
        w.add_links(["https://example.com/watch?v=abc"])
        assert _wait(qapp, lambda: all(it.state != "probing" for it in w.items.values()))
        w.settings.join = True
        w.export_panel.reload()
        w.export_panel.set_video_count(2)
        w.start()
        assert not w.running and w._convert_after_links and len(started) == 1
        w._refresh_now()
        assert w.btn_start.text() == "Waiting…" and not w.btn_cancel.isHidden()
        go.set()
        assert _wait(qapp, lambda: getattr(w, "_last_joined", 0) == 2 and not w.running, 60)
        assert all(it.state == "done" for it in w.items.values())
    finally:
        w.shutdown()
        w.close()


def test_originals_go_to_the_trash_only_when_asked_and_only_after_a_good_convert(
    qapp, clip, tmp_path, monkeypatch
):
    from listo.core.fileutil import TRASH
    from listo.ui.window import main_window

    other = tmp_path / "A001_C002.mov"
    shutil.copy(clip, other)
    binned = []

    def bin_it(p):
        binned.append(str(p))
        (tmp_path / "bin").mkdir(exist_ok=True)
        shutil.move(str(p), tmp_path / "bin")
        return True

    monkeypatch.setattr(main_window, "to_trash", bin_it)
    w = _window()
    try:
        assert not w.settings.trash_originals  # off unless you turn it on
        w.add_paths([str(clip)])
        assert _wait(qapp, lambda: all(it.state == "ready" for it in w.items.values()))
        w.start()
        assert _wait(qapp, lambda: all(it.state == "done" for it in w.items.values()))
        assert not binned and clip.is_file()

        w.export_panel.k_trash.setChecked(True)
        assert w.settings.trash_originals
        w.add_paths([str(other)])
        assert _wait(qapp, lambda: any(it.state == "ready" for it in w.items.values()))
        it = next(i for i in w.items.values() if i.state == "ready")
        w.start()
        assert _wait(qapp, lambda: it.state == "done")
        assert binned == [str(other)] and not other.exists() and clip.is_file()
        assert it.result.output.is_file() and it.gone
        assert it.card.output.endswith(f"Original in the {TRASH}")
        w._refresh_now()
        assert w.f_sub.full_text().endswith(f"The original is in the {TRASH}.")
        assert not w._previewable(it)  # nothing left to play
    finally:
        w.shutdown()
        w.close()


def test_a_file_with_a_problem_keeps_its_original(qapp, clip, monkeypatch):
    from listo.core.engine import Result
    from listo.ui.window import main_window

    binned = []
    monkeypatch.setattr(main_window, "to_trash", lambda p: binned.append(p) or True)
    w = _window()
    try:
        w.settings.trash_originals = True
        w.add_paths([str(clip)])
        assert _wait(qapp, lambda: all(it.state == "ready" for it in w.items.values()))
        it = next(iter(w.items.values()))
        it.base = w.settings.copy()
        out = clip.with_name("new.mp4")
        out.write_bytes(b"x")
        w._finished(it.id, Result("done", output=out, warning="The length doesn't match"))
        assert it.state == "warning" and not binned
        w._finished(it.id, Result("failed", message="no"))
        assert not binned
        w._trashed = 0
        w._finished(it.id, Result("done", output=clip))  # the "new file" is the original itself: never
        assert not binned and "couldn't" in it.card.output
    finally:
        w.shutdown()
        w.close()


def test_what_goes_with_an_original(tmp_path):
    from listo.ui.window.trash import safe_to_trash, with_sidecar

    mod, moi, new = tmp_path / "MOV001.MOD", tmp_path / "MOV001.MOI", tmp_path / "MOV001.mp4"
    for f in (mod, moi):
        f.write_bytes(b"x")
    assert with_sidecar(mod) == [mod, moi]  # a JVC clip takes its .MOI along
    assert with_sidecar(new) == [new]
    assert not safe_to_trash(mod, new)  # no new file
    new.write_bytes(b"")
    assert not safe_to_trash(mod, new)  # an empty one
    new.write_bytes(b"x")
    assert safe_to_trash(mod, new)
    assert not safe_to_trash(mod, mod) and not safe_to_trash(tmp_path / "gone.mod", new)


def test_after_a_batch_convert_again_and_move_the_originals_when_asked(qapp, clip, tmp_path, monkeypatch):
    """Once a batch has run, the bar converts the same files again with today's settings (new files, the
    originals untouched), and Clean Up moves the originals to the Trash only after an alert."""
    from listo.core.fileutil import TRASH  # the Recycle Bin on Windows
    from listo.ui.window import main_window

    other = tmp_path / "A001_C002.mov"
    shutil.copy(clip, other)
    binned, asked = [], []
    monkeypatch.setattr(main_window, "to_trash", lambda p: binned.append(str(p)) or True)
    monkeypatch.setattr(main_window, "confirm", lambda *a, **k: asked.append(a[1]) or True)
    w = _window()
    try:
        w.add_paths([str(clip), str(other)])
        assert _wait(qapp, lambda: all(it.state == "ready" for it in w.items.values()))
        w.start()
        assert _wait(qapp, lambda: all(it.state == "done" for it in w.items.values()) and not w.running, 60)
        w._refresh_now()
        first = {it.id: it.result.output for it in w.items.values()}
        assert w.btn_clean.isVisibleTo(w) and w.btn_start.isEnabled()
        assert w.btn_start.text() == "Convert 2 Files Again"

        w.btn_start.click()  # the bar's Convert: the finished files again
        assert _wait(qapp, lambda: w.running or any(it.state != "done" for it in w.items.values()))
        assert _wait(qapp, lambda: all(it.state == "done" for it in w.items.values()) and not w.running, 60)
        for it in w.items.values():
            assert it.result.output != first[it.id] and first[it.id].is_file()  # a new file, the old one kept
        assert clip.is_file() and other.is_file() and not binned

        one = next(iter(w.items.values()))
        w.retry_item(one.id)  # a converted row's arrow: that one again, now
        assert _wait(qapp, lambda: one.state == "done" and not w.running, 60)

        m = main_window.QMenu()
        w._fill_clean_menu(m)
        trash = next(a for a in m.actions() if TRASH in a.text())
        assert trash.isEnabled() and trash.text().startswith("Move 2 Originals")
        trash.trigger()
        assert asked and "2 Originals" in asked[-1]  # asked first, naming how many
        assert sorted(binned) == sorted([str(clip), str(other)])
        assert all(it.gone for it in w.items.values())
        w._refresh_now()
        assert w.btn_start.text() == "Convert" and not w.btn_start.isEnabled()  # nothing left to redo
        w._fill_clean_menu(m)
        assert not next(a for a in m.actions() if TRASH in a.text()).isEnabled()
    finally:
        w.shutdown()
        w.close()
