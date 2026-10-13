# Listo: notes for working on the code

Cross-platform (macOS / Windows / Linux) batch converter for video, photos and audio.
Python 3.12 + PySide6 (Qt Widgets) UI, ffmpeg/ffprobe for video and audio, Pillow + pillow-heif + rawpy for photos.
Shipped as a PyInstaller app with ffmpeg bundled; GitHub Actions builds the downloads.
The owner is a filmmaker (director/DP/editor/colorist), not a full-time developer. Explain changes in plain words.

## Read these first
- **[DESIGN.md](DESIGN.md)**: how the app looks and reads. Sizes, spacing, type, colors, which control to use, wording.
  All values live in `listo/ui/style/tokens.py`; never type a size or color anywhere else.
- **[CONTRIBUTING.md](CONTRIBUTING.md)**: code rules. Layout, style (ruff), safety rules, threads, tests, commits.
- Before finishing any change: `ruff format . && ruff check . && python -m pytest -q`.
- Commit messages: a short plain summary, nothing added after it (no sign-off, co-author or tool lines).
  Commits are authored as Nick Venecia <nicholasvenecia@gmail.com> (this repo's git config).

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
    presets.py     preset/format definitions + Settings dataclass (saved in settings.json, key "settings")
    naming.py      {token} templates, output folder rules, collision handling (never overwrite the source)
    probe.py       ffprobe JSON -> MediaInfo; file-type lists by extension; timecode math; file_date /
                   shot_moment / recorded(): when a clip was shot (wall time / with its zone / what files store)
    runner.py      ffmpeg subprocess: -progress parsing, stderr drained on a thread, pause/resume via psutil
    tools.py       find bundled/system ffmpeg; encoder/filter detection; hardware encoder test; popen_kwargs()
    links.py       "Add a link": yt-dlp (+ Deno for YouTube) downloaded on first use into paths.tools_dir(),
                   SHA-256 checked against the release's published sums; yt-dlp -U at most daily
    fileutil.py    copy file dates (incl. creation time on mac/win), reveal in Finder/Explorer
    paths.py       per-user folders: data_dir(), tools_dir(), log_dir(), downloads_dir() (~/Downloads/Listo)
    log.py         rotating log file (listo.log in log_dir(), 5 MB x 3); also printed to the terminal when run from one
    tape.py        Tape effects (VHS look only, tape.applies): glitch_windows (cut + seeded random moments),
                   video_graph (one geq per glitch, enable-gated, modelled on ntsc-rs; per-line values cached
                   in geq vars, so keep the expression's st/ld layout) / audio_filters, applied last in
                   video.build; make_blue (a matching start/end screen piece: VCR blue, black, a color, or
                   SMPTE bars + 1 kHz tone; joined on via join.concat_args; Conversion._wrap_blue for single
                   videos, Join._add_blue for joined ones)
    storage.py     Storage & Cache: kinds of data in data_dir() with sizes, clear(key) (logs are emptied, not deleted)
    console.py     Debug console: opens the system terminal following the log files live (Mac .command file,
                   Windows PowerShell, Linux terminal); turns on DEBUG logging for the session
    update.py      Updates: check() GitHub's latest release of REPO, install_kind() (mac-app / windows-installed /
                   windows-portable / appimage / linux-folder / source), download() (size + SHA-256 from GitHub's
                   digest), prepare() writes a helper script that waits for Listo to quit, swaps the new version in
                   and reopens it; run() starts it detached; whats_new(notes) -> ("heading" | "item" | "text", words)
                   blocks without the download table or what GitHub adds (credits, Full Changelog)
    progress.py    BatchClock: time left for the whole batch (done / worked, smoothed, paused time left out; once it
                   has an answer it never goes back to none); time_left() rounded words ("About 4 min left")
    sample.py      the sample clip (test pattern + timecode + date + tone) the live preview uses when the list is empty
    store.py       settings.json (Prefs: value/setValue like QSettings; prefs()/save_pref()), atomic write_json /
                   write_text, set_aside (unreadable files kept as <name>.unreadable-<time>), loads(), back_up()
    web.py         web_link(): the one "is this a web link" test (http(s) only, no file:/javascript:/name@host)
  services/
    feedback.py    Send Feedback: an outbox in data_dir()/feedback until a sender or ADDRESS is set up
  ui/
    style/tokens.py  THE design tokens (sizes, spacing, type, radii, timing, colors). DARK and LIGHT color dicts
                   (same names); APP_ACCENT "marigold" hand-set in both; ACCENTS + accent_set() build the others;
                   use(scheme, accent) points every color name at the look in use
    style/theme.py   _sheet() (the stylesheet), apply(app, appearance, folder, accent), load_fonts() (Inter + IBM
                   Plex Mono), font(), wordmark(), plain_tip(), qcolor(); SVG icons: icon(name, theme.MUTED) /
                   menu_icon(name) (a _Themed engine maps the color back to its token, so icons follow the look)
    components/widgets.py  Section, Card, Disclosure, ElidedLabel, Segmented, ToggleRow, AccentPicker, combo/set_combo,
                   PathCombo (every file / folder setting; DESIGN.md §6), SearchField, Toast (MainWindow.toast(text, tone):
                   "done" / "problem" / "" for news; floats over the list above the bar), TextBox, IconLabel,
                   circle_button / icon_button, FlowLayout, FitScroll, PanelHeader, ComboItemDelegate
    components/panels.py   LeftPanel + NavRow (the sidebar, Settings' sections), SidePanel (the right panel)
    components/glass.py    GlassRoot (backdrop + glass behind floating panels), Dock (the right panel sliding in/out)
    components/empty.py    EmptyPage + StartTile: the empty list's start tiles (Add Files… / a Folder… / a Link…);
                   set_hot() lights the files tile while files are dragged over the window
    components/titlebar.py Mac only: Listo's own title bar (ExpandedClientAreaHint; macOS moves the window;
                   double-click fills the screen or goes to the smallest size, animated)
    components/player.py   ClipPlayer: Qt player + caption overlay (burnin.caption_still) + "still" layer for the exact
                   result frame while paused (owners render it on `settled`); set_size() follows the panel's width
    window/main_window.py  the controller: Items, batches, the toolbar (the search hides while the list is empty),
                   the bar under the list (title + "3 of 9 done · About 2 min left" beside it, the bar under both;
                   Show Files, round Pause / Stop icons, Check Captions, Convert), menus, undo / redo, updates
    window/sidebar.py      places: Files (All Files / Videos / Photos / Audio) and Progress (To Convert / Done /
                   Need a Look) with counts (in_place() decides), the section +, ProfileCard (feedback, updates, Settings)
    window/tables.py       FileList (QListView + RowPainter): one painted row per file; Row = it.card (set_state,
                   set_progress, set_output, set_format, set_trim, set_captions, set_name, set_meta, set_thumb)
    window/lift.py         drag a row's grip to reorder (FileList.reordered -> MainWindow._reordered)
    window/history.py      undo / redo steps (settings, files taken off the list, order, a file's format and trim)
    window/jobs.py         threads (ConvertThread, probes/thumbnails in QThreadPool, link downloads, captions process)
    panels/convert_to.py   ConvertPanel (the right panel, a SidePanel): preview on top, then ConvertSettings, then
                   ExportSettings (it puts Clips in the video card and Speed in Advanced); set_width() on a smaller window
    panels/convert.py      ConvertSettings: recipe, then a GroupHeading + cards per kind in the list (set_kinds: "9 Videos";
                   videos: format card, Picture / Burn-In / Captions folds), summary(): what's on, shown folded
    panels/export.py       ExportSettings: the live preview (preview_box), Clips (videos_sec: joining), Saves To (the
                   example name, Where, Name), Advanced
    dialogs/common.py      Alert, confirm(), notice(), ask_name(), about()
    dialogs/settings.py    Settings (⌘,): General (Appearance, Accent Color, Updates), Keyboard Shortcuts, Your Data
                   (folder, Back Up…, Storage & Cache = dialogs/storage.StorageView, debug console, log)
    dialogs/captions.py    "Check the Captions": plays the clip, lights up the current line, click a line to jump,
                   Add Caption at the playhead; accepting marks clips reviewed
    dialogs/preview.py     "Preview": ClipPlayer at full size, converted vs original; double-clicking a clip opens it playing
    dialogs/update.py      Update window (what's new, Update Now -> download -> Restart Listo); CheckThread; Notes
                   (QTextBrowser#WhatsNew: _html escapes every word, _inline keeps **bold** / `code` / https links;
                   open_url opens https only; recolor() on look_changed)
    dialogs/trim.py, feedback.py, shortcuts.py
    old_settings.py  bring_over(): copies what older versions kept in QSettings into settings.json once (old store untouched)
  cli.py           `python -m listo cli ...`: same engine, no UI (great for testing)
  app.py           QApplication, setup_app (fonts, old settings, saved look + accent), set_appearance, rounded
                   popups / plain-text labels (_RoundPopups), single-instance hand-off, --smoke-test (throwaway data folder)
scripts/make_icon.py      draws listo/assets/icon.png ("l." on the dark tile, the dot in the accent) from the tokens and Inter
scripts/fetch_ffmpeg.py   downloads static ffmpeg for the current OS into vendor/ffmpeg (gitignored)
scripts/release_notes.py  a Release's text: "## What's New" (this version's CHANGELOG entries), then the download table
listo.spec                PyInstaller recipe
packaging/                mac entitlements, Windows Inno Setup script, Linux .desktop + install.sh + build_appimage.sh
.github/workflows/build.yml  lint (+ "is this a release?"), build + test + smoke-test on 4 runners, release (see Releasing)
.github/dependabot.yml       weekly pip and Actions updates; SECURITY.md: how to report, what's protected
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
- Light and dark, and the accent: settings.json "appearance" (system / light / dark) and "accent" ("" = marigold) are
  read in app.setup_app before the first window; app.set_appearance -> theme.apply -> tokens.use(scheme, accent),
  the stylesheet again, then every window's look_changed(). "system" follows colorSchemeChanged live
  (LISTO_LOOK=light|dark overrides). Never capture a color at startup: read tokens.NAME / theme.NAME when drawing;
  icons take a color value (theme.icon("plus", theme.MUTED)) and redraw themselves; pictures sit on SCREEN (black in
  both); words on the accent use ON_ACCENT (dark on light accents). tests/test_theme.py and test_accent.py check it.
- Everything Listo saves lives in settings.json in data_dir() (core/store.Prefs, written atomically on every change):
  "settings", "recipes", "recent_luts", "recent_folders", "group_open/*", "sidebar_folded",
  "geometry" (hex), "last_dir", "updates/*", "appearance", "accent", "auto_update". Older versions kept these in
  QSettings: ui/old_settings.bring_over() copies them once (DONE key "copied_old_settings") and never touches the
  old store. Lists and dicts are saved as themselves; store.loads() also reads the JSON text older versions wrote.
  Unreadable files are set aside, never overwritten; unreadable recipes are kept under "recipes.unreadable-<time>".
- Every setting that points at a file or folder is a widgets.PathCombo (DESIGN.md §6 "Picking a file or folder"):
  fixed choices, the ones picked before (a settings.json list, newest first, gone ones dropped), "Choose …".
  LUT: "recent_luts". Where: "recent_folders"; its value is "source" / "subfolder" / a folder (-> destination +
  dest_folder, ExportSettings._where_value). Never a Change… button, a path label or a folder-of-files mode.
- **Words are never cut off.** Text that might not fit wraps onto another line or ends in "…" with the
  whole text in its tooltip; fonts are wider on a Mac. `tests/cut_off.py` checks every screen; a new
  screen gets a line in that test (tests/test_cut_off.py: the window in each state at its usual and smallest
  size, every dialog and Settings pane as it opens and at its smallest).
  Inside anything a fixed width (tiles, cards, sidebars, the right panel) words wrap (`setWordWrap(True)`); a
  place that must stay one line uses `widgets.ElidedLabel` (`full_text()` is the whole text; the checker skips
  it) or paints its own "…" with an Ignored width policy (ToggleRow, the folds' headers); never a smaller font.
  Every dialog stays at least as tall as its wrapped lines need (app._RoundPopups -> widgets.keep_words_whole).
- Recipes are user-made only (full Settings dicts in settings.json "recipes"); `presets.BUILTIN_RECIPES` is intentionally empty.
- Trim is per file (`Item.trim` -> `Conversion(trim=)` -> `video.build(trim=)`): `-ss` before `-i`, `-t` after;
  timecode is shifted with `probe.tc_add` (drop-frame aware). Progress/verify use the trimmed length (`Item.length`).
- Filter order in video.build: deinterlace → tone-map → LUT → frame (desqueeze, crop/bars/matte) → resize → even size → burn-ins → conform (join parts only).
- `frame.frame_plan` also returns the picture area (fractions, without bars); burnin.plan keeps everything inside it.
- Captions flow: as soon as captions are on and a clip with sound is read, MainWindow._sync_captions() queues it on the
  background TranscribeThread, which hands clips to a separate process (core/captions_worker.py: nice'd, half the cores;
  progress only on the row's CC icon). Never run speech-to-text on a thread in the app process: it holds Python's
  lock and froze the window for 10-15 s. Entry points (listo/__main__.py, launcher.py) call
  multiprocessing.freeze_support() and keep their code under `if __name__ == "__main__"` (spawn re-imports them).
  Tests swap the process's target (TranscribeThread.target -> tests/speech_standin.py). Checking is separate:
  the "Check Captions" button (MainWindow.check_captions, shows "N New") opens CaptionEditor. Convert ->
  _captions_ready() only waits if some are still being made (then restarts itself), then converts with
  Conversion(captions=cues) using the captions as they are. Previews use captions.sample_cues() until the real words exist. Captions are the last overlay
  (BurnPlan.captions: an ffconcat list of per-cue PNGs), so they sit on top of bars and burn-ins.
- Playback (components/player.py ClipPlayer, used by the right panel's preview, Preview window and caption check): Qt's player
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
- Every video Listo makes (.mp4 / .mov / .webm; not GIF or audio) stores when it was shot: probe.recorded(src, info,
  trim start) -> Shot(utc, local), the same moment the Date & Time burn-in uses (MediaInfo.created: Apple's tag, else
  creation_time, else the .MOI; else the file's date). A zone-less time (.MOI, file date) gets this computer's offset
  for that date (DST aware); a clip's own creation_time (MediaInfo.creation_time) is kept, only shifted by a trim.
  video.mux_args writes creation_time (UTC) + com.apple.quicktime.creationdate (local, +HHMM) after -map_metadata,
  with ONE -movflags (+faststart+use_metadata_tags for .mp4, +use_metadata_tags for .mov; a second -movflags would
  replace the first). Used by video.build (Plan.shot), the blue-screen wrap and join.concat_args; a joined video
  takes the first clip's time from its converted part (trim included). Logged at INFO ("recording time stored").
  Finder dates are still copied too (keep_dates).
- Join: Settings.join + 2+ videos (not GIF). MainWindow.start() makes a JoinJob; each clip converts as a "part"
  (Conversion(target=hidden parts folder, conform=first clip's size/rate/48 kHz stereo; silent clips get a silent
  track; per-file format overrides don't apply), then _start_join() runs JoinThread (core/join.Join: concat demuxer,
  -c copy). Stop before gluing -> parts deleted and those clips back to ready.
- Window (DESIGN.md §1): the sidebar (places filter the list: MainWindow.go(place) / _apply_filter with the search)
  | the file list with the bar under it (Convert N Files lives there, so closing the panel never hides it)
  | Convert To in the Dock. Convert To is about every file in the list, never the picked one: the Dock opens when
  the first file arrives and closes when the last one leaves (MainWindow._show_page); picking a file, Esc or a
  click on empty space never open or close it. Its ✕ closes it; MainWindow.btn_panel (the toolbar's round
  sliders button, faded in while closed with files) or ⌥⌘I bring it back. Inside: a heading per kind in the list
  with its count (ConvertSettings.set_kinds, fed by _refresh_places), never Video / Photo / Audio tabs (they read
  as an export's picture / sound tabs). Folds (Picture / Burn-In / Captions, Saves To's Advanced) say what's on
  (convert.summary). Labels are Title Case (DESIGN.md §9).
- Undo / redo (window/history.py): MainWindow._record_settings (SAVE_DELAY_MS after a settings change settles;
  a change taken straight back drops the step), _take_off / _put_back (files off the list, one step), _reordered /
  _put_order, _set_override / _put_override, trim_item / _put_trim. ⌘Z in a text box undoes the typing instead.
- Taking files off the list goes through a menu or an alert (remove_selected names them; Clear All asks); never
  one click. The rows have no × button.
- Camera sidecars (probe.SIDECAR_EXTS) are never listed. JVC .MOI next to .MOD/.TOD is read in probe (read_moi):
  recording date -> info.created (naive wall time), aspect -> info.sar (JVC flags widescreen MOD as 4:3).
- Burn-ins never use ffmpeg's drawtext (Homebrew's ffmpeg lacks it). With burn-ins the picture goes through -filter_complex,
  starts at pts 0 (setpts=PTS-STARTPTS, audio asetpts) so time-based digit expressions line up; the engine deletes the PNGs (Plan.cleanup).
- Timecode for clips WITHOUT their own (Settings.timecode_mode, the dropdown in Burn-In › Clip Info, shown even with
  the burn-in off because it's also stored; presets.timecode_mode(s, joining, preset) resolves it: rewrap / audio keep
  the old rule). Clips with real timecode always keep theirs.
  "continuous" (default): one Convert = one tape. join.running_timecodes(clips, start) counts kept lengths in list
  order; a joined video gets them up front (JoinJob.timecodes), separate files get theirs as they start
  (MainWindow._tape_clock -> Item.clock, MainWindow._tape_s; clips added mid-batch carry on). Passed as
  Conversion(timecode=) -> video.build(timecode=) (start_tc for the burn-in and -timecode).
  "restart": nothing passed (burn-in from 00:00:00:00, nothing stored). "record": video.build works it out per clip
  (probe.record_timecode: file_date + trim start as time-of-day timecode, drop-frame at 29.97).
  Previews: MainWindow._clocks() (what Convert will give, in one pass) -> PreviewTask(clock=) / PreviewDialog's 6th
  item -> video.preview_plan(clock=(t, tc)). Only the first part of a joined video keeps the PLAY badge (REC stays on every part).
- Space = play/pause via player.space_plays(window, player) (a WindowShortcut; text fields keep their spaces).
- Tape effects never apply to rewrap / GIF / audio (tape.NO_EFFECTS), and only with the VHS look. Convert To's
  "VHS Tape" section (only with the VHS look, under Clip Info) is four dropdowns: burn_badge, burn_end (-> burn_stop),
  tape_screen ("none" -> tape_blue False), tape_glitches ("off" / "cuts" / "rare" / "often"; every value but "off"
  glitches joined cuts). The old tape_cut_glitch switch is migrated by presets._migrate. With the blue screen on, a single video is
  conformed to itself (48 kHz stereo) so the blue pieces match; its .srt and length check shift by tape.BLUE_SECONDS.
- VCR badges (VHS look): tape.marks() -> burnin.Marks(play_until, stop_at) passed as Conversion(marks=) ->
  video.build -> burnin.plan (single videos compute their own). PLAY (burn_badge "play") blinks 4 s; with a start
  screen the first 2 s are on it (make_blue badge="play"). STOP ■ (Settings.burn_stop, its own switch) shows from
  STOP_FRAMES_S before the end and then on the end screen for STOP_SHOWS_S, or for the last STOP_ALONE_S without a
  screen. Joined videos: only the first part gets play_until, only the last stop_at.
  PLAY / STOP layers are Layer.vcr: BurnPlan.graph(between=) runs the glitch after the tape's layers (timecode,
  date, REC) and before the VCR's and the captions, so the glitch never tears PLAY / STOP.
- geq gotchas: W/H/X/Y are the CURRENT plane's (chroma is smaller), vars are st/ld 0-9 only, and pow() of a
  negative number is NaN (which turns the whole shift into garbage). The glitch runs in the encoder's own
  pixel format (format=<-pix_fmt> first) so 10-bit uses 0-1023. Don't use vibrato (NaN on some camcorder sound).
- presets.SESSION_ONLY (captions, join) reset to off at every launch; everything else in Settings is remembered.
- ClipPlayer.step(-1/+1) = the previous / next clip arrows; owners call set_steps(has_prev, has_next).
- New Settings fields must have defaults that mean "off": old recipes are applied through `Settings.complete()`.
- Long lists (hundreds of clips): never do list-wide work per file. Use MainWindow._refresh_soon() (bundles the
  footer / captions status / sample into one pass, waiting longer for longer lists); the list is painted (no widget
  per row) and Row setters skip unchanged values and redraw only their row; theme.icon / pixmap are cached; read captions/burn-in settings in loops with MainWindow._base(it)
  (no copy). tests/test_big_list.py guards this (400 clips once took 205 s of window time; now ~10 s).
- Logging: conversions log the source, target, exact ffmpeg command, time taken and ffmpeg's last words on failure;
  uncaught errors (any thread) are logged by app._log_uncaught. Keep new features logging what they do at INFO.
- Selection: `MainWindow.selected` (item ids) + `_anchor` for Shift-click (over the rows showing); FileList emits
  `pressed` / `step` (↑↓) / `menu_wanted` (right-click: MainWindow._list_menu, also on empty space).
- List order is join order and Continuous Timecode order: dragging a row's grip reorders (not while converting).
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
QT_QPA_PLATFORM=offscreen python tests/screenshot.py OUTDIR SAMPLES  # UI screenshots without a display (throwaway data)
LISTO_LOOK=light python -m listo       # force the light (or dark) look instead of following the system
LISTO_DATA_DIR=/tmp/try python -m listo  # try it on a separate data folder (settings.json, captions, tools)
pyinstaller listo.spec --noconfirm     # build the app into dist/
```

## Releasing: merging is releasing
- **Every pull request with a change users will notice bumps `__version__`** in `listo/__init__.py`, once per pull
  request: the last number for fixes and polish (2.3.**3**), the middle one for a new feature (2.**4**.0), the first
  for a big change (**3**.0.0). Its notes go in CHANGELOG.md under that version's heading (`## 2.4.0`), never under
  "Unreleased". Changes users won't notice (tests, docs, the build, refactors) don't bump it.
- When that pull request is merged, build.yml's run on main sees that tag vX.Y.Z doesn't exist yet ("Is this a
  release?" in the lint job), builds and smoke-tests every platform, then the release job tags that exact commit
  (making the tag through the API is the lock: two quick merges can't release one version twice; the release job
  also runs one at a time) and publishes the Release with the downloads and the version's CHANGELOG section
  (scripts/release_notes.py; the update window shows those entries, so write them for the people updating), in
  the same run (a tag made by the workflow's own token doesn't start other workflows). Pull requests never release.
  Nobody tags or releases by hand; a tag pushed by hand still works, but only if it matches `__version__`.
  A failed release job can simply be re-run (the tag already on that commit is reused).
- A number that has been released is never used again.
- CI attaches: Listo-mac-apple-silicon.dmg, Listo-mac-intel.dmg, Listo-windows-setup.exe, Listo-windows-portable.zip,
Listo-linux-x64.AppImage, Listo-linux-x64.tar.gz. **These names are a contract**: the README's download links
(releases/latest/download/<name>) and the in-app updater (update.asset_name) both depend on them, and the repo
must stay public (private releases need a sign-in). update.REPO = "nickvenecia/listo".

## Ideas not done yet
- Watch folder ("anything dropped in here gets converted")
- A real Finder Quick Action (today: right-click > Open With > Listo on Mac, Send to > Listo on Windows)
- LUTs on photos
- 16-bit TIFF from RAW (Pillow is 8-bit for RGB; would need tifffile)
