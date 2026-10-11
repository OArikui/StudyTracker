from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
import re

from .reader import Segment


@dataclass(frozen=True)
class Summary:
    total_seconds: float
    study_days: int
    sessions: int
    segments: int
    average_seconds: float
    longest_seconds: float


def filter_segments(
    segments: list[Segment],
    *,
    start: date | None = None,
    end: date | None = None,
    category: str = "",
    subject: str = "",
    material: str = "",
    query: str = "",
    active_only: bool = False,
) -> list[Segment]:
    needle = query.strip().casefold()
    out: list[Segment] = []
    for s in segments:
        if start and s.day < start:
            continue
        if end and s.day > end:
            continue
        if category and s.category != category:
            continue
        if subject and s.subject != subject:
            continue
        if material and s.material != material:
            continue
        if active_only and not s.active:
            continue
        if needle:
            haystack = " ".join(
                (s.category, s.subject, s.material, s.position, s.unit, s.scope, s.actual_scope, *s.notes)
            ).casefold()
            if needle not in haystack:
                continue
        out.append(s)
    return out


def summarize(rows: list[Segment]) -> Summary:
    durations = [s.duration_seconds for s in rows]
    return Summary(
        total_seconds=sum(durations),
        study_days=len({s.day for s in rows}),
        sessions=len({s.session_id for s in rows}),
        segments=len(rows),
        average_seconds=(sum(durations) / len(durations)) if durations else 0.0,
        longest_seconds=max(durations, default=0.0),
    )


def group_seconds(rows: list[Segment], key: str) -> list[tuple[str, float]]:
    acc: defaultdict[str, float] = defaultdict(float)
    for s in rows:
        value = getattr(s, key)
        label = value or "(未設定)"
        acc[label] += s.duration_seconds
    return sorted(acc.items(), key=lambda x: (-x[1], x[0]))


def daily_seconds(rows: list[Segment]) -> list[tuple[date, float]]:
    acc: defaultdict[date, float] = defaultdict(float)
    for s in rows:
        acc[s.day] += s.duration_seconds
    return sorted(acc.items())


def format_duration(seconds: float) -> str:
    sec = max(0, int(round(seconds)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}時間 {m:02d}分"
    if m:
        return f"{m}分 {s:02d}秒"
    return f"{s}秒"


def period_bounds(kind: str, rows: list[Segment], today: date | None = None) -> tuple[date | None, date | None]:
    today = today or date.today()
    if kind == "今日":
        return today, today
    if kind == "今週":
        return today - timedelta(days=today.weekday()), today
    if kind == "直近7日":
        return today - timedelta(days=6), today
    if kind == "直近30日":
        return today - timedelta(days=29), today
    if kind == "今月":
        return today.replace(day=1), today
    if kind in ("全期間", "カスタム"):
        if not rows:
            return None, None
        days = [s.day for s in rows]
        return min(days), max(days)
    return None, None



def _first_int(value: str) -> int | None:
    m = re.search(r"\d+", str(value or ""))
    return int(m.group(0)) if m else None


def scope_quantity(value: str) -> int | None:
    """Estimate the number of learning units represented by a scope string.

    Examples: ``p(21-42,45)`` -> 23, ``10-12`` -> 3, ``p.21-30`` -> 10.
    The parser intentionally ignores labels such as ``p`` or ``section`` and
    counts inclusive integer ranges plus single integers.
    """
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"\(([^()]*)\)", text)
    if match:
        text = match.group(1)
    text = text.replace("–", "-").replace("—", "-").replace("〜", "-").replace("~", "-")
    total = 0
    found = False
    for token in re.split(r"[,，、;；\s]+", text):
        token = token.strip()
        if not token:
            continue
        range_match = re.search(r"(-?\d+)\s*-\s*(-?\d+)", token)
        if range_match:
            a, b = int(range_match.group(1)), int(range_match.group(2))
            total += abs(b - a) + 1
            found = True
            continue
        nums = re.findall(r"-?\d+", token)
        if len(nums) == 1:
            total += 1
            found = True
    return total if found else None


def _timestamp_rate_points_for_segment(segment, timestamps):
    points = []
    prev_time = segment.start
    prev_location = _first_int(segment.scope)
    for t in timestamps:
        try:
            location = int(str(t.location).strip())
        except (TypeError, ValueError):
            prev_time = t.at
            prev_location = None
            continue
        if prev_location is not None and t.at > prev_time and location >= prev_location:
            hours = (t.at - prev_time).total_seconds() / 3600.0
            if hours > 0:
                points.append((t.at, (location - prev_location) / hours))
        prev_time = t.at
        prev_location = location
    return points


def timestamp_rate_points(segments, timestamps):
    """Return study-units-per-hour points derived from numeric timestamps."""
    by_key = defaultdict(list)
    for t in timestamps:
        by_key[(t.session_id, t.segment_start_at)].append(t)

    points = []
    for segment in segments:
        ts = sorted(
            by_key.get((segment.session_id, segment.start), []),
            key=lambda x: (x.at, x.timestamp_id),
        )
        if ts:
            points.extend(_timestamp_rate_points_for_segment(segment, ts))
    return sorted(points, key=lambda x: x[0])


def study_rate_series(segments, timestamps):
    """Build actual and planned study-rate series.

    Segments with timestamps use timestamp-derived rates. When a segment has
    no timestamps at all, the actual rate falls back to
    ``actual_scope_quantity / segment_duration``. Planned rate is always
    derived from ``scope_quantity / segment_duration`` when possible.
    """
    by_key = defaultdict(list)
    for t in timestamps:
        by_key[(t.session_id, t.segment_start_at)].append(t)

    actual = []
    planned = []
    for segment in segments:
        duration_hours = segment.duration_seconds / 3600.0
        if duration_hours <= 0:
            continue

        planned_qty = scope_quantity(segment.scope)
        if planned_qty is not None:
            planned.append((segment.end, planned_qty / duration_hours))

        ts = sorted(
            by_key.get((segment.session_id, segment.start), []),
            key=lambda x: (x.at, x.timestamp_id),
        )
        if ts:
            actual.extend(_timestamp_rate_points_for_segment(segment, ts))
            continue

        actual_qty = scope_quantity(segment.actual_scope)
        if actual_qty is not None:
            actual.append((segment.end, actual_qty / duration_hours))

    actual.sort(key=lambda x: x[0])
    planned.sort(key=lambda x: x[0])
    return actual, planned
