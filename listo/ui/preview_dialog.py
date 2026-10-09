"""Preview: play a clip with sound, and see exactly how it will come out.

Paused, the picture is one frame through the real conversion steps (LUT, frame, size, burn-ins,
captions). Playing, it's the clip as shot with its captions over it (ClipPlayer). "Original" shows
the clip untouched. Double-clicking a clip in the list opens this and starts playing.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QWidget

from ..core import naming
from ..core.presets import VIDEO_BY_KEY
from .player import ClipPlayer, space_plays
from .tokens import SPACE_1, SPACE_2, SPACE_3, SPACE_5, VIEWER_H, VIEWER_W
from .widgets import Segmented, combo, hbox, vbox
from .workers import PreviewSignals, PreviewTask


class PreviewDialog(QDialog):
    """`clips` = [(label, path, info, settings, captions or None)] — every video in the list."""

    def __init__(self, clips: list[tuple], start: int = 0, parent: QWidget | None = None, play: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Preview")
        self.clips = clips
        self.pool = QThreadPool.globalInstance()
        self.signals = PreviewSignals(self)
        self.signals.done.connect(self._got)
        self.seq = 0
        self._at = 0.0

        lay = vbox(self, SPACE_5, SPACE_3)
        title = QLabel("Preview")
        title.setObjectName("DialogTitle")
        lay.addWidget(title)

        top = hbox(spacing=SPACE_2)
        self.pick = combo([(str(i), c[0], c[1]) for i, c in enumerate(clips)], str(start))
        self.pick.setVisible(len(clips) > 1)
        self.pick.currentIndexChanged.connect(lambda _i: self._clip_changed())
        top.addWidget(self.pick, 1)
        self.view = Segmented([("converted", "With Your Settings"), ("original", "Original")])
        self.view.set_value("converted")
        self.view.changed.connect(lambda _k: self._view_changed())
        top.addWidget(self.view)
        lay.addLayout(top)

        self._play_next = False  # the arrows keep playing if the clip was playing
        self.player = ClipPlayer(VIEWER_W, VIEWER_H)
        self.player.step.connect(self._step)
        space_plays(self, self.player)
        self.player.settled.connect(self._render)
        self.player.clicked.connect(self.player.toggle)
        lay.addWidget(self.player)

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
        self._clip_changed(play)

    # ------------------------------------------------------------------ behavior
    def _clip(self) -> tuple:
        return self.clips[max(0, self.pick.currentIndex())]

    def _original(self) -> bool:
        return self.view.value() == "original"

    def _step(self, direction: int) -> None:
        """The previous / next arrows: the clip before or after this one in the list."""
        n = self.pick.currentIndex() + direction
        if 0 <= n < len(self.clips):
            self._play_next = self.player.is_playing()
            self.pick.setCurrentIndex(n)

    def _clip_changed(self, play: bool = False) -> None:
        play, self._play_next = play or self._play_next, False
        i = max(0, self.pick.currentIndex())
        self.player.set_steps(i > 0, i < len(self.clips) - 1)
        _, path, info, s, cues = self._clip()
        w, h = naming.output_size(info, s, "video")
        size = f"{w}×{h}" if w and h else ""
        preset = VIDEO_BY_KEY[s.video_preset].title
        self.info_line.setText(
            f"Comes out as {preset}"
            + (f" · {size}" if size else "")
            + " · Paused: the exact result. Playing: the clip with its captions."
        )
        self.player.set_still(None)
        self.player.set_message("Making a preview…")
        at = 0.0  # every player opens on the first frame
        self.player.load(path, info, s, at, play=play)
        self.player.set_cues(cues)
        self.player.show_captions(not self._original())

    def _view_changed(self) -> None:
        self.player.show_captions(not self._original())
        self.player.set_still(None)
        self._render(self.player.position())

    def _render(self, at: float) -> None:
        """The exact frame where the player stopped (the untouched one for Original, if there's no player)."""
        if self._original() and self.player.is_open():
            self.player.set_still(None)  # the paused clip is the original
            return
        _, path, info, s, cues = self._clip()
        self.seq += 1
        self._at = at
        self.pool.start(
            PreviewTask(self.seq, path, info, s, at, self._original(), self.signals, captions=cues)
        )

    def _got(self, seq: int, data: bytes, error: str) -> None:
        if seq != self.seq:
            return  # an older request finished after a newer one started
        pm = QPixmap()
        if data and pm.loadFromData(data):
            self.player.set_still(pm, self._at)
        else:
            self.player.set_still(None)
            self.player.set_message(error or "Couldn't make a preview of this file.")

    def done(self, r: int) -> None:
        self.player.release()
        super().done(r)
