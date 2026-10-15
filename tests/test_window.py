"""The window: places in the sidebar filter the list, the right panel opens and closes, Settings and Feedback."""

from __future__ import annotations

import json
import shutil
import time
from typing import ClassVar

import pytest
from PySide6.QtCore import Qt

from tests.helpers import ff


@pytest.fixture
def clips(tmp_path):
    """Two short videos, a photo and a text file (made-up names)."""
    a, b = tmp_path / "A001_C001.mov", tmp_path / "A001_C002.mov"
    for c in (a, b):
        ff("-f", "lavfi", "-i", "testsrc2=s=320x180:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(c))
    still = tmp_path / "still.png"
    ff("-f", "lavfi", "-i", "color=c=teal:s=64x64", "-frames:v", "1", str(still))
    note = tmp_path / "notes.txt"
    note.write_text("not a picture")
    return [a, b, still, note]


def _wait(app, cond, timeout=30.0) -> bool:
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
    return cond()


def test_places_filter_the_list(qapp, clips):
    from listo.ui.window.main_window import MainWindow

    w = MainWindow()
    w._restored = True
    w.show()
    try:
        w.add_paths([str(p) for p in clips])
        assert _wait(qapp, lambda: all(it.state != "probing" for it in w.items.values()))
        w._refresh_now()
        rows = w.sidebar.rows
        assert rows["all"].count.text() == "4" and rows["video"].count.text() == "2"
        assert rows["photo"].count.text() == "1" and rows["attention"].count.text() == "1"  # the .txt

        w.go("video")
        assert w.title.text() == "Videos" and len(w.table.shown_ids()) == 2
        w.search.setText("C002")
        assert [w.items[i].path.endswith("A001_C002.mov") for i in w.table.shown_ids()] == [True]
        w.search.setText("")
        w.go("attention")
        assert [w.items[i].state for i in w.table.shown_ids()] == ["unsupported"]
        w.go("done")
        assert w.pages.currentWidget() is w.nothing  # nothing finished yet: says so instead of a blank list
        w.go("all")
        assert w.pages.currentWidget() is w.table and len(w.table.shown_ids()) == 4
    finally:
        w.close()


def test_the_empty_list_shows_the_ways_to_start(qapp, clips):
    from listo.ui.window.main_window import MainWindow

    w = MainWindow()
    w._restored = True
    w.show()
    try:
        assert w.pages.currentWidget() is w.empty and not w.search.isVisible()  # nothing to search yet
        tiles = w.empty.tiles
        assert [t.findChild(type(w.title), "StartTitle").text() for t in tiles] == [
            "Add Files…",
            "Add a Folder…",
            "Add a Link…",
        ]
        w.empty.set_hot(True)  # files dragged over the window light the files tile
        assert tiles[0].property("hot") is True
        w.empty.set_hot(False)
        w.add_paths([str(clips[0])])
        assert w.pages.currentWidget() is w.table and w.search.isVisible()
    finally:
        w.close()


def test_toasts(qapp):
    from listo.ui.window.main_window import MainWindow

    w = MainWindow()
    w._restored = True
    w.show()
    try:
        t = w.toaster
        w.toast("Backed up to Listo Backup.zip.", "done")
        assert t.isVisible() and (t.text, t.tone) == ("Backed up to Listo Backup.zip.", "done")
        pill = t._pill.translated(t.pos().x(), t.pos().y())
        area = w._toast_area()
        assert area.contains(pill.toRect()) and abs(pill.center().x() - area.center().x()) <= 2
        w.toast("Something odd.", "sparkly")  # an unknown tone is plain news
        assert t.tone == ""

        def wait(ms):
            stop = time.monotonic() + ms / 1000
            while time.monotonic() < stop:
                qapp.processEvents()
                time.sleep(0.01)

        t.dismiss()
        w.toast("That doesn't look like a link.", "problem")  # a new one while the last fades away stays up
        wait(500)
        assert t.isVisible() and t.tone == "problem"
        t.dismiss()
        wait(500)
        assert not t.isVisible()
    finally:
        w.close()


def test_a_start_tile_is_picked_by_click_space_or_return(qapp):
    from PySide6.QtTest import QTest

    from listo.ui.components.empty import EmptyPage

    picked = []
    page = EmptyPage((("folder", "Add a Folder…", "Everything inside it", "", lambda: picked.append(1)),))
    page.show()
    tile = page.tiles[0]
    QTest.mouseClick(tile, Qt.MouseButton.LeftButton)
    QTest.keyClick(tile, Qt.Key.Key_Space)
    QTest.keyClick(tile, Qt.Key.Key_Return)
    QTest.mouseClick(tile, Qt.MouseButton.RightButton)
    assert picked == [1, 1, 1]
    page.close()


def test_the_right_panel_comes_and_goes_with_the_files(qapp, clips):
    from listo.ui.style import tokens
    from listo.ui.window.main_window import MainWindow

    w = MainWindow()
    w._restored = True
    w.show()
    try:
        assert not w.dock.opened and w.btn_panel.isHidden()  # no files: no panel, no button for it
        w.add_paths([str(clips[0])])
        assert w.dock.opened  # the first file in brings Convert To in
        first = w.order[0]
        w._card_pressed(first, Qt.KeyboardModifier.NoModifier)
        w._escape()
        assert (
            not w.selected and w.dock.opened
        )  # Esc: nothing picked; the panel is for every file, so it stays
        w.show_panel(False)  # its ✕
        assert not w.btn_panel.isHidden()  # the toolbar's round button brings it back
        w._card_pressed(first, Qt.KeyboardModifier.NoModifier)
        assert not w.dock.opened  # picking a file doesn't open it (it isn't about that one file)
        w.btn_panel.click()
        assert w.dock.opened
        assert _wait(qapp, lambda: w.btn_panel.isHidden(), tokens.FADE_MS / 1000 + 2)  # it fades away
        w._take_off(list(w.order))
        assert not w.dock.opened and w.btn_panel.isHidden()  # the last file gone: the panel goes too
        w.history.undo()
        assert w.items and w.dock.opened  # undo puts the file back, and the panel with it
        menu = [a.text() for a in w._list_menu(first).actions() if a.text()]
        assert "Remove from the List…" in menu and "Clear All…" in menu
    finally:
        w.close()


def test_convert_to_shows_a_heading_for_each_kind_in_the_list(qapp, clips):
    from listo.ui.window.main_window import MainWindow

    w = MainWindow()
    w._restored = True
    w.show()
    try:
        sb = w.convert

        def shown():
            return [head.title.text() for box, head in sb.kinds.values() if box.isVisibleTo(sb)]

        assert shown() == ["Videos", "Photos", "Audio"]  # nothing in the list: all three can be set up
        w.add_paths([str(clips[0])])
        w._refresh_now()
        assert shown() == ["1 Video"]  # only the kinds in the list, counted
        w.add_paths([str(clips[1]), str(clips[2])])
        assert _wait(qapp, lambda: all(it.state != "probing" for it in w.items.values()))
        w._refresh_now()
        assert shown() == ["2 Videos", "1 Photo"]
        w._set_override(w.order[1], {"video_preset": "h264"})
        assert sb.kinds["video"][1].note.text() == "· 1 with its own format"
        assert not sb.kinds["video"][1].note.isHidden()
        assert w.export_panel.videos_sec.isVisibleTo(w.panel)  # 2 videos: Clips, in the video card
        assert sb.v_card.isAncestorOf(w.export_panel.videos_sec)
        assert w.export_panel.adv.isAncestorOf(sb.v_par)  # speed is for every file: under Advanced
    finally:
        w.close()


def _scroll(w, widget, angle: int, pixels: int = 0, phase=Qt.ScrollPhase.NoScrollPhase) -> None:
    """A wheel or trackpad scroll over `widget`, delivered the way a real one is (passed up to whatever scrolls)."""
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtTest import QTest

    at = QPointF(widget.mapTo(w, widget.rect().center()))
    QTest.wheelEvent(
        w.windowHandle(), at, QPoint(0, angle), QPoint(0, pixels), Qt.KeyboardModifier.NoModifier, phase
    )


def test_scrolling_the_panel_over_a_dropdown_leaves_the_dropdown_alone(qapp, clips):
    """Scrolling Convert To with the pointer over a dropdown scrolls the panel. The dropdown keeps its choice and
    doesn't take the keyboard: ↑↓ still go through the list (they used to change the dropdown instead)."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication, QComboBox

    from listo.ui.window.main_window import MainWindow

    w = MainWindow()
    w._restored = True
    w.resize(1280, 800)
    w.show()
    try:
        w.add_paths([str(c) for c in clips[:3]])
        assert _wait(qapp, lambda: all(it.state != "probing" for it in w.items.values()))
        w._refresh_now()
        area = w.panel.scroll
        bar, view = area.verticalScrollBar(), area.viewport()
        assert bar.maximum() > 0  # there's more than fits

        def in_view(c: QComboBox) -> bool:
            top = c.mapTo(view, QPoint(0, 0)).y()
            return c.isVisible() and top >= 0 and top + c.height() <= view.height()

        combo = next(c for c in w.panel.findChildren(QComboBox) if in_view(c))
        w.table.setFocus()
        choice, top = combo.currentIndex(), bar.value()
        _scroll(w, combo, -120)
        assert bar.value() > top  # the panel scrolled
        assert combo.currentIndex() == choice  # the dropdown didn't change
        assert QApplication.focusWidget() is w.table  # and the keys still go to the list
    finally:
        w.close()


def test_a_trackpad_swipe_moves_the_list_as_far_as_the_fingers(qapp, clips, tmp_path):
    """A trackpad swipe moves the list exactly as far as the fingers did. Qt's whole-row steps made a small
    swipe fly past several clips. A mouse wheel still moves in steps."""
    from PySide6.QtWidgets import QApplication

    from listo.ui.window.main_window import MainWindow

    many = []
    for n in range(12):
        f = tmp_path / f"B001_C{n:03d}.mov"
        shutil.copy(clips[0], f)
        many.append(str(f))
    w = MainWindow()
    w._restored = True
    w.resize(1280, 800)
    w.show()
    try:
        w.add_paths(many)
        assert _wait(qapp, lambda: all(it.state != "probing" for it in w.items.values()))
        bar, view = w.table.verticalScrollBar(), w.table.viewport()
        assert bar.maximum() > 100  # room to scroll
        for phase in (Qt.ScrollPhase.ScrollUpdate,) * 3 + (Qt.ScrollPhase.ScrollEnd,):  # four moves of 10 px
            _scroll(w, view, -20, -10, phase)
        assert bar.value() == 40
        bar.setValue(0)
        _scroll(w, view, -120)  # a mouse wheel's click
        assert bar.value() == min(bar.maximum(), QApplication.wheelScrollLines() * bar.singleStep())
    finally:
        w.close()


def test_settings_saves_the_look_and_accent(qapp, data_folder):
    from listo.app import set_appearance
    from listo.core import store
    from listo.ui.dialogs.settings import SettingsDialog
    from listo.ui.style import tokens
    from listo.ui.window.main_window import MainWindow

    w = MainWindow()
    try:
        d = SettingsDialog(w)
        assert d.accent.current == tokens.APP_ACCENT  # marigold until you pick another
        d.accent._pick("blue")
        assert tokens.ACCENTS["blue"][1 if tokens.SCHEME == "dark" else 2] == tokens.ACCENT
        assert store.prefs().get("accent") == "blue"
        d.accent._pick(tokens.APP_ACCENT)
        assert store.prefs().get("accent") == ""  # Listo's own again
        d.look.changed.emit("light")
        assert tokens.SCHEME == "light" and store.prefs().get("appearance") == "light"
        d.auto.setChecked(False)
        assert store.prefs().get("auto_update") is False and not w.auto_update()
        d.show_pane("data")
        assert d.windowTitle() == "Your Data" and d.storage.rows
        d.show_pane("shortcuts")
        assert d.windowTitle() == "Keyboard Shortcuts"
        d.close()
    finally:
        set_appearance(qapp, "system", "")
        w.close()


def test_feedback_waits_in_the_outbox(data_folder, monkeypatch):
    from listo.services import feedback

    fb = feedback.make("idea", "  A button to do the thing  ", "someone@example.com", include_details=True)
    assert fb.message == "A button to do the thing" and fb.details["listo"]
    assert feedback.send(fb) is False  # no sender yet: kept, never lost
    kept = feedback.waiting()
    assert len(kept) == 1 and json.loads(kept[0].read_text())["message"] == fb.message
    with pytest.raises(feedback.FeedbackError):
        feedback.make("idea", "   ")

    class Connected(feedback.FeedbackSender):  # once sending is switched on, the kept ones go too
        connected = True
        sent: ClassVar[list] = []

        def send(self, f):
            self.sent.append(f.message)

    monkeypatch.setattr(feedback, "_sender", Connected())
    assert feedback.send(feedback.make("problem", "It froze")) is True
    assert Connected.sent == ["It froze", fb.message] and feedback.waiting() == []


def test_undo_redo_and_reorder(qapp, clips, monkeypatch):
    import listo.ui.window.main_window as mw

    w = mw.MainWindow()
    w._restored = True
    w.show()
    asked = []
    monkeypatch.setattr(mw, "confirm", lambda *a, **k: asked.append(a[1]) or True)
    try:
        w.add_paths([str(p) for p in clips[:3]])
        assert _wait(qapp, lambda: all(it.state != "probing" for it in w.items.values()))
        a, b, c = w.order

        # a settings change is one step; ⌘Z takes it back, ⇧⌘Z does it again
        was = w.settings.video_preset
        w.settings.video_preset = "h264"
        w._settings_changed()
        w._settings_timer.stop()
        w._record_settings()
        w.undo()
        assert w.settings.video_preset == was and w.convert.v_fmt.currentData() == was
        w.redo()
        assert w.settings.video_preset == "h264"

        # dragging a row: list order is join and timecode order
        w._reordered([c, a, b])
        assert w.order == [c, a, b] and w.table.shown_ids() == [c, a, b]
        w.undo()
        assert w.order == [a, b, c]

        # Delete asks first (naming the file), and ⌘Z puts it back where it was
        w._select({b})
        w.remove_selected()
        assert asked and asked[-1].startswith("Remove A001_C002.mov") and b not in w.items
        w.undo()
        assert w.order == [a, b, c] and w.items[b].card.owner is w.table
        w.redo()
        assert w.order == [a, c]
    finally:
        w.close()
