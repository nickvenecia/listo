"""The debug console: a terminal window that follows Listo's log files live.

Help › Open Debug Console (or the terminal icon in the bottom bar) calls open_console(). It opens
the system's own terminal (Terminal on a Mac, PowerShell on Windows, the usual terminal on Linux)
showing the last lines of listo.log, listo-captions.log and crash.log, and everything new as it
happens. Opening it also turns on detailed logging for the rest of the session (every preview frame,
every ffmpeg command).

Running Listo from a terminal (`python -m listo`) prints the same lines there too (log.py).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from listo.core.log import get_logger
from listo.core.paths import data_dir, log_dir

log = get_logger(__name__)

LOG_FILES = ("listo.log", "listo-captions.log", "crash.log")
TITLE = "Listo Debug Console"


def _launch(args: list[str], **kw) -> None:
    subprocess.Popen(args, **kw)


def _files() -> list[Path]:
    d = log_dir()
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for name in LOG_FILES:
        p = d / name
        if not p.exists():
            p.touch()
        out.append(p)
    return out


def _q(p: Path) -> str:
    return "'" + str(p).replace("'", "'\\''") + "'"


def _tail_command(files: list[Path]) -> str:
    """The shell command a Mac / Linux terminal runs."""
    names = " ".join(_q(p) for p in files)
    return (
        f"printf '\\033]0;{TITLE}\\007'; clear; "
        f"echo '{TITLE}: everything Listo does shows up here as it happens. Close this window any time.'; "
        f"echo; tail -n 200 -F {names}"
    )


def open_console() -> str:
    """Open the debug console. Returns '' when it opened, or why it couldn't."""
    logging.getLogger("listo").setLevel(logging.DEBUG)  # detailed from now on
    log.info("debug console opened: detailed logging is on for this session")
    files = _files()
    try:
        if sys.platform == "darwin":
            # A .command file opens in Terminal by itself, with no permission prompt.
            script = data_dir() / "Listo Debug Console.command"
            script.write_text("#!/bin/bash\n" + _tail_command(files) + "\n", encoding="utf-8")
            script.chmod(0o755)
            _launch(["open", "-a", "Terminal", str(script)])
            return ""
        if sys.platform == "win32":
            main = str(files[0]).replace("'", "''")
            ps = (
                f"$host.UI.RawUI.WindowTitle = '{TITLE}'; "
                f"Write-Host '{TITLE}: everything Listo does shows up here as it happens.'; "
                f"Get-Content -Path '{main}' -Tail 200 -Wait"
            )
            _launch(
                ["powershell", "-NoExit", "-NoProfile", "-Command", ps],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
            return ""
        cmd = _tail_command(files) + "; exec bash"
        for term, args in (
            ("x-terminal-emulator", ["-e", "bash", "-c", cmd]),
            ("gnome-terminal", ["--", "bash", "-c", cmd]),
            ("konsole", ["-e", "bash", "-c", cmd]),
            ("xfce4-terminal", ["-x", "bash", "-c", cmd]),
            ("kitty", ["bash", "-c", cmd]),
            ("alacritty", ["-e", "bash", "-c", cmd]),
            ("xterm", ["-T", TITLE, "-e", "bash", "-c", cmd]),
        ):
            exe = shutil.which(term)
            if exe:
                _launch([exe, *args], start_new_session=True)
                return ""
        return "No terminal app was found. The log files are in " + os.fspath(files[0].parent)
    except OSError as e:
        log.warning("couldn't open the debug console", exc_info=True)
        return f"Couldn't open a terminal ({e.__class__.__name__}). The log files are in {files[0].parent}"
