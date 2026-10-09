"""Look and feel: colors, type, stylesheet and icons."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).resolve().parent.parent / "assets"

BG = "#111113"
PANEL = "#17171A"
CARD = "#1E1E22"
CARD_HOVER = "#24242A"
RAISED = "#2A2A30"
BORDER = "#2C2C33"
BORDER_STRONG = "#3A3A42"
TEXT = "#F4F1EC"
MUTED = "#A09B93"
FAINT = "#6E6A64"
ACCENT = "#F5A524"  # cempasúchil marigold
ACCENT_HOVER = "#FFB743"
ACCENT_PRESS = "#DB8F12"
ON_ACCENT = "#1B1206"
GOOD = "#4CC38A"
BAD = "#F0616D"
WARN = "#E9B949"

FONT_FAMILY = "Inter"


def load_fonts() -> str:
    family = ""
    for f in sorted((ASSETS / "fonts").glob("*.otf")):
        fid = QFontDatabase.addApplicationFont(str(f))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if fams and fams[0] == "Inter":
            family = "Inter"
    return family or ""


STYLESHEET = f"""
* {{ outline: none; }}
QWidget {{ color: {TEXT}; font-size: 13px; }}
QMainWindow, #Root {{ background: {BG}; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; padding: 6px 8px; border-radius: 6px; }}

#Header {{ background: {BG}; border-bottom: 1px solid {BORDER}; }}
#Wordmark {{ font-size: 24px; font-weight: 700; letter-spacing: -0.5px; }}
#Tagline {{ color: {FAINT}; font-size: 12px; }}

#Sidebar {{ background: {PANEL}; border-left: 1px solid {BORDER}; }}
#SectionLabel {{ color: {FAINT}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
#Hint {{ color: {FAINT}; font-size: 12px; }}
#Muted {{ color: {MUTED}; }}

QPushButton {{
    background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: 8px;
    padding: 7px 14px; font-weight: 500;
}}
QPushButton:hover {{ background: #33333A; }}
QPushButton:pressed {{ background: #26262C; }}
QPushButton:disabled {{ color: {FAINT}; background: {CARD}; border-color: {BORDER}; }}
QPushButton#Primary {{
    background: {ACCENT}; color: {ON_ACCENT}; border: none; font-weight: 600;
    padding: 9px 22px; border-radius: 9px; font-size: 14px;
}}
QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#Primary:pressed {{ background: {ACCENT_PRESS}; }}
QPushButton#Primary:disabled {{ background: #3A3326; color: #7D705A; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid transparent; color: {MUTED}; padding: 6px 10px; }}
QPushButton#Ghost:hover {{ background: {CARD_HOVER}; color: {TEXT}; }}
QPushButton#Danger {{ background: transparent; border: 1px solid {BORDER_STRONG}; color: {BAD}; }}
QPushButton#Danger:hover {{ background: #2A1A1D; }}

QToolButton#IconBtn {{ background: transparent; border: none; border-radius: 6px; padding: 4px; }}
QToolButton#IconBtn:hover {{ background: {RAISED}; }}

QComboBox, QLineEdit, QSpinBox {{
    background: {CARD}; border: 1px solid {BORDER_STRONG}; border-radius: 8px;
    padding: 6px 10px; selection-background-color: {ACCENT}; selection-color: {ON_ACCENT};
}}
QComboBox:hover, QLineEdit:hover {{ border-color: #4A4A54; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url(__CHEVRON__); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: 8px; padding: 4px;
    selection-background-color: {ACCENT}; selection-color: {ON_ACCENT};
}}

QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid #55555F; background: {CARD}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url(__CHECK__); }}
QCheckBox:disabled {{ color: {FAINT}; }}

QSlider::groove:horizontal {{ height: 4px; background: {RAISED}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}

QProgressBar {{ background: {RAISED}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QProgressBar#Done::chunk {{ background: {GOOD}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3A3A42; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #4A4A54; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}

#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
#Card:hover {{ background: {CARD_HOVER}; }}
#Card[state="active"] {{ border: 1px solid {ACCENT}; }}
#Card[state="failed"] {{ border: 1px solid #5A2A30; }}
#Thumb {{ background: #0C0C0E; border-radius: 8px; }}
#FileName {{ font-size: 14px; font-weight: 600; }}
#Meta {{ color: {MUTED}; font-size: 12px; }}
#OutName {{ color: {FAINT}; font-size: 12px; }}
#Status {{ font-size: 12px; font-weight: 600; }}

#Option {{ background: transparent; border: 1px solid transparent; border-radius: 10px; }}
#Option:hover {{ background: {CARD}; }}
#Option[selected="true"] {{ background: {CARD}; border: 1px solid {ACCENT}; }}
#Option[enabled="false"] {{ background: transparent; }}
#OptionTitle {{ font-weight: 600; font-size: 13px; }}
#OptionSub {{ color: {MUTED}; font-size: 12px; }}

#Seg {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 9px; }}
#SegBtn {{ background: transparent; border: none; border-radius: 7px; padding: 6px 10px; color: {MUTED}; font-weight: 500; }}
#SegBtn:hover {{ color: {TEXT}; }}
#SegBtn:checked {{ background: {RAISED}; color: {TEXT}; font-weight: 600; }}
#Tabs #SegBtn {{ padding: 7px 4px; }}

#Token {{ background: {CARD}; border: 1px solid {BORDER_STRONG}; border-radius: 6px; padding: 3px 7px; color: {MUTED}; font-size: 12px; font-weight: 500; }}
#Token:hover {{ color: {ON_ACCENT}; background: {ACCENT}; border-color: {ACCENT}; }}
#Preview {{ background: #0C0C0E; border: 1px solid {BORDER}; border-radius: 8px; padding: 8px 10px; color: {TEXT}; font-family: "Menlo", "Consolas", "DejaVu Sans Mono", monospace; font-size: 12px; }}

#DropZone {{ border: 2px dashed #3A3A42; border-radius: 18px; background: transparent; }}
#DropZone[hot="true"] {{ border-color: {ACCENT}; background: rgba(245,165,36,0.06); }}
#DropTitle {{ font-size: 20px; font-weight: 600; }}
#DropSub {{ color: {MUTED}; font-size: 13px; }}
#DropFormats {{ color: {FAINT}; font-size: 12px; }}

#Footer {{ background: {PANEL}; border-top: 1px solid {BORDER}; }}
#FooterTitle {{ font-weight: 600; font-size: 13px; }}
#Banner {{ background: rgba(76,195,138,0.10); border: 1px solid rgba(76,195,138,0.35); border-radius: 10px; }}
#BannerBad {{ background: rgba(240,97,109,0.10); border: 1px solid rgba(240,97,109,0.35); border-radius: 10px; }}
#DialogTitle {{ font-size: 18px; font-weight: 700; }}
#Example {{ background: #0C0C0E; border: 1px solid {BORDER}; border-radius: 10px; }}
#ExFrom {{ color: {MUTED}; font-size: 12px; }}
#ExTo {{ color: {TEXT}; font-size: 14px; font-weight: 600; }}
QPushButton#SaveBtn {{ background: transparent; border: 1px solid {BORDER_STRONG}; color: {MUTED}; font-weight: 500; padding: 8px 14px; }}
QPushButton#SaveBtn:hover {{ background: {CARD_HOVER}; color: {TEXT}; }}
#Toast {{ background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: 10px; padding: 9px 14px; }}

QDialog {{ background: {PANEL}; }}
QPlainTextEdit {{ background: #0C0C0E; border: 1px solid {BORDER}; border-radius: 8px; font-family: "Menlo", "Consolas", "DejaVu Sans Mono", monospace; font-size: 11px; color: {MUTED}; }}
QMenu {{ background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: {ACCENT}; color: {ON_ACCENT}; }}
"""

# Minimal line icons (Lucide-style, ISC licensed shapes redrawn).
_SVG = {
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "retry": '<path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/>',
    "reveal": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "film": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 7.5h4M3 12h18M3 16.5h4M17 7.5h4M17 16.5h4"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
    "audio": '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
    "drop": '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
    "pause": '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
    "play": '<path d="M6 4l14 8-14 8z"/>',
    "chevron": '<path d="m6 9 6 6 6-6"/>',
    "alert": '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
}


def svg_markup(name: str, color: str = TEXT, stroke: float = 2.0) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{_SVG[name]}</svg>'
    )


def pixmap(name: str, size: int = 16, color: str = TEXT, stroke: float = 2.0, dpr: float = 2.0) -> QPixmap:
    r = QSvgRenderer(QByteArray(svg_markup(name, color, stroke).encode()))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str = TEXT, size: int = 16) -> QIcon:
    return QIcon(pixmap(name, size, color))


def stylesheet(tmpdir: Path) -> str:
    """QSS can only reference image files, so write the couple it needs to a temp dir."""
    tmpdir.mkdir(parents=True, exist_ok=True)
    chevron = tmpdir / "chevron.svg"
    chevron.write_text(svg_markup("chevron", MUTED))
    check = tmpdir / "check.svg"
    check.write_text(svg_markup("check", ON_ACCENT, 3))
    return (
        STYLESHEET.replace("__CHEVRON__", chevron.as_posix())
        .replace("__CHECK__", check.as_posix())
    )
