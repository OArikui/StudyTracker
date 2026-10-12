from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

APP_CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "StudyTracker"
CONFIG_PATH = APP_CONFIG_DIR / "config.json"
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
USER_DATA_DIR = APP_ROOT / "user_data"
_FALLBACK_USER_DATA_DIR = APP_CONFIG_DIR / "user_data"
LEGACY_DATA_DIR = Path.home() / "StudyTracker"
DEFAULT_DATA_DIR = USER_DATA_DIR / "records"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "study_tracker.sqlite3"
DEFAULT_VIEWER_PACK_PATH = USER_DATA_DIR / "packages" / "StudyTrackerViewerPack_v0.8.1-StudyViewer.zip"
DEFAULT_VIEWER_FOLDER_PATH = ""
DEFAULT_LOG_DIR = USER_DATA_DIR / "logs"
DEFAULT_EXPORT_DIR = USER_DATA_DIR / "exports"


def _ensure_user_data_root() -> Path:
    """Create the portable user_data layout, falling back if the app root is read-only."""
    for root in (USER_DATA_DIR, _FALLBACK_USER_DATA_DIR):
        try:
            for child in ("config", "records", "logs", "exports", "packages"):
                (root / child).mkdir(parents=True, exist_ok=True)
            return root
        except OSError:
            continue
    raise OSError("StudyTracker の user_data 保存先を作成できませんでした。保存先を変更してください。")


def default_config() -> dict:
    root = _ensure_user_data_root()
    return {
        "config_dir": str(root / "config"),
        "db_path": str(root / "records" / "study_tracker.sqlite3"),
        "log_dir": str(root / "logs"),
        "export_dir": str(root / "exports"),
        "ViewerPackPath": str(root / "packages" / "StudyTrackerViewerPack_v0.8.1-StudyViewer.zip"),
        "ViewerFolderPath": "",
    }


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def get_config_dir() -> Path:
    bootstrap = _read_json(CONFIG_PATH)
    configured = bootstrap.get("config_dir")
    if configured:
        return Path(configured).expanduser()
    try:
        return Path(default_config()["config_dir"])
    except OSError:
        return APP_CONFIG_DIR


def get_config_path() -> Path:
    return get_config_dir() / "config.json"


def _migrate_legacy_database(legacy: Path, destination: Path) -> bool:
    """Copy the legacy default DB using SQLite's backup API without replacing anything."""
    if not legacy.is_file() or destination.exists():
        return destination.exists()
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = target = None
    try:
        source = sqlite3.connect(str(legacy), timeout=30)
        target = sqlite3.connect(str(destination), timeout=30)
        source.backup(target)
        integrity = target.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise sqlite3.DatabaseError(f"integrity_check failed: {integrity!r}")
        target.close()
        target = None
        source.close()
        source = None
        return True
    except (OSError, sqlite3.Error):
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    finally:
        if target is not None:
            target.close()
        if source is not None:
            source.close()


def load_config() -> dict:
    defaults = default_config()
    bootstrap = _read_json(CONFIG_PATH)
    active_path = get_config_path()
    data = _read_json(active_path) if active_path.exists() else bootstrap
    if not isinstance(data, dict):
        data = {}
    if "ViewerPackPath" not in data and "viewer_pack_path" in data:
        data["ViewerPackPath"] = data["viewer_pack_path"]

    # Migrate only the old implicit default, and never overwrite an existing DB.
    if "db_path" not in data:
        legacy = LEGACY_DATA_DIR / "study_tracker.sqlite3"
        target = Path(defaults["db_path"])
        if legacy.resolve() != target.resolve() and legacy.is_file() and not target.exists():
            if not _migrate_legacy_database(legacy, target):
                # Prefer the existing legacy data over silently starting an empty DB.
                defaults["db_path"] = str(legacy)

    legacy_pack = APP_ROOT / "StudyTrackerViewerPack_v0.8.0-StudyViewer.zip"
    configured_pack = Path(str(data.get("ViewerPackPath", ""))).expanduser()
    default_pack = Path(defaults["ViewerPackPath"])
    if configured_pack.name == legacy_pack.name and default_pack.is_file():
        data["ViewerPackPath"] = str(default_pack)
    return {**defaults, **data, "config_dir": str(get_config_dir())}


def save_config(data: dict) -> None:
    merged = {**default_config(), **data}
    config_dir = Path(merged.get("config_dir", APP_CONFIG_DIR)).expanduser()
    merged["config_dir"] = str(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    active_path = config_dir / "config.json"
    payload = json.dumps(merged, ensure_ascii=False, indent=2)
    active_path.write_text(payload, encoding="utf-8")
    # Keep a small bootstrap copy in the standard application-data location so
    # a customized config directory remains discoverable on the next launch.
    APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.resolve() != active_path.resolve():
        CONFIG_PATH.write_text(payload, encoding="utf-8")


def get_path(key: str) -> Path:
    cfg = load_config()
    defaults = default_config()
    return Path(cfg.get(key, defaults[key])).expanduser()


def get_db_path() -> Path:
    return get_path("db_path")


def get_viewer_pack_path() -> Path:
    cfg = load_config()
    return Path(cfg.get("ViewerPackPath", cfg.get("viewer_pack_path", str(DEFAULT_VIEWER_PACK_PATH)))).expanduser()


def get_viewer_folder_path() -> Path | None:
    value = load_config().get("ViewerFolderPath", DEFAULT_VIEWER_FOLDER_PATH)
    return Path(value).expanduser() if str(value or "").strip() else None


def set_db_path(path: str | Path) -> None:
    cfg = load_config()
    cfg["db_path"] = str(Path(path).expanduser())
    save_config(cfg)
