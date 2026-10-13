"""Finds words cut off anywhere in a window: text drawn wider (or taller) than the room it was given.

    from tests.cut_off import cut_off
    assert cut_off(window) == []

It looks at every label, button, checkbox and tab showing in a window and its children. Text that wraps onto
more lines, or is cut short on purpose with "…" (an ElidedLabel, a table's cells), is fine; text that is simply
clipped at an edge is not. Uses only Qt, so it works the same in any PySide6 app.
"""

from __future__ import annotations

from PySide6 import QtGui
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QAbstractButton, QAbstractScrollArea, QLabel, QSizePolicy, QTabBar, QWidget

SLACK = 1  # px: rounding


def _where(w: QWidget) -> str:
    names = []
    while w is not None and len(names) < 4:
        names.append(w.objectName() or type(w).__name__)
        w = w.parentWidget()
    return " < ".join(names)


def _shown_text(text: str) -> str:
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&")


def _label(lab: QLabel) -> str:
    text = lab.text()
    rich = lab.textFormat() == Qt.TextFormat.RichText or (
        lab.textFormat() == Qt.TextFormat.AutoText and QtGui.Qt.mightBeRichText(text)
    )
    if not text.strip() or rich:
        return ""
    if lab.pixmap() is not None and not lab.pixmap().isNull():
        return ""
    if callable(getattr(lab, "full_text", None)):  # cuts itself short with "…" on purpose
        return ""
    room = lab.contentsRect().adjusted(lab.margin(), lab.margin(), -lab.margin(), -lab.margin())
    if lab.indent() > 0:
        room.adjust(lab.indent(), 0, 0, 0)
    fm = lab.fontMetrics()
    if lab.wordWrap():
        need = lab.heightForWidth(lab.width())
        if need > lab.height() + SLACK:
            return f"needs {need}px of height, has {lab.height()}"
        return ""
    if lab.buddy() is not None:
        text = _shown_text(text)
    wide = max(fm.horizontalAdvance(line) for line in text.split("\n"))
    tall = fm.height() * len(text.split("\n"))
    if wide > room.width() + SLACK:
        return f"needs {wide}px, has {room.width()}"
    if tall > room.height() + SLACK:
        return f"needs {tall}px of height, has {room.height()}"
    return ""


def _button(b: QAbstractButton) -> str:
    if not b.text().strip():
        return ""
    if b.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored:  # cuts itself short with "…"
        return ""
    want = b.sizeHint()
    if b.width() + SLACK < want.width():
        return f"needs {want.width()}px, has {b.width()}"
    return ""


def _tabs(t: QTabBar) -> list[str]:
    out = []
    if t.elideMode() != Qt.TextElideMode.ElideNone:
        return out
    for i in range(t.count()):
        if t.tabRect(i).width() + SLACK < t.tabSizeHint(i).width():
            out.append(
                f"tab {t.tabText(i)!r}: needs {t.tabSizeHint(i).width()}px, has {t.tabRect(i).width()}"
            )
    return out


def _hidden_by_a_parent(w: QWidget) -> str:
    """Whether a parent cuts the widget off (scrolling areas are allowed to: that's what they're for)."""
    rect = QRect(0, 0, w.width(), w.height())
    child = w
    # a menu or dialog is a window of its own: its edge is the last one that counts
    while not child.isWindow() and (parent := child.parentWidget()) is not None:
        if isinstance(parent, QAbstractScrollArea) or isinstance(parent.parentWidget(), QAbstractScrollArea):
            return ""
        rect.translate(child.pos())
        inside = rect.intersected(parent.rect())
        if inside.width() + SLACK < rect.width():
            return f"{rect.width() - inside.width()}px of it is outside {_where(parent)}"
        child = parent
    return ""


def cut_off(root: QWidget) -> list[str]:
    """Every piece of text in `root` that doesn't fit, as 'where: "text" why'; empty when everything fits."""
    found = []
    for w in [root, *root.findChildren(QWidget)]:
        if not w.isVisible() or w.width() <= 0:
            continue
        if isinstance(w, QLabel):
            why, text = _label(w), w.text()
        elif isinstance(w, QAbstractButton):
            why, text = _button(w), w.text()
        elif isinstance(w, QTabBar):
            found += [f"{_where(w)}: {why}" for why in _tabs(w)]
            continue
        else:
            continue
        if not why and text.strip():
            why = _hidden_by_a_parent(w)
        if why:
            found.append(f"{_where(w)}: {text!r} {why}")
    return found
