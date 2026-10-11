from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

JST = timezone(timedelta(hours=9))


class StudyTrackerFormatError(RuntimeError):
    pass


@dataclass(frozen=True)
class Segment:
    segment_id: int
    session_id: int
    start: datetime
    end: datetime
    active: bool
    date: str
    category: str
    subject: str
    material: str
    position: str
    unit: str
    scope: str
    actual_scope: str
    notes: tuple[str, ...]
    branch_fields: tuple[int, ...]

    @property
    def duration_seconds(self) -> float:
        return max(0.0, (self.end - self.start).total_seconds())

    @property
    def day(self):
        return self.start.astimezone(JST).date()

    @property
    def label(self) -> str:
        return " / ".join(x for x in (self.subject, self.material, self.position, self.unit) if x)


@dataclass(frozen=True)
class TimestampRecord:
    timestamp_id: int
    session_id: int
    segment_start_at: datetime
    at: datetime
    location: str
    unit: str
    subject: str
    material: str


class StudyTrackerReader:
    """Read-only reader for the StudyTracker SQLite schema."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"Database not found: {self.path}")
        self.con = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA query_only=ON")
        self._validate()

    def close(self) -> None:
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

    def _validate(self) -> None:
        rows = self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        tables = {r[0] for r in rows}
        missing = {"segments"} - tables
        if missing:
            raise StudyTrackerFormatError(
                "This file is not a supported StudyTracker database "
                f"(missing tables: {', '.join(sorted(missing))})."
            )

    def table_names(self) -> set[str]:
        return {r[0] for r in self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def read_timestamps(self) -> list[TimestampRecord]:
        if "timestamps" not in self.table_names():
            return []
        rows = self.con.execute(
            "SELECT id, session_id, segment_start_at, at, location, unit, subject, material "
            "FROM timestamps ORDER BY at, id"
        ).fetchall()
        return [
            TimestampRecord(
                timestamp_id=int(r["id"]),
                session_id=int(r["session_id"]),
                segment_start_at=self._parse_dt(r["segment_start_at"]),
                at=self._parse_dt(r["at"]),
                location=str(r["location"]),
                unit=str(r["unit"]),
                subject=str(r["subject"]),
                material=str(r["material"]),
            )
            for r in rows
        ]

    def read_segments(self) -> list[Segment]:
        rows = self.con.execute(
            "SELECT id, session_id, start_at, end_at, active, row_json "
            "FROM segments ORDER BY start_at, id"
        ).fetchall()
        result: list[Segment] = []
        for row in rows:
            try:
                payload: dict[str, Any] = json.loads(row["row_json"])
                notes = payload.get("notes", [])
                if isinstance(notes, str):
                    notes = [notes]
                result.append(
                    Segment(
                        segment_id=int(row["id"]),
                        session_id=int(row["session_id"]),
                        start=self._parse_dt(row["start_at"]),
                        end=self._parse_dt(row["end_at"]),
                        active=bool(row["active"]),
                        date=str(payload.get("date", "")),
                        category=str(payload.get("category", "")),
                        subject=str(payload.get("subject", "")),
                        material=str(payload.get("material", "")),
                        position=str(payload.get("position", "")),
                        unit=str(payload.get("unit", "")),
                        scope=str(payload.get("scope", "")),
                        actual_scope=str(payload.get("actual_scope", "")),
                        notes=tuple(str(x) for x in notes),
                        branch_fields=tuple(int(x) for x in payload.get("branch_fields", [])),
                    )
                )
            except (TypeError, ValueError, json.JSONDecodeError, KeyError) as exc:
                raise StudyTrackerFormatError(
                    f"Invalid segment data at segments.id={row['id']}: {exc}"
                ) from exc
        return result

    @staticmethod
    def _parse_dt(value: str) -> datetime:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return dt
