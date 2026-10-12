from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from study_tracker.db import Database
from study_tracker.export import export_csv, export_xlsx
from study_tracker.import_export import import_export_file, restore_database_snapshot
from study_tracker.models import StudyRow


def _study_row(*, end: str = "11:30:00.00", subject: str = "数学") -> StudyRow:
    return StudyRow(
        date="2026.10.10",
        start="10:00:00.00",
        end=end,
        timezone="Asia/Tokyo",
        category="学習",
        subject=subject,
        material="教科書",
        position="p.10",
        unit="問題",
        scope="1-5",
        notes=["インポート試験"],
    )


def _add_db_record(database: Database, *, subject: str, date: str) -> None:
    start = datetime.fromisoformat(f"{date}T09:00:00+09:00")
    end = start + timedelta(minutes=30)
    session_id = database.start_session(start)
    database.add_segment(session_id, start, end, True, {
        "date": date.replace("-", "."),
        "start": "09:00:00.00",
        "end": "09:30:00.00",
        "timezone": "Asia/Tokyo",
        "category": "学習",
        "subject": subject,
        "material": "教科書",
        "position": "p.1",
        "unit": "問題",
        "scope": "1-2",
        "actual_scope": "",
        "notes": [],
        "branch_fields": [],
    })
    database.close_session(session_id, end)


def test_imports_csv_export_without_replacing_existing_records(tmp_path: Path) -> None:
    db = Database(tmp_path / "current.sqlite3")
    _add_db_record(db, subject="既存科目", date="2026-10-09")
    export_path = tmp_path / "export.csv"
    export_csv([_study_row()], export_path)

    summary = import_export_file(db, export_path)

    assert summary.imported == 1
    assert summary.skipped == 0
    subjects = [row.subject for row in db.archive_rows()]
    assert subjects == ["既存科目", "数学"]
    db.close()


def test_imports_xlsx_and_aliases(tmp_path: Path) -> None:
    db = Database(tmp_path / "current.sqlite3")
    export_path = tmp_path / "export.xlsx"
    export_xlsx([_study_row()], [{"title": "p", "docstring": "ページ"}], export_path)

    summary = import_export_file(db, export_path)

    assert summary.imported == 1
    assert summary.aliases_added == 1
    assert [(row["title"], row["docstring"]) for row in db.aliases()] == [("p", "ページ")]
    db.close()


def test_skips_records_with_missing_end_time(tmp_path: Path) -> None:
    db = Database(tmp_path / "current.sqlite3")
    export_path = tmp_path / "incomplete.csv"
    export_csv([_study_row(end="--:--:--")], export_path)

    summary = import_export_file(db, export_path)

    assert summary.imported == 0
    assert summary.skipped == 1
    assert summary.warnings
    assert db.archive_rows() == []
    db.close()


def test_restore_keeps_previous_database_as_separate_backup(tmp_path: Path) -> None:
    current_path = tmp_path / "current.sqlite3"
    snapshot_path = tmp_path / "snapshot.sqlite3"
    current = Database(current_path)
    _add_db_record(current, subject="古い記録", date="2026-10-09")
    current.close()
    snapshot = Database(snapshot_path)
    _add_db_record(snapshot, subject="復元記録", date="2026-10-10")
    snapshot.close()

    saved_copy = restore_database_snapshot(snapshot_path, current_path, tmp_path / "backups")

    assert saved_copy.is_file()
    restored = Database(current_path)
    assert [row.subject for row in restored.archive_rows()] == ["復元記録"]
    restored.close()

    preserved = Database(saved_copy)
    assert [row.subject for row in preserved.archive_rows()] == ["古い記録"]
    preserved.close()
