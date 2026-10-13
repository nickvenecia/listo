"""Design tokens: the ONLY place sizes, spacing, type and colors are defined.

Every widget, layout and stylesheet rule uses these names. If something needs a value
that isn't here, add a token (and document it in DESIGN.md) instead of typing a number.
"""

from __future__ import annotations

# ---------------------------------------------------------------- spacing (4-pt grid)
SPACE_1 = 4  # tight: a label and its control, an icon and its text
SPACE_2 = 8  # related items: buttons in a row, cards in the list, options in a stack
SPACE_3 = 12  # between groups (sections) inside a panel
SPACE_4 = 16  # padding of panels, bars and the main areas
SPACE_5 = 24  # padding of dialogs and the empty-state drop zone

# ---------------------------------------------------------------- control sizes
CONTROL_H = 34  # EVERY button, dropdown, text field and segmented control
SMALL_H = 24  # chips, token buttons, icon-only buttons
INDICATOR = 16  # standard icon size
TOGGLE_ROW_H = 32  # an on/off setting: label left, switch right
TOGGLE_W, TOGGLE_H = 36, 20  # the switch
TOGGLE_INSET = 3  # gap between the switch's track and its knob
ICON = 16
ICON_SM = 14
ICON_LG = 24  # placeholder icons in empty thumbnails
ICON_XL = 44  # the drop-zone arrow
BAR_H = 6  # progress bars
TRACK_H = 4  # slider groove
HANDLE = 14  # slider handle
SCROLL_W = 10  # scrollbar width
SCROLL_GUTTER = SCROLL_W  # space always kept for it (see widgets.FitScroll)
SCROLL_MIN = 30  # shortest scrollbar handle

# ---------------------------------------------------------------- corner radius
RADIUS_XS = 4  # checkbox box
RADIUS_SM = 6  # chips, menu/list rows, small buttons
RADIUS = 8  # controls: buttons, fields, dropdowns, segmented controls
RADIUS_LG = 12  # cards, popups, panels inside dialogs
RADIUS_XL = 16  # the drop zone

# ---------------------------------------------------------------- type scale (px)
TEXT_XS = 11  # SECTION LABELS (caps), chips
TEXT_SM = 12  # secondary text: file details, hints, tooltips
TEXT_MD = 13  # body text and every control (the default)
TEXT_LG = 14  # emphasized text: file names in the list, footer title
TEXT_XL = 18  # dialog titles, empty-state headline
TEXT_BRAND = 21  # the "listo." wordmark only
TEXT_TITLEBAR = 15  # the wordmark in the Mac title bar

WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500  # controls
WEIGHT_SEMIBOLD = 600  # titles, labels, primary button
WEIGHT_BOLD = 700  # wordmark, dialog titles

# ---------------------------------------------------------------- layout
SIDEBAR_W = 330  # step 2 panel (Convert To) — same width as the export panel
EXPORT_W = 330  # step 3 panel (Export): live preview, where, name, Convert
HEADER_H = 52  # the numbered step header on top of every panel
TITLEBAR_H = 32  # Listo's own Mac title bar (fitted to the real one once the window shows)
STEP_BADGE = 22  # the round step number
SEG_INSET = 2  # scroll bar inset
TAB_LINE = 2  # the marigold line under the open tab (widgets.Segmented)
THUMB_W, THUMB_H = 112, 63  # 16:9 file thumbnails
CARD_H = THUMB_H + 2 * SPACE_2
STATUS_W = 215  # right-hand status column on file cards
CARD_BAR_W = 170  # progress bar inside a card
PREVIEW_W, PREVIEW_H = 240, 135  # trim previews (16:9)
VIEWER_W, VIEWER_H = 768, 432  # the Preview window's picture area (16:9)
EDITOR_PIC_W, EDITOR_PIC_H = 512, 288  # picture in the caption editor (16:9)
CAPTION_LIST_W = 420  # the caption lines beside it
CAPTION_ROW_H = 2 * CONTROL_H - SPACE_3  # one caption's text box: two lines of text
TIME_FIELD_W = 92  # h:mm:ss.s entry boxes
LINK_BOX_W = 380  # the link field in the drop zone
DETAILS_SIZE = (640, 420)  # the file details dialog
WINDOW_SIZE = (1360, 820)
WINDOW_MIN = (1180, 620)
DIALOG_W = 480

# ---------------------------------------------------------------- colors
# Two looks with the same names: dark (the values right here) and LIGHT (below). Listo follows the
# system's light / dark setting (app.py -> theme.use), even while it's open. So read a color as
# tokens.NAME (or theme.NAME) when you draw or style, never copy one into a variable at import.
BG = "#111113"  # window background
PANEL = "#17171A"  # sidebar, footer, dialogs
CARD = "#1E1E22"  # cards, fields
CARD_HOVER = "#24242A"
CARD_SELECTED = "#29231A"  # a selected file card (warm, so it reads as marigold)
RAISED = "#2A2A30"  # buttons, popups
RAISED_HOVER = "#33333A"
RAISED_PRESS = "#26262C"
BORDER = "#2C2C33"
BORDER_STRONG = "#3A3A42"
BORDER_HOVER = "#4A4A54"
BORDER_CHECK = "#55555F"  # unchecked checkbox outline
TRACK = "#3A3A42"  # an off switch's track (TRACK_HOVER under the pointer)
TRACK_HOVER = "#4A4A54"
KNOB = "#F4F1EC"  # an off switch's knob (on: ON_ACCENT on marigold)
TEXT = "#F4F1EC"
MUTED = "#A09B93"  # secondary text
FAINT = "#6E6A64"  # hints, disabled, section labels
WELL = "#0C0C0E"  # sunken areas with text: Saves As, logs, notes
SCREEN = "#0C0C0E"  # behind pictures (players, previews, thumbnails): dark in both looks, like a monitor
SCREEN_TEXT = "#A09B93"  # words on SCREEN ("Making a preview…")
SCREEN_FAINT = "#6E6A64"  # placeholder icons on SCREEN
ACCENT = "#F5A524"  # cempasúchil marigold — selection, primary action, progress
ACCENT_HOVER = "#FFB743"
ACCENT_PRESS = "#DB8F12"
ACCENT_INK = "#F5A524"  # marigold as text, icons and thin lines on the background (darker in light)
ON_ACCENT = "#1B1206"  # text/icons on marigold
ACCENT_OFF = "#3A3326"  # disabled primary button
ACCENT_OFF_TEXT = "#7D705A"
ACCENT_TINT = "rgba(245, 165, 36, 0.08)"  # marigold wash behind custom chips / hot drop zone
ACCENT_EDGE = "rgba(245, 165, 36, 0.55)"
GOOD = "#4CC38A"
BAD = "#F0616D"
BAD_TINT = "#2A1A1D"  # danger button hover
BAD_EDGE = "#5A2A30"  # failed card border
WARN = "#E9B949"

COLORS = (
    "BG", "PANEL", "CARD", "CARD_HOVER", "CARD_SELECTED", "RAISED", "RAISED_HOVER", "RAISED_PRESS",
    "BORDER", "BORDER_STRONG", "BORDER_HOVER", "BORDER_CHECK", "TRACK", "TRACK_HOVER", "KNOB",
    "TEXT", "MUTED", "FAINT", "WELL",
    "SCREEN", "SCREEN_TEXT", "SCREEN_FAINT", "ACCENT", "ACCENT_HOVER", "ACCENT_PRESS", "ACCENT_INK",
    "ON_ACCENT", "ACCENT_OFF", "ACCENT_OFF_TEXT", "ACCENT_TINT", "ACCENT_EDGE",
    "GOOD", "BAD", "BAD_TINT", "BAD_EDGE", "WARN",
)  # fmt: skip
DARK = {k: globals()[k] for k in COLORS}
# Light: warm paper whites, the same marigold for fills; marigold text and status colors are darker
# so they read on white. Pictures still sit on SCREEN black.
LIGHT = {
    **DARK,
    "BG": "#F6F5F2",
    "PANEL": "#EFEEEA",
    "CARD": "#FFFFFF",
    "CARD_HOVER": "#FAF9F7",
    "CARD_SELECTED": "#FCEFD6",
    "RAISED": "#FFFFFF",
    "RAISED_HOVER": "#F4F3EF",
    "RAISED_PRESS": "#E9E7E2",
    "BORDER": "#E2E0DB",
    "BORDER_STRONG": "#D0CDC6",
    "BORDER_HOVER": "#B3AFA7",
    "BORDER_CHECK": "#A19D95",
    "TRACK": "#C9C5BE",
    "TRACK_HOVER": "#B3AFA7",
    "KNOB": "#FFFFFF",
    "TEXT": "#1D1C1A",
    "MUTED": "#5F5B54",
    "FAINT": "#8A857D",
    "WELL": "#E8E6E1",
    "ACCENT_HOVER": "#EE9C17",
    "ACCENT_PRESS": "#D88A0E",
    "ACCENT_INK": "#9A5800",
    "ACCENT_OFF": "#F3E4C6",
    "ACCENT_OFF_TEXT": "#A38B69",
    "ACCENT_TINT": "rgba(245, 165, 36, 0.14)",
    "ACCENT_EDGE": "rgba(214, 135, 10, 0.65)",
    "GOOD": "#1E8550",
    "BAD": "#C42F3C",
    "BAD_TINT": "#FBE6E8",
    "BAD_EDGE": "#EDB3B9",
    "WARN": "#946600",
}
SCHEME = "dark"  # which look is in use: "dark" or "light"


def use(scheme: str) -> None:
    """Point every color name at the dark or the light look (theme.use rebuilds the stylesheet)."""
    global SCHEME
    SCHEME = "light" if scheme == "light" else "dark"
    globals().update(LIGHT if SCHEME == "light" else DARK)
