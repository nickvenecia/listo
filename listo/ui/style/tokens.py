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
CHIP_SM_H = SMALL_H - 6  # a small status chip
INDICATOR = 16  # checkbox box
TOGGLE_ROW_H = 32  # an on/off setting: label left, switch right
TOGGLE_W, TOGGLE_H = 36, 20  # the switch
TOGGLE_INSET = 3  # gap between the switch's track and its knob
ICON = 16  # icons in buttons and menus
ICON_SM = 14  # icons in small buttons
ICON_LG = 20  # a hero icon that must fill its circle
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
# The FeatureSoup family's corners: capsules for controls, softly rounded cards and lists, one curve on the work area.
RADIUS_XS = 4  # checkbox box
RADIUS_SM = 7  # chips, thumbnails, small buttons
RADIUS = 10  # fields, dropdowns
RADIUS_LG = 13  # cards, alerts, pictures
RADIUS_XL = 20  # a window drawn by Listo (the alert)
WORK_R = 16  # the work area's top corners, where it meets the columns beside and above it
ROW_R = 9  # a table row's rounded highlight

# ---------------------------------------------------------------- type scale (px)
TEXT_XS = 11  # chips, menu section headings
TEXT_SM = 12  # secondary text, section labels, tooltips
TEXT_MD = 13  # body text and every control (the default)
TEXT_LG = 14  # emphasis: names in lists, alert titles
TEXT_XL = 18  # dialog titles, empty-state headline
TEXT_TITLE = 18  # the page's title in the toolbar (All Files, Videos) and a panel's (Convert To)
TEXT_BRAND = 21  # the "listo." wordmark only
TEXT_TITLEBAR = 15  # the wordmark in the Mac title bar

WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500  # controls
WEIGHT_SEMIBOLD = 600  # titles, labels, primary button
WEIGHT_BOLD = 700  # wordmark, page and dialog titles

TRACK_BRAND = -0.5  # letter spacing (px): the wordmark
TRACK_TITLEBAR = -0.3
TRACK_TITLE = -0.45  # page titles
ICON_STROKE = 1.85  # the icon set's line width

# ---------------------------------------------------------------- layout
WINDOW_SIZE = (1600, 1000)
WINDOW_MIN = (1280, 700)  # the toolbar, the list and the right panel all fit
GLASS_GAP = 0  # the columns (sidebar, right panel) sit flush with the window's edges and the work area
SHADOW_STEPS = 16  # layers of a lifted thing's shadow (a toast, a dragged row): soft
SHADOW_SPREAD = 24  # how far it reaches: wide and faint, never a dark smudge
SHADOW_DROP = 3  # how far below it sits: barely
SIDEBAR_W = 232  # the left panel: your files by kind
INSPECTOR_W = 420  # the right panel: Convert To
INSPECTOR_MIN = 360  # …on a smaller window
INSPECTOR_SHARE = 0.27  # of the window's width, between those two
TOOLBAR_H = 56  # the bar above the list: title, search, +
TITLEBAR_H = 32  # Listo's own Mac title bar (fitted to the real one once the window shows)
SEARCH_W = 440  # the search capsule asks for this much room…
SEARCH_MIN = 160  # …and gives way down to this
NAV_H = 34  # one row in the sidebar
NAV_GAP = 2  # between rows in the sidebar
NAV_INSET = SCROLL_GUTTER  # a sidebar row's gap from the column's edges (the scroll bar's room on the right)
NAV_R = 9  # its corners
MENU_GAP = 6  # between a button and the menu it opens
# ---- every list of choices looks the same: menus, dropdown lists, pickers.
# Rows sit LIST_INSET inside a list whose corners are LIST_R, so their corners (LIST_ROW_R) run parallel to it.
LIST_R = 13
LIST_INSET = 5
LIST_ROW_R = LIST_R - LIST_INSET
LIST_ROW_H = NAV_H
LIST_GAP = NAV_GAP
AVATAR = 32  # the initials at the bottom of the sidebar
PROFILE_CARD_H = 48
TABLE_ROW_H = 76  # one file in the list: a 16:9 thumbnail with room above and below, three short lines
ROW_INSET = 2  # a row's rounded highlight sits this far inside the row
THUMB_W, THUMB_H = 96, 54  # a file's 16:9 thumbnail in the list
GRIP_W = 20  # the grip at a row's left that you drag it by (list order is join and timecode order)
GRIP_GAP = 5  # between the grip's dots
GRIP_DOT = 1.2  # the radius of a dot in the grip
STATUS_W = 200  # the list's status column (Ready, Converting 42%…)
START_TILE_W = (
    184  # one way to start on the empty list (three fit beside the open panel on the smallest window)
)
START_BADGE = 40  # the circle behind a start tile's icon
PREVIEW_W, PREVIEW_H = 240, 135  # trim previews (16:9)
VIEWER_W, VIEWER_H = 768, 432  # the Preview window's picture area (16:9)
EDITOR_PIC_W, EDITOR_PIC_H = 512, 288  # the picture in Check the Captions (16:9)
PHOTO_PREVIEW = 1600  # the long edge of a photo's preview picture (sharp in the Preview window)
WAVE_W, WAVE_H = 1600, 400  # an audio file's waveform picture in a preview (fitted to the player)
PLAYHEAD_W = 2  # the line over a waveform where the sound is playing
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
NOTES_H = 320  # what's new, in the update window: as tall as its words, up to this (then it scrolls)
NOTES_LINE = 140  # what's new: the line height, in % of the font size
TOAST_MAX_W = 520
TOAST_RISE = 10  # how far a toast rises as it comes in
TOAST_LIFT = SPACE_4  # its gap above the bottom of the list

# ---------------------------------------------------------------- timing (ms)
DOCK_MS = 240  # the right panel sliding in or out
FADE_MS = 150  # small things appearing or going: a quick fade, never a pop
SAVE_DELAY_MS = 400  # save this long after the last keystroke
TOAST_MS = 3500  # how long a toast stays up
TOAST_MS_PER_CHAR = 60  # …or longer, for a long one: time to read it
TOAST_IN_MS = 220  # it rises and fades in…
TOAST_OUT_MS = 180  # …and fades away
LIFT_STEP_MS = 16  # dragging a row: how often the other rows move (about 60 a second)
LIFT_EASE = 0.3  # …and how far towards their new place each step (smaller is slower)
LIFT_ROWS_SHOWN = 3  # rows drawn on the lifted card when several move
LIFT_SHADOW_STEPS = 6
UPDATE_CHECK_DELAY_MS = 1500  # the automatic update check, just after the window is up (every launch)
UPDATE_WAIT_MS = 1500  # a found update waits this long between looks while another window is open

# ---------------------------------------------------------------- colors: a dark and a light set
# Listo follows the system (or Settings › General › Appearance). Read colors as tokens.X when drawing,
# never copy them into a constant at import: use() swaps them.
# The look is FeatureSoup's (Listo's sister app): cool neutral graphite, the frame (sidebar, toolbar, right panel)
# on one material, the work area set apart by its fill and its curve, no outlines on controls, and one inverted
# primary button. Color means something (progress, done, failed, on) and never fills a button.
DARK = {
    "BG": "#151518",  # the frame: sidebar, toolbar, right panel (FeatureSoup's "chrome")
    "PANEL": "#151518",  # dialogs
    "WORK": "#0D0D10",  # the work area under the toolbar: the list sits here, a step deeper than the frame
    "CARD": "#1C1C20",  # cards
    "TILE": "#1C1C20",  # a start tile on the work area
    "TILE_HOVER": "#26262B",
    "CARD_HOVER": "#303035",
    "CARD_SELECTED": "#393940",  # a picked row, the current sidebar row: one neutral language, no accent
    "RAISED": "#29292E",  # buttons and round icon buttons
    "RAISED_HOVER": "#303035",
    "RAISED_PRESS": "#25252A",
    "POPUP": "#2C2C31",  # menus, dropdown lists, tooltips, the alert
    "POPUP_HOVER": "#404047",  # the row under the pointer in a menu
    "POPUP_EDGE": "rgba(255, 255, 255, 0.06)",
    "BORDER": "#232328",  # the few hairlines left: the bar under the list
    "BORDER_STRONG": "#39393F",  # menu separators, a switch that's off
    "BORDER_HOVER": "#4A4A52",
    "BORDER_CHECK": "#777781",  # unchecked checkbox outline
    "FOCUS": "#B0B0B8",  # a field with the keyboard: a neutral edge, no glow
    "TEXT": "#F0F0F3",
    "MUTED": "#9696A1",  # secondary text
    "FAINT": "#6E6E79",  # hints, disabled, counts
    "WELL": "#0D0D10",  # sunken areas with words: logs
    "SCREEN": "#0B0B0D",  # behind pictures (players, previews, thumbnails): black in both looks, like a monitor
    "SCREEN_TEXT": "#9696A1",  # words on SCREEN ("Making a preview…")
    "SCREEN_FAINT": "#6E6E79",  # placeholder icons on SCREEN
    "PRIMARY": "#E4E5E9",  # the one primary button (Convert, +): inverted, never the accent
    "PRIMARY_HOVER": "#D6D7DB",
    "PRIMARY_PRESS": "#C8C9CE",
    "ON_PRIMARY": "#1A1B20",
    "PRIMARY_OFF": "#29292E",  # a primary button that can't be pressed yet
    "PRIMARY_OFF_TEXT": "#5E5E68",
    "ACCENT": "#FFB81C",  # marigold, FeatureSoup's golden yellow: progress, on, the chosen one, the wordmark's dot
    "ACCENT_HOVER": "#FFC748",
    "ACCENT_PRESS": "#E6A20A",
    "ON_ACCENT": "#1B1206",  # words and icons on marigold (white wouldn't read)
    "ACCENT_OFF": "#4A3A18",  # a switch that's on but can't be changed
    "ACCENT_OFF_TEXT": "#80652A",
    "ACCENT_TINT": "rgba(255, 184, 28, 0.15)",  # a marigold wash
    "ACCENT_EDGE": "rgba(255, 199, 72, 0.55)",
    "GOOD": "#4CC38A",
    "BAD": "#F0616D",  # failed, remove
    "ON_BAD": "#FFFFFF",  # words on a red fill (the alert's Delete)
    "BAD_TINT": "#2E1C20",  # danger button hover
    "BAD_EDGE": "#5A2A30",  # a failed outline
    "WARN": "#DCCF45",  # needs a look: shifted toward yellow, away from the marigold accent
    "ROW_HOVER": "rgba(255, 255, 255, 0.05)",  # a list row under the mouse
    "WINDOW_TOP": "#151518",  # the window's backdrop: the frame's one flat color
    "WINDOW_BOTTOM": "#151518",
    "GLASS": "#151518",  # the columns (sidebar, right panel): the frame's material, flush, no edge or shadow
    "SHADOW": "rgba(0, 0, 0, 0.45)",  # under something lifted off the page (a dragged row)
    "TOAST": "#2C2C31",  # a toast: the menus' material, lifted by a deep shadow
    "TOAST_TEXT": "#F0F0F3",
    "TOAST_EDGE": "rgba(255, 255, 255, 0.08)",
    "TOAST_SHADOW": "rgba(0, 0, 0, 0.60)",
    "TOAST_DONE": "#4CC38A",  # its icon: it worked
    "TOAST_PROBLEM": "#DCCF45",  # …it didn't (WARN's yellow)
    "TOAST_PROBLEM_FILL": "#47452A",  # a problem's toast is tinted yellow, so it's never missed
    "TOAST_PROBLEM_EDGE": "rgba(220, 207, 69, 0.45)",
    "CHIP": "rgba(255, 184, 28, 0.16)",  # a tinted capsule: key caps, where a dragged row lands
    "FIELD": "#29292E",  # a text field or dropdown: a fill, no outline
    "FIELD_HOVER": "#303035",
    "FIELD_BORDER": "rgba(0, 0, 0, 0)",  # (kept clear: the edge is only there so focus can show)
    "SEG_TRACK": "#29292D",  # a segmented control's track…
    "SEG_ON": "#434349",  # …and its chosen part
    "BLOCK": "#1C1C20",  # a card in the right panel: a step lighter than the frame, no outline
    "FILL": "rgba(255, 255, 255, 0.07)",  # a soft fill on any surface: bar tracks, a placeholder
}
LIGHT = {
    "BG": "#F6F7F9",
    "PANEL": "#F7F8FA",
    "WORK": "#FFFFFF",  # the light look's work area is the white page in the gray frame
    "CARD": "#FFFFFF",
    "TILE": "#F1F3F6",
    "TILE_HOVER": "#E9ECF0",
    "CARD_HOVER": "#E9ECF0",
    "CARD_SELECTED": "#DFE7F1",
    "RAISED": "#EBEDF1",
    "RAISED_HOVER": "#E2E5EA",
    "RAISED_PRESS": "#D9DDE3",
    "POPUP": "#FFFFFF",
    "POPUP_HOVER": "#EDF0F4",
    "POPUP_EDGE": "rgba(0, 0, 0, 0.10)",
    "BORDER": "#E6E8EC",
    "BORDER_STRONG": "#D6DAE0",
    "BORDER_HOVER": "#BCC1C8",
    "BORDER_CHECK": "#9AA1AB",
    "FOCUS": "#5F6772",
    "TEXT": "#20242A",
    "MUTED": "#646D78",
    "FAINT": "#9AA1AA",
    "WELL": "#EDEFF3",
    "SCREEN": "#0B0B0D",
    "SCREEN_TEXT": "#9696A1",
    "SCREEN_FAINT": "#6E6E79",
    "PRIMARY": "#292C34",
    "PRIMARY_HOVER": "#3A3E47",
    "PRIMARY_PRESS": "#1C1E24",
    "ON_PRIMARY": "#FEFEFF",
    "PRIMARY_OFF": "#E3E6EA",
    "PRIMARY_OFF_TEXT": "#A3A9B1",
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
    "ON_BAD": "#FFFFFF",
    "BAD_TINT": "#FBEAEC",
    "BAD_EDGE": "#EFB7BF",
    "WARN": "#7F7500",
    "ROW_HOVER": "rgba(0, 0, 0, 0.035)",
    "WINDOW_TOP": "#F6F7F9",
    "WINDOW_BOTTOM": "#F6F7F9",
    "GLASS": "#F6F7F9",
    "SHADOW": "rgba(0, 0, 0, 0.10)",
    "TOAST": "#292C34",  # dark on the white page: easy to spot
    "TOAST_TEXT": "#FEFEFF",
    "TOAST_EDGE": "rgba(255, 255, 255, 0.10)",
    "TOAST_SHADOW": "rgba(0, 0, 0, 0.30)",
    "TOAST_DONE": "#4CC38A",  # (the dark look's: these sit on the dark toast)
    "TOAST_PROBLEM": "#DCCF45",
    "TOAST_PROBLEM_FILL": "#47452A",
    "TOAST_PROBLEM_EDGE": "rgba(220, 207, 69, 0.45)",
    "CHIP": "rgba(168, 99, 0, 0.1)",
    "FIELD": "#ECEEF2",
    "FIELD_HOVER": "#E4E7EC",
    "FIELD_BORDER": "rgba(0, 0, 0, 0)",
    "SEG_TRACK": "#E6E9EE",
    "SEG_ON": "#D5DAE2",
    "BLOCK": "#FFFFFF",  # white cards on the gray frame
    "FILL": "rgba(0, 0, 0, 0.05)",
}
COLORS = tuple(DARK)

# ---------------------------------------------------------------- the accent you pick (Settings › General)
# Listo's own is marigold, hand-set in DARK / LIGHT above. The others are built from one color by accent_set().
# Never red: red means failed or remove.
APP_ACCENT = "marigold"
ACCENTS = {  # key -> (name, on dark, on light)
    "marigold": ("Marigold", "#FFB81C", "#A86300"),  # FeatureSoup's golden yellow on dark
    "blue": ("Blue", "#4A90F7", "#2F6FDB"),
    "purple": ("Purple", "#8069F7", "#6A52E8"),
    "pink": ("Pink", "#F25FA6", "#C9387F"),
    "orange": ("Orange", "#F5893A", "#C2600E"),
    "green": ("Green", "#3DBE6E", "#1B8747"),
    "turquoise": ("Turquoise", "#2EBFB0", "#0D8178"),
    "graphite": ("Graphite", "#9B999F", "#68666D"),
}
DARK_ON_ACCENT = "#141314"  # words on a light accent (green, turquoise…), where white wouldn't read


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
            "CHIP": _rgba(base, 0.10),
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
        "CHIP": _rgba(base, 0.16),
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
