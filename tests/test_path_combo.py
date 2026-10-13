"""Picking a file or folder is always one dropdown (DESIGN.md §6): the fixed choices, the ones picked
before, then "Choose …" (the LUT and Where dropdowns)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _labels(c) -> list[str]:
    return [c.itemText(i) or "—" for i in range(c.count())]  # "—" = a separator


def test_choose_remembers_and_cancel_goes_back(tmp_path: Path, app):
    from PySide6.QtCore import QSettings

    from listo.ui.components.widgets import CHOOSE, PathCombo

    qs = QSettings(str(tmp_path / "t.ini"), QSettings.Format.IniFormat)
    shoot, other = tmp_path / "Shoot" / "Exports", tmp_path / "Other" / "Exports"
    shoot.mkdir(parents=True)
    other.mkdir(parents=True)
    answer = {"path": str(shoot)}
    c = PathCombo(qs, "recent_folders", [("source", "In Source Folder", "")], "Choose a Destination…",
                  lambda start: answer["path"], folders=True)  # fmt: skip
    picked = []
    c.picked.connect(picked.append)
    assert _labels(c) == ["In Source Folder", "—", "Choose a Destination…"]

    c.activated.emit(c.findData(CHOOSE))
    assert picked == [str(shoot)] and c.currentData() == str(shoot)
    answer["path"] = str(other)
    c.activated.emit(c.findData(CHOOSE))
    # two folders called Exports: each says where it is; the newest first
    assert _labels(c) == [
        "In Source Folder",
        "—",
        "Exports (Other)",
        "Exports (Shoot)",
        "—",
        "Choose a Destination…",
    ]
    assert c.itemData(c.findData(str(shoot)), 3) == str(shoot)  # the full path in the tip

    answer["path"] = ""  # the picker was cancelled
    c.activated.emit(c.findData(CHOOSE))
    assert c.currentData() == str(other) and picked == [str(shoot), str(other)]
    c.activated.emit(c.findData("source"))
    assert picked[-1] == "source"

    other.rmdir()  # gone folders drop off
    c.set_value("source")
    assert "Exports (Other)" not in _labels(c) and "Exports" in _labels(c)


def test_lut_and_where_follow_the_rule(tmp_path: Path, monkeypatch, app):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QFileDialog

    import listo.ui.panels.convert as sb_mod
    import listo.ui.panels.export as ep
    import listo.ui.window.main_window as mw
    from listo.ui.components.widgets import CHOOSE

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb_mod, ep):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    lut = tmp_path / "CINECOLOR_APPLE_LOG2_A.cube"
    lut.write_text("LUT_3D_SIZE 2\n" + "0 0 0\n" * 8)
    dest = tmp_path / "Deliveries"
    dest.mkdir()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(lut), ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(dest))
    w = mw.MainWindow()
    sb, panel, s = w.sidebar, w.export_panel, w.settings

    assert _labels(sb.lut) == ["No LUT", "—", "Choose a LUT File…"]  # no LUT folder any more
    sb.lut.activated.emit(sb.lut.findData(CHOOSE))
    assert s.lut_path == str(lut)
    assert _labels(sb.lut) == ["No LUT", "—", "CINECOLOR_APPLE_LOG2_A", "—", "Choose a LUT File…"]

    assert _labels(panel.where) == ["In Source Folder", "Create Subfolder", "—", "Choose a Destination…"]
    panel.where.activated.emit(panel.where.findData("subfolder"))
    assert s.destination == "subfolder" and panel.d_sub_row.isVisibleTo(panel)  # its name, under it
    panel.where.activated.emit(panel.where.findData(CHOOSE))
    assert (s.destination, s.dest_folder) == ("folder", str(dest))
    assert not panel.d_sub_row.isVisibleTo(panel)
    assert _labels(panel.where) == [
        "In Source Folder", "Create Subfolder", "—", "Deliveries", "—", "Choose a Destination…"
    ]  # fmt: skip
    panel.where.activated.emit(panel.where.findData("source"))
    assert s.destination == "source"
    panel.where.activated.emit(panel.where.findData(str(dest)))  # picked again from the list
    assert (s.destination, s.dest_folder) == ("folder", str(dest))
    w.close()


def test_timecode_choice_is_in_clip_info(tmp_path: Path, monkeypatch, app):
    from PySide6.QtCore import QSettings

    import listo.ui.panels.convert as sb_mod
    import listo.ui.panels.export as ep
    import listo.ui.window.main_window as mw

    ini = str(tmp_path / "t.ini")
    for mod in (mw, sb_mod, ep):
        monkeypatch.setattr(mod, "QSettings", lambda *a, **k: QSettings(ini, QSettings.Format.IniFormat))
    w = mw.MainWindow()
    sb = w.sidebar
    sb.g_text.set_open(True)
    assert sb.tc_mode.isVisibleTo(sb)  # also the file's own timecode, so shown even without the burn-in
    assert _labels(sb.tc_mode) == ["Continuous Timecode", "Restart Timecode Each Clip", "Match Record Time"]
    sb.tc_mode.setCurrentIndex(sb.tc_mode.findData("record"))
    assert w.settings.timecode_mode == "record"
    assert "1 changed" in sb.g_text.header.text()
    w.close()
