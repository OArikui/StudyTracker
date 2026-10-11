from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import sys


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
    return log_directory() / "study_tracker.log"


def configure_logging() -> Path:
    path = log_path()
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(getattr(h, "_study_tracker_handler", False) for h in root.handlers):
        handler._study_tracker_handler = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    else:
        handler.close()
    return path


def export_log(destination: str | Path) -> Path:
    source = log_path()
    if not source.exists():
        source.write_text("StudyTracker log is empty.\n", encoding="utf-8")
    target = Path(destination)
    if source.resolve() == target.expanduser().resolve():
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
