"""Trim one file: pick a start and end point, with a frame preview of each."""

from __future__ import annotations

import math
import re

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from listo.core.probe import MediaInfo
from listo.ui.components.widgets import section_label
from listo.ui.style import tokens
from listo.ui.window.jobs import FrameSignals, FrameTask

PREVIEW_W, PREVIEW_H = tokens.PREVIEW_W, tokens.PREVIEW_H
STEP = 10  # slider units per second (0.1 s precision)


def fmt_time(sec: float) -> str:
    sec = max(0.0, sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:04.1f}" if h >= 1 else f"{int(m)}:{s:04.1f}"


def fmt_clock(sec: float, longest: float = 0.0) -> str:
    """A player's clock: 00:18, 07:29, or 1:02:03 once the clip runs an hour or more."""
    s = max(0, int(sec))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if max(sec, longest) >= 3600 else f"{m:02d}:{s:02d}"


def parse_time(text: str) -> float | None:
    t = text.strip()
    if not t:
        return None
    if not re.fullmatch(r"[0-9:.]+", t):
        return None
    try:
        parts = [float(p) for p in t.split(":")]
    except ValueError:
        return None
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


class _End(QWidget):
    """One end of the trim: preview + time box + slider."""

    def __init__(self, label: str, dialog: TrimDialog, is_video: bool):
        super().__init__()
        self.d = dialog
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(tokens.SPACE_1)
        top = QHBoxLayout()
        top.addWidget(section_label(label))
        top.addStretch(1)
        self.time = QLineEdit()
        self.time.setFixedWidth(tokens.TIME_FIELD_W)
        self.time.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.time.editingFinished.connect(self._typed)
        top.addWidget(self.time)
        lay.addLayout(top)
        self.preview = QLabel()
        self.preview.setObjectName("TrimPreview")
        self.preview.setFixedSize(PREVIEW_W, PREVIEW_H)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setVisible(is_video)
        lay.addWidget(self.preview)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, dialog.max_units)
        self.slider.valueChanged.connect(self._moved)
        lay.addWidget(self.slider)
        self.seq = 0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(140)
        self._timer.timeout.connect(self._grab)

    def seconds(self) -> float:
        return self.slider.value() / STEP

    def set_seconds(self, sec: float) -> None:
        self.slider.setValue(round(sec * STEP))
        self.time.setText(fmt_time(self.seconds()))

    def _moved(self, _v: int) -> None:
        self.time.setText(fmt_time(self.seconds()))
        self.d.ends_changed(self)
        if self.preview.isVisible():
            self._timer.start()

    def _typed(self) -> None:
        sec = parse_time(self.time.text())
        if sec is None:
            self.time.setText(fmt_time(self.seconds()))
            return
        self.set_seconds(min(sec, self.d.duration))

    def _grab(self) -> None:
        self.seq += 1
        # a hair before the end so the last frame isn't past the file
        t = min(self.seconds(), max(0.0, self.d.duration - 0.05))
        self.d.pool.start(FrameTask(self.seq, self.d.path, t, self.d.info, self.signals, PREVIEW_W))

    def show_frame(self, seq: int, data: bytes) -> None:
        if seq != self.seq or not data:
            return
        img = QImage.fromData(data)
        if not img.isNull():
            self.preview.setPixmap(
                QPixmap.fromImage(img).scaled(
                    PREVIEW_W,
                    PREVIEW_H,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )


class TrimDialog(QDialog):
    def __init__(
        self, path: str, info: MediaInfo, trim: tuple[float, float] | None, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Trim")
        self.path, self.info = path, info
        self.duration = max(0.1, info.duration)
        self.max_units = math.ceil(self.duration * STEP - 1e-9)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.result_trim: tuple[float, float] | None = trim
        is_video = info.kind == "video"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(*(tokens.SPACE_5,) * 4)
        lay.setSpacing(tokens.SPACE_3)
        title = QLabel("Trim")
        title.setObjectName("DialogTitle")
        lay.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(tokens.SPACE_4)
        self.start = _End("Start", self, is_video)
        self.end = _End("End", self, is_video)
        for e in (self.start, self.end):
            e.signals = FrameSignals()
            e.signals.done.connect(e.show_frame)
        grid.addWidget(self.start, 0, 0)
        grid.addWidget(self.end, 0, 1)
        lay.addLayout(grid)

        self.length = QLabel()
        self.length.setObjectName("Muted")
        lay.addWidget(self.length)

        row = QHBoxLayout()
        reset = QPushButton("Use the Whole Clip")
        reset.setObjectName("Ghost")
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.clicked.connect(self._reset)
        cancel = QPushButton("Cancel")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Set Trim")
        ok.setObjectName("Primary")
        ok.setDefault(True)
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.clicked.connect(self._accept)
        row.addWidget(reset)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

        s, e = trim if trim else (0.0, self.duration)
        self._guard = False
        self.end.set_seconds(e)
        self.start.set_seconds(s)
        if is_video:
            self.start._grab()
            self.end._grab()
        self._update_length()

    def ends_changed(self, which: _End) -> None:
        if self._guard:
            return
        self._guard = True
        try:  # keep start before end (at least 0.1 s apart)
            if which is self.start and self.start.slider.value() >= self.end.slider.value():
                self.end.slider.setValue(min(self.max_units, self.start.slider.value() + 1))
            elif which is self.end and self.end.slider.value() <= self.start.slider.value():
                self.start.slider.setValue(max(0, self.end.slider.value() - 1))
        finally:
            self._guard = False
        self._update_length()

    def _update_length(self) -> None:
        self.length.setText(
            f"Keeps {fmt_time(self.end.seconds() - self.start.seconds())} of {fmt_time(self.duration)}"
        )

    def _reset(self) -> None:
        self.start.set_seconds(0)
        self.end.set_seconds(self.duration)

    def _accept(self) -> None:
        s, e = self.start.seconds(), min(self.end.seconds(), self.duration)
        whole = s <= 0.05 and self.end.slider.value() >= self.max_units
        self.result_trim = None if whole else (s, e)
        self.accept()

    def done(self, r: int) -> None:
        self.pool.clear()
        self.pool.waitForDone(2000)
        super().done(r)
