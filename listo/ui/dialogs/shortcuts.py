"""Settings › Keyboard Shortcuts (Help › Keyboard Shortcuts, ⌘/): every command that has a key, read from the
menus themselves, so the list is never out of date. Shows ⌘ ⇧ ⌥ on the Mac and Ctrl/Shift/Alt elsewhere."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QLabel, QMenuBar, QWidget

from listo.ui.components.widgets import Section, hbox, vbox
from listo.ui.style import tokens

# keys that work without a menu item
EXTRA = [
    ("Play or Pause the Preview", QKeySequence(Qt.Key.Key_Space)),
    ("Pick the File Above or Below", QKeySequence("Up")),
    ("Remove What's Picked from the List", QKeySequence(Qt.Key.Key_Backspace)),
    ("Close the Panel", QKeySequence(Qt.Key.Key_Escape)),
]


def keys_by_menu(bar: QMenuBar) -> list[tuple[str, list[tuple[str, str]]]]:
    out = []
    for top in bar.actions():
        menu = top.menu()
        if menu is None:
            continue
        rows = []
        for a in menu.actions():
            keys = a.shortcuts()
            if a.isSeparator() or not keys or keys[0].isEmpty():
                continue
            rows.append(
                (a.text().replace("&&", "&"), keys[0].toString(QKeySequence.SequenceFormat.NativeText))
            )
        if rows:
            out.append((top.text().replace("&", ""), rows))
    return out


class ShortcutsList(QWidget):
    """Every key, grouped by menu (Settings › Keyboard Shortcuts)."""

    def __init__(self, bar: QMenuBar, parent: QWidget | None = None):
        super().__init__(parent)
        bl = vbox(self, (0, 0, tokens.SPACE_3, tokens.SPACE_4), tokens.SPACE_3)
        groups = keys_by_menu(bar)
        groups.append(
            ("Anywhere", [(t, k.toString(QKeySequence.SequenceFormat.NativeText)) for t, k in EXTRA])
        )
        for title, rows in groups:
            sec = Section(title)
            for text, key in rows:
                row = hbox(spacing=tokens.SPACE_2)
                what = QLabel(text)
                what.setWordWrap(True)  # a narrow window: onto another line, never cut off
                row.addWidget(what, 1)
                cap = QLabel(key)
                cap.setObjectName("KeyCap")
                row.addWidget(cap, 0, Qt.AlignmentFlag.AlignTop)  # level with the first line
                sec.add(row)
            bl.addWidget(sec)
        bl.addStretch(1)
