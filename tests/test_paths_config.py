from pathlib import Path

from study_tracker import paths


def _isolate_paths(tmp_path, monkeypatch, app_root=None):
    root = app_root or tmp_path / "app-root"
    root.mkdir(parents=True, exist_ok=True)
    config_dir = tmp_path / "appdata"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths, "APP_ROOT", root)
    monkeypatch.setattr(paths, "USER_DATA_DIR", root / "user_data")
    monkeypatch.setattr(paths, "_FALLBACK_USER_DATA_DIR", config_dir / "user_data")
    monkeypatch.setattr(paths, "APP_CONFIG_DIR", config_dir)
    monkeypatch.setattr(paths, "CONFIG_PATH", config_dir / "config.json")
    return root, config_dir


def test_default_viewer_pack_path_is_inside_user_data_and_named_correctly():
    target = paths.default_config()["ViewerPackPath"]
    assert Path(target).parent == paths.APP_ROOT / "user_data" / "packages"
    assert Path(target).name.startswith("StudyTrackerViewerPack_v0.8.1-")
    assert Path(target).suffix == ".zip"


def test_config_round_trip_and_legacy_viewer_pack_key(tmp_path, monkeypatch):
    _isolate_paths(tmp_path, monkeypatch)
    paths.save_config({
        "db_path": str(tmp_path / "db.sqlite3"),
        "ViewerPackPath": str(tmp_path / "pack.zip"),
    })
    loaded = paths.load_config()
    assert loaded["db_path"] == str(tmp_path / "db.sqlite3")
    assert loaded["ViewerPackPath"] == str(tmp_path / "pack.zip")
    assert paths.get_viewer_pack_path() == tmp_path / "pack.zip"


def test_legacy_lowercase_viewer_pack_path_is_migrated(tmp_path, monkeypatch):
    _, config_dir = _isolate_paths(tmp_path, monkeypatch)
    paths.CONFIG_PATH.write_text(
        '{"viewer_pack_path":"legacy.zip"}',
        encoding="utf-8",
    )
    assert paths.get_viewer_pack_path() == Path("legacy.zip")


def test_config_directory_can_be_relocated_and_discovered(tmp_path, monkeypatch):
    _isolate_paths(tmp_path, monkeypatch)
    target_dir = tmp_path / "portable-config"
    paths.save_config({
        "config_dir": str(target_dir),
        "db_path": str(tmp_path / "db.sqlite3"),
    })
    assert (target_dir / "config.json").is_file()
    assert paths.get_config_dir() == target_dir
    assert paths.load_config()["db_path"] == str(tmp_path / "db.sqlite3")
    # Bootstrap copy remains available in the standard location.
    assert paths.CONFIG_PATH.is_file()



def test_legacy_default_paths_migrate_without_overwriting_existing_files(tmp_path, monkeypatch):
    import json
    import sqlite3

    app_root = tmp_path / "StudyTracker_v3_3_2"
    _, config_dir = _isolate_paths(tmp_path, monkeypatch, app_root=app_root)
    legacy_data = tmp_path / "legacy-home" / "StudyTracker"
    legacy_data.mkdir(parents=True)
    monkeypatch.setattr(paths, "LEGACY_DATA_DIR", legacy_data)

    legacy_db = legacy_data / "study_tracker.sqlite3"
    connection = sqlite3.connect(legacy_db)
    try:
        connection.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY, marker TEXT)")
        connection.execute("INSERT INTO sessions(marker) VALUES ('preserve-me')")
        connection.execute("CREATE TABLE segments (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()

    legacy_logs = config_dir / "logs"
    legacy_logs.mkdir()
    (legacy_logs / "previous.log").write_text("old log", encoding="utf-8")
    legacy_exports = legacy_data / "exports"
    legacy_exports.mkdir()
    (legacy_exports / "old.csv").write_text("old export", encoding="utf-8")
    legacy_pack = app_root / "StudyTrackerViewerPack_v0.8.1-StudyViewer.zip"
    legacy_pack.write_bytes(b"old viewer package")

    paths.CONFIG_PATH.write_text(json.dumps({
        "config_dir": str(config_dir),
        "db_path": str(legacy_db),
        "log_dir": str(legacy_logs),
        "export_dir": str(legacy_exports),
        "ViewerPackPath": str(legacy_pack),
    }), encoding="utf-8")

    loaded = paths.load_config()
    new_root = app_root / "user_data"

    assert Path(loaded["config_dir"]) == new_root / "config"
    assert Path(loaded["db_path"]) == new_root / "records" / "study_tracker.sqlite3"
    assert Path(loaded["log_dir"]) == new_root / "logs"
    assert Path(loaded["export_dir"]) == new_root / "exports"
    assert Path(loaded["ViewerPackPath"]) == new_root / "packages" / legacy_pack.name

    migrated = sqlite3.connect(loaded["db_path"])
    try:
        assert migrated.execute("SELECT marker FROM sessions").fetchone() == ("preserve-me",)
    finally:
        migrated.close()

    # Migration copies rather than moves legacy files, so the old paths remain recoverable.
    assert legacy_db.is_file()
    assert (legacy_logs / "previous.log").read_text(encoding="utf-8") == "old log"
    assert (new_root / "logs" / "previous.log").read_text(encoding="utf-8") == "old log"
    assert (legacy_exports / "old.csv").is_file()
    assert (new_root / "exports" / "old.csv").read_text(encoding="utf-8") == "old export"
    assert legacy_pack.is_file()
    assert (new_root / "packages" / legacy_pack.name).read_bytes() == b"old viewer package"

def test_legacy_default_viewer_pack_migrates_to_current_root(tmp_path, monkeypatch):
    current_root = tmp_path / "StudyTracker_v3_3_2"
    _isolate_paths(tmp_path, monkeypatch, app_root=current_root)
    new_pack = current_root / "user_data" / "packages" / "StudyTrackerViewerPack_v0.8.1-StudyViewer.zip"
    new_pack.parent.mkdir(parents=True, exist_ok=True)
    new_pack.write_bytes(b"zip placeholder")
    legacy = tmp_path / "StudyTracker_v3_3_1" / "StudyTrackerViewerPack_v0.8.0-StudyViewer.zip"
    paths.CONFIG_PATH.write_text(
        __import__("json").dumps({"ViewerPackPath": str(legacy)}),
        encoding="utf-8",
    )

    assert paths.get_viewer_pack_path() == new_pack
