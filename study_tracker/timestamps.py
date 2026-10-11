from __future__ import annotations

from dataclasses import dataclass
import re


_SCOPE_PART_RE = re.compile(r"(?<![\w-])(\d+)\s*(?:-\s*(\d+))?(?![\w-])")


@dataclass(frozen=True)
class TimestampAssessment:
    warnings: tuple[str, ...]
    completes_scope: bool
    position: int | None


def parse_scope_ranges(scope: str) -> list[tuple[int, int]]:
    """Extract inclusive numeric ranges from a scope such as ``21-42,45``."""
    result: list[tuple[int, int]] = []
    for match in _SCOPE_PART_RE.finditer(str(scope or "")):
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if last < first:
            first, last = last, first
        result.append((first, last))
    return result


def assess_timestamp(
    location: str,
    planned_scope: str,
    previous_locations: list[str],
) -> TimestampAssessment:
    """Check a numeric timestamp against a planned scope and completed prefix.

    A range is considered complete when the user records its final planned
    numeric position. This intentionally does not infer completion from an
    out-of-range position.
    """
    raw = str(location or "").strip()
    if not raw.isdigit():
        return TimestampAssessment(("学習位置が整数ではないため、範囲を判定できません。",), False, None)

    position = int(raw)
    ranges = parse_scope_ranges(planned_scope)
    previous = [int(str(item).strip()) for item in previous_locations if str(item).strip().isdigit()]
    warnings: list[str] = []

    if not ranges:
        warnings.append("学習範囲に数値範囲がないため、範囲外かどうか判定できません。")
    elif not any(first <= position <= last for first, last in ranges):
        planned = ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges)
        warnings.append(f"入力位置 {position} は学習予定範囲（{planned}）の外です。")

    planned_start = min(start for start, _ in ranges) if ranges else None
    if position in previous:
        warnings.append(f"位置 {position} は既にタイムスタンプとして記録されています。")
    elif previous and planned_start is not None:
        completed_end = max(previous)
        if planned_start <= position <= completed_end:
            warnings.append(
                f"位置 {position} は既に実施済みとみなされる範囲（{planned_start}-{completed_end}）に含まれます。"
            )

    final_position = max((end for _, end in ranges), default=None)
    completes_scope = final_position is not None and position == final_position
    return TimestampAssessment(tuple(warnings), completes_scope, position)
