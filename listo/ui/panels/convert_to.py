"""The right panel: Convert To. The live preview on top (the picked clip, or the first, exactly as it will come
out), then what the files become: the recipe, and a heading with settings for each kind of file in the list
("9 Videos": format, Clips, the Picture, Burn-In and Captions folds; "2 Photos"; "1 Audio File"), then where
they go and what they're called (Saves To, Advanced). The settings apply to every file in the list; a file's
own format is changed from its row. Its title is a menu, as FeatureSoup's are: Every File, or one kind's settings
(it follows the list's place: Videos in the list shows Video Settings).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QToolButton, QWidget

from listo.core.presets import Settings
from listo.ui.components.panels import SidePanel
from listo.ui.panels.convert import SCOPE_TITLES, ConvertSettings
from listo.ui.panels.export import ExportSettings
from listo.ui.style import theme, tokens

TITLE = "Convert To"


class ConvertPanel(SidePanel):
    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(TITLE, parent=parent)
        self.settings_part = ConvertSettings(settings)
        self.export_part = ExportSettings(settings)
        self.settings_part.put_clips(self.export_part.videos_sec)  # a file per clip or joined: a video choice
        self.export_part.adv.add(self.settings_part.sec_speed)  # speed is for every file, not just videos
        self.btn_preview = self.header_icon("eye", "Bigger Preview")
        self.btn_reset = self.header_icon("reset", "Reset to Defaults…")  # (before the eye)
        # the title is a menu: every file's settings, or one kind's
        self.header.title.hide()
        self.title_menu = QToolButton()
        self.title_menu.setObjectName("TitleMenu")
        self.title_menu.setText(TITLE)
        self.title_menu.setIcon(theme.icon("chevron", theme.MUTED, tokens.ICON_SM))
        self.title_menu.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.title_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)  # the chevron after the words
        self.title_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_menu.setToolTip("Show the Settings for Every File, or for One Kind")
        self.title_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.title_menu.setMenu(QMenu(self.title_menu))
        self.title_menu.menu().setLayoutDirection(
            Qt.LayoutDirection.LeftToRight
        )  # (not the button's mirroring)
        self.title_menu.menu().aboutToShow.connect(lambda: self._fill_scope_menu(self.title_menu.menu()))
        self.header.layout().insertWidget(0, self.title_menu)
        self.header.layout().insertStretch(1, 1)
        self.lay.addWidget(self.export_part.preview_box)
        self.lay.addWidget(self.settings_part)
        self.lay.addWidget(self.export_part)
        self.lay.addStretch(1)
        self.set_width(tokens.INSPECTOR_W)

    def set_scope(self, kind: str | None) -> None:
        """Every kind's settings (None), or one kind's: "video", "photo", "audio"."""
        self.settings_part.set_scope(kind)
        self.title_menu.setText(SCOPE_TITLES.get(self.settings_part.scope, TITLE))

    def _fill_scope_menu(self, m: QMenu) -> None:
        m.clear()
        for kind, name, n in self.settings_part.scope_choices():
            a = m.addAction(
                theme.menu_icon(
                    {"video": "film", "photo": "image", "audio": "audio"}.get(kind, "sliders"),
                    theme.TEXT if kind == self.settings_part.scope else theme.MUTED,
                ),
                f"{name}\t{n}" if n else name,
                lambda _c=False, k=kind: self.set_scope(k),
            )
            if kind == self.settings_part.scope:
                f = a.font()
                f.setBold(True)
                a.setFont(f)

    def set_width(self, w: int) -> None:
        """Narrower on a smaller window (between INSPECTOR_MIN and INSPECTOR_W); the preview follows."""
        self.setFixedWidth(w)
        self.export_part.set_panel_width(w)
