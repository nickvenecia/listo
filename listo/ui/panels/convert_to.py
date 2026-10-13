"""The right panel: Convert To. The live preview on top (the picked clip, or the first, exactly as it will come
out), then what the files become (recipe, Video / Photo / Audio, the Image, Burn-In and Encoding cards), then
where they go and what they're called (Saves To). The settings apply to every file in the list; a file's own
format is changed from its row.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from listo.core.presets import Settings
from listo.ui.components.panels import SidePanel
from listo.ui.panels.convert import ConvertSettings
from listo.ui.panels.export import ExportSettings
from listo.ui.style import tokens


class ConvertPanel(SidePanel):
    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__("Convert To", parent=parent)
        self.settings_part = ConvertSettings(settings)
        self.export_part = ExportSettings(settings)
        self.btn_preview = self.header_icon("eye", "Bigger Preview")
        self.lay.addWidget(self.export_part.preview_box)
        self.lay.addWidget(self.settings_part)
        self.lay.addWidget(self.export_part)
        self.lay.addStretch(1)
        self.set_width(tokens.INSPECTOR_W)

    def set_width(self, w: int) -> None:
        """Narrower on a smaller window (between INSPECTOR_MIN and INSPECTOR_W); the preview follows."""
        self.setFixedWidth(w)
        self.export_part.set_panel_width(w)
