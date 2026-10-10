# Changelog

## 2.3.2
- **The recording date and time travel inside the file**: every video Listo makes (MP4, MOV, WebM) now stores when it was shot, in the places Apple Photos, Finder, DaVinci Resolve, Premiere and Listo read: the standard creation time and Apple's creation date with your time zone. Camcorder .MOD clips get the date from their .MOI (with this computer's time zone for that day, daylight saving included), so you can upload, email or copy the new file, delete the .MOD and .MOI, and the real date stays. It's the same time the Date & Time burn-in shows: a trimmed clip gets the time of its new first frame, a joined video its first clip's time, and a clip that already had a creation time keeps it. File dates (Finder's "Created") are still copied as before

## 2.3.1
- **Glitches look like real tape, and no two are the same**: no more confetti of identical white dashes or a blocky band. Now the lines drift unevenly and jitter one by one, a band of lost tracking rolls through with streaky analog noise (every line different, ragged edges, torn lines leaving black at the left edge like a real VCR), a few lines get a fading streak of snow, the bottom bends and the picture sometimes hops. Every glitch gets its own shape, speed, position and strength, different for every clip
- **Burn-In is tidier**: with the VHS look, a **VHS Tape** section right under Clip Info holds four dropdowns that read top to bottom: what shows at the start (PLAY ► / ● REC / nothing), at the end (STOP ■ / nothing), the start & end screen (none / VCR blue / black / color bars & tone / custom color) and glitches (none / at each cut / now and then / often; the random ones also glitch the cuts). Old recipes keep their cut glitch
- **Updates inside Listo**: once a day Listo checks GitHub for a newer version; an **Update to …** button appears in the bottom bar, shows what's new, downloads the right file for your computer (checked against GitHub's fingerprint), swaps it in and reopens Listo. Also in ⋯ → Check for Updates…, where the daily check can be turned off
- **Download links that always give the newest version** at the top of the README (Mac Apple Silicon / Intel, Windows, Linux)
- The old SimpleConverter code (legacy/) is gone from the project; it stays in the history
- Tape glitches tear what's on the tape (picture, date, timecode, REC) but never PLAY / STOP or captions, which the VCR draws on top, like a real VCR
- **STOP ■ at the End** is its own switch under the PLAY badge (VHS look): STOP comes up for the last moment of the video like pressing stop on a VCR, carrying on to the end screen if there is one
- **Tape glitches look like real lost tracking** now, modelled on ntsc-rs (the open-source VHS emulator used as an After Effects / Resolve plugin): the lines wave sideways, a band of torn lines and snow rolls up the picture, the bottom bends (head switching), the picture hops, color slips and drops out, and the sound flutters, goes dull and crunches. It hits at once and settles, about a third of a second at each cut
- **Start and end screen**: VCR blue, black, SMPTE color bars with a 1 kHz tone, or any color you pick
- Tape Effects only show (and only apply) with the VHS Camcorder Look
- Tape Effects feel more like a real VCR: the glitch at joined cuts is shorter (about 6 frames) and subtler (a small sideways jolt, a faint band, a touch of color split), random glitches last a third of a second at most. With the blue screen and the VHS PLAY badge, PLAY blinks on the blue screen and carries on into the footage; at the end, **STOP ■** comes up on the last frames of the clip and stays on the blue screen, like pressing stop
- **Tape Effects** (Burn-In group): VCR blue screen at the start and end, a tracking glitch at each cut of a joined video, and random glitches now and then or often. The picture jitters, a noise band rolls through, colors split and the sound crunches; random moments are the same in the preview and the file
- **Storage & Cache** (the ⋯ menu in the bottom bar, or Help): see what Listo keeps on your computer (speech models, saved captions, link tools, logs, small extras), how big it is, and delete any of it. Settings, recipes and your files are never touched
- The bottom bar's ⋯ menu holds Storage & Cache, the Debug Console, the log file and About, on every system
- Joined videos: clips without their own timecode (camcorder .MOD, phones) get a counter that keeps running from clip to clip like a tape, through the whole joined video (each Convert is a new tape, from 00:00:00:00); clips with real timecode keep theirs. The VHS PLAY badge blinks only at the start of the joined video
- Space plays and pauses in every player (Export preview, Preview window, Check Captions), even when a button or dropdown has focus
- Player clocks read like time (00:18 / 07:29, hours when needed)
- Previous / next clip arrows beside Play in the Export preview, the Preview window and Check Captions; in the Export preview they also select that clip in the list, and a playing clip keeps playing
- Captions and Join Into One Video start off each time Listo opens (everything else is remembered; recipes still carry them)
- Every player (Export preview, Preview window, caption check, double-click) opens on the first frame instead of partway in
- **Much faster with big lists**: reading 400 clips used to keep the window busy for over 3 minutes; now about 10 seconds, and it stays responsive the whole time
- **Debug console**: the terminal icon in the bottom bar (or Help › Open Debug Console) opens a terminal window that shows everything Listo does as it happens: each file, the exact ffmpeg command, how long it took, and what went wrong if something fails. Run from a terminal, Listo prints the same there
- New app icon: the "listo." wordmark
- Mac: the title bar is dark like the rest of the app, with the "listo." logo in the middle, in line with the window buttons (one bar, drag it to move the window) (Windows and Linux get a dark title bar too)
- The file count left the top of the Files panel (the bottom bar already shows it)
- After joining, the bottom bar says how many clips were joined into one video
- Fix: a preview frame at the very end of a camcorder clip (with burn-ins on) could keep ffmpeg busy at full speed for a minute; previews stay just before the end, and burn-in layers always stop with the clip
- Fix: a crash when playing some camcorder clips (.MOD) on a Mac. Playback inside Listo no longer uses the Mac's hardware video decoder, and a clip only opens in the player once you press Play. Any hard crash is now written to crash.log next to the log file
- Changing caption accuracy (Fast / Balanced / Most Accurate) or picking a language now redoes the captions in the background; clips you fixed by hand ask first
- **Play videos inside Listo**: double-click a clip to play it with sound; the Export preview and the Preview window play too. Paused shows the exact result (LUT, frame, burn-ins, captions); playing shows the clip with its captions
- **Check Captions is its own button** (above Convert, with how many are new). Convert no longer stops to open it
- Caption check: click any line to jump there; **Add Caption** writes a new one where the clip is paused
- Joined videos are named after the first and last clip (e.g. MOV001-MOV014.mov), in whatever naming style you picked
- The live preview opens on a moment with a caption, and says "No speech heard in this clip" when there's nothing to caption
- **No more freezing when captions turn on**: speech-to-text now runs in its own low-priority process, so the window and the live preview stay smooth while the speech model loads and listens
- **Play in Check the Captions**: play the clip with sound; the caption on screen is drawn over the picture in the real look, its line lights up and the list follows along. Click a time to jump there; Space plays and pauses
- **Join Into One Video** (Export → Videos, with 2+ videos in the list): every clip, in list order, becomes one long video. Clips are matched to the first one (size, frame rate, sound; silent clips get silence) and put together without a second re-encode. Burn-ins, captions and trims still apply per clip, and the .srt covers the whole video
- VHS captions are ALL CAPS, like closed captions on tape (the clean look keeps the words as spoken)
- On/off settings are now switches in full-width rows (label left, switch right) instead of checkboxes
- Panels no longer shift or squeeze when a group opens (the scroll bar's space is always kept)
- Hover tips have rounded corners
- Each clip's length comes first in its details, so it's never cut off
- The window reads as three numbered steps: **1 Files → 2 Convert To → 3 Export**, with matching headers and equal side panels; the logo sits in the empty drop area
- Cleaner sample picture for the preview: a soft colour gradient instead of a test pattern
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
