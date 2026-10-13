"""The window: places in the sidebar filter the list, the right panel opens and closes, Settings and Feedback."""

from __future__ import annotations

import json
import time

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


def test_the_right_panel_and_esc(qapp, clips):
    from listo.ui.window.main_window import MainWindow

    w = MainWindow()
    w._restored = True
    w.show()
    try:
        w.show_panel(False)
        w.add_paths([str(clips[0])])
        assert w.dock.opened  # the first file in brings Convert To in
        first = w.order[0]
        w._card_pressed(first, Qt.KeyboardModifier.NoModifier)
        assert w.selected == {first}
        w._escape()
        assert not w.selected and not w.dock.opened  # Esc: nothing picked, the panel slides away
        w._card_pressed(first, Qt.KeyboardModifier.NoModifier)
        assert w.dock.opened  # picking a file brings it back
        menu = [a.text() for a in w._list_menu(first).actions() if a.text()]
        assert "Remove from the List…" in menu and "Clear All…" in menu
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


def test_feedback_waits_in_the_outbox(data_folder):
    from listo.services import feedback

    fb = feedback.make("idea", "  A button to do the thing  ", "someone@example.com", include_details=True)
    assert fb.message == "A button to do the thing" and fb.details["listo"]
    assert feedback.send(fb) is False  # no sender yet: kept, never lost
    kept = feedback.waiting()
    assert len(kept) == 1 and json.loads(kept[0].read_text())["message"] == fb.message
    with pytest.raises(feedback.FeedbackError):
        feedback.make("idea", "   ")


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
