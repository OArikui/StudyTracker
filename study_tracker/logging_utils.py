from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
import shutil
import sys

_CURRENT_LOG_PATH: Path | None = None


def log_directory() -> Path:
    try:
        from .paths import get_path
        base = get_path("log_dir")
    except Exception:
        base = Path(os.environ.get("APPDATA", Path.home())) / "StudyTracker" / "logs"
    try:
        base.mkdir(parents=True, exist_ok=True)
        return base
    except OSError:
        fallback = Path.home() / "StudyTracker" / "logs"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def log_path() -> Path:
    """Return this process' log file, creating a per-launch filename if needed."""
    global _CURRENT_LOG_PATH
    if _CURRENT_LOG_PATH is None:
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        candidate = log_directory() / f"study_tracker_{stamp}.log"
        suffix = 1
        while candidate.exists():
            candidate = log_directory() / f"study_tracker_{stamp}_{suffix}.log"
            suffix += 1
        _CURRENT_LOG_PATH = candidate
    return _CURRENT_LOG_PATH


def configure_logging() -> Path:
    global _CURRENT_LOG_PATH
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for existing in root.handlers:
        if getattr(existing, "_study_tracker_handler", False):
            configured = getattr(existing, "_study_tracker_path", None)
            if configured:
                _CURRENT_LOG_PATH = Path(configured)
                return _CURRENT_LOG_PATH

    path = log_path()
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    handler._study_tracker_handler = True  # type: ignore[attr-defined]
    handler._study_tracker_path = str(path)  # type: ignore[attr-defined]
    root.addHandler(handler)
    logging.getLogger("study_tracker").info("Log initialized: %s", path)
    return path


def export_log(destination: str | Path) -> Path:
    source = log_path()
    if not source.exists():
        source.write_text("StudyTracker log is empty.\n", encoding="utf-8")
    target = Path(destination).expanduser()
    if source.resolve() == target.resolve():
        return source
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def install_exception_hook(get_main_window):
    previous_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            previous_hook(exc_type, exc_value, exc_traceback)
            return
        logging.getLogger("study_tracker").critical(
            "Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback)
        )
        window = get_main_window()
        if window is not None:
            try:
                window.report_error(
                    f"予期しないエラー: {exc_value}（詳細は設定からログを出力できます）"
                )
            except Exception:
                pass
        previous_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception
