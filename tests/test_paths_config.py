from pathlib import Path

from study_tracker import paths


def test_default_viewer_pack_path_is_in_app_root_and_named_correctly():
    target = paths.default_config()["ViewerPackPath"]
    assert Path(target).parent == paths.APP_ROOT
    assert Path(target).name.startswith("StudyTrackerViewerPack_v0.8.1-")
    assert Path(target).suffix == ".zip"


def test_config_round_trip_and_legacy_viewer_pack_key(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "APP_CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(paths, "CONFIG_PATH", tmp_path / "config" / "config.json")
    paths.save_config({"db_path": str(tmp_path / "db.sqlite3"), "ViewerPackPath": str(tmp_path / "pack.zip")})
    loaded = paths.load_config()
    assert loaded["db_path"] == str(tmp_path / "db.sqlite3")
    assert loaded["ViewerPackPath"] == str(tmp_path / "pack.zip")
    assert paths.get_viewer_pack_path() == tmp_path / "pack.zip"


def test_legacy_lowercase_viewer_pack_path_is_migrated(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(paths, "APP_CONFIG_DIR", config_dir)
    monkeypatch.setattr(paths, "CONFIG_PATH", config_dir / "config.json")
    paths.CONFIG_PATH.write_text('{"viewer_pack_path":"legacy.zip"}', encoding="utf-8")
    assert paths.get_viewer_pack_path() == Path("legacy.zip")


def test_config_directory_can_be_relocated_and_discovered(tmp_path, monkeypatch):
    bootstrap_dir = tmp_path / "bootstrap"
    monkeypatch.setattr(paths, "APP_CONFIG_DIR", bootstrap_dir)
    monkeypatch.setattr(paths, "CONFIG_PATH", bootstrap_dir / "config.json")
    target_dir = tmp_path / "portable-config"
    paths.save_config({"config_dir": str(target_dir), "db_path": str(tmp_path / "db.sqlite3")})
    assert (target_dir / "config.json").is_file()
    assert paths.get_config_dir() == target_dir
    assert paths.load_config()["db_path"] == str(tmp_path / "db.sqlite3")
    # Bootstrap copy remains available in the standard location.
    assert paths.CONFIG_PATH.is_file()


def test_legacy_default_viewer_pack_migrates_to_current_root(tmp_path, monkeypatch):
    from pathlib import Path

    config_dir = tmp_path / "appdata"
    config_dir.mkdir()
    monkeypatch.setattr(paths, "APP_CONFIG_DIR", config_dir)
    monkeypatch.setattr(paths, "CONFIG_PATH", config_dir / "config.json")
    current_root = tmp_path / "StudyTracker_v3_3_2"
    current_root.mkdir()
    new_pack = current_root / "StudyTrackerViewerPack_v0.8.1-StudyViewer.zip"
    new_pack.write_bytes(b"zip placeholder")
    monkeypatch.setattr(paths, "APP_ROOT", current_root)
    monkeypatch.setattr(paths, "DEFAULT_VIEWER_PACK_PATH", new_pack)
    legacy = tmp_path / "StudyTracker_v3_3_1" / "StudyTrackerViewerPack_v0.8.0-StudyViewer.zip"
    paths.CONFIG_PATH.write_text(
        __import__("json").dumps({"ViewerPackPath": str(legacy)}), encoding="utf-8"
    )

    assert paths.get_viewer_pack_path() == new_pack
