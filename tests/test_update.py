"""Updates (core/update.py, ui/update_dialog.py): finding a newer release, downloading it safely and
swapping it in once Listo has quit."""

from __future__ import annotations

import hashlib
import http.server
import io
import os
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path

import pytest

from listo import __version__
from listo.core import update

GITHUB_ANSWER = {
    "tag_name": "v9.1.0",
    "html_url": "https://github.com/nickvenecia/listo/releases/tag/v9.1.0",
    "body": "## Download\n| a | b |\n\n## What's new\n- Faster glitches",
    "assets": [
        {
            "name": "Listo-mac-apple-silicon.dmg",
            "browser_download_url": "https://example.invalid/a.dmg",
            "size": 10,
            "digest": "sha256:ABCDEF",
        },
        {"name": "Listo-linux-x64.AppImage", "browser_download_url": "https://example.invalid/b", "size": 5},
    ],
}


def test_versions_compare_like_numbers():
    assert update.version_tuple("v2.10.1") == (2, 10, 1)
    assert update.version_tuple("3") == (3, 0, 0)
    assert update.is_newer("v2.10.0", "2.9.9")  # 10 > 9, not "1" < "9"
    assert not update.is_newer("2.3.0", "2.3.0")
    assert not update.is_newer("2.3.0-beta", "2.3.0")


def test_release_from_github():
    rel = update.parse_release(GITHUB_ANSWER)
    assert rel.version == "9.1.0" and rel.newer
    a = rel.assets["Listo-mac-apple-silicon.dmg"]
    assert a.size == 10 and a.sha256 == "abcdef"
    assert rel.assets["Listo-linux-x64.AppImage"].sha256 == ""


def test_the_right_file_for_each_kind_of_install():
    assert update.asset_name("mac-app", "arm64") == "Listo-mac-apple-silicon.dmg"
    assert update.asset_name("windows-installed") == "Listo-windows-setup.exe"
    assert update.asset_name("windows-portable") == "Listo-windows-portable.zip"
    assert update.asset_name("appimage") == "Listo-linux-x64.AppImage"
    assert update.asset_name("linux-folder") == "Listo-linux-x64.tar.gz"
    assert update.asset_name("source") is None


def test_running_from_the_code_is_updated_with_git():
    assert update.install_kind() == "source"  # the tests run from the code
    assert "GitHub Desktop" in update.can_update_here("source")


class _Files(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture
def server(tmp_path: Path):
    root = tmp_path / "web"
    root.mkdir()
    handler = lambda *a, **k: _Files(*a, directory=str(root), **k)  # noqa: E731
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield root, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_download_checks_size_and_fingerprint(tmp_path: Path, server):
    root, base = server
    data = b"new listo" * 1000
    (root / "f.AppImage").write_bytes(data)
    good = update.Asset(
        "Listo-linux-x64.AppImage", f"{base}/f.AppImage", len(data), hashlib.sha256(data).hexdigest()
    )
    seen = []
    out = update.download(good, tmp_path, seen.append)
    assert out.read_bytes() == data and seen and seen[-1] == 1.0
    bad = update.Asset("x", f"{base}/f.AppImage", len(data), "0" * 64)
    with pytest.raises(ValueError, match="doesn't match"):
        update.download(bad, tmp_path, lambda _v: None)
    short = update.Asset("y", f"{base}/f.AppImage", len(data) + 5)
    with pytest.raises(ValueError, match="cut short"):
        update.download(short, tmp_path, lambda _v: None)


def _gone_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def _wait_for(path: Path, timeout: float = 15) -> bool:
    end = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < end:
        time.sleep(0.1)
    return path.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="Linux / Mac helper")
def test_appimage_is_swapped_and_reopened(tmp_path: Path, monkeypatch):
    app = tmp_path / "apps" / "Listo-linux-x64.AppImage"
    app.parent.mkdir()
    app.write_text("old")
    monkeypatch.setenv("APPIMAGE", str(app))
    opened = tmp_path / "opened"
    work = update.new_work_folder()
    new = work / "Listo-linux-x64.AppImage"
    new.write_text(f"#!/bin/sh\ntouch {opened}\n")
    plan = update.prepare("appimage", new, pid=_gone_pid())
    subprocess.run(plan.command, check=True, timeout=30)
    assert "touch" in app.read_text() and os.access(app, os.X_OK)  # the new one, runnable
    assert _wait_for(opened)  # and it was opened
    assert not work.exists()  # the download is cleaned up


@pytest.mark.skipif(sys.platform == "win32", reason="Linux / Mac helper")
def test_linux_folder_is_swapped_and_reopened(tmp_path: Path, monkeypatch):
    folder = tmp_path / "listo"
    folder.mkdir()
    (folder / "Listo").write_text("old")
    (folder / "leftover.txt").write_text("old file")
    monkeypatch.setattr(update, "target", lambda _kind: folder)
    opened = tmp_path / "opened"
    work = update.new_work_folder()
    tar = work / "Listo-linux-x64.tar.gz"
    with tarfile.open(tar, "w:gz") as t:
        script = f"#!/bin/sh\ntouch {opened}\n".encode()
        info = tarfile.TarInfo("Listo/Listo")
        info.size, info.mode = len(script), 0o755
        t.addfile(info, io.BytesIO(script))
    plan = update.prepare("linux-folder", tar, pid=_gone_pid())
    subprocess.run(plan.command, check=True, timeout=30)
    assert "touch" in (folder / "Listo").read_text()
    assert not (folder / "leftover.txt").exists()  # the whole folder is the new version
    assert _wait_for(opened)
    assert not list(tmp_path.glob("listo.old.*"))


def test_mac_and_windows_helpers(tmp_path: Path, monkeypatch):
    app = tmp_path / "Applications" / "Listo.app"
    monkeypatch.setattr(update, "target", lambda _kind: app)
    dmg = tmp_path / "Listo-mac-apple-silicon.dmg"
    dmg.write_bytes(b"dmg")
    mac = update.prepare("mac-app", dmg, pid=4242).script.read_text()
    for step in ("kill -0 4242", "hdiutil attach", "ditto", "com.apple.quarantine", "open "):
        assert step in mac, step

    folder = tmp_path / "Programs" / "Listo"
    monkeypatch.setattr(update, "target", lambda _kind: folder)
    setup = tmp_path / "Listo-windows-setup.exe"
    setup.write_bytes(b"exe")
    win = update.prepare("windows-installed", setup, pid=4242).script.read_text()
    assert "/VERYSILENT" in win and "PID eq 4242" in win and "Listo.exe" in win


def test_update_window(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from listo.ui.dialogs.update import UpdateDialog

    app = QApplication.instance() or QApplication([])
    d = UpdateDialog(update.parse_release(GITHUB_ANSWER))
    assert "9.1.0" in d.findChild(type(d.status), "DialogTitle").text()
    shown = d.notes.toPlainText()
    assert "Faster glitches" in shown and "Download" not in shown
    assert d.btn_go.isHidden() and "GitHub Desktop" in d.status.text()  # from the code: nothing to install
    d.close()
    app.processEvents()


def test_whats_new_is_the_words_without_downloads_or_github_credits():
    generated = (
        "## Download\n| a | b |\n**First launch on Mac:** open it.\n\n"
        "## What's Changed\n"
        "* Start tiles by @someone in https://github.com/nickvenecia/listo/pull/7\n"
        "<!-- generated -->\n\n"
        "## New Contributors\n* @someone made their first contribution in https://x\n\n"
        "**Full Changelog**: https://github.com/nickvenecia/listo/compare/v2.3.1...v2.3.2"
    )
    assert update.whats_new(generated) == [("heading", "What's Changed"), ("item", "Start tiles")]
    written = "The first one.\n\n## What's New\n\n- A long line\n  carried on.\n1. Two\n\n## Empty\n## Download\n| x |"
    assert update.whats_new(written) == [
        ("text", "The first one."),
        ("heading", "What's New"),
        ("item", "A long line carried on."),
        ("item", "Two"),
    ]
    assert update.whats_new("") == []


def test_release_text_is_never_read_as_html(qapp):
    from listo.ui.dialogs.update import Notes

    n = Notes([("item", "<b>x</b> **bold** `code` [page](https://example.com/a?b=1&c=2) [run](file:///etc)")])
    page = n.toHtml()
    assert "&lt;b&gt;x&lt;/b&gt;" in page and "bold" in page and "`" not in n.toPlainText()
    assert 'href="https://example.com/a?b=1&amp;c=2"' in page and "file:" not in page
    assert Notes([]).toPlainText() == "Fixes and improvements."


def test_release_notes_are_the_changelog_entries():
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("release_notes", root / "scripts" / "release_notes.py")
    rn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rn)
    log = "# Changelog\n\n## 2.0.1\n\n- Fixed it.\n\n## 2.0.0\n\n- Made it.\n"
    body = rn.notes(log, "v2.0.1")
    assert update.whats_new(body) == [("heading", "What's New"), ("item", "Fixed it.")]
    assert "Listo-mac-apple-silicon.dmg" in body and "Made it." not in body
    assert (
        update.whats_new(rn.notes(log, "3.0.0")) == []
    )  # no entries: the window says "Fixes and improvements."
    assert rn.changes(rn.CHANGELOG.read_text(encoding="utf-8"), __version__)  # this version has its entries
    kinds = ("windows-installed", "windows-portable", "appimage", "linux-folder")
    names = [update.asset_name(k) for k in kinds] + [update.asset_name("mac-app", "arm64")]
    for name in names:
        assert name in body  # every download the updater looks for is listed


def test_window_offers_the_update(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    import listo.ui.window.main_window as mw

    app = QApplication.instance() or QApplication([])
    w = mw.MainWindow()
    assert w.btn_update.isHidden()
    w._update_found(update.parse_release(GITHUB_ANSWER), quiet=True)
    assert not w.btn_update.isHidden() and "9.1.0" in w.btn_update.text()
    same = dict(GITHUB_ANSWER, tag_name=f"v{__version__}")
    w._update_found(update.parse_release(same), quiet=True)
    assert w.btn_update.isHidden()
    w.close()
    app.processEvents()
