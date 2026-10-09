# Changelog

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
