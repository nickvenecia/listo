"""Check and fix captions before they're burned in.

The clip plays on the left (with sound) and the caption on screen is drawn over it exactly as it
will be burned in; the list on the right lights up the caption that's showing and follows along.
Click a time to jump there, click a line to edit it.

If Qt's media player isn't available (or can't open a file), the picture falls back to still
frames rendered by Listo's ffmpeg (PreviewTask), one per caption.
"""

from __future__ import annotations

import io
from copy import deepcopy

from PySide6.QtCore import QEvent, QObject, QRectF, QSize, QSizeF, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QToolButton,
    QWidget,
)

from ..core import burnin, captions, naming
from ..core.captions import Cue, Transcript
from ..core.presets import Settings
from ..core.probe import MediaInfo
from . import theme
from .tokens import (
    CAPTION_LIST_W,
    CAPTION_ROW_H,
    EDITOR_PIC_H,
    EDITOR_PIC_W,
    ICON,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    SPACE_5,
    TIME_FIELD_W,
    WELL,
)
from .trim_dialog import fmt_time
from .widgets import ClickLabel, combo, hbox, hint, repolish, vbox
from .workers import PreviewSignals, PreviewTask

try:  # Qt's player (PySide6-Addons). Without it the editor shows still frames.
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QGraphicsVideoItem

    HAS_PLAYER = True
except ImportError:  # pragma: no cover - depends on the install
    HAS_PLAYER = False

LANGUAGE_NAMES = dict(captions.LANGUAGES)
TICK_MS = 40  # how often the list and the caption follow the playing clip

Clip = tuple[str, str, MediaInfo, Settings, Transcript]  # label, path, info, settings, transcript


def _has_screen() -> bool:
    """Headless runs (tests, screenshots) have no sound system; asking Qt for one there can crash."""
    return QGuiApplication.platformName() not in ("offscreen", "minimal")


def _fit(w: float, h: float, box: QRectF) -> QRectF:
    """A w×h picture fitted inside box, centered."""
    if w <= 0 or h <= 0:
        return QRectF(box)
    scale = min(box.width() / w, box.height() / h)
    fw, fh = w * scale, h * scale
    return QRectF(box.x() + (box.width() - fw) / 2, box.y() + (box.height() - fh) / 2, fw, fh)


class _FocusWatch(QObject):
    def __init__(self, on_focus):
        super().__init__()
        self.on_focus = on_focus

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.FocusIn:
            self.on_focus(obj)
        return False


class CaptionEditor(QDialog):
    """Edit each clip's captions. Accepting marks every clip shown here as checked."""

    def __init__(
        self, clips: list[Clip], start: int = 0, action: str = "Done", parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Captions")
        self.clips = clips
        self.cues: dict[int, list[Cue]] = {}  # clip index -> working copy
        self.changed: set[int] = set()
        self.pool = QThreadPool.globalInstance()
        self.signals = PreviewSignals(self)
        self.signals.done.connect(self._got)
        self.seq = 0
        self.at = 0.0
        self.current: int | None = None  # the caption showing right now (row index)
        self._shown: tuple | None = None  # what the caption overlay is drawing
        self._pending_seek: float | None = None
        self._still_mode = not HAS_PLAYER
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._render)
        self._watch = _FocusWatch(self._row_focused)

        lay = vbox(self, SPACE_5, SPACE_3)
        title = QLabel("Check the Captions")
        title.setObjectName("DialogTitle")
        lay.addWidget(title)
        top = hbox(spacing=SPACE_2)
        self.pick = combo([(str(i), c[0], c[1]) for i, c in enumerate(clips)], str(start))
        self.pick.setVisible(len(clips) > 1)
        self.pick.currentIndexChanged.connect(self._load)
        top.addWidget(self.pick, 1)
        self.heard = QLabel()
        self.heard.setObjectName("Muted")
        top.addWidget(self.heard)
        lay.addLayout(top)

        body = hbox(spacing=SPACE_3)
        left = vbox(spacing=SPACE_2)
        self.stage = QStackedWidget()
        self.stage.setFixedSize(EDITOR_PIC_W, EDITOR_PIC_H)
        self.picture = QLabel("Making a preview…")  # still frames (fallback)
        self.picture.setObjectName("Preview")
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stage.addWidget(self.picture)
        if HAS_PLAYER:
            self._build_player()
        left.addWidget(self.stage)

        self.transport = QWidget()
        tr = hbox(self.transport, spacing=SPACE_2)
        self.btn_play = QToolButton()
        self.btn_play.setObjectName("IconBtn")
        self.btn_play.setIconSize(QSize(ICON, ICON))
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play.setToolTip("Play / Pause (Space)")
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_play.clicked.connect(self.toggle_play)
        tr.addWidget(self.btn_play)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider.valueChanged.connect(self._slid)
        tr.addWidget(self.slider, 1)
        self.clock = QLabel()
        self.clock.setObjectName("Muted")
        tr.addWidget(self.clock)
        left.addWidget(self.transport)
        self.help = hint("")
        left.addWidget(self.help)
        left.addStretch(1)
        body.addLayout(left)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFixedWidth(CAPTION_LIST_W)
        self.scroll.setFixedHeight(EDITOR_PIC_H + 72)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body.addWidget(self.scroll)
        lay.addLayout(body)

        bottom = hbox(margins=(0, SPACE_1, 0, 0))
        bottom.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        ok = QPushButton(action)
        ok.setObjectName("Primary")
        ok.setDefault(False)
        ok.setAutoDefault(False)
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.clicked.connect(self._accept)
        bottom.addWidget(ok)
        lay.addLayout(bottom)
        self._set_mode(self._still_mode)
        self._load()

    # ------------------------------------------------------------------ player
    def _build_player(self) -> None:
        self.view = QGraphicsView()
        self.view.setObjectName("Player")
        self.view.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setBackgroundBrush(QBrush(QColor(WELL)))
        self.scene = QGraphicsScene(0, 0, EDITOR_PIC_W, EDITOR_PIC_H, self.view)
        self.view.setScene(self.scene)
        self.video = QGraphicsVideoItem()
        self.video.setAspectRatioMode(Qt.AspectRatioMode.IgnoreAspectRatio)  # we size it (pixel shape known)
        self.scene.addItem(self.video)
        self.overlay = QGraphicsPixmapItem()
        self.overlay.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.overlay.setZValue(1)
        self.scene.addItem(self.overlay)
        self.stage.addWidget(self.view)

        self.player = QMediaPlayer(self)
        self.audio = None
        if _has_screen():
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.durationChanged.connect(self._duration)
        self.player.positionChanged.connect(lambda _ms: self._tick())
        self.player.playbackStateChanged.connect(self._play_state)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.errorOccurred.connect(self._player_error)
        self._ticker = QTimer(self)
        self._ticker.setInterval(TICK_MS)
        self._ticker.timeout.connect(self._tick)

    def _set_mode(self, still: bool) -> None:
        self._still_mode = still
        self.stage.setCurrentIndex(0 if still else 1)
        self.transport.setVisible(not still)
        self.help.setText(
            "Click a line to see it on the picture. Clear a line to remove that caption."
            if still
            else "Press Play (or Space) to watch with the captions; the one on screen lights up. "
            "Click a time to jump there. Clear a line to remove that caption."
        )
        self._play_state()

    def _playing(self) -> bool:
        return not self._still_mode and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def toggle_play(self) -> None:
        if self._still_mode:
            return
        if self._playing():
            self.player.pause()
        else:
            self.player.play()

    def seek(self, t: float) -> None:
        if self._still_mode:
            self._show_at(t)
            return
        if self.player.mediaStatus() in (
            QMediaPlayer.MediaStatus.LoadingMedia,
            QMediaPlayer.MediaStatus.NoMedia,
        ):
            self._pending_seek = t
            return
        self.player.setPosition(int(t * 1000))
        self._tick()

    def _media_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self._pending_seek is not None:
            t, self._pending_seek = self._pending_seek, None
            self.player.setPosition(int(t * 1000))
            self.player.pause()  # shows that frame without playing
            self._tick()

    def _player_error(self, _err, message: str) -> None:
        """This file won't play here: fall back to still frames."""
        self._set_mode(True)
        self._show_at(self.at)
        if message:
            self.help.setText(f"This clip can't play here ({message}). Showing still frames instead.")

    def _play_state(self, *_a) -> None:
        playing = HAS_PLAYER and self._playing()
        self.btn_play.setIcon(theme.icon("pause" if playing else "play", theme.TEXT))
        if HAS_PLAYER:
            if playing:
                self._ticker.start()
            else:
                self._ticker.stop()
                self._tick()

    def _duration(self, ms: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, ms))
        self.slider.setPageStep(max(1000, ms // 20))
        self.slider.blockSignals(False)
        self._tick()

    def _slid(self, ms: int) -> None:
        if not self._still_mode:
            self.player.setPosition(ms)
            self._tick()

    def _tick(self) -> None:
        """Follow the clip: clock, slider, which caption lights up, and the caption over the picture."""
        if self._still_mode:
            return
        ms = self.player.position()
        t = ms / 1000
        self.at = t
        if not self.slider.isSliderDown():
            self.slider.blockSignals(True)
            self.slider.setValue(ms)
            self.slider.blockSignals(False)
        self.clock.setText(f"{fmt_time(t)} / {fmt_time(self.player.duration() / 1000)}")
        self._light(self._cue_at(t), follow=self._playing())
        self._draw_overlay()

    # ------------------------------------------------------------------ captions over the picture
    def _cue_at(self, t: float) -> int | None:
        for n, c in enumerate(self.cues.get(self._i(), [])):
            if c.start <= t < c.end and c.text.strip():
                return n
        return None

    def _layout_video(self) -> None:
        """Size the picture from the clip's real shape (pixel aspect included, e.g. DV and MOD)."""
        _, _, info, s, _ = self.clips[self._i()]
        box = QRectF(0, 0, EDITOR_PIC_W, EDITOR_PIC_H)
        dw = (info.width or 16) * (info.sar or 1.0)
        self.video_rect = _fit(dw, info.height or 9, box)
        self.video.setPos(self.video_rect.topLeft())
        self.video.setSize(QSizeF(self.video_rect.width(), self.video_rect.height()))
        w, h = naming.output_size(info, s, "video")
        self.out_size = (w, h) if w and h else (round(dw), info.height or 9)
        # the finished frame (it may be cropped to another shape) as it sits over this picture
        self.out_rect = _fit(*self.out_size, self.video_rect)

    def _draw_overlay(self) -> None:
        i = self._i()
        n = self.current
        text = self.cues[i][n].text if n is not None else ""
        key = (i, text)
        if key == self._shown:
            return
        self._shown = key
        if not text.strip():
            self.overlay.setPixmap(QPixmap())
            return
        s = self.clips[i][3]
        img, (x, y) = burnin.caption_still(text, s, self.out_size)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        pm = QPixmap()
        pm.loadFromData(buf.getvalue())
        scale = self.out_rect.height() / self.out_size[1]
        self.overlay.setPixmap(pm)
        self.overlay.setScale(scale)
        self.overlay.setPos(self.out_rect.x() + x * scale, self.out_rect.y() + y * scale)

    def _light(self, n: int | None, follow: bool) -> None:
        """Light up the caption that's on screen (and keep it in view while playing)."""
        if n == self.current:
            return
        for k in (self.current, n):
            if k is not None and k < len(self.edits):
                on = k == n
                self.edits[k].setProperty("current", on)
                self.times[k].setProperty("current", on)
                repolish(self.edits[k])
                repolish(self.times[k])
        self.current = n
        if follow and n is not None and n < len(self.edits):
            self.scroll.ensureWidgetVisible(self.edits[n], 0, SPACE_5)

    # ------------------------------------------------------------------ clips
    def _i(self) -> int:
        return max(0, self.pick.currentIndex())

    def _load(self) -> None:
        i = self._i()
        _, path, _, s, t = self.clips[i]
        if i not in self.cues:
            self.cues[i] = deepcopy(t.cues_for(s.caption_words, s.caption_lines))
        lang = LANGUAGE_NAMES.get(t.language, t.language.upper() if t.language else "")
        self.heard.setText(f"Heard: {lang}" if lang else "")
        rows = QWidget()
        rl = vbox(rows, (0, 0, SPACE_2, 0), SPACE_1)
        self.edits: list[QPlainTextEdit] = []
        self.times: list[ClickLabel] = []
        self.current = None
        self._shown = None
        for n, c in enumerate(self.cues[i]):
            row = hbox(spacing=SPACE_2)
            when = ClickLabel(fmt_time(c.start))
            when.setObjectName("CueTime")
            when.setAlignment(Qt.AlignmentFlag.AlignTop)
            when.setFixedWidth(TIME_FIELD_W - SPACE_5)
            when.setCursor(Qt.CursorShape.PointingHandCursor)
            when.setToolTip("Jump here")
            when.clicked.connect(lambda c=c: self.seek(c.start))
            e = QPlainTextEdit(c.text)
            e.setObjectName("CaptionText")
            e.setFixedHeight(CAPTION_ROW_H)
            e.setTabChangesFocus(True)
            e.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            e.setProperty("cue", n)
            e.installEventFilter(self._watch)
            e.textChanged.connect(lambda n=n, e=e: self._edited(n, e.toPlainText().replace("\n", " ")))
            row.addWidget(when)
            row.addWidget(e, 1)
            rl.addLayout(row)
            self.edits.append(e)
            self.times.append(when)
        if not self.cues[i]:
            rl.addWidget(hint("No speech was heard in this clip."))
        rl.addStretch(1)
        self.scroll.setWidget(rows)
        first = self.cues[i][0] if self.cues[i] else None
        at = first.start + min(0.3, (first.end - first.start) / 2) if first else 0.0
        if HAS_PLAYER:
            self.player.stop()
            self._set_mode(False)
            self._layout_video()
            self._pending_seek = at
            self.player.setSource(QUrl.fromLocalFile(path))
        else:
            self._show_at(at)

    def _edited(self, n: int, text: str) -> None:
        self.cues[self._i()][n].text = text
        self.changed.add(self._i())
        if self._still_mode:
            self._timer.start()
        else:
            self._draw_overlay()

    def _row_focused(self, edit: QObject) -> None:
        """Clicking a line shows it on the picture (unless the clip is playing: then keep playing)."""
        if self._playing():
            return
        c = self.cues[self._i()][edit.property("cue")]
        self.seek(c.start + min(0.3, (c.end - c.start) / 2))

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() == Qt.Key.Key_Space and not isinstance(self.focusWidget(), QPlainTextEdit):
            self.toggle_play()
            return
        super().keyPressEvent(e)

    # ------------------------------------------------------------------ still frames (fallback)
    def _show_at(self, t: float) -> None:
        self.at = t
        self._light(self._cue_at(t), follow=False)
        self._timer.start()

    def _render(self) -> None:
        if not self._still_mode:
            return
        i = self._i()
        _, path, info, s, _ = self.clips[i]
        self.seq += 1
        shown = [c for c in self.cues[i] if c.text.strip()]
        self.pool.start(PreviewTask(self.seq, path, info, s, self.at, False, self.signals, captions=shown))

    def _got(self, seq: int, data: bytes, error: str) -> None:
        if seq != self.seq:
            return
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
            self.picture.setText(error or "Couldn't make a preview.")

    # ------------------------------------------------------------------ save / close
    def done(self, r: int) -> None:
        if HAS_PLAYER:
            self._ticker.stop()
            self.player.stop()
            self.player.setSource(QUrl())  # let go of the file
        super().done(r)

    def _accept(self) -> None:
        for i, (_, _, _, _, t) in enumerate(self.clips):
            if i in self.changed:
                t.cues = [c for c in self.cues[i] if c.text.strip()]
                t.edited = True
            t.reviewed = True
            captions.save(t)
        self.accept()
