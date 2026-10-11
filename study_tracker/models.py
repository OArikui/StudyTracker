from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
import json
import re

COLUMNS = [
    "年月日", "開始時刻", "終了時刻", "タイムゾーン", "学習区分",
    "科目", "教材", "学習位置", "学習単位", "学習範囲", "備考"
]

# A branch row repeats only the portion of the hierarchy that changed.
# The visual table uses the literal word "branch" in inherited cells.
HIERARCHY_END = {
    "category": 4,
    "subject": 5,
    "material": 6,
    "position": 7,
    "unit": 8,
    "scope": 9,
}


@dataclass
class StudyRow:
    date: str = ""
    start: str = ""
    end: str = ""
    timezone: str = "Asia/Tokyo"
    category: str = ""
    subject: str = ""
    material: str = ""
    position: str = ""
    unit: str = ""
    scope: str = ""
    actual_scope: str = ""
    notes: list[str] = field(default_factory=list)
    branch_fields: set[int] = field(default_factory=set)
    start_auto_at: str | None = None
    end_auto_at: str | None = None

    def actual_values(self) -> list[str]:
        return [
            self.date, self.start, self.end, self.timezone, self.category,
            self.subject, self.material, self.position, self.unit,
            self.scope, "\n".join(self.notes)
        ]

    def table_values(self) -> list[str]:
        vals = self.actual_values()
        for i in self.branch_fields:
            if 0 <= i < 10:
                vals[i] = "branch"
        return vals


@dataclass
class StudySegment:
    start: datetime
    end: datetime
    active: bool
    session_id: int
    row: StudyRow


def notes_json(notes: list[str]) -> str:
    return json.dumps(notes, ensure_ascii=False)


def notes_from_json(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []



def build_actual_scope(unit: str, planned_scope: str, locations: list[str]) -> str:
    """Treat the planned-range start through the latest timestamp as completed."""
    values: list[int] = []
    for raw in locations:
        text = str(raw).strip()
        if text.isdigit():
            values.append(int(text))
    if not values:
        return ""

    planned_match = re.search(r"\d+", str(planned_scope or ""))
    planned_start = int(planned_match.group(0)) if planned_match else None
    latest = max(values)
    if planned_start is not None and latest >= planned_start:
        body = str(planned_start) if latest == planned_start else f"{planned_start}-{latest}"
    else:
        first = values[0]
        body = str(first) if latest == first else f"{first}-{latest}"

    unit = str(unit or "").strip()
    return f"{unit}({body})" if unit else body
