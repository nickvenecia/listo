"""ClipPlayer: plays a clip with sound inside Listo (Export preview, Preview window, caption check).

Layers, bottom to top:
  video     the clip as shot (Qt's player; pixel shape from MediaInfo, so DV / MOD look right)
  captions  the caption on screen right now, drawn exactly as it will be burned in (burnin.caption_still)
  still     an exact frame of the result (owners render it with PreviewTask when the player settles):
            shown while paused, hidden while playing
  message   "Making a preview…", errors

While paused you see the real result (LUT, frame, burn-ins, captions); while playing you see the clip
with its captions over it. Owners listen to `settled(t)` (paused or moved somewhere new) and call
set_still() with the frame for that moment.

Qt's player only opens the clip when Play is pressed (until then, scrubbing shows still frames).
That keeps decoders closed while you're just looking, and keeps Qt's player away from files you
never play (it crashed on some MPEG-2 camcorder clips when the Mac's hardware decoder refused
them, so hardware decoding is also switched off for playback: see app.py).

Without Qt's player (or for a file it can't open) the widget becomes a still-frame viewer with a
scrubber: `fallback` is True, the play button hides, and `settled` still drives the frames.
"""

from __future__ import annotations

import io
import os

from PySide6.QtCore import QRectF, QSizeF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
    QSlider,
    QToolButton,
    QWidget,
)

from listo.core import burnin, naming
from listo.core.presets import Settings
from listo.core.probe import MediaInfo
from listo.ui.components.widgets import hbox, icon_button, vbox
from listo.ui.dialogs.trim import fmt_clock
from listo.ui.style import theme
from listo.ui.style.tokens import ICON, SCREEN, SCREEN_TEXT, SPACE_1, SPACE_2, TEXT_SM

# No hardware decoding for playback: Qt's player crashed on MPEG-2 (.MOD) when the Mac's decoder
# refused it. "," = an empty list (Qt docs: Advanced FFmpeg Configuration). Must be set before Qt
# opens its first decoder; app.main() sets it at start-up too.
os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", ",")

try:  # Qt's player (PySide6-Addons)
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QGraphicsVideoItem

    HAS_PLAYER = True
except ImportError:  # pragma: no cover - depends on the install
    HAS_PLAYER = False

TICK_MS = 40  # how often captions and owners follow the playing clip
SETTLE_MS = 250  # wait this long after the last move before asking for an exact frame


def space_plays(window: QWidget, player: ClipPlayer) -> QShortcut:
    """Space plays / pauses this player anywhere in the window (a shortcut wins over buttons and
    dropdowns that have focus; text fields still get their spaces)."""
    sc = QShortcut(QKeySequence(Qt.Key.Key_Space), window)
    sc.setContext(Qt.ShortcutContext.WindowShortcut)
    sc.activated.connect(player.toggle)
    return sc


def has_screen() -> bool:
    """Headless runs (tests, screenshots) have no sound system; asking Qt for one there can crash."""
    return QGuiApplication.platformName() not in ("offscreen", "minimal")


def fit(w: float, h: float, box: QRectF) -> QRectF:
    """A w×h picture fitted inside box, centered."""
    if w <= 0 or h <= 0:
        return QRectF(box)
    scale = min(box.width() / w, box.height() / h)
    fw, fh = w * scale, h * scale
    return QRectF(box.x() + (box.width() - fw) / 2, box.y() + (box.height() - fh) / 2, fw, fh)


class _Stage(QGraphicsView):
    clicked = Signal()
    double_clicked = Signal()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.double_clicked.emit()

    def wheelEvent(self, e):
        e.ignore()  # let the panel scroll


class ClipPlayer(QWidget):
    position_changed = Signal(float)  # seconds, while playing and after every move
    playing_changed = Signal(bool)
    step = Signal(int)  # -1 previous clip, +1 next clip (owners decide what that means)
    settled = Signal(float)  # paused somewhere new: owners can show the exact result frame there
    clicked = Signal()

    def __init__(
        self, width: int, height: int, parent: QWidget | None = None, captions_over_stills: bool = False
    ):
        """captions_over_stills: the owner renders still frames without captions and the live caption
        layer sits on top (the caption check: edits show instantly)."""
        super().__init__(parent)
        self.W, self.H = width, height
        self.path = ""
        self.info: MediaInfo | None = None
        self.s = Settings()
        self.cues: list | None = None
        self.captions_on = True
        self.range: tuple[float, float] | None = None
        self.fallback = not HAS_PLAYER
        self._pos = 0.0  # position when there's no player
        self._pending: float | None = None
        self._open = False  # Qt's player has this clip open (only after Play)
        self._autoplay = False
        self._shown: tuple | None = None
        self._still_at: float | None = None  # where the still frame was taken (None = any time)
        self._still_pm: QPixmap | None = None  # that frame as it came (to fit it again at a new size)
        self.video_rect = QRectF(0, 0, width, height)
        self.out_size = (width, height)
        self.out_rect = QRectF(self.video_rect)

        lay = vbox(self, 0, SPACE_2)
        self.stage = _Stage()
        self.stage.setObjectName("Player")
        self.stage.setFixedSize(width, height)
        self.stage.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.stage.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stage.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stage.setBackgroundBrush(QBrush(QColor(SCREEN)))  # dark in both looks
        self.stage.clicked.connect(self.clicked)
        self.scene = QGraphicsScene(0, 0, width, height, self.stage)
        self.stage.setScene(self.scene)
        self.overlay = QGraphicsPixmapItem()
        self.overlay.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.overlay.setZValue(2.5 if captions_over_stills else 1)
        self.scene.addItem(self.overlay)
        self.still = QGraphicsPixmapItem()
        self.still.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.still.setZValue(2)
        self.scene.addItem(self.still)
        self.message = QGraphicsSimpleTextItem()
        self.message.setBrush(QBrush(QColor(SCREEN_TEXT)))
        f = QFont(self.font())
        f.setPixelSize(TEXT_SM)
        self.message.setFont(f)
        self.message.setZValue(3)
        self.scene.addItem(self.message)
        lay.addWidget(self.stage)

        self.transport = QWidget()
        tr = hbox(self.transport, spacing=SPACE_1)
        self.btn_prev = self._nav_button("chevron-left", "Previous clip", -1)
        tr.addWidget(self.btn_prev)
        self.btn_play = icon_button("", "Play / Pause", size=ICON)  # its icon follows playing / paused
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_play.clicked.connect(self.toggle)
        tr.addWidget(self.btn_play)
        self.btn_next = self._nav_button("chevron-right", "Next clip", 1)
        tr.addWidget(self.btn_next)
        tr.addSpacing(SPACE_1)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider.valueChanged.connect(self._slid)
        tr.addWidget(self.slider, 1)
        self.clock = QLabel()
        self.clock.setObjectName("Muted")
        tr.addWidget(self.clock)
        lay.addWidget(self.transport)

        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(SETTLE_MS)
        self._settle.timeout.connect(lambda: self.path and self.settled.emit(self.position()))
        self._ticker = QTimer(self)
        self._ticker.setInterval(TICK_MS)
        self._ticker.timeout.connect(self._tick)
        self.player = None
        if HAS_PLAYER:
            self.video = QGraphicsVideoItem()
            self.video.setAspectRatioMode(
                Qt.AspectRatioMode.IgnoreAspectRatio
            )  # we size it (pixel shape known)
            self.scene.addItem(self.video)
            self.player = QMediaPlayer(self)
            self.audio = None
            if has_screen():
                self.audio = QAudioOutput(self)
                self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(self.video)
            self.player.durationChanged.connect(self._duration)
            self.player.positionChanged.connect(lambda _ms: self._tick())
            self.player.playbackStateChanged.connect(self._state)
            self.player.mediaStatusChanged.connect(self._status)
            self.player.errorOccurred.connect(self._error)
        self._state()

    def _nav_button(self, icon: str, tip: str, direction: int) -> QToolButton:
        b = icon_button(icon, tip, theme.TEXT, ICON)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.clicked.connect(lambda: self.step.emit(direction))
        b.hide()  # until the owner says there's more than one clip
        return b

    def set_steps(self, has_prev: bool, has_next: bool) -> None:
        """Show the previous / next clip arrows (shown, but dimmed at either end of the list)."""
        many = has_prev or has_next
        for b, on in ((self.btn_prev, has_prev), (self.btn_next, has_next)):
            b.setVisible(many)
            b.setEnabled(on)

    # ------------------------------------------------------------------ loading
    def load(
        self,
        path: str,
        info: MediaInfo,
        settings: Settings,
        at: float = 0.0,
        play: bool = False,
        range_: tuple[float, float] | None = None,
    ) -> None:
        """Open a clip at `at` seconds (paused unless play=True). range_ = the part of a trimmed clip."""
        self.path, self.info, self.s, self.range = path, info, settings, range_
        self._shown = None
        self.overlay.setPixmap(QPixmap())
        self.still.setPixmap(QPixmap())  # the old clip's frame
        self._still_at = None
        self._layout()
        self._pos = at
        self.fallback = not HAS_PLAYER
        self._close()
        self._duration(int(info.duration * 1000))
        self._sync_slider(int(at * 1000))
        if play:
            self._open_at(at, autoplay=True)
        else:
            self._moved()
        self._state()

    def _open_at(self, at: float, autoplay: bool) -> None:
        if self.player is None or self.fallback or not self.path:
            return
        self._open = True
        self._pending, self._autoplay = at, autoplay
        self.player.setSource(QUrl.fromLocalFile(self.path))

    def _close(self) -> None:
        if self.player is not None and self._open:
            self.player.stop()
            self.player.setSource(QUrl())
        self._open = False
        self._pending = None

    def is_open(self) -> bool:
        """Qt's player has the clip open (it was played)."""
        return self._live()

    def _live(self) -> bool:
        """Qt's player has the clip open and is in charge of the position."""
        return self.player is not None and not self.fallback and self._open

    def release(self) -> None:
        """Let go of the file (close the dialog / quit)."""
        self._ticker.stop()
        self._close()

    def set_settings(self, settings: Settings) -> None:
        self.s = settings
        self._layout()
        self._shown = None
        self._draw_caption()

    def set_cues(self, cues: list | None) -> None:
        self.cues = cues
        self._shown = None
        self._draw_caption()

    def show_captions(self, on: bool) -> None:
        self.captions_on = on
        self._shown = None
        self._draw_caption()

    def set_size(self, width: int, height: int) -> None:
        """A new picture size (the right panel is narrower on a smaller window)."""
        if (width, height) == (self.W, self.H) or width < 2 or height < 2:
            return
        self.W, self.H = width, height
        self.stage.setFixedSize(width, height)
        self.scene.setSceneRect(0, 0, width, height)
        self._layout()
        self._shown = None
        self._draw_caption()
        self.set_message(self.message.text())
        if self._still_pm is not None:
            self.set_still(self._still_pm, self._still_at)

    def set_still(self, pm: QPixmap | None, at: float | None = None) -> None:
        """The exact result frame at `at` seconds (shown while paused there, hidden while playing)."""
        self.message.setText("")
        self._still_at = at
        self._still_pm = pm if pm is not None and not pm.isNull() else None
        if pm is None or pm.isNull():
            self.still.setPixmap(QPixmap())
            return
        r = fit(pm.width(), pm.height(), QRectF(0, 0, self.W, self.H))
        scaled = pm.scaled(
            round(r.width()),
            round(r.height()),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.still.setPixmap(scaled)
        self.still.setPos(r.topLeft())
        self._still_visibility()

    def _still_visibility(self) -> None:
        """Show the exact frame only while paused where it was taken (a moved player shows the clip
        until the new frame arrives); without a player it's the only picture, so always."""
        near = self._still_at is None or abs(self._still_at - self.position()) < 0.08
        self.still.setVisible(self.fallback or not self._open or (not self.is_playing() and near))

    def set_message(self, text: str) -> None:
        self.message.setText(text)
        br = self.message.boundingRect()
        self.message.setPos((self.W - br.width()) / 2, (self.H - br.height()) / 2)

    # ------------------------------------------------------------------ control
    def is_playing(self) -> bool:
        return self._live() and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def position(self) -> float:
        if self._live():
            return self._pending if self._pending is not None else self.player.position() / 1000
        return self._pos

    def play(self) -> None:
        if self.player is None or self.fallback or not self.path:
            return
        if self.range and self.position() >= self.range[1] - 0.05:
            self.seek(self.range[0])  # at the end of the trimmed part: start it again
        if not self._open:
            self._open_at(self._pos, autoplay=True)  # the clip opens on the first Play
            return
        self.player.play()

    def pause(self) -> None:
        if self.is_playing():
            self.player.pause()

    def toggle(self) -> None:
        if self.is_playing():
            self.pause()
        else:
            self.play()

    def seek(self, t: float) -> None:
        if self.info is not None and self.info.duration:
            t = min(max(0.0, t), self.info.duration)
        self._pos = t
        if not self._live():
            self._sync_slider(int(t * 1000))
            self._moved()
            return
        if self._pending is not None or self.player.mediaStatus() in (
            QMediaPlayer.MediaStatus.LoadingMedia,
            QMediaPlayer.MediaStatus.NoMedia,
        ):
            self._pending = t
            return
        self.player.setPosition(int(t * 1000))
        self._moved()

    # ------------------------------------------------------------------ player events
    def _status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            self.message.setText("")
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self._pending is not None:
            t, self._pending = self._pending, None
            self._pos = t
            self.player.setPosition(int(t * 1000))
            if self._autoplay:
                self._autoplay = False
                self.player.play()
            else:
                self.player.pause()  # shows that frame
                self._moved()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._state()

    def _error(self, _err, message: str) -> None:
        """This file won't play here: still frames only."""
        pos = self.position()
        self._close()
        self._pos = pos
        self.fallback = True
        self._duration(int((self.info.duration if self.info else 0) * 1000))
        self._state()
        self._moved()
        self.transport.setToolTip(
            f"This clip can't play here ({message}). Showing still frames." if message else ""
        )

    def _state(self, *_a) -> None:
        playing = self.is_playing()
        self.btn_play.setVisible(not self.fallback)
        self.btn_play.setIcon(theme.icon("pause" if playing else "play", theme.TEXT))
        self._still_visibility()
        if playing:
            self._settle.stop()
            self._ticker.start()
        else:
            self._ticker.stop()
            self._tick()
            self._settle.start()
        self.playing_changed.emit(playing)

    def _duration(self, ms: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, ms))
        self.slider.setPageStep(max(1000, ms // 20))
        self.slider.blockSignals(False)
        self._tick()

    def _slid(self, ms: int) -> None:
        self._pos = ms / 1000
        if self._live() and self._pending is None:
            self.player.setPosition(ms)
        elif self._live():
            self._pending = ms / 1000
        self._moved()

    def _moved(self) -> None:
        """The position jumped: follow it, and (when paused) ask for the exact frame there."""
        self._tick()
        if not self.is_playing():
            self._settle.start()

    def _sync_slider(self, ms: int) -> None:
        if not self.slider.isSliderDown():
            self.slider.blockSignals(True)
            self.slider.setValue(ms)
            self.slider.blockSignals(False)

    def _tick(self) -> None:
        t = self.position()
        if self.range and self.is_playing() and t >= self.range[1]:
            self.player.pause()  # end of the trimmed part
            return
        self._sync_slider(int(t * 1000))
        total = self.info.duration if self.info else 0.0
        self.clock.setText(f"{fmt_clock(t, total)} / {fmt_clock(total)}")
        self._draw_caption()
        self._still_visibility()
        self.position_changed.emit(t)

    # ------------------------------------------------------------------ captions over the picture
    def _layout(self) -> None:
        """Size the picture from the clip's real shape (pixel aspect included, e.g. DV and MOD)."""
        info = self.info
        box = QRectF(0, 0, self.W, self.H)
        if info is None:
            return
        dw = (info.width or 16) * (info.sar or 1.0)
        self.video_rect = fit(dw, info.height or 9, box)
        if HAS_PLAYER:
            self.video.setPos(self.video_rect.topLeft())
            self.video.setSize(QSizeF(self.video_rect.width(), self.video_rect.height()))
        w, h = naming.output_size(info, self.s, "video")
        self.out_size = (w, h) if w and h else (round(dw), info.height or 9)
        # the finished frame (it may be cropped to another shape) as it sits over this picture
        self.out_rect = fit(*self.out_size, self.video_rect)

    def cue_at(self, t: float) -> int | None:
        for n, c in enumerate(self.cues or []):
            if c.start <= t < c.end and c.text.strip():
                return n
        return None

    def _draw_caption(self) -> None:
        n = self.cue_at(self.position()) if (self.captions_on and self.s.captions) else None
        text = self.cues[n].text if n is not None else ""
        key = (
            text,
            self.s.caption_style,
            self.s.caption_size,
            self.s.caption_box,
            self.s.caption_words,
            self.out_size,
        )
        if key == self._shown:
            return
        self._shown = key
        if not text.strip():
            self.overlay.setPixmap(QPixmap())
            return
        img, (x, y) = burnin.caption_still(text, self.s, self.out_size)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        pm = QPixmap()
        pm.loadFromData(buf.getvalue())
        scale = self.out_rect.height() / self.out_size[1]
        self.overlay.setPixmap(pm)
        self.overlay.setScale(scale)
        self.overlay.setPos(self.out_rect.x() + x * scale, self.out_rect.y() + y * scale)
