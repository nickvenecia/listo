# Listo code rules

How Listo's code is organized and the rules every change follows. The look of the app has its
own rulebook: **[DESIGN.md](DESIGN.md)**. Read both before changing anything.

---

## 1. Where things go

```
listo/
  core/        Everything that converts files. No Qt imports here — ever.
               engine, video, photo, probe, naming, presets, runner, tools, links, fileutil, paths, log
  ui/          Everything you see. Qt Widgets only. Talks to core/, never the other way round.
               tokens (sizes/colors), theme (stylesheet/icons), widgets (shared building blocks),
               main_window, sidebar, export_dialog, trim_dialog, job_card, workers
  app.py       Starts the window (fonts, stylesheet, single-instance hand-off, --smoke-test)
  cli.py       Same engine without a window: `python -m listo cli ...`
tests/         One test file per core module (test_<module>.py)
scripts/       Build helpers (fetch_ffmpeg.py)
packaging/     Installer files per OS
```

- `core/` must work headless. If you need to report progress, take a callback or emit through a
  `ui/workers.py` thread, don't import Qt.
- A new file format or preset goes in `core/presets.py` (definition) + `core/video.py` or
  `core/photo.py` (how it's built) + a test.
- Per-user files (logs, downloaded tools, UI icons) go under `core.paths.data_dir()`.
  Never write next to the app, and never into a fixed name in the shared temp folder.

---

## 2. Style

- Python 3.12. `from __future__ import annotations` at the top of every module.
- **Ruff** formats and lints. Before every commit:
  ```bash
  ruff format . && ruff check . && python -m pytest -q
  ```
  CI fails if any of the three fails. Settings are in `pyproject.toml` (line length 110).
- Type hints on every function signature. Prefer `X | None` and built-in generics (`list[str]`).
- Names: `snake_case` functions/variables, `PascalCase` classes, `UPPER_CASE` constants,
  `_leading_underscore` for anything private to a module.
- Every module starts with a one-line docstring saying what it's for. Public functions get a
  docstring when the name doesn't say everything.
- Comments explain **why**, not what. Link to the bug or quirk when a line looks odd.
- No dead code, no commented-out code, no `print()` in the app (use the logger).

---

## 3. Safety rules (never break these)

**The user's files**
1. **Never overwrite or modify a source file.** All output names go through
   `naming.resolve_output`, which compares paths case-insensitively (Mac and Windows disks ignore case)
   and reserves every queued source so "Replace" can never hit another original.
2. Write to a hidden temp file in the destination folder, then `os.replace` it into place on success.
   A failed or stopped conversion leaves nothing behind. Pass `-f <muxer>` to ffmpeg, since the temp
   name's extension can't be trusted.
3. Downloads are the same: write to `*.part`, then `os.replace`.

**Running other programs**
4. Always pass arguments as a **list**. Never `shell=True`, never build a command string.
5. Every `subprocess` call gets `**tools.popen_kwargs()` (no console windows on Windows).
6. Always drain stderr/stdout while a process runs (a full pipe freezes ffmpeg).
7. Anything that can run long must be stoppable: keep the `Popen`, and kill the whole process tree
   (`links._kill_tree`) on cancel or quit.

**Network**
8. HTTPS only, with certificate checks on (`links._ssl_context()`; never `verify=False` or `CERT_NONE`).
9. Every program Listo downloads is checked against the **SHA-256 published with that release**
   before it's saved (`links._verified`). A mismatch means it's thrown away.
10. Pin download sources to official release pages (GitHub releases of yt-dlp, Deno, BtbN; ffmpeg.martin-riedl.de).

**Input from outside**
11. Treat file names, links, metadata and anything from another process as untrusted.
    The single-instance socket only accepts the same user (`UserAccessOption`), caps its size,
    and only adds paths that exist.
12. Never `eval`/`exec`/`pickle` anything. Settings are JSON.
13. Never log or show secrets or full environment variables.

**Errors**
14. No silent `except: pass` around real work. Catch the narrowest exception you can; if you must
    swallow one, `log.warning(..., exc_info=True)` so it lands in the log file.
15. Messages shown to the user are plain English and say what to do next (see DESIGN.md §7).
    Technical details go to the log (`core/log.py`, `listo.log` in the data folder).

---

## 4. Threads

- The UI only changes on the main thread. Conversions run in `ConvertThread`, downloads in their own
  thread, probes and thumbnails in a `QThreadPool`. They talk to the window with **signals**.
- Shared state in `core/` is guarded by a lock (`engine._plan_lock` for output names,
  `links._setup_lock` for tool setup). Hold locks briefly; never across a long process run.
- At most `Settings.parallel` conversions (1 or 2) run at once.

---

## 5. Speed

- Ask ffprobe once per file and keep the `MediaInfo`. Don't re-probe in the UI.
- Thumbnails and probes run in the thread pool, never on the main thread.
- Prefer stream copy (`-c copy`) when the format allows it; use hardware encoders when
  `tools.capabilities()` says they work.
- Cache anything that's expensive and doesn't change during a session (capabilities, icons).

---

## 6. Tests

- Every change to `core/` comes with a test. Name it after the behavior:
  `test_replace_never_hits_another_original`.
- Integration tests that need ffmpeg skip themselves when it isn't installed (`tests/helpers.py`).
- UI changes: check screenshots (`QT_QPA_PLATFORM=offscreen python tests/screenshot.py SHOTS OUTDIR`).
- Before a release, the packaged app must pass `--smoke-test` (CI does this on every platform).

---

## 7. Commits and releases

- One topic per commit. Message: short summary line in the present tense ("Add WebP output"),
  then a blank line and the why, if it isn't obvious.
- Update `CHANGELOG.md` under "Unreleased" for anything a user would notice.
- Release: bump `__version__` in `listo/__init__.py`, move the changelog entries under the new version,
  commit, then `git tag vX.Y.Z && git push --tags`. CI builds and publishes the downloads.
- Never commit `vendor/`, `build/`, `dist/`, or anything with a password or key in it.
  Signing secrets live only in GitHub → Settings → Secrets.
