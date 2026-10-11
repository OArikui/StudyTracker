from __future__ import annotations

import re
from datetime import datetime

from .models import StudyRow

TIME_TOKEN = r"(?:\d{2}:\d{2}:\d{2}(?:\.\d+)?|--:--:--)"
HEADER_RE = re.compile(
    rf"(?P<date>\d{{4}}\.\d{{2}}\.\d{{2}})\s+"
    rf"(?P<start>{TIME_TOKEN})\s*~\s*"
    rf"(?P<end>{TIME_TOKEN})"
)
NOTE_RE = re.compile(r"/\*(.*?)\*/", re.S)
SUBJECT_RE = re.compile(r"^\[(.+?)\]$")
POSITION_RE = re.compile(r"<([^>]+)>")
UNIT_RE = re.compile(r"([A-Za-z_][\w-]*)\s*\(([^()]*)\)")

# Whitespace immediately around syntactic separators is not meaningful.
# Do not globally collapse spaces inside user values because those spaces may
# be part of a material/position name.
COMMA_WS_RE = re.compile(r"\s*,\s*")
PAREN_OPEN_WS_RE = re.compile(r"\s*\(\s*")
PAREN_CLOSE_WS_RE = re.compile(r"\s*\)")


def is_time_placeholder(value: str) -> bool:
    return value.strip() == "--:--:--"


def _normalize_line(line: str) -> str:
    """Normalize formatting noise while preserving meaningful inner spaces."""
    # strip() is the primary normalization requested for HR-below content.
    line = line.strip()
    if not line:
        return ""

    # Tabs and full-width spaces directly surrounding syntax are formatting.
    line = line.replace("\t", " ").replace("\u3000", " ")
    line = COMMA_WS_RE.sub(",", line)
    line = PAREN_OPEN_WS_RE.sub("(", line)
    line = PAREN_CLOSE_WS_RE.sub(")", line)
    return line.strip()


def _normalize_body(body: str) -> list[str]:
    """Apply strip-based normalization to every line below the header."""
    # Normalize line endings first.
    body = body.replace("\r\n", "\n").replace("\r", "\n")

    normalized: list[str] = []
    for raw_line in body.split("\n"):
        line = _normalize_line(raw_line)
        if not line:
            continue
        if line == "-----":
            continue
        normalized.append(line)
    return normalized


def _normalize_note_block(block: str) -> str:
    """Normalize note content with the same strip-based policy."""
    lines: list[str] = []
    for raw_line in block.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.replace("\t", " ").replace("\u3000", " ").strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _extract_notes(text: str) -> tuple[list[str], str]:
    notes: list[str] = []

    def replacer(match: re.Match) -> str:
        note = _normalize_note_block(match.group(1))
        if note:
            notes.append(note)
        return "\n"

    content = NOTE_RE.sub(replacer, text)
    return notes, content


def _parse_header(text: str):
    # Leading blank/indentation before HR is formatting noise as well.
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip()
    match = HEADER_RE.match(normalized)
    if not match:
        raise ValueError(
            "ヘッダーが不正です。例: "
            "2026.10.04 10:00:00.00 ~ --:--:--"
        )
    return (
        match.group("date").strip(),
        match.group("start").strip(),
        match.group("end").strip(),
        match.end(),
        normalized,
    )


def _validate_datetime(date: str, start: str, end: str):
    for value in (start, end):
        if is_time_placeholder(value):
            continue
        try:
            datetime.strptime(f"{date} {value}", "%Y.%m.%d %H:%M:%S.%f")
        except ValueError:
            datetime.strptime(f"{date} {value}", "%Y.%m.%d %H:%M:%S")


def _new_row(
    date,
    start,
    end,
    *,
    subject="",
    material="",
    position="",
    unit="",
    scope="",
    notes=None,
    branch_fields=None,
):
    return StudyRow(
        date=date,
        start=start,
        end=end,
        timezone="Asia/Tokyo",
        category="",
        subject=subject,
        material=material,
        position=position,
        unit=unit,
        scope=scope,
        notes=list(notes or []),
        branch_fields=set(branch_fields or set()),
    )


def parse(text: str) -> list[StudyRow]:
    """Parse the study text after strip-based normalization below HR.

    The header is parsed first. Everything below it is then normalized line by
    line with strip(), blank lines are discarded, and whitespace around commas
    and parentheses is normalized before the semantic parser runs.
    """
    if text is None:
        raise ValueError("テキストが空です。")

    raw = str(text)
    if not raw.strip():
        raise ValueError("テキストが空です。")

    date, start, end, header_end, normalized_text = _parse_header(raw)
    _validate_datetime(date, start, end)

    # Notes are extracted before blank-line elimination so their content is
    # normalized independently and does not interfere with study lines.
    remaining = normalized_text[header_end:]
    notes, study_body = _extract_notes(remaining)
    lines = _normalize_body(study_body)

    subject = ""
    material = ""
    position = ""
    rows: list[StudyRow] = []

    for line in lines:
        subject_match = SUBJECT_RE.match(line)
        if subject_match:
            subject = subject_match.group(1).strip()
            material = ""
            position = ""
            continue

        position_match = POSITION_RE.search(line)
        if position_match:
            position = position_match.group(1).strip()
            before = line[:position_match.start()].strip()
            after = line[position_match.end():].strip()
        else:
            before = line.strip()
            after = ""

        # A line such as "教材<位置>" changes material/position context.
        # A line such as "<位置>,section(2-4)" inherits the previous material.
        if before:
            material = before

        matches = list(UNIT_RE.finditer(after))
        if matches:
            for index, match in enumerate(matches):
                # Additional units on the same logical branch become branch rows.
                branch_fields = set(range(7)) if index > 0 or not before else set()
                rows.append(
                    _new_row(
                        date,
                        start,
                        end,
                        subject=subject,
                        material=material,
                        position=position,
                        unit=match.group(1).strip(),
                        scope=match.group(2).strip(),
                        notes=notes,
                        branch_fields=branch_fields,
                    )
                )
            continue

        # Partial form: unit without a parenthesized scope, e.g. ",p".
        if after:
            parts = [part.strip() for part in after.split(",") if part.strip()]
            rows.append(
                _new_row(
                    date,
                    start,
                    end,
                    subject=subject,
                    material=material,
                    position=position,
                    unit=parts[0] if parts else "",
                    scope=",".join(parts[1:]) if len(parts) > 1 else "",
                    notes=notes,
                )
            )
            continue

        # Partial material/position-only line.
        if material or position:
            rows.append(
                _new_row(
                    date,
                    start,
                    end,
                    subject=subject,
                    material=material,
                    position=position,
                    notes=notes,
                )
            )

    if not rows:
        # A subject-only or header-only document is still synchronizable.
        rows.append(
            _new_row(
                date,
                start,
                end,
                subject=subject,
                notes=notes,
            )
        )

    return rows


def render(rows: list[StudyRow]) -> str:
    if not rows:
        return ""

    first = rows[0]
    start = first.start or "--:--:--"
    end = first.end or "--:--:--"

    lines = [
        f"{first.date} {start} ~ {end}",
        "-----",
    ]

    last_subject = None
    last_material = None

    for row in rows:
        is_branch_subject = 5 in row.branch_fields
        is_branch_material = 6 in row.branch_fields

        if row.subject and row.subject != last_subject and not is_branch_subject:
            lines.append(f"[{row.subject}]")
            last_subject = row.subject
            last_material = None

        prefix = ""
        if (
            row.material
            and not is_branch_material
            and row.material != last_material
        ):
            prefix = row.material
            last_material = row.material

        position = f"<{row.position}>" if row.position else ""

        if row.unit:
            unit = f"{row.unit}({row.scope})" if row.scope else row.unit
            line = f"{prefix}{position},{unit}".rstrip(",")
        else:
            line = f"{prefix}{position}"

        if line.strip():
            lines.append(line)

    unique_notes: list[str] = []
    seen = set()
    for row in rows:
        for note in row.notes:
            if note not in seen:
                unique_notes.append(note)
                seen.add(note)

    if unique_notes:
        lines.extend(["", "/*", *unique_notes, "*/"])

    return "\n".join(lines)
