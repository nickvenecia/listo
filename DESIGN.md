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
| `INDICATOR` | 16 | Checkbox box |
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
  `combo(...)` for dropdowns, and `Section("Title")` for a labelled group (caps label + its controls, `SPACE_1` apart).
- Margins are `SPACE_*` tokens or `0`. Nothing else.

---

## 3. Type

Font: **Inter** (bundled in `listo/assets/fonts`). One family only.

| Token | px | Used for |
|---|---|---|
| `TEXT_XS` | 11 | SECTION LABELS (caps, letter-spaced, `FAINT`), chips |
| `TEXT_SM` | 12 | Secondary text: file details, hints, tooltips |
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
| `RADIUS_XS` | 4 | Checkbox box |
| `RADIUS_SM` | 6 | Chips, menu and list rows, small buttons |
| `RADIUS` | 8 | Buttons, fields, dropdowns, segmented controls |
| `RADIUS_LG` | 12 | File cards, popups and menus, boxes inside dialogs |
| `RADIUS_XL` | 16 | The drop zone |

Menus and dropdown lists are **always rounded**, with transparent corners. `app._RoundPopups`
handles this for every `QMenu` and dropdown automatically. Don't create popups that bypass it.

---

## 5. Color (dark theme)

| Token | Use |
|---|---|
| `BG` | Window background |
| `PANEL` | Sidebar, footer, dialogs |
| `CARD` / `CARD_HOVER` | File cards, text fields |
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
| Secondary button | `Secondary` | Footer buttons beside the primary one (Export options) |
| Quiet button | `Ghost` | Toolbar actions (+ Add), Show files, Pause, Stop |
| Danger button | `Danger` | Destructive confirmations only |
| Icon-only button | `IconBtn` (QToolButton) | Trash, scissors, info, close. **Must** have a tooltip |
| Chip | `Chip` | The per-file format pill on a card |
| Token button | `Token` | "+ Name" buttons in the naming pattern builder |
| Tabs | `widgets.Segmented` | Switching between pages only (Video / Photo / Audio). Not for settings |
| Dropdown | `widgets.combo(items, current)` | **Every** pick-one setting, however few choices. Put extra detail in the item's tooltip |
| Checkbox | `QCheckBox` | On/off settings. Label says what happens when it's **on** |
| Section | `widgets.Section` | Every labelled group in the sidebar and dialogs |

Choosing a control:
- Pick one setting → **dropdown**, always, even with only 2–3 choices. Format, quality, size, LUT, recipe,
  Where, Name and Name taken are all dropdowns. Build them with `widgets.combo` / `set_combo` / `disable_item`.
- The result of a choice is shown once, in a live preview (e.g. the example box in Export options),
  not repeated under every option.
- Tabs (`Segmented`) only switch which page of settings you see.
- Actions that belong to a dropdown (Save recipe…, Choose a LUT file…) go **inside** that dropdown, below a separator.
- Menus open from buttons with an icon (`+ Add`); the menu arrow is hidden.

---

## 7. Words

Listo talks like a helpful person, not like software.

- **Fewer words.** Labels and section titles are 1–4 words ("Name taken", not "If that name is already taken"). If something needs explaining, put it in a tooltip, not on screen.
- Plain language: "Double-check each file", not "Verify output integrity". "Keep every audio track", not "Map all audio streams".
- Sentence case everywhere ("Export options", not "Export Options"). Section labels are drawn in caps by the
  stylesheet; write them in sentence case in code.
- Buttons are verbs ("Convert 8 files", "Show files"). Use "…" when the button opens a dialog or file picker.
- Errors say what happened and what to do, without jargon: "Listo doesn't know .txt files."
- Promise safety where it matters: "Your original files are never touched".
- No exclamation marks, no emoji in the UI.

---

## 8. Layout of the main window

```
┌ toolbar: wordmark · + Add ·············· N FILES · 🗑 ┬ sidebar (SIDEBAR_W) ─┐
│ file list (cards, SPACE_2 apart)  — or drop zone     │ RECIPE dropdown      │
│                                                      │ Video | Photo | Audio│
│                                                      │ sections…            │
├ footer: summary ·········· Export options · Convert ──┴──────────────────────┤
```

- The sidebar holds **what** the files become; Export options holds **where** they go and **what they're called**.
- The footer's right side is always: Show files / Pause / Stop (when relevant), Export options, then the Primary action.
- New settings go into an existing section if they fit; a new section needs a short caps label.

---

## 9. Checklist before you commit a UI change

1. No raw numbers or colors outside `tokens.py`. This should print nothing:
   `grep -nE '[^{_A-Z0-9][0-9]{2,}px|#[0-9A-Fa-f]{6}|rgba' listo/ui/*.py | grep -v tokens.py`
   (1px hairline borders are the one allowed literal.)
2. New controls are `CONTROL_H` tall (or `SMALL_H` for chips / icon buttons) and line up with their neighbours.
3. Every icon-only button has a tooltip.
4. Text is short, plain and in sentence case.
5. Screenshots look right: `QT_QPA_PLATFORM=offscreen python tests/screenshot.py SHOTS OUTDIR`.
