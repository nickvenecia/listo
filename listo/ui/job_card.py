"""One file in the queue."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import theme, tokens
from .widgets import repolish

THUMB_W, THUMB_H = tokens.THUMB_W, tokens.THUMB_H


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", mode=Qt.TextElideMode.ElideMiddle):
        super().__init__()
        self._full = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full = text
        self.setToolTip(text if len(text) > 30 else "")
        self._refresh()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._refresh()

    def _refresh(self) -> None:
        w = max(10, self.width())
        super().setText(self.fontMetrics().elidedText(self._full, self._mode, w))


def _rounded(pm: QPixmap, w: int, h: int, radius: float = tokens.RADIUS) -> QPixmap:
    dpr = 2.0
    out = QPixmap(int(w * dpr), int(h * dpr))
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    scaled = pm.scaled(
        int(w * dpr),
        int(h * dpr),
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(dpr)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, w, h, radius, radius)
    p.setClipPath(path)
    sx = (scaled.width() / dpr - w) / 2
    sy = (scaled.height() / dpr - h) / 2
    p.drawPixmap(int(-sx), int(-sy), scaled)
    p.end()
    return out


class JobCard(QFrame):
    remove = Signal(int)
    retry = Signal(int)
    reveal = Signal(int)
    details = Signal(int)
    format_clicked = Signal(int, object)  # item id, the chip button (to anchor a menu)
    trim_clicked = Signal(int)
    captions_clicked = Signal(int)
    pressed = Signal(int, object)  # item id, keyboard modifiers (for selecting)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.pressed.emit(self.item_id, e.modifiers())
        e.accept()  # don't let the list behind the card see it (that would deselect)

    def set_selected(self, on: bool) -> None:
        if self.property("selected") != on:
            self.setProperty("selected", on)
            repolish(self)

    def __init__(self, item_id: int, name: str, kind: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.item_id = item_id
        self.kind = kind
        self.setObjectName("Card")
        self.setProperty("selected", False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(tokens.CARD_H)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(*(tokens.SPACE_2,) * 4)
        lay.setSpacing(tokens.SPACE_3)

        self.thumb = QLabel()
        self.thumb.setObjectName("Thumb")
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_kind_icon()
        lay.addWidget(self.thumb)

        mid = QVBoxLayout()
        mid.setSpacing(0)
        mid.setContentsMargins(0, 0, 0, 0)
        self.name = ElidedLabel(name)
        self.name.setObjectName("FileName")
        self.meta = ElidedLabel("Reading…", Qt.TextElideMode.ElideRight)
        self.meta.setObjectName("Meta")
        self.out = ElidedLabel("", Qt.TextElideMode.ElideMiddle)
        self.out.setObjectName("OutName")
        self.chip = QPushButton("")
        self.chip.setObjectName("Chip")
        self.chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chip.setToolTip("Change the format for just this file")
        self.chip.clicked.connect(lambda: self.format_clicked.emit(self.item_id, self.chip))
        self.chip.hide()
        out_row = QHBoxLayout()
        out_row.setContentsMargins(0, tokens.SPACE_1, 0, 0)
        out_row.setSpacing(tokens.SPACE_2)
        self.trim_tag = QLabel("")
        self.trim_tag.setObjectName("TrimTag")
        self.trim_tag.hide()
        out_row.addWidget(self.chip)
        out_row.addWidget(self.trim_tag)
        out_row.addWidget(self.out, 1)
        mid.addStretch(1)
        mid.addWidget(self.name)
        mid.addWidget(self.meta)
        mid.addLayout(out_row)
        mid.addStretch(1)
        lay.addLayout(mid, 1)

        right = QVBoxLayout()
        right.setSpacing(tokens.SPACE_2)
        right.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.setSpacing(tokens.SPACE_1)
        self.status = QLabel("")
        self.status.setObjectName("Status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addStretch(1)
        top.addWidget(self.status)
        top.addSpacing(tokens.SPACE_2)
        self.btn_trim = self._icon_btn("scissors", "Trim", lambda: self.trim_clicked.emit(self.item_id))
        self.btn_cc = self._icon_btn("captions", "Captions", lambda: self.captions_clicked.emit(self.item_id))
        self.btn_cc.hide()
        self._cc = ""
        self.btn_details = self._icon_btn("info", "Details", lambda: self.details.emit(self.item_id))
        self.btn_retry = self._icon_btn("retry", "Try Again", lambda: self.retry.emit(self.item_id))
        self.btn_reveal = self._icon_btn(
            "reveal", "Show the new file", lambda: self.reveal.emit(self.item_id)
        )
        self.btn_remove = self._icon_btn("x", "Remove from list", lambda: self.remove.emit(self.item_id))
        for b in (
            self.btn_cc,
            self.btn_trim,
            self.btn_details,
            self.btn_retry,
            self.btn_reveal,
            self.btn_remove,
        ):
            top.addWidget(b)
        right.addStretch(1)
        right.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(tokens.CARD_BAR_W)
        self.bar.hide()
        bar_row = QHBoxLayout()
        bar_row.addStretch(1)
        bar_row.addWidget(self.bar)
        right.addLayout(bar_row)
        right.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(right)
        wrap.setFixedWidth(tokens.STATUS_W)
        lay.addWidget(wrap)
        self.set_state("probing")

    def _icon_btn(self, name: str, tip: str, fn) -> QToolButton:
        b = QToolButton()
        b.setObjectName("IconBtn")
        b.setIcon(theme.icon(name, theme.MUTED, tokens.ICON))
        b.setIconSize(QSize(tokens.ICON, tokens.ICON))
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(fn)
        b.hide()
        return b

    def _set_kind_icon(self) -> None:
        name = {"video": "film", "photo": "image", "audio": "audio", "link": "link"}.get(self.kind, "file")
        self.thumb.setPixmap(theme.pixmap(name, tokens.ICON_LG, theme.FAINT, 1.6))

    # ---- updates
    def set_thumb(self, data: bytes) -> None:
        if not data:
            return
        img = QImage.fromData(data)
        if img.isNull():
            return
        self.thumb.setPixmap(_rounded(QPixmap.fromImage(img), THUMB_W, THUMB_H))

    def set_meta(self, text: str) -> None:
        self.meta.setText(text)

    def set_output(self, text: str) -> None:
        self.out.setText(text)

    def set_format(self, label: str, overridden: bool, editable: bool) -> None:
        self.chip.setText(label + ("  ▾" if editable else ""))
        self.chip.setProperty("custom", "true" if overridden else "false")
        self.chip.setEnabled(editable)
        self.chip.setVisible(bool(label))
        repolish(self.chip)

    def set_trim(self, text: str) -> None:
        self.trim_tag.setText(text)
        self.trim_tag.setVisible(bool(text))

    def set_captions(self, status: str, detail: str = "") -> None:
        """'' = captions off for this clip; 'working' / 'failed' / 'review' / 'reviewed'."""
        self._cc = status
        tips = {
            "working": detail or "Making captions in the background…",
            "failed": (detail or "Couldn't make captions") + " — click to try again",
            "review": "Captions ready — click to check them",
            "reviewed": "Captions checked — click to edit",
        }
        self.btn_cc.setToolTip(tips.get(status, ""))
        color = {"review": theme.ACCENT, "reviewed": theme.GOOD, "failed": theme.BAD}.get(status, theme.FAINT)
        self.btn_cc.setIcon(theme.icon("captions", color))
        self._show_cc()

    def _show_cc(self) -> None:
        self.btn_cc.setVisible(
            bool(self._cc) and getattr(self, "_state", "") in ("ready", "waiting", "done", "warning")
        )

    def set_name(self, name: str) -> None:
        self.name.setText(name)

    def set_progress(self, frac: float) -> None:
        self.bar.setValue(int(max(0.0, min(1.0, frac)) * 1000))

    def set_state(self, state: str, text: str = "") -> None:
        default = {
            "probing": "Reading…",
            "ready": "Ready",
            "waiting": "Waiting",
            "converting": "Converting",
            "paused": "Paused",
            "done": "Listo",
            "failed": "Failed",
            "skipped": "Skipped",
            "canceled": "Canceled",
            "unsupported": "Can't Convert",
            "warning": "Check This One",
            "transcribing": "Making Captions",
            "downloading": "Downloading",
        }
        self.status.setText(text or default.get(state, state))
        self.status.setProperty("tone", state)  # colored by the stylesheet (#Status[tone=...])
        repolish(self.status)
        busy = state in ("converting", "paused", "downloading", "transcribing")
        finished_ok = state in ("done", "warning")
        self.bar.setVisible(busy or finished_ok)
        self.bar.setObjectName("Done" if state == "done" else ("Warn" if state == "warning" else ""))
        repolish(self.bar)
        if finished_ok:
            self.bar.setValue(1000)
        self.btn_remove.setVisible(not busy or state == "downloading")
        self.btn_trim.setVisible(state in ("ready", "waiting") and self.kind in ("video", "audio"))
        self._state = state
        self._show_cc()
        self.btn_retry.setVisible(state in ("failed", "canceled", "skipped", "warning"))
        self.btn_reveal.setVisible(finished_ok)
        self.btn_details.setVisible(state in ("failed", "done", "skipped", "unsupported", "warning"))
        self.setProperty(
            "state",
            "active"
            if state in ("converting", "paused")
            else ("failed" if state in ("failed", "unsupported") else ""),
        )
        repolish(self)
