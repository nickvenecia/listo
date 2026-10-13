"""Check and fix captions before they're burned in.

The clip plays on the left (ClipPlayer: with sound, the caption on screen drawn exactly as it will be
burned in); the list on the right lights up the caption that's showing and follows along. Click a
line or its time to jump there, type to fix it, clear it to remove it, and "Add Caption" puts a new
one where the clip is paused.
"""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QEvent, QObject, Qt, QThreadPool
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QWidget

from listo.core import captions
from listo.core.captions import Cue, Transcript
from listo.core.presets import Settings
from listo.core.probe import MediaInfo
from listo.ui.components.player import HAS_PLAYER, ClipPlayer, space_plays
from listo.ui.components.widgets import ClickLabel, combo, hbox, hint, repolish, vbox
from listo.ui.dialogs.trim import fmt_clock
from listo.ui.style import theme
from listo.ui.style.tokens import (
    CAPTION_LIST_W,
    CAPTION_ROW_H,
    EDITOR_PIC_H,
    EDITOR_PIC_W,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    SPACE_5,
    TIME_FIELD_W,
)
from listo.ui.window.jobs import PreviewSignals, PreviewTask

__all__ = ["HAS_PLAYER", "CaptionEditor"]

LANGUAGE_NAMES = dict(captions.LANGUAGES)
NEW_CAPTION_S = 2.0  # how long a new caption lasts (shorter if the next one starts sooner)
MIN_CAPTION_S = 0.3

Clip = tuple[str, str, MediaInfo, Settings, Transcript]  # label, path, info, settings, transcript


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
        self.current: int | None = None  # the caption showing right now (row index)
        self.edits: list[QPlainTextEdit] = []
        self.times: list[ClickLabel] = []
        self.pool = QThreadPool.globalInstance()
        self.signals = PreviewSignals(self)
        self.signals.done.connect(self._got)
        self.seq = 0
        self._still_at = 0.0
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
        self._play_next = False  # the arrows keep playing if the clip was playing
        self.player = ClipPlayer(EDITOR_PIC_W, EDITOR_PIC_H, captions_over_stills=True)
        self.player.step.connect(self._step)
        space_plays(self, self.player)  # (typing in a caption still types spaces)
        self.player.position_changed.connect(self._followed)
        self.player.settled.connect(self._settled)
        self.player.clicked.connect(self.player.toggle)
        left.addWidget(self.player)
        self.help = hint(
            "Press Play (or Space) to watch with the captions; the one on screen lights up. "
            "Click a line to jump there and fix it. Clear a line to remove that caption."
        )
        left.addWidget(self.help)
        left.addStretch(1)
        body.addLayout(left)

        right = vbox(spacing=SPACE_2)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFixedWidth(CAPTION_LIST_W)
        self.scroll.setFixedHeight(EDITOR_PIC_H + 24)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right.addWidget(self.scroll)
        self.btn_add = QPushButton(" Add Caption")
        self.btn_add.setIcon(theme.icon("plus", theme.TEXT))
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setToolTip("Add a caption where the clip is now (pause where the words start)")
        self.btn_add.clicked.connect(self.add_caption)
        add_row = hbox()
        add_row.addWidget(self.btn_add)
        add_row.addStretch(1)
        right.addLayout(add_row)
        body.addLayout(right)
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
        self._load()

    # ------------------------------------------------------------------ clips
    def _i(self) -> int:
        return max(0, self.pick.currentIndex())

    def _load(self) -> None:
        i = self._i()
        _, path, info, s, t = self.clips[i]
        if i not in self.cues:
            self.cues[i] = deepcopy(t.cues_for(s.caption_words, s.caption_lines))
        lang = LANGUAGE_NAMES.get(t.language, t.language.upper() if t.language else "")
        self.heard.setText(f"Heard: {lang}" if lang else "")
        self._rows()
        at = 0.0  # from the first frame, like every player in Listo
        self.player.set_still(None)
        self.player.set_message("Making a preview…")
        play, self._play_next = self._play_next, False
        self.player.set_steps(i > 0, i < len(self.clips) - 1)
        self.player.load(path, info, s, at, play=play)
        self.player.set_cues(self.cues[i])

    def _step(self, direction: int) -> None:
        """The previous / next arrows: the clip before or after this one (edits are kept)."""
        n = self._i() + direction
        if 0 <= n < len(self.clips):
            self._play_next = self.player.is_playing()
            self.pick.setCurrentIndex(n)

    def _rows(self, focus: int | None = None) -> None:
        """(Re)build the caption list for the current clip."""
        i = self._i()
        rows = QWidget()
        rl = vbox(rows, (0, 0, SPACE_2, 0), SPACE_1)
        self.edits, self.times = [], []
        self.current = None
        for n, c in enumerate(self.cues[i]):
            row = hbox(spacing=SPACE_2)
            when = ClickLabel(fmt_clock(c.start, self.clips[i][2].duration))
            when.setObjectName("CueTime")
            when.setAlignment(Qt.AlignmentFlag.AlignTop)
            when.setFixedWidth(TIME_FIELD_W - SPACE_5)
            when.setCursor(Qt.CursorShape.PointingHandCursor)
            when.setToolTip("Jump here")
            when.clicked.connect(lambda n=n: self._jump(n))
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
            rl.addWidget(hint("No speech was heard in this clip. Use Add Caption to write your own."))
        rl.addStretch(1)
        self.scroll.setWidget(rows)
        self._light(self.player.cue_at(self.player.position()), follow=False)
        if focus is not None and focus < len(self.edits):
            e = self.edits[focus]
            e.blockSignals(True)
            e.setFocus()
            e.blockSignals(False)
            self.scroll.ensureWidgetVisible(e, 0, SPACE_5)

    # ------------------------------------------------------------------ following the clip
    def _followed(self, t: float) -> None:
        self._light(self.player.cue_at(t), follow=self.player.is_playing())

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

    def _jump(self, n: int) -> None:
        c = self.cues[self._i()][n]
        self.player.seek(c.start + min(0.3, (c.end - c.start) / 2))

    def _row_focused(self, edit: QObject) -> None:
        """Clicking a line jumps the clip there (and keeps playing if it was)."""
        n = edit.property("cue")
        if n is not None and n != self.player.cue_at(self.player.position()):
            self._jump(n)

    # ------------------------------------------------------------------ editing
    def _edited(self, n: int, text: str) -> None:
        self.cues[self._i()][n].text = text
        self.changed.add(self._i())
        self.player.set_cues(self.cues[self._i()])  # the caption layer is on top: shows at once

    def add_caption(self) -> None:
        """A new, empty caption where the clip is now, up to the next one (2 s at most)."""
        i = self._i()
        cues = self.cues[i]
        _, _, info, _, _ = self.clips[i]
        t = self.player.position()
        inside = self.player.cue_at(t)
        if inside is not None:
            t = cues[inside].end  # on top of a caption: start right after it
        nxt = min((c.start for c in cues if c.start > t + 1e-3), default=info.duration or t + NEW_CAPTION_S)
        end = min(t + NEW_CAPTION_S, nxt)
        if end - t < MIN_CAPTION_S:
            self.help.setText("No room for a caption here. Move to a gap between captions, then Add Caption.")
            return
        self.player.pause()
        cue = Cue(round(t, 3), round(end, 3), "")
        cues.append(cue)
        cues.sort(key=lambda c: c.start)
        self.changed.add(i)
        self.player.set_cues(cues)
        self._rows(focus=cues.index(cue))
        self.player.seek(t + min(0.3, (end - t) / 2))

    # ------------------------------------------------------------------ still frames
    def _settled(self, t: float) -> None:
        """Paused / moved: the exact frame (LUT, frame, burn-ins). Captions aren't burned into it: the
        live caption layer sits on top, so edits show instantly."""
        i = self._i()
        _, path, info, s, _ = self.clips[i]
        self.seq += 1
        self._still_at = t
        self.pool.start(PreviewTask(self.seq, path, info, s, t, False, self.signals, captions=None))

    def _got(self, seq: int, data: bytes, error: str) -> None:
        if seq != self.seq:
            return
        pm = QPixmap()
        if data and pm.loadFromData(data):
            self.player.set_still(pm, self._still_at)
        else:
            self.player.set_still(None)
            self.player.set_message(error or "Couldn't make a preview.")

    # ------------------------------------------------------------------ save / close
    def done(self, r: int) -> None:
        self.player.release()
        super().done(r)

    def _accept(self) -> None:
        for i, (_, _, _, _, t) in enumerate(self.clips):
            if i in self.changed:
                t.cues = [c for c in self.cues[i] if c.text.strip()]
                t.edited = True
            t.reviewed = True
            captions.save(t)
        self.accept()
