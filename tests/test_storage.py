"""Storage & Cache: sizes, deleting each kind, and never touching anything else."""

from __future__ import annotations

import os
from pathlib import Path

from listo.core import storage


def _fill(d: Path) -> None:
    (d / "models" / "small").mkdir(parents=True)
    (d / "models" / "small" / "model.bin").write_bytes(b"x" * 5000)
    (d / "captions").mkdir()
    (d / "captions" / "a.json").write_text("{}")
    (d / "tools").mkdir()
    (d / "tools" / "yt-dlp").write_bytes(b"x" * 300)
    (d / "logs").mkdir()
    (d / "logs" / "listo.log").write_text("hello\n")
    (d / "logs" / "listo.log.1").write_text("old\n")
    (d / "sample").mkdir()
    (d / "sample" / "s.mov").write_bytes(b"x" * 100)


def test_sizes_and_deleting_each_kind(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(storage, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(storage, "tools_dir", lambda: tmp_path / "tools")
    monkeypatch.setattr(storage, "log_dir", lambda: tmp_path / "logs")
    _fill(tmp_path)
    keep = tmp_path / "settings-and-recipes.ini"  # anything else in the folder is left alone
    keep.write_text("keep me")
    sizes = {k.key: storage.kind_size(k) for k in storage.kinds()}
    assert sizes["models"] == 5000 and sizes["tools"] == 300 and sizes["extras"] == 100
    assert storage.human(5000) == "5.0 KB" and storage.human(1_600_000_000) == "1.6 GB"

    assert storage.clear("models") == 5000
    assert not (tmp_path / "models").exists()
    storage.clear("logs")
    assert (tmp_path / "logs" / "listo.log").read_text() == ""  # emptied (it may be open), not deleted
    assert not (tmp_path / "logs" / "listo.log.1").exists()
    for k in ("captions", "tools", "extras"):
        storage.clear(k)
    assert sum(storage.kind_size(k) for k in storage.kinds()) == 0
    assert keep.read_text() == "keep me"


def test_storage_view_deletes_and_refreshes(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    import listo.ui.dialogs.storage as sd

    monkeypatch.setattr(storage, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(storage, "tools_dir", lambda: tmp_path / "tools")
    monkeypatch.setattr(storage, "log_dir", lambda: tmp_path / "logs")
    asked = []
    monkeypatch.setattr(sd, "confirm", lambda *a, **k: asked.append(a[1]) or True)
    monkeypatch.setattr(sd, "notice", lambda *a, **k: None)
    _fill(tmp_path)
    app = QApplication.instance() or QApplication([])
    cleared = []
    d = sd.StorageView(busy=lambda k: "busy" if k == "tools" else "", cleared=cleared.append)
    assert not d.rows["tools"][1].isEnabled()  # busy: can't delete right now
    assert d.rows["models"][0].text() == "5.0 KB"
    d._delete(["models"])
    assert asked and asked[0].startswith("Delete ")  # always asked first
    assert cleared == ["models"] and d.rows["models"][0].text() == "Empty"
    d._delete([k.key for k in storage.kinds()])  # Delete All skips what's busy
    assert (tmp_path / "tools" / "yt-dlp").exists()
    assert "captions" in cleared
    d.close()
    app.processEvents()
