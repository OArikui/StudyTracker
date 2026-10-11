from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "StudyTracker"
CONFIG_PATH = APP_CONFIG_DIR / "config.json"
DEFAULT_DATA_DIR = Path.home() / "StudyTracker"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "study_tracker.sqlite3"
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
DEFAULT_VIEWER_PACK_PATH = APP_ROOT / "StudyTrackerViewerPack_v0.8.1-StudyViewer.zip"
DEFAULT_LOG_DIR = APP_CONFIG_DIR / "logs"
DEFAULT_EXPORT_DIR = DEFAULT_DATA_DIR / "exports"


def default_config() -> dict:
    return {
        "config_dir": str(APP_CONFIG_DIR),
        "db_path": str(DEFAULT_DB_PATH),
        "log_dir": str(DEFAULT_LOG_DIR),
        "export_dir": str(DEFAULT_EXPORT_DIR),
        "ViewerPackPath": str(DEFAULT_VIEWER_PACK_PATH),
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
    return Path(configured).expanduser() if configured else APP_CONFIG_DIR


def get_config_path() -> Path:
    return get_config_dir() / "config.json"


def load_config() -> dict:
    APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    defaults = default_config()
    bootstrap = _read_json(CONFIG_PATH)
    active_path = get_config_path()
    data = _read_json(active_path) if active_path.exists() else bootstrap
    if not isinstance(data, dict):
        data = {}
    if "ViewerPackPath" not in data and "viewer_pack_path" in data:
        data["ViewerPackPath"] = data["viewer_pack_path"]
    # Migrate the former default add-on filename only when its replacement exists.
    configured_pack = Path(str(data.get("ViewerPackPath", ""))).expanduser()
    legacy_default = APP_ROOT / "StudyTrackerViewerPack_v0.8.0-StudyViewer.zip"
    if configured_pack.name == legacy_default.name and DEFAULT_VIEWER_PACK_PATH.is_file():
        data["ViewerPackPath"] = str(DEFAULT_VIEWER_PACK_PATH)
    return {**defaults, **data, "config_dir": str(get_config_dir())}


def save_config(data: dict) -> None:
    merged = {**default_config(), **data}
    config_dir = Path(merged.get("config_dir", APP_CONFIG_DIR)).expanduser()
    merged["config_dir"] = str(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    active_path = config_dir / "config.json"
    payload = json.dumps(merged, ensure_ascii=False, indent=2)
    active_path.write_text(payload, encoding="utf-8")
    # Keep a bootstrap copy in the standard application-data location so a
    # relocated config directory remains discoverable on the next launch.
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


def set_db_path(path: str | Path) -> None:
    cfg = load_config()
    cfg["db_path"] = str(Path(path).expanduser())
    save_config(cfg)
