from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass
class SyncValidation:
    ok: bool
    errors: list[str]
    missing_presets: list[tuple[str, str, str]]
    similar: list[tuple[str, str, str]]


def _missing_preset_info(db, rows):
    missing = []

    for row in rows:
        if row.category and row.category not in db.preset_titles("category"):
            missing.append(("category", "", row.category))

        if row.subject and row.subject not in db.preset_titles("subject"):
            missing.append(("subject", "", row.subject))

        if row.material and row.subject:
            if row.material not in db.preset_titles("material", row.subject):
                missing.append(("material", row.subject, row.material))

        if row.unit and not any(alias["title"] == row.unit for alias in db.aliases()):
            missing.append(("unit", "", row.unit))

    dedup = []
    seen = set()
    for item in missing:
        if item not in seen:
            seen.add(item)
            dedup.append(item)
    return dedup


def _similar(db, missing):
    similar = []

    for kind, parent, value in missing:
        candidates = (
            db.preset_titles(kind, parent)
            if kind != "unit"
            else [alias["title"] for alias in db.aliases()]
        )
        scored = sorted(
            (
                (SequenceMatcher(None, value.lower(), candidate.lower()).ratio(), candidate)
                for candidate in candidates
            ),
            reverse=True,
        )
        if scored and scored[0][0] >= 0.45:
            similar.append((kind, value, scored[0][1]))

    return similar


def validate(db, rows) -> SyncValidation:
    """Permissive validation for synchronization."""
    errors = []

    if not rows:
        errors.append("学習内容が空です。")

    for index, row in enumerate(rows, 1):
        if not row.date.strip():
            errors.append(f"{index}行目: 年月日が解釈できません。")
        if not row.timezone.strip():
            errors.append(f"{index}行目: タイムゾーンがありません。")

    missing = _missing_preset_info(db, rows)

    return SyncValidation(
        ok=not errors and not missing,
        errors=errors,
        missing_presets=missing,
        similar=_similar(db, missing),
    )


def validate_for_apply(db, rows) -> SyncValidation:
    """Strict validation used only when applying current study content."""
    base = validate(db, rows)
    errors = list(base.errors)

    required = (
        ("category", "学習区分"),
        ("subject", "科目"),
        ("material", "教材"),
        ("position", "学習位置"),
        ("unit", "学習単位"),
        ("scope", "学習範囲"),
    )

    for index, row in enumerate(rows, 1):
        for attr, label in required:
            if not getattr(row, attr).strip():
                errors.append(f"{index}行目: {label}は適用時に必須です。")

    return SyncValidation(
        ok=not errors and not base.missing_presets,
        errors=errors,
        missing_presets=base.missing_presets,
        similar=base.similar,
    )
