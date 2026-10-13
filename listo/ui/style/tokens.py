"""Design tokens: the ONLY place sizes, spacing, type, timing and colors are defined.

Every widget, layout and stylesheet rule uses these names. If something needs a value
that isn't here, add a token (and document it in DESIGN.md) instead of typing a number.
"""

from __future__ import annotations

# ---------------------------------------------------------------- spacing (4-pt grid)
SPACE_1 = 4  # tight: a label and its control, an icon and its text
SPACE_2 = 8  # related items: buttons in a row, rows in a list, options in a stack
SPACE_3 = 12  # between groups (sections) inside a panel
SPACE_4 = 16  # padding of panels, bars and the main areas
SPACE_5 = 24  # padding of dialogs and empty states

# ---------------------------------------------------------------- control sizes
CONTROL_H = 34  # EVERY button, dropdown, text field, segmented control and round icon button
SMALL_H = 24  # small round icon buttons inside rows and cards, chips, naming tokens
SECTION_ADD = 20  # a sidebar section's plain + (a gray glyph, the Mac's size)
CHIP_H = 28  # a tinted capsule button
CHIP_SM_H = SMALL_H - 6  # a small status chip
INDICATOR = 16  # checkbox box
TOGGLE_ROW_H = 32  # an on/off setting: label left, switch right
TOGGLE_W, TOGGLE_H = 36, 20  # the switch
TOGGLE_INSET = 3  # gap between the switch's track and its knob
ICON = 16  # icons in buttons and menus
ICON_SM = 14  # icons in small buttons
ICON_LG = 20  # a hero icon that must fill its circle
ICON_XL = 44  # the empty list's arrow
BAR_H = 6  # progress bars
TRACK_H = 4  # slider groove
HANDLE = 14  # slider handle
SCROLL_W = 10  # scrollbar width
SCROLL_GUTTER = SCROLL_W  # space always kept for it (see widgets.FitScroll)
SCROLL_MIN = 30  # shortest scrollbar handle
SCROLL_INSET = 2  # a scrollbar's handle sits this far inside its track
SEG_INSET = 2  # gap between a segmented control's frame and its buttons
TEXT_BOX_H = 2 * CONTROL_H - SPACE_2  # a two-line text box
TEXT_BOX_TALL = 4 * CONTROL_H - SPACE_3  # notes, a feedback message
SWATCH = 22  # a color circle in Settings › Accent Color
SWATCH_RING = 2  # the ring around the chosen one (and the gap inside it)

# ---------------------------------------------------------------- corner radius
RADIUS_XS = 4  # checkbox box
RADIUS_SM = 6  # chips, small buttons
RADIUS = 8  # fields, dropdowns, segmented controls
RADIUS_LG = 12  # cards, alerts, popups
GLASS_R = 18  # a floating glass panel's corners
ROW_R = 9  # a table row's rounded highlight

# ---------------------------------------------------------------- type scale (px)
TEXT_XS = 11  # chips, menu section headings
TEXT_SM = 12  # secondary text, section labels, tooltips
TEXT_MD = 13  # body text and every control (the default)
TEXT_LG = 14  # emphasis: names in lists, alert titles
TEXT_XL = 18  # dialog titles, empty-state headline
TEXT_TITLE = 24  # the page's large title in the toolbar (All Files, Videos)
TEXT_BRAND = 21  # the "listo." wordmark only
TEXT_TITLEBAR = 15  # the wordmark in the Mac title bar

WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500  # controls
WEIGHT_SEMIBOLD = 600  # titles, labels, primary button
WEIGHT_BOLD = 700  # wordmark, page and dialog titles

TRACK_BRAND = -0.5  # letter spacing (px): the wordmark
TRACK_TITLEBAR = -0.3
TRACK_TITLE = -0.4  # page titles
ICON_STROKE = 2.0  # the icon set's line width
LINE_STROKE = 1.8  # drawn chevrons

# ---------------------------------------------------------------- layout
WINDOW_SIZE = (1600, 1000)
WINDOW_MIN = (1280, 700)  # the toolbar, the list and the right panel all fit
GLASS_GAP = 10  # between the window's edge and its floating panels, and between panels
GLASS_SHADOW_STEPS = 16  # layers of a panel's shadow (soft, like the Mac's)
GLASS_SHADOW_SPREAD = 24  # how far it reaches: wide and faint, never a dark smudge
GLASS_SHADOW_DROP = 3  # how far below the panel it sits: barely
GLASS_EDGE_FADE = 60  # the hairline is brightest along the top, settling over this many px
SIDEBAR_W = 232  # the left panel: your files by kind
INSPECTOR_W = 420  # the right panel: Convert To, or the clip you picked
INSPECTOR_MIN = 360  # …on a smaller window
INSPECTOR_SHARE = 0.27  # of the window's width, between those two
TOOLBAR_H = 64  # the bar above the list: title, search, filter, +
HEADER_H = 52  # a panel header that isn't level with a toolbar
TITLEBAR_H = 32  # Listo's own Mac title bar (fitted to the real one once the window shows)
SEARCH_W = 440  # the search capsule asks for this much room…
SEARCH_MIN = 160  # …and gives way down to this
NAV_H = 30  # one row in the sidebar
NAV_GAP = 2  # between rows in the sidebar
NAV_INSET = SCROLL_GUTTER  # a sidebar row's gap from the glass edge (the scroll bar's room on the right)
NAV_R = GLASS_R - NAV_INSET  # its corners: concentric with the glass (the curves run parallel)
MENU_GAP = 6  # between a button and the menu it opens
# ---- every list of choices looks like the sidebar and Settings: menus, dropdown lists, pickers.
# Rows sit LIST_INSET inside a list whose corners are LIST_R, so their corners (LIST_ROW_R) run parallel to it.
LIST_R = GLASS_R
LIST_INSET = NAV_INSET
LIST_ROW_R = NAV_R
LIST_ROW_H = NAV_H
LIST_GAP = NAV_GAP
AVATAR = 32  # the initials at the bottom of the sidebar
PROFILE_CARD_H = 48
TABLE_ROW_H = 64  # one file in the list: a 16:9 thumbnail and two lines
ROW_INSET = 2  # a row's rounded highlight sits this far inside the row
THUMB_W, THUMB_H = 96, 54  # a file's 16:9 thumbnail in the list
STATUS_W = 200  # the list's status column (Ready, Converting 42%…)
LINK_BOX_W = 380  # the link field on the empty list
PREVIEW_W, PREVIEW_H = 240, 135  # trim previews (16:9)
VIEWER_W, VIEWER_H = 768, 432  # the Preview window's picture area (16:9)
EDITOR_PIC_W, EDITOR_PIC_H = 512, 288  # the picture in Check the Captions (16:9)
CAPTION_LIST_W = 420  # the caption lines beside it
CAPTION_ROW_H = 2 * CONTROL_H - SPACE_3  # one caption's text box: two lines of text
TIME_FIELD_W = 92  # h:mm:ss.s entry boxes
DETAILS_SIZE = (640, 420)  # the file details window
DIALOG_W = 480
DIALOG_W_WIDE = DIALOG_W + 2 * SPACE_5
DIALOG_W_XWIDE = DIALOG_W + 6 * SPACE_5  # the update window
SETTINGS_SIZE = (820, 620)  # the Settings window
SETTINGS_MIN = (680, 480)
SETTINGS_SIDE_W = 210  # its sidebar
ALERT_W = 300  # an alert (Remove …?), narrow like a Mac's
ALERT_ICON = 56  # the app icon at the top of it
NOTES_H = 220  # what's new, in the update window
TOAST_MAX_W = 520

# ---------------------------------------------------------------- timing (ms)
DOCK_MS = 240  # the right panel sliding in or out
FADE_MS = 150  # small things appearing or going: a quick fade, never a pop
SAVE_DELAY_MS = 400  # save this long after the last keystroke
TOAST_MS = 3500  # how long a toast stays up
UPDATE_CHECK_DELAY_MS = 1500  # the automatic update check, just after the window is up (every launch)
UPDATE_WAIT_MS = 1500  # a found update waits this long between looks while another window is open
QUIT_WAIT_MS = 1500  # how long quitting waits for an update check to finish

# ---------------------------------------------------------------- colors: a dark and a light set
# Listo follows the system (or Settings › General › Appearance). Read colors as tokens.X when drawing,
# never copy them into a constant at import: use() swaps them.
DARK = {
    "BG": "#1E1E1E",  # window background: the Mac's dark charcoal, not black
    "PANEL": "#1E1E1E",  # dialogs, footers
    "CARD": "#1F1E20",  # cards, fields
    "CARD_HOVER": "#262527",
    "CARD_SELECTED": "#392E20",  # a selected row (a hint of the accent)
    "RAISED": "#2B2A2C",  # buttons, popups
    "RAISED_HOVER": "#343335",
    "RAISED_PRESS": "#272628",
    "BORDER": "#2D2C2E",
    "BORDER_STRONG": "#3B3A3D",
    "BORDER_HOVER": "#4D4B4F",
    "BORDER_CHECK": "#5C5A5F",  # unchecked checkbox outline
    "TEXT": "#F4F2F1",
    "MUTED": "#A8A5A6",  # secondary text
    "FAINT": "#737072",  # hints, disabled, section labels
    "WELL": "#0C0B0C",  # sunken areas with words: Saves As, logs
    "SCREEN": "#0C0B0C",  # behind pictures (players, previews, thumbnails): black in both looks, like a monitor
    "SCREEN_TEXT": "#A8A5A6",  # words on SCREEN ("Making a preview…")
    "SCREEN_FAINT": "#737072",  # placeholder icons on SCREEN
    "ACCENT": "#F5A524",  # cempasúchil marigold — selection, the one primary action, progress, focus
    "ACCENT_HOVER": "#FFB743",
    "ACCENT_PRESS": "#DB8F12",
    "ON_ACCENT": "#1B1206",  # words and icons on marigold (white wouldn't read)
    "ACCENT_OFF": "#463621",  # disabled primary button
    "ACCENT_OFF_TEXT": "#7F5B22",
    "ACCENT_TINT": "rgba(245, 165, 36, 0.15)",  # a marigold wash
    "ACCENT_EDGE": "rgba(255, 183, 67, 0.55)",
    "GOOD": "#4CC38A",
    "BAD": "#F0616D",  # failed, remove
    "BAD_TINT": "#2A1A1D",  # danger button hover
    "BAD_EDGE": "#5A2A30",  # a failed outline
    "WARN": "#DCCF45",  # needs a look: shifted toward yellow, away from the marigold accent
    "ROW_HOVER": "rgba(255, 255, 255, 0.05)",  # a list row under the mouse
    "WINDOW_TOP": "#1E1E1E",  # the window's backdrop: one flat color, no gradient
    "WINDOW_BOTTOM": "#1E1E1E",
    "GLASS": "rgba(48, 47, 50, 0.92)",  # a floating panel: one even tone, lighter than the page
    "GLASS_STROKE": "rgba(255, 255, 255, 0.10)",  # its one hairline: faintly lighter than the panel
    "GLASS_EDGE": "rgba(255, 255, 255, 0.18)",  # …a little brighter along the top, where light catches it
    "GLASS_SHADOW": "rgba(0, 0, 0, 0.35)",  # soft and wide
    "CHIP": "rgba(245, 165, 36, 0.16)",  # a tinted capsule (+ Add)
    "CHIP_HOVER": "rgba(245, 165, 36, 0.26)",
    "FIELD": "rgba(255, 255, 255, 0.07)",  # a text field or dropdown: lightly frosted
    "FIELD_BORDER": "rgba(255, 255, 255, 0.08)",
    "BLOCK": "rgba(255, 255, 255, 0.045)",  # a card inside a glass panel: a soft tint, no outline
    "FILL": "rgba(255, 255, 255, 0.045)",  # a soft fill on the page: a switch's track, a placeholder
    "DIVIDER": "#3E321F",  # a band in the list
    "DIVIDER_TEXT": "#FACE87",
    "DIVIDER_HOVER": "#49391F",
}
LIGHT = {
    "BG": "#FFFFFF",
    "PANEL": "#FFFFFF",
    "CARD": "#FFFFFF",
    "CARD_HOVER": "#F2F2F4",
    "CARD_SELECTED": "#F6EFE6",
    "RAISED": "#FFFFFF",
    "RAISED_HOVER": "#F5F5F7",
    "RAISED_PRESS": "#E8E8EC",
    "BORDER": "#E5E5EA",
    "BORDER_STRONG": "#D8D8DD",
    "BORDER_HOVER": "#B8B8BF",
    "BORDER_CHECK": "#A2A2AA",
    "TEXT": "#1D1D1F",
    "MUTED": "#6E6E73",
    "FAINT": "#A1A1A6",
    "WELL": "#EDEDF0",
    "SCREEN": "#0C0B0C",
    "SCREEN_TEXT": "#A8A5A6",
    "SCREEN_FAINT": "#737072",
    "ACCENT": "#A86300",  # a step deeper, so white words on it and marigold words on white both read
    "ACCENT_HOVER": "#B17319",
    "ACCENT_PRESS": "#8F5400",
    "ON_ACCENT": "#FFFFFE",
    "ACCENT_OFF": "#EEE0CC",
    "ACCENT_OFF_TEXT": "#D4B180",
    "ACCENT_TINT": "rgba(168, 99, 0, 0.09)",
    "ACCENT_EDGE": "rgba(168, 99, 0, 0.45)",
    "GOOD": "#1E9A5E",
    "BAD": "#D3374A",
    "BAD_TINT": "#FBEAEC",
    "BAD_EDGE": "#EFB7BF",
    "WARN": "#7F7500",
    "ROW_HOVER": "rgba(0, 0, 0, 0.04)",
    "WINDOW_TOP": "#FFFFFF",
    "WINDOW_BOTTOM": "#FFFFFF",
    "GLASS": "rgba(242, 242, 245, 0.94)",
    "GLASS_STROKE": "rgba(0, 0, 0, 0.06)",  # a very faint gray hairline
    "GLASS_EDGE": "rgba(0, 0, 0, 0.04)",  # (fainter still along the top)
    "GLASS_SHADOW": "rgba(0, 0, 0, 0.08)",  # soft and wide
    "CHIP": "rgba(168, 99, 0, 0.1)",
    "CHIP_HOVER": "rgba(168, 99, 0, 0.18)",
    "FIELD": "rgba(255, 255, 255, 1.0)",
    "FIELD_BORDER": "rgba(0, 0, 0, 0.10)",
    "BLOCK": "rgba(255, 255, 255, 0.85)",  # white cards on the gray glass
    "FILL": "rgba(0, 0, 0, 0.045)",  # light gray on white
    "DIVIDER": "#F2E8D9",
    "DIVIDER_TEXT": "#8F5400",
    "DIVIDER_HOVER": "#ECDDC7",
}
COLORS = tuple(DARK)

# ---------------------------------------------------------------- the accent you pick (Settings › General)
# Listo's own is marigold, hand-set in DARK / LIGHT above. The others are built from one color by accent_set().
# Never red: red means failed or remove.
APP_ACCENT = "marigold"
ACCENTS = {  # key -> (name, on dark, on light)
    "marigold": ("Marigold", "#F5A524", "#A86300"),
    "blue": ("Blue", "#4A90F7", "#2F6FDB"),
    "purple": ("Purple", "#8069F7", "#6A52E8"),
    "pink": ("Pink", "#F25FA6", "#C9387F"),
    "orange": ("Orange", "#F5893A", "#C2600E"),
    "yellow": ("Yellow", "#EDBA3A", "#9C7104"),
    "green": ("Green", "#3DBE6E", "#1B8747"),
    "turquoise": ("Turquoise", "#2EBFB0", "#0D8178"),
    "graphite": ("Graphite", "#9B999F", "#68666D"),
}
DARK_ON_ACCENT = "#141314"  # words on a light accent (yellow, green…), where white wouldn't read


def _rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in rgb)


def _mix(c: str, into: str, amount: float) -> str:
    """`amount` of color c mixed into `into`."""
    a, b = _rgb(c), _rgb(into)
    return _hex(x * amount + y * (1 - amount) for x, y in zip(a, b, strict=True))


def _rgba(c: str, alpha: float) -> str:
    r, g, b = _rgb(c)
    return f"rgba({r}, {g}, {b}, {alpha:g})"


def luminance(c: str) -> float:
    """Relative luminance (WCAG), 0 black … 1 white."""

    def ch(v: int) -> float:
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = _rgb(c)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def accent_set(base: str, scheme: str) -> dict[str, str]:
    """Every accent token for one color, in the dark or light look (the same steps as the hand-set one)."""
    light = scheme == "light"
    on = "#FFFFFF" if contrast("#FFFFFF", base) >= 3 else DARK_ON_ACCENT
    if light:
        return {
            "ACCENT": base,
            "ACCENT_HOVER": _mix(base, "#FFFFFF", 0.9),
            "ACCENT_PRESS": _mix(base, "#000000", 0.85),
            "ON_ACCENT": "#FFFFFE" if on == "#FFFFFF" else on,
            "ACCENT_OFF": _mix(base, "#FFFFFF", 0.2),
            "ACCENT_OFF_TEXT": _mix(base, "#FFFFFF", 0.5),
            "ACCENT_TINT": _rgba(base, 0.09),
            "ACCENT_EDGE": _rgba(base, 0.45),
            "CARD_SELECTED": _mix(base, "#FFFFFF", 0.1),
            "DIVIDER": _mix(base, "#FFFFFF", 0.15),
            "DIVIDER_TEXT": _mix(base, "#000000", 0.85),
            "DIVIDER_HOVER": _mix(base, "#FFFFFF", 0.22),
            "CHIP": _rgba(base, 0.10),
            "CHIP_HOVER": _rgba(base, 0.18),
        }
    return {
        "ACCENT": base,
        "ACCENT_HOVER": _mix(base, "#FFFFFF", 0.85),
        "ACCENT_PRESS": _mix(base, "#000000", 0.88),
        "ON_ACCENT": on,
        "ACCENT_OFF": _mix(base, DARK["CARD"], 0.18),
        "ACCENT_OFF_TEXT": _mix(base, DARK["CARD"], 0.45),
        "ACCENT_TINT": _rgba(base, 0.15),
        "ACCENT_EDGE": _rgba(_mix(base, "#FFFFFF", 0.85), 0.55),
        "CARD_SELECTED": _mix(base, DARK["CARD"], 0.12),
        "DIVIDER": _mix(base, DARK["BG"], 0.15),
        "DIVIDER_TEXT": _mix(base, "#FFFFFF", 0.55),
        "DIVIDER_HOVER": _mix(base, DARK["BG"], 0.2),
        "CHIP": _rgba(base, 0.16),
        "CHIP_HOVER": _rgba(base, 0.26),
    }


SCHEME = "dark"  # the look in use: "dark" or "light"
ACCENT_KEY = APP_ACCENT
globals().update(DARK)


def use(scheme: str, accent: str | None = None) -> None:
    """Switch every color token to the dark or light set, in the chosen accent (None keeps the current one;
    an unknown or empty one means Listo's own)."""
    global SCHEME, ACCENT_KEY
    SCHEME = "light" if scheme == "light" else "dark"
    if accent is not None:
        ACCENT_KEY = accent if accent in ACCENTS else APP_ACCENT
    globals().update(LIGHT if SCHEME == "light" else DARK)
    if ACCENT_KEY != APP_ACCENT:
        _name, dark, light = ACCENTS[ACCENT_KEY]
        globals().update(accent_set(light if SCHEME == "light" else dark, SCHEME))


def accent_of(key: str, scheme: str | None = None) -> str:
    """A choice's color in the dark or light look (the current one by default)."""
    _name, dark, light = ACCENTS.get(key, ACCENTS[APP_ACCENT])
    return light if (scheme or SCHEME) == "light" else dark
