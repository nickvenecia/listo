"""Check and fix captions before they're burned in: the words on the left of each clip, the picture on the right."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QEvent, QObject, Qt, QThreadPool, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QWidget

from ..core import captions
from ..core.captions import Cue, Transcript
from ..core.presets import Settings
from ..core.probe import MediaInfo
from .tokens import (
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
from .trim_dialog import fmt_time
from .widgets import combo, hbox, hint, vbox
from .workers import PreviewSignals, PreviewTask

LANGUAGE_NAMES = dict(captions.LANGUAGES)

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
        self.pool = QThreadPool.globalInstance()
        self.signals = PreviewSignals(self)
        self.signals.done.connect(self._got)
        self.seq = 0
        self.at = 0.0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._render)
        self._watch = _FocusWatch(self._row_focused)

        lay = vbox(self, SPACE_5, SPACE_3)
        title = QLabel("Check the captions")
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
        self.picture = QLabel("Making a preview…")
        self.picture.setObjectName("Preview")
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setFixedSize(EDITOR_PIC_W, EDITOR_PIC_H)
        left.addWidget(self.picture)
        left.addWidget(hint("Click a line to see it on the picture. Clear a line to remove that caption."))
        left.addStretch(1)
        body.addLayout(left)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFixedWidth(CAPTION_LIST_W)
        self.scroll.setFixedHeight(EDITOR_PIC_H + 48)
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
        self._load()

    # ------------------------------------------------------------------ clips
    def _i(self) -> int:
        return max(0, self.pick.currentIndex())

    def _load(self) -> None:
        i = self._i()
        _, _, _, s, t = self.clips[i]
        if i not in self.cues:
            self.cues[i] = deepcopy(t.cues_for(s.caption_words, s.caption_lines))
        lang = LANGUAGE_NAMES.get(t.language, t.language.upper() if t.language else "")
        self.heard.setText(f"Heard: {lang}" if lang else "")
        rows = QWidget()
        rl = vbox(rows, (0, 0, SPACE_2, 0), SPACE_1)
        self.edits: list[QPlainTextEdit] = []
        for n, c in enumerate(self.cues[i]):
            row = hbox(spacing=SPACE_2)
            when = QLabel(fmt_time(c.start))
            when.setAlignment(Qt.AlignmentFlag.AlignTop)
            when.setObjectName("Muted")
            when.setFixedWidth(TIME_FIELD_W - SPACE_5)
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
        if not self.cues[i]:
            rl.addWidget(hint("No speech was heard in this clip."))
        rl.addStretch(1)
        self.scroll.setWidget(rows)
        first = self.cues[i][0] if self.cues[i] else None
        self._show_at(first.start + min(0.3, (first.end - first.start) / 2) if first else 0.0)

    def _edited(self, n: int, text: str) -> None:
        self.cues[self._i()][n].text = text
        self.changed.add(self._i())
        self._timer.start()

    def _row_focused(self, edit: QObject) -> None:
        c = self.cues[self._i()][edit.property("cue")]
        self._show_at(c.start + min(0.3, (c.end - c.start) / 2))

    # ------------------------------------------------------------------ picture
    def _show_at(self, t: float) -> None:
        self.at = t
        self._timer.start()

    def _render(self) -> None:
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

    # ------------------------------------------------------------------ save
    def _accept(self) -> None:
        for i, (_, _, _, _, t) in enumerate(self.clips):
            if i in self.changed:
                t.cues = [c for c in self.cues[i] if c.text.strip()]
                t.edited = True
            t.reviewed = True
            captions.save(t)
        self.accept()
