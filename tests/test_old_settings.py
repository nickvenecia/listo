"""Settings saved by older Listo versions come across into settings.json, once, and nothing is lost."""

from __future__ import annotations

import json

from PySide6.QtCore import QByteArray

from listo.core import store

# What an older Listo kept in the system's settings store (made-up folders and names). Its settings come
# from before the timecode choice existed and use the old tape_cut_glitch switch.
OLD_SETTINGS = {
    "video_preset": "dnxhr",
    "video_resize": "1080",
    "burn_timecode": True,
    "burn_style": "vhs",
    "tape_cut_glitch": True,
    "destination": "subfolder",
    "subfolder_name": "Dailies",
    "naming": "{date}_{name}",
    "a_setting_that_no_longer_exists": 42,
}
OLD_RECIPES = [{"name": "Client Review", "values": {"video_preset": "h264", "burn_filename": True}}]


def _old_store(tmp_path):
    from listo.ui.old_settings import old_store

    old = old_store()
    old.setValue("settings", json.dumps(OLD_SETTINGS))
    old.setValue("recipes", json.dumps(OLD_RECIPES))
    old.setValue("recent_folders", json.dumps([str(tmp_path)]))
    old.setValue("group_open/text", True)
    old.setValue("updates/auto", False)
    old.setValue("geometry", QByteArray(b"\x01\xd9\xd0\xcb"))
    old.sync()
    return old


def test_old_settings_come_across_once_and_stay(qapp, tmp_path, data_folder):
    from listo.ui.old_settings import DONE, bring_over

    old = _old_store(tmp_path)
    keys_before = sorted(old.allKeys())
    assert bring_over() == 6
    data = store.prefs()
    assert data[DONE] is True
    assert json.loads(data["settings"])["subfolder_name"] == "Dailies"
    assert data["geometry"] == "01d9d0cb"  # bytes kept as text
    assert data["auto_update"] is False  # kept under an older name: today's name too
    assert sorted(old.allKeys()) == keys_before  # the old store is a backup: never changed
    assert old.value("settings") == json.dumps(OLD_SETTINGS)

    store.save_pref("accent", "green")
    data = store.prefs()
    data.pop(DONE)
    store.save_prefs(data)
    old.setValue("accent", "purple")
    assert bring_over() == 0 or store.prefs()["accent"] == "green"  # settings.json always wins


def test_the_window_opens_old_settings(qapp, tmp_path, data_folder):
    from listo.ui.old_settings import bring_over
    from listo.ui.window.main_window import MainWindow

    _old_store(tmp_path)
    bring_over()
    w = MainWindow()
    try:
        s = w.settings
        assert (s.video_preset, s.video_resize, s.subfolder_name, s.naming) == (
            "dnxhr",
            "1080",
            "Dailies",
            "{date}_{name}",
        )
        assert s.tape_glitches == "cuts"  # the old switch, read the new way
        assert s.timecode_mode == "continuous"  # added since: its default
        assert "Client Review" in [w.convert.recipe.itemText(i) for i in range(w.convert.recipe.count())]
        assert w.convert.g_text.is_open()
        assert not w.auto_update()
        assert str(tmp_path) in w.export_panel.where.recent()
        w.settings.subfolder_name = "Selects"
        w._settings_changed()
        saved = store.loads(store.prefs()["settings"], {})
        assert saved["subfolder_name"] == "Selects"  # saved as itself now, readable in settings.json
    finally:
        w.close()


def test_unreadable_recipes_are_kept_not_overwritten(qapp, data_folder):
    from listo.ui.window.main_window import MainWindow

    store.save_pref("recipes", "{ this is not a recipe list")
    w = MainWindow()
    try:
        w.convert._store_recipe("New One")
        data = store.prefs()
        assert [r["name"] for r in data["recipes"]] == ["New One"]
        kept = [k for k in data if k.startswith("recipes.unreadable-")]
        assert kept and data[kept[0]] == "{ this is not a recipe list"
    finally:
        w.close()


def test_back_up_keeps_what_is_yours(data_folder, tmp_path):
    import zipfile

    store.save_pref("recipes", OLD_RECIPES)
    (data_folder / "captions").mkdir(parents=True)
    (data_folder / "captions" / "abc.json").write_text("{}")
    (data_folder / "models").mkdir()
    (data_folder / "models" / "big.bin").write_bytes(b"0" * 100)  # downloaded again when needed: left out
    dest = tmp_path / "out" / "Listo Backup.zip"
    assert store.back_up(dest) == 2
    with zipfile.ZipFile(dest) as z:
        assert sorted(z.namelist()) == ["captions/abc.json", "settings.json"]
        assert json.loads(z.read("settings.json"))["recipes"] == OLD_RECIPES
