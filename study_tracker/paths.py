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


def _same_path(left: str | Path, right: str | Path) -> bool:
    try:
        return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        return os.path.normcase(os.path.abspath(os.path.expanduser(str(left)))) == os.path.normcase(
            os.path.abspath(os.path.expanduser(str(right)))
        )


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
        return False
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


def _copy_tree_preserving_existing(source: Path, destination: Path) -> bool:
    """Copy legacy files without replacing any file already present at the destination."""
    if not source.is_dir():
        return True
    try:
        for item in source.rglob("*"):
            if not item.is_file():
                continue
            target = destination / item.relative_to(source)
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
        return True
    except OSError:
        return False


def _copy_file_preserving_existing(source: Path, destination: Path) -> bool:
    if not source.is_file() or destination.exists():
        return False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return True
    except OSError:
        return False


def load_config() -> dict:
    """Load configuration, migrating only old defaults and keeping custom paths intact."""
    defaults = default_config()
    bootstrap = _read_json(CONFIG_PATH)
    active_path = get_config_path()
    data = _read_json(active_path) if active_path.exists() else bootstrap
    if not isinstance(data, dict):
        data = {}
    if "ViewerPackPath" not in data and "viewer_pack_path" in data:
        data["ViewerPackPath"] = data["viewer_pack_path"]

    changed = False
    target_config_dir = Path(defaults["config_dir"])
    configured_config_dir = data.get("config_dir", bootstrap.get("config_dir"))
    if not configured_config_dir or _same_path(configured_config_dir, APP_CONFIG_DIR):
        if not configured_config_dir or not _same_path(configured_config_dir, target_config_dir):
            data["config_dir"] = str(target_config_dir)
            changed = True
    else:
        data["config_dir"] = str(Path(configured_config_dir).expanduser())

    # Move the old implicit/default DB only if the destination does not exist.
    # When both locations contain data, keep the explicitly configured legacy DB
    # active rather than silently switching the user to another database.
    legacy_db = LEGACY_DATA_DIR / "study_tracker.sqlite3"
    target_db = Path(defaults["db_path"])
    configured_db = data.get("db_path")
    uses_default_db = configured_db is None or _same_path(configured_db, legacy_db)
    if uses_default_db and not _same_path(legacy_db, target_db):
        if legacy_db.is_file():
            if not target_db.exists():
                if _migrate_legacy_database(legacy_db, target_db):
                    data["db_path"] = str(target_db)
                    changed = True
                elif configured_db is None:
                    data["db_path"] = str(legacy_db)
                    changed = True
            elif configured_db is None:
                data["db_path"] = str(legacy_db)
                changed = True
        elif configured_db is not None:
            data["db_path"] = str(target_db)
            changed = True

    # Old default logs and exports are copied, never moved or overwritten.
    legacy_locations = (
        ("log_dir", APP_CONFIG_DIR / "logs", Path(defaults["log_dir"])),
        ("export_dir", LEGACY_DATA_DIR / "exports", Path(defaults["export_dir"])),
    )
    for key, legacy_path, target_path in legacy_locations:
        configured_path = data.get(key)
        if configured_path is None or not _same_path(configured_path, legacy_path):
            continue
        if _same_path(legacy_path, target_path):
            continue
        if _copy_tree_preserving_existing(legacy_path, target_path):
            data[key] = str(target_path)
            changed = True

    # Relocate the previous default ZIP only when the configured path is the
    # old application-root default. Explicit custom ViewerPack paths are kept.
    legacy_pack = APP_ROOT / "StudyTrackerViewerPack_v0.8.1-StudyViewer.zip"
    legacy_080_pack = APP_ROOT / "StudyTrackerViewerPack_v0.8.0-StudyViewer.zip"
    configured_pack_value = data.get("ViewerPackPath", "")
    configured_pack = Path(str(configured_pack_value)).expanduser()
    default_pack = Path(defaults["ViewerPackPath"])
    if configured_pack.name == legacy_080_pack.name and default_pack.is_file():
        data["ViewerPackPath"] = str(default_pack)
        changed = True
    elif configured_pack_value and _same_path(configured_pack, legacy_pack):
        if _copy_file_preserving_existing(legacy_pack, default_pack):
            data["ViewerPackPath"] = str(default_pack)
            changed = True

    # Persist migrated defaults into user_data/config while retaining the
    # standard APPDATA bootstrap copy for future discovery.
    if changed:
        save_config({**defaults, **data})

    result = {**defaults, **data}
    result["config_dir"] = str(data.get("config_dir") or get_config_dir())
    return result


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
