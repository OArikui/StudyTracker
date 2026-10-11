from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .ui import ViewerWindow


def run(database_path: str | Path | None = None) -> int:
    """Run the Viewer against the database configured by the StudyTracker host.

    StudyTracker must pass its configured ``db_path`` explicitly. The Viewer
    deliberately has no independent database-path fallback.
    """
    selected = database_path
    if not selected:
        raise ValueError(
            "ViewerPackはStudyTracker本体から起動してください。"
            "本体のdb_pathがViewerへ渡されていません。"
        )
    path = Path(selected).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"StudyTracker本体の設定DBが見つかりません: {path}")

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("StudyTracker Viewer")
    window = ViewerWindow(database_path=path)
    window.show()
    return app.exec()
