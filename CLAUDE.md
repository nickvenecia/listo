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
    video.py       build(): (file, MediaInfo, Settings, Capabilities) -> ffmpeg args.  All video/audio presets live here
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
    log.py         rotating log file (listo.log in log_dir()); get_logger(__name__)
  ui/
    tokens.py      THE design tokens (sizes, spacing, type, radii, colors)
    theme.py       stylesheet built from tokens, SVG icons (icon(name, color))
    widgets.py     shared building blocks: vbox/hbox, Section, Segmented, Option/OptionList, FlowLayout, repolish
    main_window.py queue + batch controller, toolbar, drop zone, footer
    sidebar.py     recipe dropdown + Video/Photo/Audio format settings (all dropdowns)
    export_dialog.py  "Export options": where files go + naming + collisions (opened from the footer)
    trim_dialog.py start/end sliders with ffmpeg frame-grab previews
    job_card.py    one file in the list
    workers.py     threads (ConvertThread, probes/thumbnails in QThreadPool, link downloads)
  cli.py           `python -m listo cli ...`: same engine, no UI (great for testing)
  app.py           QApplication, fonts, stylesheet, rounded popups, single-instance hand-off, --smoke-test
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
