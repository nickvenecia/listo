"""One file in the queue."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from . import theme
from .widgets import repolish

THUMB_W, THUMB_H = 112, 63


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", mode=Qt.TextElideMode.ElideMiddle):
        super().__init__()
        self._full = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text
        self.setToolTip(text if len(text) > 30 else "")
        self._refresh()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._refresh()

    def _refresh(self) -> None:
        w = max(10, self.width())
        super().setText(self.fontMetrics().elidedText(self._full, self._mode, w))


def _rounded(pm: QPixmap, w: int, h: int, radius: float = 8) -> QPixmap:
    dpr = 2.0
    out = QPixmap(int(w * dpr), int(h * dpr))
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    scaled = pm.scaled(
        int(w * dpr), int(h * dpr),
        Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation,
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

    def __init__(self, item_id: int, name: str, kind: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.item_id = item_id
        self.kind = kind
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(THUMB_H + 22)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(11, 11, 12, 11)
        lay.setSpacing(14)

        self.thumb = QLabel()
        self.thumb.setObjectName("Thumb")
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_kind_icon()
        lay.addWidget(self.thumb)

        mid = QVBoxLayout()
        mid.setSpacing(3)
        mid.setContentsMargins(0, 0, 0, 0)
        self.name = ElidedLabel(name)
        self.name.setObjectName("FileName")
        self.meta = ElidedLabel("Reading…", Qt.TextElideMode.ElideRight)
        self.meta.setObjectName("Meta")
        self.out = ElidedLabel("", Qt.TextElideMode.ElideMiddle)
        self.out.setObjectName("OutName")
        mid.addStretch(1)
        mid.addWidget(self.name)
        mid.addWidget(self.meta)
        mid.addWidget(self.out)
        mid.addStretch(1)
        lay.addLayout(mid, 1)

        right = QVBoxLayout()
        right.setSpacing(7)
        right.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.setSpacing(2)
        self.status = QLabel("")
        self.status.setObjectName("Status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addStretch(1)
        top.addWidget(self.status)
        top.addSpacing(6)
        self.btn_details = self._icon_btn("info", "Details", lambda: self.details.emit(self.item_id))
        self.btn_retry = self._icon_btn("retry", "Try again", lambda: self.retry.emit(self.item_id))
        self.btn_reveal = self._icon_btn("reveal", "Show the new file", lambda: self.reveal.emit(self.item_id))
        self.btn_remove = self._icon_btn("x", "Remove from list", lambda: self.remove.emit(self.item_id))
        for b in (self.btn_details, self.btn_retry, self.btn_reveal, self.btn_remove):
            top.addWidget(b)
        right.addStretch(1)
        right.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(210)
        self.bar.hide()
        bar_row = QHBoxLayout()
        bar_row.addStretch(1)
        bar_row.addWidget(self.bar)
        right.addLayout(bar_row)
        right.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(right)
        wrap.setFixedWidth(250)
        lay.addWidget(wrap)
        self.set_state("probing")

    def _icon_btn(self, name: str, tip: str, fn) -> QToolButton:
        b = QToolButton()
        b.setObjectName("IconBtn")
        b.setIcon(theme.icon(name, theme.MUTED, 16))
        b.setIconSize(QSize(16, 16))
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(fn)
        b.hide()
        return b

    def _set_kind_icon(self) -> None:
        name = {"video": "film", "photo": "image", "audio": "audio"}.get(self.kind, "file")
        self.thumb.setPixmap(theme.pixmap(name, 26, theme.FAINT, 1.6))

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

    def set_progress(self, frac: float) -> None:
        self.bar.setValue(int(max(0.0, min(1.0, frac)) * 1000))

    def set_state(self, state: str, text: str = "") -> None:
        colors = {
            "probing": theme.FAINT, "ready": theme.MUTED, "waiting": theme.MUTED,
            "converting": theme.ACCENT, "paused": theme.WARN, "done": theme.GOOD,
            "failed": theme.BAD, "skipped": theme.MUTED, "canceled": theme.MUTED,
            "unsupported": theme.BAD,
        }
        default = {
            "probing": "Reading…", "ready": "Ready", "waiting": "Waiting",
            "converting": "Converting", "paused": "Paused", "done": "Listo",
            "failed": "Failed", "skipped": "Skipped", "canceled": "Canceled",
            "unsupported": "Can't convert",
        }
        self.status.setText(text or default.get(state, state))
        self.status.setStyleSheet(f"color: {colors.get(state, theme.MUTED)};")
        busy = state in ("converting", "paused")
        self.bar.setVisible(busy or state == "done")
        self.bar.setObjectName("Done" if state == "done" else "")
        repolish(self.bar)
        if state == "done":
            self.bar.setValue(1000)
        self.btn_remove.setVisible(not busy)
        self.btn_retry.setVisible(state in ("failed", "canceled", "skipped"))
        self.btn_reveal.setVisible(state == "done")
        self.btn_details.setVisible(state in ("failed", "done", "skipped", "unsupported"))
        self.setProperty("state", "active" if busy else ("failed" if state in ("failed", "unsupported") else ""))
        repolish(self)
