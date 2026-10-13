"""The text of a GitHub Release: this version's CHANGELOG.md entries, then the downloads.

    python scripts/release_notes.py v3.0.0 > release-notes.md

The update window shows the What's New part (core/update.whats_new leaves the downloads out), so the
changelog's plain words are what people read before updating.
"""

from __future__ import annotations

import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"

DOWNLOADS = """## Download
| Your computer | File |
|---|---|
| Mac with Apple Silicon (M1 and newer) | `Listo-mac-apple-silicon.dmg` |
| Intel Mac | `Listo-mac-intel.dmg` |
| Windows (installer) | `Listo-windows-setup.exe` |
| Windows (no install) | `Listo-windows-portable.zip` |
| Linux (one file, double-click to run) | `Listo-linux-x64.AppImage` |
| Linux (folder + install script) | `Listo-linux-x64.tar.gz` |

Everything Listo needs (including ffmpeg) is inside, nothing else to install.
**First launch on Mac:** if macOS says it can't check the app, open **System Settings → Privacy & Security** and click **Open Anyway**.
**First launch on Windows:** if SmartScreen appears, click **More info → Run anyway**.
"""


def changes(changelog: str, version: str) -> str:
    """The entries under "## <version>" up to the next version ("" when it has none)."""
    keep: list[str] = []
    inside = False
    for line in changelog.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip().lstrip("vV") == version
        elif inside:
            keep.append(line)
    return "\n".join(keep).strip()


def notes(changelog: str, version: str) -> str:
    what = changes(changelog, version.lstrip("vV"))
    return (f"## What's New\n\n{what}\n\n" if what else "") + DOWNLOADS


if __name__ == "__main__":
    sys.stdout.write(notes(CHANGELOG.read_text(encoding="utf-8"), sys.argv[1]))
