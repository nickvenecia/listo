"""Preview: one frame of a clip exactly as it will come out (LUT, frame, size, burn-ins)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QSlider, QWidget

from ..core import naming
from ..core.presets import VIDEO_BY_KEY
from .tokens import SPACE_1, SPACE_2, SPACE_3, SPACE_5, VIEWER_H, VIEWER_W
from .trim_dialog import fmt_time
from .widgets import Segmented, combo, hbox, vbox
from .workers import PreviewSignals, PreviewTask

STEP = 10  # slider units per second


class PreviewDialog(QDialog):
    """`clips` = [(label, path, info, settings, captions or None)] — every video in the list."""

    def __init__(self, clips: list[tuple], start: int = 0, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Preview")
        self.clips = clips
        self.pool = QThreadPool.globalInstance()
        self.signals = PreviewSignals(self)
        self.signals.done.connect(self._got)
        self.seq = 0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)  # wait until the slider settles
        self._timer.timeout.connect(self._render)

        lay = vbox(self, SPACE_5, SPACE_3)
        title = QLabel("Preview")
        title.setObjectName("DialogTitle")
        lay.addWidget(title)

        top = hbox(spacing=SPACE_2)
        self.pick = combo([(str(i), c[0], c[1]) for i, c in enumerate(clips)], str(start))
        self.pick.setVisible(len(clips) > 1)
        self.pick.currentIndexChanged.connect(self._clip_changed)
        top.addWidget(self.pick, 1)
        self.view = Segmented([("converted", "With your settings"), ("original", "Original")])
        self.view.set_value("converted")
        self.view.changed.connect(lambda _k: self._render())
        top.addWidget(self.view)
        lay.addLayout(top)

        self.picture = QLabel("Making a preview…")
        self.picture.setObjectName("Preview")
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setFixedSize(VIEWER_W, VIEWER_H)
        lay.addWidget(self.picture)

        row = hbox(spacing=SPACE_3)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.valueChanged.connect(self._moved)
        self.time = QLabel()
        self.time.setObjectName("Muted")
        row.addWidget(self.slider, 1)
        row.addWidget(self.time)
        lay.addLayout(row)

        self.info_line = QLabel()
        self.info_line.setObjectName("Hint")
        lay.addWidget(self.info_line)

        bottom = hbox(margins=(0, SPACE_1, 0, 0))
        bottom.addStretch(1)
        done = QPushButton("Done")
        done.setObjectName("Primary")
        done.setDefault(True)
        done.setCursor(Qt.CursorShape.PointingHandCursor)
        done.clicked.connect(self.accept)
        bottom.addWidget(done)
        lay.addLayout(bottom)
        self._clip_changed()

    # ------------------------------------------------------------------ behavior
    def _clip(self) -> tuple:
        return self.clips[max(0, self.pick.currentIndex())]

    def _clip_changed(self) -> None:
        _, _, info, s, _ = self._clip()
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, int(info.duration * STEP) - 1))
        self.slider.setValue(int(min(info.duration / 3, 10) * STEP))  # a moment in, not the black first frame
        self.slider.blockSignals(False)
        w, h = naming.output_size(info, s, "video")
        size = f"{w}×{h}" if w and h else ""
        preset = VIDEO_BY_KEY[s.video_preset].title
        self.info_line.setText(f"Comes out as {preset}" + (f" · {size}" if size else ""))
        self._moved()

    def _moved(self) -> None:
        self.time.setText(fmt_time(self.slider.value() / STEP))
        self._timer.start()

    def _render(self) -> None:
        _, path, info, s, cues = self._clip()
        self.seq += 1
        self.picture.setText("Making a preview…")
        self.pool.start(
            PreviewTask(
                self.seq,
                path,
                info,
                s,
                self.slider.value() / STEP,
                self.view.value() == "original",
                self.signals,
                captions=cues,
            )
        )

    def _got(self, seq: int, data: bytes, error: str) -> None:
        if seq != self.seq:
            return  # an older request finished after a newer one started
        pm = QPixmap()
        if data and pm.loadFromData(data):
            self.picture.setPixmap(
                pm.scaled(
                    self.picture.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.picture.setPixmap(QPixmap())
            self.picture.setText(error or "Couldn't make a preview of this file.")
