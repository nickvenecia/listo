# Listo design rules

The rules for how Listo looks and reads. Follow them for every screen, dialog and control.
If a change needs something these rules don't cover, add a rule here in the same commit.

All numbers and colors live in **`listo/ui/tokens.py`**. The stylesheet (`listo/ui/theme.py`) and
every widget import from there. **Never type a size, spacing, font size or color anywhere else.**
If you need a value that doesn't exist, add a token, give it a comment, and add it to the tables below.

---

## 1. Sizes

### Controls: one height for everything you click or type in

| Token | px | Used for |
|---|---|---|
| `CONTROL_H` | 34 | **Every** button, dropdown, text field and segmented control |
| `SMALL_H` | 24 | Chips on file cards, naming token buttons, icon-only buttons |
| `INDICATOR` | 16 | Standard icon box |
| `TOGGLE_ROW_H` · `TOGGLE_W`×`TOGGLE_H` | 32 · 36×20 | An on/off row and its switch |
| `BAR_H` | 6 | Progress bars |
| `TRACK_H` / `HANDLE` | 4 / 14 | Slider groove / handle |
| `SCROLL_W` / `SCROLL_MIN` | 10 / 30 | Scrollbar width / shortest handle |

- A button, a dropdown and a text field side by side must line up exactly. Never set a height on
  a single control; the stylesheet already sets it.
- Buttons size their width to their text (padding `0 SPACE_3`). Don't give buttons fixed widths.
- Dropdowns and text fields in the sidebar stretch to the full column width.

### Icons

| Token | px | Used for |
|---|---|---|
| `ICON_SM` | 14 | Icons inside small buttons (scissors, info, close) |
| `ICON` | 16 | Icons inside normal buttons and menus |
| `ICON_LG` | 24 | Placeholder icons in empty thumbnails |
| `ICON_XL` | 44 | The drop-zone arrow |

All icons are line icons drawn as SVG in `theme._SVG` and made with `theme.icon(name, color)`.
Add new icons there; don't load image files for UI icons.

### Fixed layout sizes

`SIDEBAR_W`, `THUMB_W/H` (16:9), `CARD_H`, `STATUS_W`, `CARD_BAR_W`, `PREVIEW_W/H`, `TIME_FIELD_W`,
`LINK_BOX_W`, `DIALOG_W`, `DETAILS_SIZE`, `WINDOW_SIZE`, `WINDOW_MIN`. Use these names, never the numbers.

---

## 2. Spacing: a 4-point grid

| Token | px | Use it for |
|---|---|---|
| `SPACE_1` | 4 | A label and its control; an icon and its text; lines inside one item |
| `SPACE_2` | 8 | Related items: buttons in a row, cards in the list, checkboxes in a stack |
| `SPACE_3` | 12 | Between sections inside a panel |
| `SPACE_4` | 16 | Padding of panels, bars and the main areas |
| `SPACE_5` | 24 | Padding of dialogs and the empty drop zone |

- Build layouts with the helpers in `listo/ui/widgets.py`:
  `vbox(widget, margins, spacing)` / `hbox(...)` (spacing defaults to `SPACE_2`),
  `combo(...)` for dropdowns, and `Section("Title")` for a labelled group (Title Case label + its controls, `SPACE_1` apart).
- Margins are `SPACE_*` tokens or `0`. Nothing else.

---

## 3. Type

Font: **Inter** (bundled in `listo/assets/fonts`). One family only.

| Token | px | Used for |
|---|---|---|
| `TEXT_XS` | 11 | Chips |
| `TEXT_SM` | 12 | Section labels (`MUTED`, semibold), secondary text: file details, hints, tooltips |
| `TEXT_MD` | 13 | Body text and every control (the default) |
| `TEXT_LG` | 14 | Emphasis: file names in the list, the footer title |
| `TEXT_XL` | 18 | Dialog titles, the empty-state headline |
| `TEXT_BRAND` | 21 | The "listo." wordmark only |

Weights: `WEIGHT_REGULAR` 400 for text, `WEIGHT_MEDIUM` 500 for controls,
`WEIGHT_SEMIBOLD` 600 for titles, labels and the primary button, `WEIGHT_BOLD` 700 for the wordmark and dialog titles.

---

## 4. Corners

| Token | px | Used for |
|---|---|---|
| `RADIUS_XS` | 4 | Small inner corners |
| `RADIUS_SM` | 6 | Chips, menu and list rows, small buttons |
| `RADIUS` | 8 | Buttons, fields, dropdowns, segmented controls |
| `RADIUS_LG` | 12 | File cards, popups and menus, boxes inside dialogs |
| `RADIUS_XL` | 16 | The drop zone |

Menus and dropdown lists are **always rounded**, with transparent corners, and so is the highlighted
row inside them. `app._RoundPopups` handles this for every `QMenu` and dropdown automatically: it makes
the popup window see-through and gives every dropdown `widgets.ComboItemDelegate` (rounded highlight,
`CONTROL_H - SPACE_2` rows, thin separator lines). Don't create popups that bypass it.

---

## 5. Color (dark theme)

| Token | Use |
|---|---|
| `BG` | Window background |
| `PANEL` | Sidebar, footer, dialogs |
| `CARD` / `CARD_HOVER` / `CARD_SELECTED` | File cards (normal / hover / selected), text fields |
| `RAISED` (+ `_HOVER`, `_PRESS`) | Buttons, popups |
| `WELL` | Sunken areas: thumbnails, previews, logs |
| `BORDER` / `BORDER_STRONG` / `BORDER_HOVER` / `BORDER_CHECK` | Hairlines, control borders, hover, empty checkbox |
| `TEXT` / `MUTED` / `FAINT` | Main text / secondary text / hints, labels, disabled |
| `ACCENT` (+ `_HOVER`, `_PRESS`) | Marigold. Selection, the one primary action, progress, focus |
| `ON_ACCENT` | Text and icons on marigold |
| `ACCENT_OFF` / `ACCENT_OFF_TEXT` | A disabled primary button |
| `ACCENT_TINT` / `ACCENT_EDGE` | Marigold wash and outline (custom chip, hot drop zone) |
| `GOOD` / `WARN` / `BAD` | Done / needs a look / failed |
| `BAD_TINT` / `BAD_EDGE` | Danger button hover / failed card border |

- Marigold means "selected" or "do this". **One** Primary button per view.
- Status color comes from data, not code: set `setProperty("tone", "done" | "warning" | "failed" | ...)`
  and call `widgets.repolish(w)`. The stylesheet maps tone to color.
- Never call `setStyleSheet()` on a single widget. Add a rule to `theme.STYLESHEET`
  under an object name instead.

---

## 6. Components

Use an object name to pick a style (`btn.setObjectName("Ghost")`). These are the only variants:

| Kind | Object name | When |
|---|---|---|
| Primary button | `Primary` | The single main action in a view (Convert, Done) |
| Normal button | *(none)* | Everything else in dialogs (Change…, Cancel) |
| Secondary button | `Secondary` | Buttons next to a primary one in dialogs |
| Quiet button | `Ghost` | Show files, Pause, Stop |
| Danger button | `Danger` | Destructive confirmations only |
| Icon-only button | `IconBtn` (QToolButton) | Toolbar (+ add, clear list), scissors, info, close. **Must** have a tooltip |
| Chip | `Chip` | The per-file format pill on a card |
| Token button | `Token` | "+ Name" buttons in the naming pattern builder |
| Tabs | `widgets.Segmented` | Switching between pages only (Video / Photo / Audio). Not for settings |
| Dropdown | `widgets.combo(items, current)` | **Every** pick-one setting, however few choices. Put extra detail in the item's tooltip |
| On/off setting | `widgets.ToggleRow` | Every on/off setting: one full-width row, label left, switch right, whole row clickable. Never side-by-side |
| Section | `widgets.Section` | Every labelled group in the sidebar and dialogs |
| Preview window | `preview_dialog.PreviewDialog` | One frame rendered with the real conversion steps |
| Fold-away group | `widgets.Disclosure` | "Advanced options": a chevron header with a changed-count summary |

Choosing a control:
- Pick one setting → **dropdown**, always, even with only 2–3 choices. Format, quality, size, LUT, recipe,
  Where, Name and Name taken are all dropdowns. Build them with `widgets.combo` / `set_combo` / `disable_item`.
- The result of a choice is shown once, in a live preview (the export panel's picture and "Saves As" box),
  not repeated under every option.
- Tabs (`Segmented`) only switch which page of settings you see.
- Actions that belong to a dropdown (Save recipe…, Choose a LUT file…) go **inside** that dropdown, below a separator.
- Menus open from icon buttons (the toolbar `+`) with `InstantPopup`; the menu arrow is hidden.
- The toolbar holds only the wordmark on the left and icon buttons on the right. No text buttons up there.

---

## 7. Words

Listo talks like a helpful person, not like software.

- **Fewer words.** Labels and section titles are 1–4 words ("Name taken", not "If that name is already taken"). If something needs explaining, put it in a tooltip, not on screen.
- Plain language: "Double-check each file", not "Verify output integrity". "Keep every audio track", not "Map all audio streams".
- **Title Case for labels**: section and group names, buttons, checkboxes, tabs, menu items, dropdown
  choices, dialog titles and card states ("Keep Every Audio Track", "Convert 3 Files", "Name Taken").
  Small words stay lowercase inside a label (a, an, the, and, or, of, to, in, on, at, for, by, with, as, per);
  acronyms and file things stay as they are (LUT, VHS, 4K, H.264, .srt, px). No ALL-CAPS labels.
- **Sentences stay sentences**: tooltips, hints, placeholders, progress and error messages, toasts, and the
  one-line descriptions under formats ("Plays everywhere", "Making captions in the background…").
- Buttons are verbs ("Convert 8 files", "Show files"). Use "…" when the button opens a dialog or file picker.
- Errors say what happened and what to do, without jargon: "Listo doesn't know .txt files."
- Promise safety where it matters: "Your original files are never touched".
- No exclamation marks, no emoji in the UI.

---

## 8. Layout of the main window

```
┌ ① Files ·········· N Files · + · ☰× ┬ ② Convert To (SIDEBAR_W) ┬ ③ Export (EXPORT_W) ┐
│ file list (cards, SPACE_2 apart)      │ Recipe                   │ Preview (live)      │
│   — or the drop zone (with the logo)  │ Video | Photo | Audio    │ Saves As example    │
│                                       │ Format, Quality, Size    │ Where · Name        │
│                                       │ ▸ Image ▸ Burn-In        │ ▸ Advanced Options  │
├ status · progress · Show Files/Pause/Stop  ▸ Encoding            │ [ Convert N Files ] │
└───────────────────────────────────────┴──────────────────────────┴─────────────────────┘
```
The window reads as three steps, left to right, in the order you work: **① add your files → ② choose what
they become → ③ choose where they go and convert.** Every panel starts with a `widgets.StepHeader`
(marigold number + Title Case name, `HEADER_H` tall) so the three line up. The two side panels share one
width (`SIDEBAR_W` = `EXPORT_W`); the file list takes the rest because names, paths and status need room.

- **The file list works like Finder / Explorer:** click selects, Cmd/Ctrl-click adds or removes one,
  Shift-click selects a range, Cmd/Ctrl+A selects all, Delete or Backspace removes the selection,
  Esc or a click on empty space clears it. Selected cards: `CARD_SELECTED` background + `ACCENT_EDGE` border
  (a converting card has a solid `ACCENT` border instead).
- The clear-list icon (`list-x`) opens a menu: Remove selected, Clear finished, Clear all. Actions that remove
  things always go through a menu or a confirmation, never a single click. They only take files off the list; nothing on disk is touched.
- A value along a range (opacity, photo quality) is a slider with its value shown as text next to it or in the section title.
- Use `&&` for a literal "&" in Qt buttons and labels (a single `&` becomes a keyboard-shortcut underline);
  `ToggleRow` draws its text as-is, so write a single `&` there.
- Every keyboard shortcut needs a visible way to do the same thing (a button, icon or menu item).
- **Only show what applies.** A control that depends on another appears only when that one is on
  (burn-in style only when a burn-in is ticked, fit only when the shape changes, bar opacity only for
  cinema bars). A feature this computer or these files can't use is hidden, not greyed out
  (hardware encoding without a hardware encoder; deinterlacing with no interlaced files in the list).
  The one exception: items in a format list stay, disabled with a tooltip saying why.
- **Nothing moves when a group opens.** Scrolling panels use `widgets.FitScroll`, which always keeps the scroll
  bar's space (invisible until there's something to scroll); give the content `SCROLL_GUTTER` less right margin.
- **Menus open on click, never on hover** (accidental opens, especially for the clear-list menu). Hover shows a tip.
  Tips and menus have rounded corners (`app._RoundPopups` makes their windows see-through).
- **Scrolling never changes a value.** The wheel over a dropdown or slider scrolls the panel
  (`app._RoundPopups` enforces it); values change only by clicking or dragging.
- **One identity everywhere.** The app icon is the "listo." wordmark on the dark tile (`scripts/make_icon.py`);
  on the Mac the title bar is ours (`ui/titlebar.py`): `BG`, a `BORDER` hairline, the wordmark centred.
  Nothing is said twice: counts live in the bottom bar, not also in a header.
- **Troubleshooting is one click, out of the way.** A faint terminal icon at the right of the bottom bar opens
  the debug console; it never interrupts and is never needed for normal work.
- **Background work stays in the background.** Slow jobs that aren't the conversion itself (making captions)
  run at low priority on half the cores, show their progress on the clip's own icon, and never take over the window.
  Heavy Python work (loading the speech model, listening) runs in its **own process**, not a thread: Python runs
  one thread at a time, so a busy thread makes the window stutter. Nothing slow is imported on the UI thread.
- **Checking is watching.** Every picture of a clip can play with sound (double-click a clip, the Export
  preview, the Preview window, the caption check). Paused shows the exact result; playing shows the clip
  with its captions. In lists that follow time (captions), the item on screen right now lights up
  (`CARD_SELECTED` + `ACCENT_EDGE`, time in `ACCENT`) and the list follows it. Clicking a line or a time
  jumps there. Space plays/pauses when you're not typing.
- **Optional steps are buttons, not interruptions.** Checking captions is its own button ("Check Captions · 2 New")
  above Convert; Convert never opens a window in your way (it only waits for work that must finish).
- **Captions read like their era.** The VHS caption look is ALL CAPS (tape closed captions were);
  the clean look keeps the words as spoken. The .srt file always keeps the real case.
- **Menus hold commands, the panel holds settings.** File / Edit / View / Help list actions with their
  shortcuts (add, select, remove, preview, convert). They live in the Mac menu bar; on Windows and Linux
  the bar is hidden (no strip across the window) and the shortcuts still work. Never put a setting in a menu.
- **Basic first, the rest folded away.** Each panel shows only what most people change every time
  (Video: Format, Quality/Flavor, Size; Photo: Format, Quality, Size; export panel: Preview, Where, Name).
  Everything else lives in three fold-away groups (`widgets.Disclosure`): **Image** (frame, interlacing, LUT),
  **Burn-In** (clip info, captions) and **Encoding** (audio tracks, speed) — closed by default, each remembered.
  The folded header always says how many advanced settings differ from a fresh start ("· 2 changed"),
  so nothing that changes the output is ever hidden silently. New settings go into Advanced unless
  nearly everyone needs them.
- Burn-ins always sit inside the picture: inside cinema bars, inside black bars, and on the cropped frame.
- The settings panel holds **what** the files become; the export panel holds **where** they go, **what they're called**,
  a live preview of the selected (or first) clip — the sample test pattern when the list is empty — and Convert.
  The preview always shows the real result: it runs the exact conversion steps on one frame (captions use
  sample text until the real words exist). Clicking it opens the big Preview window.
- Under the file list: status and progress, with Show Files / Pause / Stop when relevant. Convert lives at the
  bottom of the export panel and says "Converting…" while it works.
- New settings go into an existing section if they fit; a new section needs a short Title Case label.

---

## 9. Checklist before you commit a UI change

1. No raw numbers or colors outside `tokens.py`. This should print nothing:
   `grep -nE '[^{_A-Z0-9][0-9]{2,}px|#[0-9A-Fa-f]{6}|rgba' listo/ui/*.py | grep -v tokens.py`
   (1px hairline borders are the one allowed literal.)
2. New controls are `CONTROL_H` tall (or `SMALL_H` for chips / icon buttons) and line up with their neighbours.
3. Every icon-only button has a tooltip.
4. Labels are short and in Title Case; sentences (tooltips, hints, messages) are plain sentences.
5. Screenshots look right: `QT_QPA_PLATFORM=offscreen python tests/screenshot.py SHOTS OUTDIR`.
