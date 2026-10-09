# Listo: notes for Claude Code

Cross-platform (macOS / Windows / Linux) batch converter for video, photos and audio.
Python 3.12 + PySide6 (Qt Widgets) UI, ffmpeg/ffprobe for video and audio, Pillow + pillow-heif + rawpy for photos.
Shipped as a PyInstaller app with ffmpeg bundled; GitHub Actions builds the downloads.
The owner is a filmmaker (director/DP/editor/colorist), not a full-time developer. Explain changes in plain words.

## Read these first
- **[DESIGN.md](DESIGN.md)**: how the app looks and reads. Sizes, spacing, type, colors, which control to use, wording.
  All values live in `listo/ui/tokens.py`; never type a size or color anywhere else.
- **[CONTRIBUTING.md](CONTRIBUTING.md)**: code rules. Layout, style (ruff), safety rules, threads, tests, commits.
- Before finishing any change: `ruff format . && ruff check . && python -m pytest -q`.

## Layout
```
listo/
  core/            Converting. No Qt imports.
    engine.py      Conversion: one file start→finish (plan path, temp file, run, rename, copy dates, verify)
    video.py       build(): (file, MediaInfo, Settings, Capabilities) -> ffmpeg args.  All video/audio presets live here;
                   preview_plan(): one PNG frame through the exact same steps (used by the Preview window)
    captions_worker.py  the separate low-priority process that runs captions.transcribe (multiprocessing "spawn",
                   a Pipe of small messages); ping() is used by --smoke-test
    join.py        "Join Into One Video": Conform (shape every part must match), Join (concat the parts, no
                   re-encode, combined .srt, cleanup), mismatch() for Rewrap
    captions.py    speech to text (faster-whisper, model downloaded into data_dir()/models on first use; audio decoded
                   by our ffmpeg, PyAV left out via a stub), Transcript store (data_dir()/captions, keyed by path+size+mtime),
                   split_cues / wrap / for_output (trim shift) / to_srt
    burnin.py      burn-ins drawn by Listo (Pillow PNGs + overlay; digits via crop-expression "strips"), so they
                   work with ANY ffmpeg (no drawtext). Timecode math mirrors probe.tc_add (drop-frame aware)
    frame.py       picture shape: desqueeze, aspect crop / black bars / cinema bars, short-edge resize
                   (shared by video.build and naming.output_size so names and files agree)
    photo.py       photo decode (incl. RAW/HEIC) + save
    presets.py     preset/format definitions + Settings dataclass (persisted as JSON in QSettings)
    naming.py      {token} templates, output folder rules, collision handling (never overwrite the source)
    probe.py       ffprobe JSON -> MediaInfo; file-type lists by extension; timecode math
    runner.py      ffmpeg subprocess: -progress parsing, stderr drained on a thread, pause/resume via psutil
    tools.py       find bundled/system ffmpeg; encoder/filter detection; hardware encoder test; popen_kwargs()
    links.py       "Add a link": yt-dlp (+ Deno for YouTube) downloaded on first use into paths.tools_dir(),
                   SHA-256 checked against the release's published sums; yt-dlp -U at most daily
    fileutil.py    copy file dates (incl. creation time on mac/win), reveal in Finder/Explorer
    paths.py       per-user folders: data_dir(), tools_dir(), log_dir(), downloads_dir() (~/Downloads/Listo)
    log.py         rotating log file (listo.log in log_dir(), 5 MB x 3); also printed to the terminal when run from one
    tape.py        Tape effects: glitch_windows (cut + seeded random moments), video_graph / audio_filters (applied last in
                   video.build, timeline-enabled filters), make_blue (a matching blue-screen piece joined on via
                   join.concat_args; Conversion._wrap_blue for single videos, Join._add_blue for joined ones)
    storage.py     Storage & Cache: kinds of data in data_dir() with sizes, clear(key) (logs are emptied, not deleted)
    console.py     Debug console: opens the system terminal following the log files live (Mac .command file,
                   Windows PowerShell, Linux terminal); turns on DEBUG logging for the session
    sample.py      the sample clip (test pattern + timecode + date + tone) the live preview uses when the list is empty
  ui/
    tokens.py      THE design tokens (sizes, spacing, type, radii, colors)
    theme.py       stylesheet built from tokens, SVG icons (icon(name, color))
    widgets.py     shared building blocks: vbox/hbox, Section, combo/set_combo (dropdowns), Segmented (tabs), FlowLayout, repolish
    main_window.py queue + batch controller, toolbar, drop zone, footer
    sidebar.py     recipe dropdown + Video/Photo/Audio format settings (all dropdowns)
    titlebar.py    Mac only: Listo's own title bar (Qt ExpandedClientAreaHint, dark, "listo." centred; the Mac's
                   title text hidden via one AppKit call). Windows/Linux keep the system bar, dark via styleHints
    player.py      ClipPlayer: Qt player + caption overlay (burnin.caption_still) + "still" layer for the exact
                   result frame while paused (owners render it on `settled`); still-frame fallback without Qt's player
    storage_dialog.py  Storage & Cache window (sizes, Delete per kind, Delete All); MainWindow._storage_busy/_cleared
    caption_editor.py  "Check the Captions" (its own button over Convert): plays the clip, lights up the current line,
                   click a line to jump, Add Caption at the playhead; accepting marks clips reviewed
    preview_dialog.py  "Preview": ClipPlayer at full size, converted vs original; double-clicking a clip opens it playing
    export_panel.py  the right panel: live preview (a small ClipPlayer; MainWindow._render_live / _live_settled), Saves As example, Where, Name,
                   Advanced (Name taken / After converting), and the Convert button (MainWindow adds it to .bottom)
    trim_dialog.py start/end sliders with ffmpeg frame-grab previews
    job_card.py    one file in the list
    workers.py     threads (ConvertThread, probes/thumbnails in QThreadPool, link downloads)
  cli.py           `python -m listo cli ...`: same engine, no UI (great for testing)
  app.py           QApplication, fonts, stylesheet, rounded popups, single-instance hand-off, --smoke-test
scripts/make_icon.py      draws listo/assets/icon.png (the "listo." wordmark tile) from the tokens and Inter
scripts/fetch_ffmpeg.py   downloads static ffmpeg for the current OS into vendor/ffmpeg (gitignored)
listo.spec                PyInstaller recipe
packaging/                mac entitlements, Windows Inno Setup script, Linux .desktop + install.sh + build_appimage.sh
.github/workflows/build.yml  lint, then build + test + smoke-test on 4 runners; tags v* publish a Release
legacy/                   the original SimpleConverter (Swift + first Python port), for reference only
```

## Rules that matter
- **Never overwrite the source file.** `naming.resolve_output` compares paths case-insensitively and with samefile, because macOS/Windows disks ignore case. Keep it that way.
- ffmpeg output always goes to a hidden temp file in the destination folder, then `os.replace` on success. Pass `-f <muxer>` explicitly since the temp name's extension can't be trusted.
- Always drain ffmpeg's stderr while it runs (pipe-fill deadlock was a real bug in the old app).
- On Windows, every subprocess call needs `popen_kwargs()` (no console window flashes).
- UI work happens on the main thread; conversions run in `ConvertThread`, probes and thumbnails in a `QThreadPool`. Communicate with signals.
- Settings never lock. When a file joins a batch it captures `Item.base` (a copy of the panel's Settings);
  `MainWindow.eff(item)` = base (or live panel) + the file's own `Item.override` (format only, see presets.OVERRIDE_KEYS).
- Up to 2 conversions run at once (`Settings.parallel`); `MainWindow.active` maps item id -> ConvertThread.
  Output names are reserved under `engine._plan_lock`, and every queued source path is pre-reserved so "Replace" can't hit another original.
- Recipes are user-made only (full Settings dicts in QSettings "recipes"); `presets.BUILTIN_RECIPES` is intentionally empty.
- Trim is per file (`Item.trim` -> `Conversion(trim=)` -> `video.build(trim=)`): `-ss` before `-i`, `-t` after;
  timecode is shifted with `probe.tc_add` (drop-frame aware). Progress/verify use the trimmed length (`Item.length`).
- Filter order in video.build: deinterlace → tone-map → LUT → frame (desqueeze, crop/bars/matte) → resize → even size → burn-ins → conform (join parts only).
- `frame.frame_plan` also returns the picture area (fractions, without bars); burnin.plan keeps everything inside it.
- Captions flow: as soon as captions are on and a clip with sound is read, MainWindow._sync_captions() queues it on the
  background TranscribeThread, which hands clips to a separate process (core/captions_worker.py: nice'd, half the cores;
  progress only on the card's CC icon). Never run speech-to-text on a thread in the app process: it holds Python's
  lock and froze the window for 10-15 s. Entry points (listo/__main__.py, launcher.py) call
  multiprocessing.freeze_support() and keep their code under `if __name__ == "__main__"` (spawn re-imports them).
  Tests swap the process's target (TranscribeThread.target -> tests/speech_standin.py). Checking is separate:
  the "Check Captions" button (MainWindow.check_captions, shows "N New") opens CaptionEditor. Convert ->
  _captions_ready() only waits if some are still being made (then restarts itself), then converts with
  Conversion(captions=cues) using the captions as they are. Previews use captions.sample_cues() until the real words exist. Captions are the last overlay
  (BurnPlan.captions: an ffconcat list of per-cue PNGs), so they sit on top of bars and burn-ins.
- Playback (ui/player.py ClipPlayer, used by the Export preview, Preview window and caption check): Qt's player
  (PySide6-Addons QtMultimedia, QGraphicsVideoItem) with the caption drawn by burnin.caption_still on top. Paused =
  the exact result frame (owners render on `settled`, set_still(pm, at)); playing = the clip as shot + captions.
  No player or a file it can't open -> still frames only (`fallback`). No sound output in headless runs
  (offscreen): asking Qt for an audio device there can crash. Call release() when a dialog closes.
  Qt's player opens a clip only on the first Play (until then the still frames are the picture), and hardware
  decoding is off for playback (QT_FFMPEG_DECODING_HW_DEVICE_TYPES="," in app.main / player.py): Qt's player
  segfaulted on MPEG-2 .MOD on a Mac after VideoToolbox refused it. Hard crashes go to crash.log (faulthandler).
- Changing caption_model / caption_language redoes captions made another way (MainWindow._needs_redo: Transcript.model
  / .language differ). Hand-edited ones only after a Yes (MainWindow._redo_edited); the old captions stay until the new arrive.
- Joined videos are named with {name} = "FIRST-LAST" (join.joined_name), every naming style still applies.
- Join: Settings.join + 2+ videos (not GIF). MainWindow.start() makes a JoinJob; each clip converts as a "part"
  (Conversion(target=hidden parts folder, conform=first clip's size/rate/48 kHz stereo; silent clips get a silent
  track; per-file format overrides don't apply), then _start_join() runs JoinThread (core/join.Join: concat demuxer,
  -c copy). Stop before gluing -> parts deleted and those clips back to ready.
- Window = three steps: ① files (left, footer under them) | ② Convert To settings (sidebar.py) | ③ Export (export_panel.py),
  each topped by widgets.StepHeader. Sidebar groups:
  Image / Burn-In / Encoding (sidebar.GROUPS lists what each "N changed" counts). Labels are Title Case (DESIGN.md §7).
- Camera sidecars (probe.SIDECAR_EXTS) are never listed. JVC .MOI next to .MOD/.TOD is read in probe (read_moi):
  recording date -> info.created (naive wall time), aspect -> info.sar (JVC flags widescreen MOD as 4:3).
- Burn-ins never use ffmpeg's drawtext (Homebrew's ffmpeg lacks it). With burn-ins the picture goes through -filter_complex,
  starts at pts 0 (setpts=PTS-STARTPTS, audio asetpts) so time-based digit expressions line up; the engine deletes the PNGs (Plan.cleanup).
- Joined videos: join.running_timecodes() gives clips without timecode a tape-style running counter through the whole
  joined video (one Convert = one tape, from 0); passed as Conversion(timecode=) -> video.build(timecode=) (start_tc for
  the burn-in and -timecode). Only the first part keeps the PLAY badge (REC stays on every part).
- Space = play/pause via player.space_plays(window, player) (a WindowShortcut; text fields keep their spaces).
- Tape effects never apply to rewrap / GIF / audio (tape.NO_EFFECTS). With the blue screen on, a single video is
  conformed to itself (48 kHz stereo) so the blue pieces match; its .srt and length check shift by tape.BLUE_SECONDS.
- presets.SESSION_ONLY (captions, join) reset to off at every launch; everything else in Settings is remembered.
- ClipPlayer.step(-1/+1) = the previous / next clip arrows; owners call set_steps(has_prev, has_next).
- New Settings fields must have defaults that mean "off": old recipes are applied through `Settings.complete()`.
- Long lists (hundreds of clips): never do list-wide work per file. Use MainWindow._refresh_soon() (bundles the
  footer / captions status / sample into one pass, waiting longer for longer lists); card setters skip unchanged
  values; theme.icon / pixmap are cached; read captions/burn-in settings in loops with MainWindow._base(it)
  (no copy). tests/test_big_list.py guards this (400 clips once took 205 s of window time; now ~10 s).
- Logging: conversions log the source, target, exact ffmpeg command, time taken and ffmpeg's last words on failure;
  uncaught errors (any thread) are logged by app._log_uncaught. Keep new features logging what they do at INFO.
- Selection: `MainWindow.selected` (item ids) + `_anchor` for Shift-click; cards emit `pressed`; the clear-list icon opens a menu (Remove selected / Clear finished / Clear all).
- Link items start in state "downloading" (kind "link"); when done they become a normal file item and get probed.
- A second launch hands its files to the open window over a QLocalServer (app.py) — needed for Windows "Send to" / Linux.
- Don't add presets that need encoders missing from common static ffmpeg builds without gating on `caps.has_encoder`.

## Commands
```bash
pip install -r requirements-dev.txt     # includes ruff, pytest, pyinstaller
python scripts/fetch_ffmpeg.py         # or have ffmpeg on PATH
python -m listo                        # run the app
python -m listo cli FILES --video prores --variant 3 --out OUT --naming "{name}_{preset}"
python -m pytest -q                    # unit + integration tests (integration needs ffmpeg on PATH)
python tests/samples.py OUTDIR         # generate tricky sample media
QT_QPA_PLATFORM=offscreen python tests/screenshot.py SHOTS OUTDIR   # UI screenshots without a display
pyinstaller listo.spec --noconfirm     # build the app into dist/
```

## Releasing
Bump `__version__` in `listo/__init__.py`, commit, `git tag vX.Y.Z && git push --tags`.
CI attaches: Listo-mac-apple-silicon.dmg, Listo-mac-intel.dmg, Listo-windows-setup.exe, Listo-windows-portable.zip,
Listo-linux-x64.AppImage, Listo-linux-x64.tar.gz.

## Ideas not done yet
- Watch folder ("anything dropped in here gets converted")
- A real Finder Quick Action (today: right-click > Open With > Listo on Mac, Send to > Listo on Windows)
- LUTs on photos
- 16-bit TIFF from RAW (Pillow is 8-bit for RGB; would need tifffile)
