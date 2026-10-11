from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
import json
from typing import Iterable

JST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class Record:
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
    notes: tuple[str, ...]
    branch_fields: tuple[int, ...]

    @property
    def duration(self) -> float:
        return max(0.0, (self.end - self.start).total_seconds())

    @property
    def day(self) -> date:
        return self.start.astimezone(JST).date()


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return dt


def load_records(db) -> list[Record]:
    records: list[Record] = []
    for row in db.segments(active_only=False):
        payload = json.loads(row["row_json"])
        notes = tuple(payload.get("notes", []))
        records.append(
            Record(
                segment_id=row["id"],
                session_id=row["session_id"],
                start=_parse_iso(row["start_at"]),
                end=_parse_iso(row["end_at"]),
                active=bool(row["active"]),
                date=payload.get("date", ""),
                category=payload.get("category", ""),
                subject=payload.get("subject", ""),
                material=payload.get("material", ""),
                position=payload.get("position", ""),
                unit=payload.get("unit", ""),
                scope=payload.get("scope", ""),
                notes=notes,
                branch_fields=tuple(payload.get("branch_fields", [])),
            )
        )
    return records


def overlap_seconds(record: Record, start: datetime | None, end: datetime | None) -> float:
    a = record.start
    b = record.end
    if start is not None:
        a = max(a, start)
    if end is not None:
        b = min(b, end)
    if b <= a:
        return 0.0
    return (b - a).total_seconds()


def filter_records(
    records: Iterable[Record],
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    category: str = "",
    subject: str = "",
    material: str = "",
    query: str = "",
    active_only: bool = True,
) -> list[Record]:
    q = query.strip().casefold()
    out: list[Record] = []
    for record in records:
        if active_only and not record.active:
            continue
        if start is not None and record.end <= start:
            continue
        if end is not None and record.start >= end:
            continue
        if category and record.category != category:
            continue
        if subject and record.subject != subject:
            continue
        if material and record.material != material:
            continue
        if q:
            haystack = " ".join(
                [
                    record.category,
                    record.subject,
                    record.material,
                    record.position,
                    record.unit,
                    record.scope,
                    *record.notes,
                ]
            ).casefold()
            if q not in haystack:
                continue
        out.append(record)
    return out


def aggregate_duration(
    records: Iterable[Record],
    *,
    key,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[tuple[str, float]]:
    totals = defaultdict(float)
    for record in records:
        duration = overlap_seconds(record, start, end)
        if duration <= 0:
            continue
        value = key(record) or "(未設定)"
        totals[value] += duration
    return sorted(totals.items(), key=lambda item: (-item[1], item[0]))


def daily_totals(records: Iterable[Record], start: datetime, end: datetime) -> list[tuple[date, float]]:
    totals = defaultdict(float)
    day = start.astimezone(JST).date()
    end_day = (end - timedelta(microseconds=1)).astimezone(JST).date()
    while day <= end_day:
        totals[day] = 0.0
        day += timedelta(days=1)

    for record in records:
        cursor = max(record.start, start)
        finish = min(record.end, end)
        while cursor < finish:
            local_day = cursor.astimezone(JST).date()
            next_midnight = datetime.combine(
                local_day + timedelta(days=1),
                datetime.min.time(),
                tzinfo=JST,
            )
            piece_end = min(finish, next_midnight)
            totals[local_day] += (piece_end - cursor).total_seconds()
            cursor = piece_end

    return sorted(totals.items())


def calendar_totals(records: Iterable[Record], start: datetime, end: datetime) -> dict[date, float]:
    return dict(daily_totals(records, start, end))


def unique_values(records: Iterable[Record], attr: str) -> list[str]:
    values = {getattr(record, attr) for record in records if getattr(record, attr)}
    return sorted(values, key=str.casefold)


def stats(records: list[Record], start: datetime, end: datetime) -> dict:
    clipped = [overlap_seconds(r, start, end) for r in records]
    clipped = [x for x in clipped if x > 0]
    total = sum(clipped)
    days = len({r.day for r in records if overlap_seconds(r, start, end) > 0})
    sessions = len({r.session_id for r in records if overlap_seconds(r, start, end) > 0})
    longest = max(clipped, default=0.0)
    average = total / len(clipped) if clipped else 0.0
    return {
        "total": total,
        "study_days": days,
        "sessions": sessions,
        "segments": len(clipped),
        "average": average,
        "longest": longest,
    }
