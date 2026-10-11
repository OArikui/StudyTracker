from __future__ import annotations
from pathlib import Path
import sys
import re
from PySide6.QtWidgets import QApplication
from .db import Database
from .ui import MainWindow
from .paths import get_db_path
from .logging_utils import configure_logging, install_exception_hook
import logging


def run():
    configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Study Tracker")
    app.setOrganizationName("Personal")

    window_ref: dict[str, MainWindow] = {}
    install_exception_hook(lambda: window_ref.get("window"))

    db_path = get_db_path()
    db = Database(db_path)

    forced_subject = None
    if getattr(sys, "frozen", False):
        stem = Path(sys.executable).stem
        m = re.match(r"^StudyTracker - (.+)$", stem)
        if m:
            forced_subject = m.group(1).strip()

    window = MainWindow(db, forced_subject=forced_subject)
    window_ref["window"] = window
    logging.getLogger("study_tracker").info("StudyTracker started (%s)", window.windowTitle())
    window.show()

    code = app.exec()
    db.close()
    raise SystemExit(code)
