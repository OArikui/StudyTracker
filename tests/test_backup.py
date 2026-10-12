from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from study_tracker.backup import create_backup


def _make_database(path):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE records (value TEXT NOT NULL)")
        connection.execute("INSERT INTO records(value) VALUES (?)", ("preserved",))


def test_create_backup_contains_consistent_sqlite_snapshot(tmp_path):
    database = tmp_path / "study_tracker.sqlite3"
    _make_database(database)

    output = create_backup(database, tmp_path / "backups", retention_count=14)

    assert output.is_file()
    assert output.name.startswith("study_tracker_backup_")
    with sqlite3.connect(output) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT value FROM records").fetchone()[0] == "preserved"


def test_create_backup_keeps_only_configured_number_of_generations(tmp_path):
    database = tmp_path / "study_tracker.sqlite3"
    _make_database(database)
    destination = tmp_path / "backups"
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    outputs = [
        create_backup(
            database,
            destination,
            retention_count=2,
            now=start + timedelta(hours=hour),
        )
        for hour in range(3)
    ]

    backups = list(destination.glob("study_tracker_backup_*.sqlite3"))
    assert len(backups) == 2
    assert outputs[-1].exists()
    assert not outputs[0].exists()
    assert outputs[-1].name > outputs[-2].name


def test_create_backup_rejects_missing_database_and_invalid_retention(tmp_path):
    with pytest.raises(FileNotFoundError):
        create_backup(tmp_path / "missing.sqlite3", tmp_path / "backups")

    database = tmp_path / "study_tracker.sqlite3"
    _make_database(database)
    with pytest.raises(ValueError):
        create_backup(database, tmp_path / "backups", retention_count=0)
