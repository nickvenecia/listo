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
INDICATOR = 16  # checkbox box, standard icon size
ICON = 16
ICON_SM = 14
ICON_LG = 24  # placeholder icons in empty thumbnails
ICON_XL = 44  # the drop-zone arrow
BAR_H = 6  # progress bars
TRACK_H = 4  # slider groove
HANDLE = 14  # slider handle
SCROLL_W = 10  # scrollbar width
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

WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500  # controls
WEIGHT_SEMIBOLD = 600  # titles, labels, primary button
WEIGHT_BOLD = 700  # wordmark, dialog titles

# ---------------------------------------------------------------- layout
SIDEBAR_W = 310
SEG_INSET = 2  # gap between a segmented control's frame and its buttons
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
WINDOW_SIZE = (1120, 720)
WINDOW_MIN = (880, 560)
DIALOG_W = 480

# ---------------------------------------------------------------- colors (dark theme)
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
TEXT = "#F4F1EC"
MUTED = "#A09B93"  # secondary text
FAINT = "#6E6A64"  # hints, disabled, section labels
WELL = "#0C0C0E"  # sunken areas: thumbnails, previews, logs
ACCENT = "#F5A524"  # cempasúchil marigold — selection, primary action, progress
ACCENT_HOVER = "#FFB743"
ACCENT_PRESS = "#DB8F12"
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
