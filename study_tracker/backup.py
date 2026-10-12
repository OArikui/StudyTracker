"""Safe SQLite backups and retention for StudyTracker."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path


BACKUP_GLOB = "study_tracker_backup_*.sqlite3"


def create_backup(
    database_path: str | Path,
    backup_dir: str | Path,
    retention_count: int = 14,
    *,
    now: datetime | None = None,
) -> Path:
    """Create a consistent SQLite snapshot and prune old StudyTracker backups.

    The SQLite backup API is used instead of copying the database file directly,
    so this also works while StudyTracker has the database open.
    """
    source_path = Path(database_path).expanduser().resolve()
    destination_dir = Path(backup_dir).expanduser().resolve()

    try:
        keep_count = int(retention_count)
    except (TypeError, ValueError) as exc:
        raise ValueError("retention_count must be a positive integer") from exc
    if keep_count < 1:
        raise ValueError("retention_count must be at least 1")
    if not source_path.is_file():
        raise FileNotFoundError(f"StudyTracker database not found: {source_path}")

    timestamp = (now or datetime.now().astimezone()).strftime("%Y%m%d_%H%M%S_%f")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"study_tracker_backup_{timestamp}.sqlite3"
    suffix = 1
    while destination.exists():
        destination = destination_dir / f"study_tracker_backup_{timestamp}_{suffix}.sqlite3"
        suffix += 1
    temporary = destination.with_name(destination.name + ".partial")

    source = None
    target = None
    try:
        source = sqlite3.connect(str(source_path), timeout=30)
        target = sqlite3.connect(str(temporary), timeout=30)
        source.backup(target)
        integrity = target.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise sqlite3.DatabaseError(f"Backup integrity check failed: {integrity!r}")
    finally:
        if target is not None:
            target.close()
        if source is not None:
            source.close()

    try:
        os.replace(temporary, destination)
        backups = sorted(
            destination_dir.glob(BACKUP_GLOB),
            key=lambda path: path.name,
            reverse=True,
        )
        for old_backup in backups[keep_count:]:
            old_backup.unlink()
    finally:
        if temporary.exists():
            temporary.unlink()

    return destination
