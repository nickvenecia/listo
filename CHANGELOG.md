# Changelog

## Unreleased
- Fix: Preview window crashed when opened with clips in the list
- VHS look: much subtler colour fringing (1 px at 1080, a third of the strength)
- Captions use half the processor on the first run too (while the model downloads)
- **New layout**: settings on the left, your files in the middle, and an export panel on the right with a **live preview** of the selected (or first) clip — or a test pattern when the list is empty — plus where files go, their names and the Convert button. Click the preview for a bigger one you can scrub
- **Captions are made in the background** as soon as they're on (low priority, half the processor), with progress on each clip's CC icon; Convert opens the check once they're ready. Previews show sample text until the real words exist
- Groups renamed: Image, Burn-In, Encoding. Labels are in Title Case; no more all-caps section labels
- Fold arrows and icon buttons no longer go dark after you click them
- **Captions**: Listo listens to each clip on your computer (faster-whisper; nothing is uploaded), you check and fix the words, then they're burned in on top of everything (bars and burn-ins included). Clean or VHS look, black background on/off, words per line, 1–3 lines, text size, any language or auto-detect (follows people switching between Spanish and English). Optional .srt file. Click CC on a clip to check its captions any time
- **VHS look redone**: solid letters with a black outline, a little tape softness and colour fringing (no more milky glow). Badge choice: PLAY ► (blinks for the first seconds, then goes away), ● REC (red dot blinking) or none
- **Advanced options** are three groups: Picture, Text on screen, Sound & speed (each folds on its own and says how many settings are changed)
- **Menus**: File / Edit / View / Help with shortcuts (in the Mac menu bar; hidden on Windows and Linux so the window stays clean, shortcuts still work)
- Same-named clips (JVC restarts MOV01A in every PRG folder) never skip or replace each other: the second gets its folder's name (MOV01A_PRG002.mp4), and the list shows each one's folder
- JVC camcorder clips (.MOD / .TOD) read their matching .MOI automatically: real recording date (for Date & time burn-ins and {date} names) and the true 4:3 / 16:9 shape. .MOI and other camera sidecar files are left out of the list
- **Burn-ins work with any copy of ffmpeg**: Listo draws the text itself (no more greyed-out checkboxes with Homebrew's ffmpeg); timecode is frame-accurate, drop-frame included
- **Preview**: see one frame of the selected clip (or the first) exactly as it will come out, compare with the original, scrub to any moment
- **Upscaling**: Size is the size you get, up or down (720×480 4:3 camcorder footage at 1080 → 1440×1080, true shape)
- Scrolling over a dropdown or slider scrolls the panel instead of changing it
- Options only show when they apply (burn-in style, hardware encoding, interlaced footage, …)
- Camcorder .MOD / .VOB: burned-in timecode starts on the first frame, sound stays in sync
- **Advanced options**: the sidebar shows Format, Quality and Size; Frame, Interlaced footage, LUT, Burn in, Speed and Audio fold away (the header says how many are changed). Export options folds away Name taken and After converting the same way
- Burn-ins stay inside the picture: never on cinema bars or black bars, and sized to the picture
- **Burn in** is its own section: Timecode, File name and new **Date & time** (when the clip was shot, read from the clip, with a clock that runs as it plays), in a **Clean** or **VHS camcorder** style (VCR OSD Mono font)
- **Frame** section: anamorphic desqueeze (1.33×–2×), aspect ratios (16:9, 8:5, 4:3, 1:1, 4:5, 9:16, 1.85, 2:1, 2.35, 2.39) with Crop to fill, Add black bars, or Cinema bars on top with adjustable opacity
- Size now means the short edge (vertical video stays sharp), plus a 1440 option
- Phone clips: the recording time is read in the time zone it was shot in
- Non-square-pixel footage (DV, HDV) keeps its real shape when reshaped
- The list button opens a menu (Remove selected, Clear finished, Clear all) and uses a clear-list icon, so nothing is removed by accident
- Old recipes turn new options off instead of leaving them as they were
- Select files in the list like in Finder (click, ⌘-click, Shift-click, ⌘A) and press Delete / Backspace to remove them; the trash icon removes the selection, or clears the list when nothing is selected
- Dropdown lists have a rounded highlight and proper row spacing on every computer (was square on Mac)
- Add is now a + icon next to the trash
- README: the Listo name and icon belong to Nick; forks should use their own
- Export options: Where, Name and "Name taken" are dropdowns; all naming buttons show when building your own pattern
- Every button, dropdown and text field is the same height; spacing, type and colors follow one set of rules ([DESIGN.md](DESIGN.md))
- Linux download is now one double-clickable file (AppImage)
- Safer setup: the link tools Listo downloads are checked against their published checksums before use
- Only your own user account can send files to an open Listo window
- Problems are written to a log file (`listo.log` in Listo's data folder) to make bugs easier to track down
- No more leftover folders in the system temp folder after each launch
- Code reorganized (`listo/core` for converting, `listo/ui` for the window) with code rules in [CONTRIBUTING.md](CONTRIBUTING.md); ruff checks every change

## 2.2.0
- **Add a link**: paste a YouTube / Vimeo / Instagram link (or drag it from your browser, or ⌘V) and it downloads into the list, ready for any format — Audio only, GIF, H.264, ProRes…
  yt-dlp and Deno are fetched the first time and yt-dlp keeps itself up to date (daily check)
- **Trim** any video or audio file: pick start and end with frame previews; timecode follows the cut
- Paste a link right in the drop area
- Recipe is always a dropdown (save / update / delete live inside it)
- Format, flavor and quality are dropdowns
- LUT dropdown: your LUT folder + recently used LUTs, one click to apply
- "Save options" renamed "Export options" (short button in the bottom bar)
- Menus and dropdowns have truly rounded corners; menu icons stay readable when highlighted
- One **+ Add** button (files, a folder or a link) and a trash icon to clear the list
- Adding new files after a batch clears the ones that converted fine (failed / flagged ones stay)

## 2.1.0
- Top bar merged into the list toolbar (logo, Add files, Add folder, Clear list in one row)
- Less explanation text: one-line format rows with the file extension; details moved into hover tips
- Formats are one flat list again; recipes are only the ones you save
- Recipes: save your own combos of format, folder and naming
- Per-file formats: click a file's format tag to change just that file
- LUT (.cube) and burn-in timecode / file name for review copies
- Every converted video/audio file is re-read and checked against the original's length
- Convert two files at once
- Settings no longer lock during a batch; each file keeps the settings it was queued with
- Save options moved next to Convert and redesigned (live example, simple name styles, friendly token buttons)
- Add files / Add folder moved above the list; Clear dropdown replaced
- Smaller, more compact window
- Second launches (Open With / Send to) hand their files to the open window

## 2.0.0: SimpleConverter becomes Listo

A ground-up rewrite in Python so it runs on Mac, Windows and Linux, ships with ffmpeg inside, and builds downloadable apps on GitHub.

### Fixed (from SimpleConverter)
- **Could overwrite the original file.** `IMG_0001.MOV` → ProRes in the same folder wrote `IMG_0001.mov`, which is the same file on a Mac disk. Originals are now never overwritten.
- Files with the same name silently replaced each other (e.g. two cards' `00000.MTS` into one folder). Now: add a number, skip, or replace — your choice.
- ffmpeg could freeze mid-file on footage that prints lots of warnings (its error output was only read at the end).
- WAV/AIF/AIFF were accepted but always failed.
- "ProRes 422" was actually ProRes 422 HQ.
- Only the first audio track was kept; ProRes audio was cut to 16-bit.
- H.264 failed on odd-sized video.
- iPhone HDR came out washed-out in H.264.
- Unsupported files (MXF, TS, VOB, DV, WebM…) were silently ignored. Most are supported now, and the rest say why.
- Quitting mid-conversion left ffmpeg running (frozen, if paused). No cancel button.
- Confusing statuses ("Queued" for the active file); errors popped up mid-batch, and only the last one was shown.
- Files dropped in during a batch were never converted; duplicates could be added.
- Python port: drag-and-drop was broken and the done counter never moved.

### Also fixed during review
- "Replace" can no longer overwrite a *different* original (e.g. the JPEG in a RAW+JPEG pair)
- Naming keeps original file names exactly (proxies relink in Resolve/Premiere)
- WebM/H.264 no longer fail on 4-channel or 5.1 camera audio (downmixed to stereo for share formats)
- Correct color matrix when converting HDR to standard range
- 16-bit / float grayscale and CMYK photos convert with correct tones and colors; RAW no longer double-rotates
- Clear messages for Rewrap of VP9/AV1 and for clips too small for DNxHR/AV1
- Batch no longer gets stuck if a file is removed while it's still being read
- Clear dropdown replaced with "Remove finished" / "Clear list" above the queue
- Smaller app: unused Qt translations and plugins left out

### New
- New name, new UI: queue cards with thumbnails and file info, per-file progress and ETA, details for every result
- Photos: HEIC, camera RAW, JPEG, PNG, TIFF and WebP in and out (HEIC out too), with resize and EXIF kept
- More video: ProRes flavors, DNxHR, HEVC, AV1, WebM, GIF, edit proxies, Rewrap, audio extraction, resize
- Audio: WAV 24/16, AIFF, FLAC, MP3, AAC
- Naming templates with tokens and a live preview
- Save next to the original, in a subfolder, or in one folder
- Hardware encoding (VideoToolbox / NVENC), timecode and creation-date carry-over, deinterlace choice
- Drop files on the Dock icon; command-line mode (`python -m listo cli`)
