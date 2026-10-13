# Listo design rules

The rules for how Listo looks, reads and behaves. Follow them for every screen, dialog and control.
If a change needs something these rules don't cover, add a rule here in the same commit.

All numbers and colors live in **`listo/ui/style/tokens.py`**. The stylesheet (`listo/ui/style/theme.py`) and
every widget read from there. **Never type a size, spacing, font size, timing or color anywhere else.**
If you need a value that doesn't exist, add a token, give it a comment, and add it to the tables below.

The look is the Mac's: a flat backdrop, floating rounded glass panels, capsule buttons, round icon buttons,
light and dark. Marigold is Listo's own accent; people can pick another in Settings › General.

---

## 1. The window

```
┌───────────────┬────────────────────────────────────────────────────┬───────────────────┐
│ listo.        │ All Files 12        ( Search            )      (+) │ Convert To   (◉)(✕)│
│ Files ⌄    +  │ ⋮⋮ ▢ A001_C001.MOV                         Ready    │ ┌ preview ───────┐ │
│ ▸ All Files 12│      0:02 · 3840×2160 · 23.976p · HEVC              │ └────────────────┘ │
│   Videos    9 │      [ProRes 422 ▾]  → A001_C001.mov                │ Recipe             │
│   Photos    2 │ ⋮⋮ ▢ A001_C002.MOV                         31% ▬▬   │ Video|Photo|Audio  │
│   Audio     1 │ …                                                   │ ╭ Format… ╮        │
│ Progress ⌄    │                                                     │ ╭ ▸ Image ╮        │
│   To Convert 9│                                                     │ ╭ ▸ Burn-In ╮      │
│   Done      2 │ ─────────────────────────────────────────────────── │ ╭ ▸ Encoding ╮     │
│   Need a Look1│ 9 videos · 2 photos · 1 audio file   [Convert 12 Files]│ ╭ Saves To ╮    │
│ (NV) Your Name│ 0:42 of media                                       │ ╭ ▸ Advanced ╮     │
└───────────────┴────────────────────────────────────────────────────┴───────────────────┘
  left panel (glass)        the files (on the backdrop)                   right panel (glass)
```

**Where you are (left) → your files (middle) → what they become (right).**

- **The backdrop** is one flat color (`WINDOW_TOP`), drawn once (`components/glass.GlassRoot`). The file list sits
  directly on it. Panels float on glass, `GLASS_GAP` from the window's edges and from each other.
- **The left panel** (`window/sidebar.Sidebar`, a `components/panels.LeftPanel`, `SIDEBAR_W`): the wordmark on top
  (`TOOLBAR_H` tall, level with the toolbar), then two sections with small headings that fold when clicked:
  **Files** (All Files, Videos, Photos, Audio) and **Progress** (To Convert, Done, Need a Look), each row with its
  count. Need a Look's count turns `BAD` when something failed. The **+** beside Files (Add Files / a Folder /
  a Link) fades in only while the pointer is over that section (`FADE_MS`). At the bottom: "Update to …" when
  there is one, and the **profile card** (the computer user's initials and name; click it for Send Feedback,
  Check for Updates and Settings).
- **The toolbar** (`TOOLBAR_H`): the place's large title and count ("12", or "3 selected") on the left, the
  **search capsule** centred (it shrinks to `SEARCH_MIN` before anything collides), the primary round **+** on
  the right (Add Files / a Folder / a Link). Nothing else.
- **The file list** (`window/tables.FileList`): one painted row per file, `TABLE_ROW_H` tall (never a widget per
  row). Left to right: the grip (drag to reorder), a 16:9 thumbnail on `SCREEN`, the name, what the file is,
  then its format chip, a trim and the new name; on the right its status word (colored by tone) and progress
  bar, and its buttons (captions, trim, details, try again, show the new file), shown while the pointer is over
  the row or it's picked. Under the list, the **bar**: what's in the list (or the batch's progress), Show Files,
  Pause, Stop, Check Captions, and **Convert N Files**, the one primary button.
- **The right panel** (`panels/convert_to.ConvertPanel`, a `SidePanel`, `INSPECTOR_W`): **Convert To**. On top,
  the live preview (the picked clip, or the first, exactly as it will come out; the sample test pattern when the
  list is empty). Then Recipe, the Video / Photo / Audio tabs, the format card, the fold-away **Image**,
  **Burn-In** and **Encoding** cards, **Saves To** (joining, the example name, Where, Name) and **Advanced
  Options**. Its header: the title, a round eye (the bigger Preview window), the round ✕. It slides in
  (`DOCK_MS`) when the first file arrives or you click a file, and away with its ✕, Esc or a click on empty space
  in the list. View › Convert Settings (⌥⌘I) toggles it. On a smaller window it narrows (to `INSPECTOR_MIN`).
- **Size and place**: the first launch fills the screen (all but the menu bar and Dock); after that Listo opens
  where and how big you left it, if that still fits a screen.
- **The Mac title bar is Listo's own** (`components/titlebar.py`): the traffic lights, the wordmark centred,
  macOS drags the window. Double-click fills the screen, or (if it already does) goes to the smallest size,
  centred, animated. Windows and Linux keep the system bar, which follows light / dark.

---

## 2. Sizes

| Token | px | Used for |
|---|---|---|
| `CONTROL_H` | 34 | **Every** button, dropdown, text field, segmented control and round icon button |
| `SMALL_H` | 24 | Small round icon buttons inside rows and cards, naming token buttons |
| `CHIP_SM_H` | 18 | The format chip on a row |
| `SECTION_ADD` | 20 | A sidebar section's + |
| `TOGGLE_ROW_H` · `TOGGLE_W`×`TOGGLE_H` | 32 · 36×20 | An on/off row and its switch |
| `BAR_H` · `TRACK_H` · `HANDLE` | 6 · 4 · 14 | Progress bars · slider groove · slider handle |
| `NAV_H` · `NAV_GAP` | 30 · 2 | A sidebar row and the gap between rows |
| `TABLE_ROW_H` · `THUMB_W`×`THUMB_H` · `GRIP_W` · `STATUS_W` | 64 · 96×54 · 20 · 200 | A file row, its thumbnail, grip and status column |
| `SIDEBAR_W` · `INSPECTOR_W` / `INSPECTOR_MIN` · `TOOLBAR_H` | 232 · 420 / 360 · 64 | The window's parts |
| `ICON_SM` · `ICON` · `ICON_LG` · `ICON_XL` | 14 · 16 · 20 · 44 | Icons in small buttons · buttons and menus · placeholders · the empty list's arrow |

- A button, a dropdown and a text field side by side line up exactly. Never set a height on one control.
- Buttons size to their words (capsules). Never a fixed width.
- Every other fixed size (`PREVIEW_W/H`, `VIEWER_W/H`, `DIALOG_W`, `SETTINGS_SIZE`, `ALERT_W`, `WINDOW_SIZE`,
  `WINDOW_MIN`…) is a token with a comment saying where it's used.

## 3. Spacing: a 4-point grid

| Token | px | Use it for |
|---|---|---|
| `SPACE_1` | 4 | A label and its control; an icon and its text |
| `SPACE_2` | 8 | Related items: buttons in a row, options in a stack |
| `SPACE_3` | 12 | Between sections and cards inside a panel |
| `SPACE_4` | 16 | Padding of panels, bars and the main areas |
| `SPACE_5` | 24 | Padding of dialogs and the empty list |

Build layouts with `widgets.vbox(widget, margins, spacing)` / `hbox(...)`. Margins are `SPACE_*` tokens or 0.

## 4. Type and corners

**Inter** for everything; **IBM Plex Mono** only for codes (the log, an ffmpeg command, a checksum). Both are bundled
(`listo/assets/fonts`). Make a font with `theme.font(size, weight)`, never by hand.

| Token | px | Used for |
|---|---|---|
| `TEXT_XS` | 11 | Chips, menu headings |
| `TEXT_SM` | 12 | Section labels (`MUTED`, semibold), secondary text, tooltips, status words |
| `TEXT_MD` | 13 | Body text and every control (the default) |
| `TEXT_LG` | 14 | Panel titles, alert titles, the bar's title |
| `TEXT_XL` | 18 | Dialog titles, the empty list's headline |
| `TEXT_TITLE` | 24 | The page's large title in the toolbar and Settings |
| `TEXT_BRAND` | 21 | The "listo." wordmark only |

Corners: `RADIUS_XS` 4 (checkbox), `RADIUS_SM` 6 (chips, thumbnails), `RADIUS` 8 (fields, dropdowns, segmented
controls), `RADIUS_LG` 12 (cards, alerts), `GLASS_R` 18 (floating panels), `ROW_R` 9 (a row's highlight).
**Every list of choices looks the same** (menus, dropdown lists, the sidebar, Settings' sections): rows `LIST_ROW_H`
tall, inset `LIST_INSET` inside a list whose corners are `LIST_R`, so the corners run parallel. `app._RoundPopups`
makes menus and dropdown lists see-through so those corners are what you see, opens a button's menu just below
it (`MENU_GAP`), and stops the wheel from changing a dropdown or slider (it scrolls the panel instead).

## 5. Color

Every color token has a dark value (`tokens.DARK`) and a light one (`tokens.LIGHT`), the same names. Listo follows
the computer, also while it's open, unless Settings › General › Appearance picks Light or Dark
(`app.set_appearance`, `theme.apply`). Both are read from settings.json before the first window opens.

| Token | Use |
|---|---|
| `WINDOW_TOP` / `GLASS` / `GLASS_STROKE` / `GLASS_EDGE` / `GLASS_SHADOW` | The backdrop and the floating panels |
| `BG` / `PANEL` | Window background / dialogs |
| `BLOCK` | A card inside a panel (a soft tint, no outline) |
| `CARD` / `CARD_HOVER` / `CARD_SELECTED` / `ROW_HOVER` | Surfaces, hover, a picked row |
| `FIELD` / `FIELD_BORDER` / `FILL` | Text fields and dropdowns / their outline / segmented controls, bar tracks |
| `RAISED` (+ `_HOVER`, `_PRESS`) | Buttons, popups, the lifted row |
| `WELL` | Sunken text: the log, release notes |
| `SCREEN` / `SCREEN_TEXT` / `SCREEN_FAINT` | Behind pictures (players, previews, thumbnails): **black in both looks** |
| `BORDER` / `BORDER_STRONG` / `BORDER_HOVER` / `BORDER_CHECK` | Hairlines, outlines, hover, an empty checkbox |
| `TEXT` / `MUTED` / `FAINT` | Main text / secondary text / hints, counts, disabled |
| `ACCENT` (+ `_HOVER`, `_PRESS`) | The accent: the primary button, selection, progress, focus, the wordmark's dot |
| `ON_ACCENT` | Words and icons on the accent (dark on a light accent: never assume white) |
| `ACCENT_OFF` / `ACCENT_OFF_TEXT` | A disabled primary button |
| `ACCENT_TINT` / `ACCENT_EDGE` | The accent's wash and outline (the current sidebar row, a changed format chip, the drop target) |
| `CHIP` / `CHIP_HOVER` | Tinted capsules, the gap where a dragged row will land |
| `GOOD` / `WARN` / `BAD` (+ `BAD_TINT`, `BAD_EDGE`, `ON_BAD`) | Done / needs a look / failed (a danger button's hover, words on the alert's red button) |

- **The accent** comes from `tokens.use(scheme, accent)`: marigold (`APP_ACCENT`) is hand-set in both looks; the
  other choices in `tokens.ACCENTS` get a full set of shades from `tokens.accent_set()`. No choice is red (red means
  failed or delete). `tests/test_accent.py` checks every choice reads.
- **Read colors when you draw**: `tokens.NAME` / `theme.NAME` in a stylesheet rule or a `paintEvent`. Never keep
  one from startup: the look and the accent can change while Listo is open.
- **Icons** are line icons drawn as SVG in `theme._SVG` (24×24 grid, stroke 2, round caps): `theme.icon(name,
  theme.MUTED)` for buttons, `theme.menu_icon(name)` in menus. They redraw themselves in the current look and
  accent. A small icon that isn't a button is a `widgets.IconLabel(name, "MUTED")`. Never image files for UI icons.
  `tests/test_icons.py` checks every icon named in the code exists.
- Status color comes from data: `setProperty("tone", "done" | "warning" | "failed" | …)` and `widgets.repolish(w)`;
  the file list paints its status words from the same tones.
- Never call `setStyleSheet()` on one widget: add a rule to `theme._sheet()` under an object name.

## 6. Components

Use these; never build a control's look by hand.

**Buttons: text buttons are capsules, icon buttons are circles.**

| Kind | How | When |
|---|---|---|
| Primary | `setObjectName("Primary")` | The one main action in a view (Convert 12 Files, Send, Delete in an alert) |
| Normal | *(none)* | Everything else (Cancel, Show Files, Back Up…) |
| Quiet | `Ghost` | Small helpers inside a card, "Update to …" |
| Danger | `Danger` | Destructive actions in a form (Stop, Delete All): red words |
| Alert's yes | `DangerFill` | Only the destructive button inside an alert |
| Add | `widgets.add_chip("Caption")` | Adding a part at the end of a list |
| Round icon button | `widgets.circle_button(icon, tip)` (`CirclePrimary` for the +) | Every icon button in the toolbar or a panel header |
| Small round icon button | `widgets.icon_button(icon, tip)` (`IconBtn`) | Icon buttons inside a row or card |
| Section + | `SectionAdd` | The plain gray + beside a sidebar heading |

Every icon-only button has a tooltip. "…" when a button opens a window or a picker.

| Component | Use |
|---|---|
| `panels.LeftPanel` + `NavRow` | Every list of places on the left (the sidebar, Settings' sections) |
| `panels.SidePanel` | Every panel on the right; `header_icon()` adds its round buttons, the ✕ is always last |
| `widgets.Card` · `Disclosure` | Every group inside a panel. A Disclosure folds away and its header says what's changed ("Burn-In · 2 changed"), so nothing that changes the output hides silently. Each remembers whether it's open |
| `widgets.Section("Title")` | A labelled group of controls: Title Case label above, `SPACE_1` apart |
| `widgets.combo(items, current)` / `set_combo` / `disable_item` | **Every** pick-one setting, however few choices; extra detail in the item's tooltip |
| `widgets.PathCombo` | **Every** setting that points at a file or folder (LUT, Where); see below |
| `widgets.ToggleRow` | Every on/off setting: one full-width row, label left, switch right, the whole row clickable |
| `widgets.Segmented` | 2–3 views of the same thing (Video / Photo / Audio; Match System / Light / Dark) |
| `widgets.AccentPicker` | The Accent Color circles in Settings › General |
| `widgets.SearchField` | The toolbar's search capsule |
| `widgets.ElidedLabel` | One line that may not fit: cut with "…", the whole text in its tooltip |
| `widgets.Toast` | A few words at the bottom confirming what just happened (`TOAST_MS`); never a question |
| `dialogs/common.Alert` (`confirm`, `notice`, `ask_name`) | Every "are you sure" and every error that needs more than a toast |
| `widgets.button_row()` | The bottom row of every dialog: right-aligned, the main button last |
| `glass.GlassRoot` · `Dock` · `glass()` | The backdrop, the sliding right panel, marking a widget as glass |

**Picking a file or folder** (`widgets.PathCombo`), always the same three parts: the fixed choices first ("No LUT";
"In Source Folder", "Create Subfolder"); a separator and the files or folders picked before, most recent first
(the name, the full path in the tooltip; ones that are gone drop off); a separator and **"Choose a … …"** (the
system picker). No Change… buttons, no path labels, no "folder of files" modes. A setting a choice needs (the
subfolder's name) shows under it only for that choice.

## 7. Behavior

- **Nothing to save by hand.** Every setting saves itself to settings.json as you change it; quitting saves too.
- **Undo / Redo** (⌘Z / ⇧⌘Z, and Ctrl+Y on Windows) cover the Convert To settings, taking files off the list,
  their order, and a file's own format and trim. In a text box they undo the typing instead. A change taken
  straight back leaves no step.
- **Removing goes through a menu or an alert, never one click.** Delete or Backspace asks first, naming the file
  ("Remove A001_C001.MOV from the List?"). Taking files off the list never touches them on disk.
- **The alert** (`dialogs/common.Alert`): narrow (`ALERT_W`), the app icon, a bold question, one short line, Cancel
  and the action side by side (red when destructive). Return does it, Esc cancels.
- **Picking**: click picks, ⌘-click adds or removes one, Shift-click a range, ⌘A everything showing, ↑ / ↓ the
  file above or below. **Esc** (or a click on empty space in the list) picks nothing and closes the right panel.
- **Drag to reorder** by a row's grip: the row lifts onto a card and follows the pointer, the others slide apart
  to show where it will land, the list scrolls near its edges, Esc puts it back. List order is the order a joined
  video plays in and Continuous Timecode runs in. A batch keeps its order while it converts.
- **Only show what applies.** A control that depends on another appears only when that one is on. A feature this
  computer or these files can't use is hidden, not greyed out (hardware encoding without a hardware encoder,
  deinterlacing without interlaced files); an item in a format list stays, disabled, with a tooltip saying why.
- **Nothing moves when a group opens**: scrolling panels keep the scroll bar's room (`widgets.FitScroll`).
- **Names are shown as typed** (a file called "<b>clip.mov" stays that). Long ones are cut with "…" and shown
  whole in a tooltip.
- **Background work stays in the background.** Making captions runs in its own low-priority process and shows
  its progress on the clip's captions icon. Nothing slow runs on the window's thread.
- **Checking is watching.** Every picture of a clip can play with sound (double-click a clip, the preview, the
  Preview window, the caption check). Paused shows the exact result; playing shows the clip with its captions.
  Space plays and pauses when you're not typing.
- **Updates**: every launch (unless switched off in Settings › General), Listo checks for a newer version just
  after the window is up; if there is one, the update window opens by itself (never over another window, a menu
  or a batch that's converting), and "Update to …" stays at the bottom of the sidebar.

## 8. Motion

The right panel slides over `DOCK_MS` (ease-out) and the list beside it slides as a picture, then the real one
comes back. Dragged rows ease toward their places (`LIFT_EASE` per `LIFT_STEP_MS`). Small controls that come and go
fade over `FADE_MS`. Nothing bounces. The backdrop, the glass, icons and thumbnails are drawn once and reused.

## 9. Words

Listo talks like a helpful person, not like software.

- **No explaining on screen.** No hint sentences under fields; if a label needs explaining, change the label; if
  it still does, a short tooltip. Promises that matter stay ("Your files themselves stay where they are").
- **Few words.** Labels and headings 1–4 words, in plain language: "Double-Check Each File", not "Verify output
  integrity".
- **Title Case for labels**: buttons, menu items, section and card titles, dropdown choices, tabs, dialog titles.
  Small words stay lowercase inside (a, an, the, and, or, of, to, in, on, at, for, by, with, as, per); LUT, VHS,
  H.264 and .srt stay as they are. No ALL CAPS (the VHS caption look and STOP ■ are what's burned in, not labels).
- **Sentences stay sentences**: tooltips, placeholders, toasts, errors.
- Buttons are verbs ("Convert 8 Files", "Show Files"). "…" when they open a window.
- Errors say what happened and what to do: "Listo doesn't know .txt files."
- No exclamation marks (a thank-you aside), no emoji, no jargon. `&&` for a literal "&" in Qt buttons and
  menu items; `ToggleRow` draws its text as typed.

## 10. Checklist before you commit a UI change

1. No raw sizes or colors outside `tokens.py`; this prints only `theme.qcolor`'s color reader (1 px hairlines are
   the one allowed literal): `grep -rnE '[^{_A-Z0-9][0-9]{2,}px|#[0-9A-Fa-f]{6}|rgba' listo/ui --include=*.py | grep -v tokens.py`
2. New controls are `CONTROL_H` tall (or `SMALL_H`) and line up with their neighbours; icon buttons have tooltips.
3. Labels are short and in Title Case; sentences are plain sentences.
4. Screenshots look right in both looks and in a light accent:
   `QT_QPA_PLATFORM=offscreen LISTO_LOOK=light python tests/screenshot.py OUTDIR SAMPLES` (then `LISTO_LOOK=dark`,
   then `LISTO_ACCENT=yellow`).
