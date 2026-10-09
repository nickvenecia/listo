"""Look and feel: colors, type, stylesheet and icons."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .tokens import (
    ACCENT,
    ACCENT_EDGE,
    ACCENT_HOVER,
    ACCENT_OFF,
    ACCENT_OFF_TEXT,
    ACCENT_PRESS,
    ACCENT_TINT,
    BAD,
    BAD_EDGE,
    BAD_TINT,
    BAR_H,
    BG,
    BORDER,
    BORDER_CHECK,
    BORDER_HOVER,
    BORDER_STRONG,
    CARD,
    CARD_HOVER,
    CARD_SELECTED,
    CONTROL_H,
    FAINT,
    GOOD,
    HANDLE,
    ICON,
    INDICATOR,
    MUTED,
    ON_ACCENT,
    PANEL,
    RADIUS,
    RADIUS_LG,
    RADIUS_SM,
    RADIUS_XL,
    RADIUS_XS,
    RAISED,
    RAISED_HOVER,
    RAISED_PRESS,
    SCROLL_MIN,
    SCROLL_W,
    SEG_INSET,
    SMALL_H,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    SPACE_4,
    SPACE_5,
    TEXT,
    TEXT_BRAND,
    TEXT_LG,
    TEXT_MD,
    TEXT_SM,
    TEXT_XL,
    TEXT_XS,
    TRACK_H,
    WARN,
    WEIGHT_BOLD,
    WEIGHT_MEDIUM,
    WEIGHT_SEMIBOLD,
    WELL,
)

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONT_FAMILY = "Inter"
MONO = '"Menlo", "Consolas", "DejaVu Sans Mono", monospace'

# A control's box = border (1px top + bottom) + content. Padding is horizontal only, so every
# button, dropdown and text field comes out exactly CONTROL_H tall.
_INNER = CONTROL_H - 2
_SMALL_INNER = SMALL_H - 2
_SEG_INNER = CONTROL_H - 2 - 2 * SEG_INSET  # segmented control: 1px border + inset


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
QWidget {{ color: {TEXT}; font-size: {TEXT_MD}px; }}
QMainWindow, #Root {{ background: {BG}; }}
QDialog {{ background: {PANEL}; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {BORDER_STRONG};
    padding: {SPACE_1}px {SPACE_2}px; border-radius: {RADIUS_SM}px; font-size: {TEXT_SM}px; }}

/* ---------- text styles */
#Wordmark {{ font-size: {TEXT_BRAND}px; font-weight: {WEIGHT_BOLD}; letter-spacing: -0.5px; }}
#DialogTitle {{ font-size: {TEXT_XL}px; font-weight: {WEIGHT_BOLD}; }}
#SectionLabel {{ color: {FAINT}; font-size: {TEXT_XS}px; font-weight: {WEIGHT_SEMIBOLD}; letter-spacing: 1px; }}
#Hint {{ color: {FAINT}; font-size: {TEXT_SM}px; }}
#Muted {{ color: {MUTED}; }}
#FileName, #FooterTitle {{ font-size: {TEXT_LG}px; font-weight: {WEIGHT_SEMIBOLD}; }}
#Meta {{ color: {MUTED}; font-size: {TEXT_SM}px; }}
#OutName {{ color: {FAINT}; font-size: {TEXT_SM}px; }}
#Status {{ font-size: {TEXT_SM}px; font-weight: {WEIGHT_SEMIBOLD}; color: {MUTED}; }}
#Status[tone="probing"] {{ color: {FAINT}; }}
#Status[tone="converting"], #Status[tone="downloading"] {{ color: {ACCENT}; }}
#Status[tone="paused"], #Status[tone="warning"] {{ color: {WARN}; }}
#Status[tone="done"] {{ color: {GOOD}; }}
#Status[tone="failed"], #Status[tone="unsupported"] {{ color: {BAD}; }}

/* ---------- areas */
#Sidebar {{ background: {PANEL}; border-left: 1px solid {BORDER}; }}
#Footer {{ background: {PANEL}; border-top: 1px solid {BORDER}; }}

/* ---------- buttons: all CONTROL_H tall */
QPushButton {{
    background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: {RADIUS}px;
    padding: 0 {SPACE_3}px; min-height: {_INNER}px; max-height: {_INNER}px; font-weight: {WEIGHT_MEDIUM};
}}
QPushButton:hover {{ background: {RAISED_HOVER}; }}
QPushButton:pressed {{ background: {RAISED_PRESS}; }}
QPushButton:disabled {{ color: {FAINT}; background: {CARD}; border-color: {BORDER}; }}
QPushButton#Primary {{ background: {ACCENT}; color: {ON_ACCENT}; border-color: {ACCENT};
    font-weight: {WEIGHT_SEMIBOLD}; padding: 0 {SPACE_4}px; }}
QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#Primary:pressed {{ background: {ACCENT_PRESS}; border-color: {ACCENT_PRESS}; }}
QPushButton#Primary:disabled {{ background: {ACCENT_OFF}; border-color: {ACCENT_OFF}; color: {ACCENT_OFF_TEXT}; }}
QPushButton#Ghost {{ background: transparent; border-color: transparent; color: {MUTED}; }}
QPushButton#Ghost:hover {{ background: {CARD_HOVER}; color: {TEXT}; }}
QPushButton#Secondary {{ background: transparent; color: {MUTED}; }}
QPushButton#Secondary:hover {{ background: {CARD_HOVER}; color: {TEXT}; }}
QPushButton#Danger {{ background: transparent; color: {BAD}; }}
QPushButton#Danger:hover {{ background: {BAD_TINT}; }}
QPushButton::menu-indicator, QToolButton::menu-indicator {{ image: none; width: 0; }}

/* ---------- small controls: all SMALL_H tall */
QToolButton#IconBtn {{ background: transparent; border: none; border-radius: {RADIUS_SM}px;
    min-width: {SMALL_H}px; max-width: {SMALL_H}px; min-height: {SMALL_H}px; max-height: {SMALL_H}px; }}
QToolButton#IconBtn:hover {{ background: {RAISED}; }}
QPushButton#Chip, QPushButton#Token {{ border-radius: {RADIUS_SM}px; padding: 0 {SPACE_2}px;
    min-height: {_SMALL_INNER}px; max-height: {_SMALL_INNER}px; font-size: {TEXT_XS}px; font-weight: {WEIGHT_SEMIBOLD};
    color: {MUTED}; }}
QPushButton#Chip {{ background: {RAISED}; border: 1px solid {BORDER_STRONG}; }}
QPushButton#Chip:hover {{ color: {TEXT}; border-color: {BORDER_HOVER}; }}
QPushButton#Chip[custom="true"] {{ color: {ACCENT}; border-color: {ACCENT_EDGE}; background: {ACCENT_TINT}; }}
QPushButton#Chip:disabled {{ background: transparent; border-color: {BORDER}; color: {FAINT}; }}
QPushButton#Token {{ background: {CARD}; border: 1px solid {BORDER_STRONG}; }}
QPushButton#Token:hover {{ color: {ON_ACCENT}; background: {ACCENT}; border-color: {ACCENT}; }}
#TrimTag {{ color: {ACCENT}; font-size: {TEXT_XS}px; font-weight: {WEIGHT_SEMIBOLD}; }}

/* ---------- fields + dropdowns: all CONTROL_H tall */
QComboBox, QLineEdit {{
    background: {CARD}; border: 1px solid {BORDER_STRONG}; border-radius: {RADIUS}px;
    padding: 0 {SPACE_3}px; min-height: {_INNER}px; max-height: {_INNER}px;
    selection-background-color: {ACCENT}; selection-color: {ON_ACCENT};
}}
QComboBox:hover, QLineEdit:hover {{ border-color: {BORDER_HOVER}; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: {SPACE_5}px; }}
QComboBox::down-arrow {{ image: url(__CHEVRON__); width: {SPACE_3}px; height: {SPACE_3}px; }}
QComboBox QAbstractItemView {{
    background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: {RADIUS_LG}px; padding: {SPACE_1}px;
    selection-background-color: {ACCENT}; selection-color: {ON_ACCENT}; outline: none;
}}
QComboBox QAbstractItemView::item {{ padding: 0 {SPACE_3}px; min-height: {CONTROL_H - SPACE_2}px; border-radius: {RADIUS_SM}px; }}
QComboBox QAbstractItemView::item:selected {{ background: {ACCENT}; color: {ON_ACCENT}; }}
QComboBox QAbstractItemView::separator {{ height: 1px; background: {BORDER_STRONG}; margin: {SPACE_1}px {SPACE_2}px; }}

/* ---------- segmented control: CONTROL_H tall overall */
#Seg {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}
#SegBtn {{ background: transparent; border: none; border-radius: {RADIUS_SM}px; padding: 0 {SPACE_2}px;
    min-height: {_SEG_INNER}px; max-height: {_SEG_INNER}px; color: {MUTED}; font-weight: {WEIGHT_MEDIUM}; }}
#SegBtn:hover {{ color: {TEXT}; }}
#SegBtn:checked {{ background: {RAISED}; color: {TEXT}; font-weight: {WEIGHT_SEMIBOLD}; }}

/* ---------- checkboxes, sliders, progress */
QCheckBox {{ spacing: {SPACE_2}px; min-height: {SMALL_H}px; }}
QCheckBox::indicator {{ width: {INDICATOR}px; height: {INDICATOR}px; border-radius: {RADIUS_XS}px; border: 1px solid {BORDER_CHECK}; background: {CARD}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url(__CHECK__); }}
QCheckBox:disabled {{ color: {FAINT}; }}
QSlider {{ min-height: {SMALL_H}px; }}
QSlider::groove:horizontal {{ height: {TRACK_H}px; background: {RAISED}; border-radius: {TRACK_H // 2}px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: {TRACK_H // 2}px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: {HANDLE}px; height: {HANDLE}px; margin: -{(HANDLE - TRACK_H) // 2}px 0; border-radius: {HANDLE // 2}px; }}
QProgressBar {{ background: {RAISED}; border: none; border-radius: {BAR_H // 2}px; max-height: {BAR_H}px; min-height: {BAR_H}px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: {BAR_H // 2}px; }}
QProgressBar#Done::chunk {{ background: {GOOD}; }}
QProgressBar#Warn::chunk {{ background: {WARN}; }}

/* ---------- scrolling */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: {SCROLL_W}px; margin: {SEG_INSET}px; }}
QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border-radius: {(SCROLL_W - 2 * SEG_INSET) // 2}px; min-height: {SCROLL_MIN}px; }}
QScrollBar::handle:vertical:hover {{ background: {BORDER_HOVER}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}

/* ---------- file cards */
#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: {RADIUS_LG}px; }}
#Card:hover {{ background: {CARD_HOVER}; }}
#Card[state="active"] {{ border-color: {ACCENT}; }}
#Card[state="failed"] {{ border-color: {BAD_EDGE}; }}
#Card[selected="true"], #Card[selected="true"]:hover {{ background: {CARD_SELECTED}; border-color: {ACCENT_EDGE}; }}
#Thumb, #TrimPreview {{ background: {WELL}; border-radius: {RADIUS}px; }}
#TrimPreview {{ border: 1px solid {BORDER}; }}

/* ---------- option list (export dialog) */

/* ---------- drop zone + link box */
#DropZone {{ border: 2px dashed {BORDER_STRONG}; border-radius: {RADIUS_XL}px; background: transparent; }}
#DropZone[hot="true"] {{ border-color: {ACCENT}; background: {ACCENT_TINT}; }}
#DropTitle {{ font-size: {TEXT_XL}px; font-weight: {WEIGHT_SEMIBOLD}; }}
#DropSub {{ color: {MUTED}; }}
#DropFormats {{ color: {FAINT}; font-size: {TEXT_SM}px; }}

/* ---------- export dialog */
#Example, #Preview {{ background: {WELL}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}
#ExFrom {{ color: {MUTED}; font-size: {TEXT_SM}px; }}
#ExTo {{ font-size: {TEXT_LG}px; font-weight: {WEIGHT_SEMIBOLD}; }}

/* ---------- popups, logs, toasts */
#Toast {{ background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: {RADIUS_LG}px; padding: {SPACE_2}px {SPACE_4}px; }}
QPlainTextEdit {{ background: {WELL}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; font-family: {MONO};
    font-size: {TEXT_XS}px; color: {MUTED}; }}
QMenu {{ background: {RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: {RADIUS_LG}px; padding: {SPACE_1}px; }}
QMenu::item {{ padding: 0 {SPACE_4}px 0 {SPACE_2}px; min-height: {CONTROL_H - SPACE_2}px; border-radius: {RADIUS_SM}px; }}
QMenu::item:selected {{ background: {ACCENT}; color: {ON_ACCENT}; }}
QMenu::item:disabled {{ color: {FAINT}; }}
QMenu::icon {{ padding-left: {SPACE_2}px; }}
QMenu::separator {{ height: 1px; background: {BORDER_STRONG}; margin: {SPACE_1}px {SPACE_2}px; }}
QMenu::section {{ color: {FAINT}; padding: {SPACE_2}px {SPACE_2}px 0 {SPACE_2}px; font-size: {TEXT_XS}px; font-weight: {WEIGHT_SEMIBOLD}; }}
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
    "scissors": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.12 15.88M14.47 14.48 20 20M8.12 8.12 12 12"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "trash": '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/>',
    "export": '<path d="M12 15V3"/><path d="m7 8 5-5 5 5"/><path d="M20 14v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-5"/>',
    "alert": '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
}


def svg_markup(name: str, color: str = TEXT, stroke: float = 2.0) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{_SVG[name]}</svg>'
    )


def pixmap(name: str, size: int = ICON, color: str = TEXT, stroke: float = 2.0, dpr: float = 2.0) -> QPixmap:
    r = QSvgRenderer(QByteArray(svg_markup(name, color, stroke).encode()))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str = TEXT, size: int = ICON) -> QIcon:
    ic = QIcon(pixmap(name, size, color))
    # menus draw the highlighted row in marigold: switch the icon to dark there
    ic.addPixmap(pixmap(name, size, ON_ACCENT), QIcon.Mode.Active)
    ic.addPixmap(pixmap(name, size, ON_ACCENT), QIcon.Mode.Selected)
    return ic


def stylesheet(folder: Path) -> str:
    """QSS can only reference image files, so write the couple it needs into `folder`
    (Listo's per-user data folder, overwritten each launch)."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:  # data folder not writable: fall back to a private temp folder
        import tempfile

        folder = Path(tempfile.mkdtemp(prefix="listo-ui-"))
    chevron = folder / "chevron.svg"
    chevron.write_text(svg_markup("chevron", MUTED))
    check = folder / "check.svg"
    check.write_text(svg_markup("check", ON_ACCENT, 3))
    return STYLESHEET.replace("__CHEVRON__", chevron.as_posix()).replace("__CHECK__", check.as_posix())
