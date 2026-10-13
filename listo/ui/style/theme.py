"""Look and feel: colors, type, stylesheet and icons."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QIconEngine, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from listo.core.paths import ASSETS
from listo.ui.style import tokens
from listo.ui.style.tokens import (
    AVATAR,
    BAR_H,
    CONTROL_H,
    HANDLE,
    ICON,
    ICON_STROKE,
    INDICATOR,
    RADIUS,
    RADIUS_LG,
    RADIUS_SM,
    RADIUS_XS,
    SCROLL_INSET,
    SCROLL_MIN,
    SCROLL_W,
    SEG_INSET,
    SMALL_H,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    SPACE_4,
    TEXT_BRAND,
    TEXT_LG,
    TEXT_MD,
    TEXT_SM,
    TEXT_TITLE,
    TEXT_TITLEBAR,
    TEXT_XL,
    TEXT_XS,
    TRACK_BRAND,
    TRACK_H,
    TRACK_TITLE,
    TRACK_TITLEBAR,
    WEIGHT_BOLD,
    WEIGHT_MEDIUM,
    WEIGHT_REGULAR,
    WEIGHT_SEMIBOLD,
)

FONT_FAMILY = "Inter"  # everything
MONO_FAMILY = "IBM Plex Mono"  # only for codes: logs, commands, checksums

# A control's box = border (1px top + bottom) + content. Padding is horizontal only, so every
# button, dropdown and text field comes out exactly CONTROL_H tall.
_INNER = CONTROL_H - 2
_SMALL_INNER = SMALL_H - 2
_SEG_INNER = CONTROL_H - 2 - 2 * SEG_INSET  # segmented control: 1px border + inset


def _load_colors() -> None:
    """Copy the current color tokens here (theme.MUTED etc.), for the stylesheet and icons."""
    globals().update({k: getattr(tokens, k) for k in tokens.COLORS})


_load_colors()


def load_fonts() -> str:
    """Register the bundled UI fonts (Inter, IBM Plex Mono) once. Returns the app's family, or "" if missing."""
    from PySide6.QtGui import QFontDatabase

    found: set[str] = set()
    for f in sorted((ASSETS / "fonts").glob("*")):
        if f.suffix.lower() in (".ttf", ".otf") and not f.name.startswith("VCR"):  # (VCR: burned into video)
            fid = QFontDatabase.addApplicationFont(str(f))
            if fid >= 0:
                found.update(QFontDatabase.applicationFontFamilies(fid))
    return FONT_FAMILY if FONT_FAMILY in found else ""


def _sheet() -> str:
    """The app stylesheet in the current colors."""
    return f"""
* {{ outline: none; }}
QWidget {{ color: {tokens.TEXT}; font-size: {TEXT_MD}px; }}
QMainWindow, #Root {{ background: {tokens.BG}; }}
*[glass="true"] {{ background: transparent; border: none; }}
QDialog {{ background: {tokens.PANEL}; }}
QToolTip {{ background: {tokens.RAISED}; color: {tokens.TEXT}; border: 1px solid {tokens.BORDER_STRONG};
    padding: {SPACE_1}px {SPACE_2}px; border-radius: {RADIUS_SM}px; font-size: {TEXT_SM}px; }}

/* ---------- text styles */
#Wordmark {{ font-size: {TEXT_BRAND}px; font-weight: {WEIGHT_BOLD}; letter-spacing: {TRACK_BRAND}px; }}
#TitleBar {{ background: transparent; border: none; }}
#TitleWordmark {{ font-size: {TEXT_TITLEBAR}px; font-weight: {WEIGHT_BOLD}; letter-spacing: {TRACK_TITLEBAR}px; }}
#DialogTitle {{ font-size: {TEXT_XL}px; font-weight: {WEIGHT_BOLD}; }}
#SectionLabel {{ color: {tokens.MUTED}; font-size: {TEXT_SM}px; font-weight: {WEIGHT_SEMIBOLD}; }}
#Hint {{ color: {tokens.FAINT}; font-size: {TEXT_SM}px; }}
#Muted {{ color: {tokens.MUTED}; }}

/* ---------- areas */
#PanelHeader {{ border: none; }}
#PanelTitle {{ font-size: {TEXT_LG}px; font-weight: {WEIGHT_SEMIBOLD}; }}

/* ---------- buttons: capsules, all CONTROL_H tall */
QPushButton {{
    background: {tokens.RAISED}; border: 1px solid {tokens.BORDER_STRONG}; border-radius: {_INNER // 2}px;
    padding: 0 {SPACE_4}px; min-height: {_INNER}px; max-height: {_INNER}px; font-weight: {WEIGHT_MEDIUM};
}}
QPushButton:hover {{ background: {tokens.RAISED_HOVER}; }}
QPushButton:pressed {{ background: {tokens.RAISED_PRESS}; }}
QPushButton:disabled {{ color: {tokens.FAINT}; background: {tokens.CARD}; border-color: {tokens.BORDER}; }}
QPushButton#Primary {{ background: {tokens.ACCENT}; color: {tokens.ON_ACCENT}; border-color: {tokens.ACCENT};
    font-weight: {WEIGHT_SEMIBOLD}; padding: 0 {SPACE_4}px; }}
QPushButton#Primary:hover {{ background: {tokens.ACCENT_HOVER}; border-color: {tokens.ACCENT_HOVER}; }}
QPushButton#Primary:pressed {{ background: {tokens.ACCENT_PRESS}; border-color: {tokens.ACCENT_PRESS}; }}
QPushButton#Primary:disabled {{ background: {tokens.ACCENT_OFF}; border-color: {tokens.ACCENT_OFF}; color: {tokens.ACCENT_OFF_TEXT}; }}
QPushButton#Ghost {{ background: transparent; border-color: transparent; color: {tokens.MUTED}; }}
QPushButton#Ghost:hover {{ background: {tokens.CARD_HOVER}; color: {tokens.TEXT}; }}
QToolButton#SectionAdd {{ background: transparent; border: none; border-radius: {tokens.SECTION_ADD // 2}px;
    min-width: {tokens.SECTION_ADD}px; max-width: {tokens.SECTION_ADD}px;
    min-height: {tokens.SECTION_ADD}px; max-height: {tokens.SECTION_ADD}px; }}
QToolButton#SectionAdd:hover {{ background: {tokens.CARD_HOVER}; }}
*[capsule="true"] {{ border-radius: {_INNER // 2}px; padding-left: {SPACE_4}px; }}
QPushButton#Disclosure {{ background: transparent; border: none; border-radius: 0; padding: 0; text-align: left;
    color: {tokens.MUTED}; font-size: {TEXT_SM}px; font-weight: {WEIGHT_SEMIBOLD}; min-height: {SMALL_H}px; max-height: {SMALL_H}px; }}
QPushButton#Disclosure:hover {{ color: {tokens.TEXT}; background: transparent; }}
QPushButton#Danger {{ color: {tokens.BAD}; }}
QPushButton#Danger:hover {{ background: {tokens.BAD_TINT}; border-color: {tokens.BAD_EDGE}; }}
QPushButton::menu-indicator, QToolButton::menu-indicator {{ image: none; width: 0; }}
QPushButton#Token {{ border-radius: {_SMALL_INNER // 2}px; padding: 0 {SPACE_2}px; min-height: {_SMALL_INNER}px;
    max-height: {_SMALL_INNER}px; font-size: {TEXT_SM}px; background: {tokens.FILL}; border: 1px solid {tokens.FIELD_BORDER}; }}
QPushButton#Token:hover {{ color: {tokens.ON_ACCENT}; background: {tokens.ACCENT}; border-color: {tokens.ACCENT}; }}

/* ---------- round icon buttons */
QToolButton#IconBtn {{ background: transparent; border: none; border-radius: {SMALL_H // 2}px;
    min-width: {SMALL_H}px; max-width: {SMALL_H}px; min-height: {SMALL_H}px; max-height: {SMALL_H}px; }}
QToolButton#IconBtn:hover {{ background: {tokens.RAISED}; }}
QToolButton#Circle, QToolButton#CirclePrimary {{ border-radius: {_INNER // 2}px; min-width: {_INNER}px; max-width: {_INNER}px;
    min-height: {_INNER}px; max-height: {_INNER}px; }}
QToolButton#Circle {{ background: {tokens.RAISED}; border: 1px solid {tokens.BORDER_STRONG}; }}
QToolButton#Circle:hover {{ background: {tokens.RAISED_HOVER}; }}
QToolButton#CirclePrimary {{ background: {tokens.ACCENT}; border: 1px solid {tokens.ACCENT}; }}
QToolButton#CirclePrimary:hover {{ background: {tokens.ACCENT_HOVER}; border-color: {tokens.ACCENT_HOVER}; }}
QToolButton#CirclePrimary:pressed {{ background: {tokens.ACCENT_PRESS}; }}
#Alert {{ background: {tokens.RAISED}; border: 1px solid {tokens.BORDER_STRONG}; border-radius: {RADIUS_LG}px; }}
#AlertTitle {{ font-size: {TEXT_LG}px; font-weight: {WEIGHT_SEMIBOLD}; }}
QPushButton#DangerFill {{ background: {tokens.BAD}; border: 1px solid {tokens.BAD}; color: {tokens.ON_BAD}; font-weight: {WEIGHT_SEMIBOLD}; }}
QPushButton#DangerFill:hover {{ background: {tokens.BAD}; border-color: {tokens.BAD}; }}
#KeyCap {{ background: {tokens.CHIP}; color: {tokens.MUTED}; border-radius: {RADIUS_SM}px; padding: 2px {SPACE_2}px;
    font-weight: {WEIGHT_MEDIUM}; }}

/* ---------- fields + dropdowns: all CONTROL_H tall */
QComboBox {{ combobox-popup: 0; }}
QComboBox, QLineEdit {{
    background: {tokens.FIELD}; border: 1px solid {tokens.FIELD_BORDER}; border-radius: {RADIUS}px;
    padding: 0 {SPACE_3}px; min-height: {_INNER}px; max-height: {_INNER}px;
    selection-background-color: {tokens.ACCENT}; selection-color: {tokens.ON_ACCENT};
}}
QComboBox:hover, QLineEdit:hover {{ border-color: {tokens.BORDER_HOVER}; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {tokens.ACCENT}; }}
QComboBox::drop-down {{ border: none; width: {tokens.SPACE_5}px; }}
QComboBox::down-arrow {{ image: url(__CHEVRON__); width: {SPACE_3}px; height: {SPACE_3}px; }}
QComboBoxPrivateContainer {{ background: transparent; border: none; }}
QComboBox QAbstractItemView {{
    background: {tokens.RAISED}; border: 1px solid {tokens.BORDER_STRONG}; border-radius: {tokens.LIST_R}px;
    padding: {tokens.LIST_INSET - 1}px; outline: none;
    selection-background-color: {tokens.ACCENT_TINT}; selection-color: {tokens.ACCENT_HOVER};
}}
QComboBox QAbstractItemView::item {{
    padding: 0 {SPACE_2}px; min-height: {tokens.LIST_ROW_H}px; border-radius: {tokens.LIST_ROW_R}px;
    margin: {tokens.LIST_GAP // 2}px 0;
}}
QComboBox QAbstractItemView::item:hover {{ background: {tokens.CARD_HOVER}; }}
QComboBox QAbstractItemView::item:selected {{ background: {tokens.ACCENT_TINT}; color: {tokens.ACCENT_HOVER}; }}
QComboBox QAbstractItemView::separator {{ height: 1px; background: {tokens.BORDER_STRONG}; margin: {SPACE_1}px {SPACE_2}px; }}

/* ---------- segmented control: CONTROL_H tall overall */
#Seg {{ background: {tokens.FILL}; border: 1px solid {tokens.FIELD_BORDER}; border-radius: {RADIUS}px; }}
#SegBtn {{ background: transparent; border: none; border-radius: {RADIUS_SM}px; padding: 0 {SPACE_2}px;
    min-height: {_SEG_INNER}px; max-height: {_SEG_INNER}px; color: {tokens.MUTED}; font-weight: {WEIGHT_MEDIUM}; }}
#SegBtn:hover {{ color: {tokens.TEXT}; }}
#SegBtn:checked {{ background: {tokens.RAISED}; border: 1px solid {tokens.FIELD_BORDER}; color: {tokens.TEXT}; font-weight: {WEIGHT_SEMIBOLD}; }}

/* ---------- checkboxes, sliders, progress */
QCheckBox {{ spacing: {SPACE_2}px; min-height: {SMALL_H}px; }}
QCheckBox::indicator {{ width: {INDICATOR}px; height: {INDICATOR}px; border-radius: {RADIUS_XS}px; border: 1px solid {tokens.BORDER_CHECK}; background: {tokens.CARD}; }}
QCheckBox::indicator:checked {{ background: {tokens.ACCENT}; border-color: {tokens.ACCENT}; image: url(__CHECK__); }}
QCheckBox:disabled {{ color: {tokens.FAINT}; }}
QSlider {{ min-height: {SMALL_H}px; }}
QSlider::groove:horizontal {{ height: {TRACK_H}px; background: {tokens.RAISED}; border-radius: {TRACK_H // 2}px; }}
QSlider::sub-page:horizontal {{ background: {tokens.ACCENT}; border-radius: {TRACK_H // 2}px; }}
QSlider::handle:horizontal {{ background: {tokens.TEXT}; width: {HANDLE}px; height: {HANDLE}px; margin: -{(HANDLE - TRACK_H) // 2}px 0; border-radius: {HANDLE // 2}px; }}
QProgressBar {{ background: {tokens.FILL}; border: none; border-radius: {BAR_H // 2}px; max-height: {BAR_H}px; min-height: {BAR_H}px; }}
QProgressBar::chunk {{ background: {tokens.ACCENT}; border-radius: {BAR_H // 2}px; }}

/* ---------- scrolling */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: {SCROLL_W}px; margin: {SCROLL_INSET}px; }}
QScrollBar::handle:vertical {{ background: {tokens.BORDER_STRONG}; border-radius: {(SCROLL_W - 2 * SCROLL_INSET) // 2}px; min-height: {SCROLL_MIN}px; }}
QScrollBar::handle:vertical:hover {{ background: {tokens.BORDER_HOVER}; }}
QScrollBar:vertical:disabled, QScrollBar::handle:vertical:disabled {{ background: transparent; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}

/* ---------- status words and chips: the color comes from the tone */

/* ---------- cards in a panel */
#CardTitle {{ color: {tokens.MUTED}; font-size: {TEXT_SM}px; font-weight: {WEIGHT_SEMIBOLD}; }}
#Card {{ background: {tokens.BLOCK}; border: none; border-radius: {RADIUS_LG}px; }}
#Totals {{ background: transparent; border-top: 1px solid {tokens.BORDER}; }}
#TotalLabel {{ color: {tokens.MUTED}; font-size: {TEXT_SM}px; }}
#TotalValue {{ font-size: {TEXT_LG}px; font-weight: {WEIGHT_SEMIBOLD}; }}

/* ---------- the window: sidebar, toolbar, the file list */
#Sidebar {{ background: transparent; border: none; }}
#SidebarFoot {{ border: none; }}
#ProfileCard {{ background: transparent; border-radius: {tokens.NAV_R}px; }}
#ProfileCard:hover {{ background: {tokens.CARD_HOVER}; }}
#Avatar {{ background: {tokens.ACCENT_TINT}; color: {tokens.ACCENT}; border-radius: {AVATAR // 2}px;
    font-size: {TEXT_SM}px; font-weight: {WEIGHT_SEMIBOLD}; }}
#ProfileName {{ font-weight: {WEIGHT_SEMIBOLD}; }}
#Nav {{ background: transparent; border-radius: {tokens.NAV_R}px; }}
#Nav:hover {{ background: {tokens.CARD_HOVER}; }}
#Nav[selected="true"] {{ background: {tokens.ACCENT_TINT}; }}
#NavLabel {{ color: {tokens.TEXT}; font-weight: {WEIGHT_MEDIUM}; }}
#NavHead {{ background: transparent; }}
#NavHead:hover #SectionLabel {{ color: {tokens.TEXT}; }}
#Nav[selected="true"] #NavLabel {{ color: {tokens.ACCENT_HOVER}; }}
#NavCount {{ color: {tokens.FAINT}; font-size: {TEXT_SM}px; }}
#NavCount[tone="converting"] {{ color: {tokens.ACCENT}; font-weight: {WEIGHT_SEMIBOLD}; }}
#NavCount[tone="failed"] {{ color: {tokens.BAD}; font-weight: {WEIGHT_SEMIBOLD}; }}
#Toolbar {{ border: none; }}
#PageTitle {{ font-size: {TEXT_TITLE}px; font-weight: {WEIGHT_BOLD}; letter-spacing: {TRACK_TITLE}px; }}
#PageCount {{ color: {tokens.FAINT}; font-size: {TEXT_LG}px; }}
#Center {{ background: transparent; }}
QListView#FileList {{ background: transparent; border: none; outline: none; }}

/* ---------- empty states */
#EmptyText {{ color: {tokens.MUTED}; }}
#StartBadge {{ background: {tokens.ACCENT_TINT}; border: none; border-radius: {tokens.START_BADGE // 2}px; }}
#StartTile {{ background: {tokens.RAISED}; border: 1px solid {tokens.BORDER}; border-radius: {RADIUS_LG}px; }}
#StartTile:hover {{ background: {tokens.RAISED_HOVER}; border-color: {tokens.BORDER_HOVER}; }}
#StartTile:focus, #StartTile[hot="true"] {{ border-color: {tokens.ACCENT}; }}
#StartTile[hot="true"] {{ background: {tokens.ACCENT_TINT}; }}
#StartTitle {{ font-size: {TEXT_LG}px; font-weight: {WEIGHT_SEMIBOLD}; }}
#StartDetail {{ color: {tokens.MUTED}; font-size: {TEXT_SM}px; }}

/* ---------- the right panel */
#Details {{ background: transparent; border: none; }}
#Example {{ background: {tokens.BLOCK}; border: none; border-radius: {RADIUS_LG}px; }}
#ExFrom {{ color: {tokens.MUTED}; font-size: {TEXT_SM}px; }}
#ExTo {{ font-size: {TEXT_LG}px; font-weight: {WEIGHT_SEMIBOLD}; }}

/* ---------- pictures sit on black in both looks, like a monitor */
#TrimPreview {{ background: {tokens.SCREEN}; border-radius: {RADIUS}px; }}
#Player {{ background: {tokens.SCREEN}; border-radius: {RADIUS}px; }}

/* ---------- Check the Captions */
QPlainTextEdit#CaptionText {{ background: {tokens.FIELD}; border: 1px solid {tokens.FIELD_BORDER}; border-radius: {RADIUS}px;
    font-family: inherit; font-size: {TEXT_MD}px; padding: {SPACE_1}px {SPACE_2}px; }}
QPlainTextEdit#CaptionText:focus {{ border-color: {tokens.ACCENT}; }}
QPlainTextEdit#CaptionText[current="true"] {{ background: {tokens.CARD_SELECTED}; border-color: {tokens.ACCENT_EDGE}; }}
QPlainTextEdit#CaptionText[current="true"]:focus {{ border-color: {tokens.ACCENT}; }}
#CueTime {{ color: {tokens.MUTED}; padding-top: {SPACE_1}px; }}
#CueTime:hover {{ color: {tokens.TEXT}; }}
#CueTime[current="true"] {{ color: {tokens.ACCENT}; font-weight: {WEIGHT_SEMIBOLD}; }}

/* ---------- popups, logs */
QTextBrowser#WhatsNew {{ background: {tokens.FILL}; color: {tokens.TEXT}; border: none; border-radius: {RADIUS_LG}px; }}
QPlainTextEdit#Field {{ background: {tokens.FIELD}; border: 1px solid {tokens.FIELD_BORDER}; border-radius: {RADIUS}px;
    padding: {SPACE_1}px {SPACE_2}px; color: {tokens.TEXT}; font-size: {TEXT_MD}px; font-family: "{FONT_FAMILY}"; }}
QPlainTextEdit#Field:hover {{ border-color: {tokens.BORDER_HOVER}; }}
QPlainTextEdit#Field:focus {{ border-color: {tokens.ACCENT}; }}
QPlainTextEdit {{ background: {tokens.WELL}; border: 1px solid {tokens.BORDER}; border-radius: {RADIUS}px;
    font-family: "{MONO_FAMILY}"; font-size: {TEXT_XS}px; color: {tokens.MUTED}; }}
QMenu {{ background: {tokens.RAISED}; border: 1px solid {tokens.BORDER_STRONG}; border-radius: {tokens.LIST_R}px;
    padding: {tokens.LIST_INSET - 1}px; }}
QMenu::item {{ padding: 0 {SPACE_4}px 0 {SPACE_2}px; min-height: {tokens.LIST_ROW_H}px; border-radius: {tokens.LIST_ROW_R}px;
    margin: {tokens.LIST_GAP // 2}px 0; }}
QMenu::item:selected {{ background: {tokens.ACCENT_TINT}; color: {tokens.ACCENT_HOVER}; }}
QMenu::item:disabled {{ color: {tokens.FAINT}; }}
QMenu::icon {{ padding-left: {SPACE_2}px; }}
QMenu::separator {{ height: 1px; background: {tokens.BORDER_STRONG}; margin: {SPACE_1}px {SPACE_2}px; }}
QMenu::section {{ color: {tokens.FAINT}; padding: {SPACE_2}px {SPACE_2}px 0 {SPACE_2}px; font-size: {TEXT_XS}px; font-weight: {WEIGHT_SEMIBOLD}; }}
"""


# Line icons on a 24×24 grid, stroke 2, round caps and joins (original drawings, no company's marks).
_SVG = {
    "alert": '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
    "arrow-down": '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
    "audio": '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "box": '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
    "captions": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 10.5a2 2 0 1 0 0 3M16 10.5a2 2 0 1 0 0 3"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "chevron": '<path d="m6 9 6 6 6-6"/>',
    "chevron-left": '<path d="m15 6-6 6 6 6"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "cog": '<circle cx="12" cy="12" r="2.6"/><circle cx="12" cy="12" r="6.2"/><path d="M12 2.6v3.2M12 18.2v3.2M2.6 12h3.2M18.2 12h3.2M5.4 5.4l2.2 2.2M16.4 16.4l2.2 2.2M5.4 18.6l2.2-2.2M16.4 7.6l2.2-2.2"/>',
    "copy": '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',
    "edit": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    "eye": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
    "film": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 7.5h4M3 12h18M3 16.5h4M17 7.5h4M17 16.5h4"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/>',
    "keyboard": '<rect x="2.5" y="6" width="19" height="12" rx="2.5"/><path d="M6.5 10h.01M10 10h.01M14 10h.01M17.5 10h.01M8 14h8"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "list-x": '<path d="M11 12H3M16 6H3M16 18H3"/><path d="m15 10 4 4M19 10l-4 4"/>',
    "message": '<path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "pause": '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
    "play": '<path d="M6 4l14 8-14 8z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "retry": '<path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/>',
    "reveal": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "scissors": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.12 15.88M14.47 14.48 20 20M8.12 8.12 12 12"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "share": '<path d="M12 3.5v10"/><path d="m8 7.5 4-4 4 4"/><path d="M6 11.5H5.5A1.5 1.5 0 0 0 4 13v5.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V13a1.5 1.5 0 0 0-1.5-1.5H18"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "updown": '<path d="m8 9 4-4 4 4M8 15l4 4 4-4"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M5 21v-1a6 6 0 0 1 6-6h2a6 6 0 0 1 6 6v1"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
}


def svg_markup(name: str, color: str = "", stroke: float = ICON_STROKE) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color or tokens.TEXT}" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
        + _SVG[name].replace("{fill}", color or tokens.TEXT).replace("{on}", tokens.ON_ACCENT)
        + "</svg>"
    )


@lru_cache(maxsize=512)
def pixmap(
    name: str, size: int = ICON, color: str = "", stroke: float = ICON_STROKE, dpr: float = 2.0
) -> QPixmap:
    """Drawn once per look and reused (a long list redraws the same few icons thousands of times).
    A QLabel keeps the picture it got, so a label's icon uses a color that's the same in both looks."""
    r = QSvgRenderer(QByteArray(svg_markup(name, color, stroke).encode()))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


# icons are asked for by color value (theme.MUTED); remember which token that was, so they follow a switch
_ICON_TOKENS = (
    "TEXT", "MUTED", "FAINT", "ACCENT", "ON_ACCENT", "BAD", "WARN", "GOOD", "ACCENT_HOVER", "SCREEN_TEXT",
    "SCREEN_FAINT",
)  # fmt: skip


def _token_of(color: str) -> str:
    for k in _ICON_TOKENS:
        if getattr(tokens, k) == color:
            return k
    return ""


class _Themed(QIconEngine):
    """Draws the icon in the current colors every time, so it follows light, dark and the accent."""

    def __init__(self, name: str, key: str, color: str, size: int, menu: bool):
        super().__init__()
        self.name, self.key, self.color, self.size, self.menu = name, key, color, size, menu

    def _color(self, mode) -> str:
        if self.menu and mode in (QIcon.Mode.Active, QIcon.Mode.Selected):
            return tokens.ACCENT_HOVER
        if mode == QIcon.Mode.Disabled:
            return tokens.FAINT
        return getattr(tokens, self.key) if self.key else self.color

    def pixmap(self, size, mode, state):
        return pixmap(self.name, self.size, self._color(mode))

    def paint(self, painter, rect, mode, state):
        painter.drawPixmap(rect, pixmap(self.name, self.size, self._color(mode)))

    def clone(self):
        return _Themed(self.name, self.key, self.color, self.size, self.menu)


def icon(name: str, color: str = "", size: int = ICON) -> QIcon:
    """An icon that looks the same however the button is hovered, focused or pressed, and follows the look."""
    color = color or tokens.TEXT
    return QIcon(_Themed(name, _token_of(color), color, size, False))


def menu_icon(name: str, color: str = "", size: int = ICON) -> QIcon:
    """For menu rows: on the highlighted row (the accent's tint) the icon takes the accent, like its words."""
    color = color or tokens.MUTED
    return QIcon(_Themed(name, _token_of(color), color, size, True))


def stylesheet(folder: Path) -> str:
    """QSS can only reference image files, so write the couple it needs into `folder`
    (Listo's per-user data folder, overwritten each launch), one set per look."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:  # data folder not writable: fall back to a private temp folder
        import tempfile

        folder = Path(tempfile.mkdtemp(prefix="listo-ui-"))
    look = f"{tokens.SCHEME}-{tokens.ACCENT_KEY}"  # Qt keeps images it loaded by their path
    chevron = folder / f"chevron-{look}.svg"
    chevron.write_text(svg_markup("chevron", tokens.MUTED))
    check = folder / f"check-{look}.svg"
    check.write_text(svg_markup("check", tokens.ON_ACCENT, 3))
    return _sheet().replace("__CHEVRON__", chevron.as_posix()).replace("__CHECK__", check.as_posix())


def wordmark() -> str:
    """The "listo." wordmark as rich text, the dot in the accent."""
    return f'listo<span style="color:{tokens.ACCENT}">.</span>'


def system_scheme() -> str:
    """ "light" or "dark", as the computer is set (dark when it can't tell). LISTO_LOOK=light / dark
    overrides it (screenshots, testing the other look)."""
    import os

    from PySide6.QtGui import QGuiApplication

    forced = os.environ.get("LISTO_LOOK", "")
    if forced in ("light", "dark"):
        return forced
    app = QGuiApplication.instance()
    if app is None:
        return "dark"
    hints = app.styleHints()
    if hasattr(hints, "unsetColorScheme"):
        hints.unsetColorScheme()
    scheme = hints.colorScheme() if hasattr(hints, "colorScheme") else None
    return "light" if scheme == Qt.ColorScheme.Light else "dark"


def apply(app, appearance: str, folder: Path, accent: str | None = None) -> str:
    """Use the light or dark look ("system" asks the computer), in an accent (None keeps the current one).
    Returns the look in use."""
    look = system_scheme() if appearance not in ("light", "dark") else appearance
    tokens.use(look, accent)
    _load_colors()
    hints = app.styleHints()
    if appearance in ("light", "dark") and hasattr(hints, "setColorScheme"):  # title bars match
        hints.setColorScheme(Qt.ColorScheme.Light if look == "light" else Qt.ColorScheme.Dark)
    app.setStyleSheet(stylesheet(folder))
    return look


def use(scheme: str, accent: str | None = None) -> None:
    """Switch the colors without touching an app (tests); apply() is the one that restyles the window."""
    tokens.use(scheme, accent)
    _load_colors()


def font(size: int = TEXT_MD, weight: int = WEIGHT_REGULAR):
    """The app's font at a type-scale size (TEXT_*) and weight (WEIGHT_*): the one way to make a QFont."""
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    f = QFont(QApplication.font())
    f.setPixelSize(size)
    f.setWeight(QFont.Weight(weight))
    return f


def plain_tip(text: str) -> str:
    """A tooltip that shows `text` exactly as typed (Qt would read "<b>…" in a name as formatting)."""
    import html

    return f"<p style='white-space:pre-wrap'>{html.escape(text)}</p>" if text else ""


def qcolor(value: str):
    """A token as a QColor: "#RRGGBB" or "rgba(r, g, b, a)" (QColor can't read the CSS form itself).
    Read once per value; each call gets its own copy to change."""
    from PySide6.QtGui import QColor

    return QColor(_parsed(value))


@lru_cache(maxsize=256)
def _parsed(value: str):
    import re

    from PySide6.QtGui import QColor

    m = re.match(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", value)
    if m:
        r, g, b, a = m.groups()
        return QColor(int(r), int(g), int(b), round(float(a) * 255))
    return QColor(value)
