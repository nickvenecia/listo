"""The debug console opens each system's own terminal, following Listo's log files."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from listo.core import console


@pytest.fixture
def opened(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(console, "log_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(console, "data_dir", lambda: tmp_path)
    calls = []
    monkeypatch.setattr(console, "_launch", lambda args, **kw: calls.append((args, kw)))
    return calls


def test_mac_opens_terminal_following_the_logs(opened, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(console.sys, "platform", "darwin")
    assert console.open_console() == ""
    script = tmp_path / "Listo Debug Console.command"
    assert opened[0][0] == ["open", "-a", "Terminal", str(script)]
    text = script.read_text()
    assert "tail -n 200 -F" in text and "listo.log" in text and "crash.log" in text
    assert (tmp_path / "logs" / "listo-captions.log").exists()  # every file exists, so tail -F follows it
    assert logging.getLogger("listo").level == logging.DEBUG  # detailed while the console is open


def test_windows_opens_powershell(opened, monkeypatch):
    monkeypatch.setattr(console.sys, "platform", "win32")
    assert console.open_console() == ""
    args = opened[0][0]
    assert args[0] == "powershell" and "Get-Content" in args[-1] and "-Wait" in args[-1]


def test_linux_uses_the_first_terminal_found(opened, monkeypatch):
    monkeypatch.setattr(console.sys, "platform", "linux")
    monkeypatch.setattr(
        console.shutil, "which", lambda t: "/usr/bin/gnome-terminal" if t == "gnome-terminal" else None
    )
    assert console.open_console() == ""
    args = opened[0][0]
    assert args[:2] == ["/usr/bin/gnome-terminal", "--"] and "tail -n 200 -F" in args[-1]


def test_no_terminal_says_where_the_logs_are(opened, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(console.sys, "platform", "linux")
    monkeypatch.setattr(console.shutil, "which", lambda t: None)
    assert str(tmp_path / "logs") in console.open_console()
    assert not opened
