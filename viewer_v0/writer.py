from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


class StudyTrackerWriter:
    """Write editor changes to the shared DB and keep an append-only audit trail."""

    HISTORY_TABLE = "viewer_edit_history"

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        self.con = sqlite3.connect(self.path, timeout=5.0)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA busy_timeout=5000")
        self.con.execute(
            f"""CREATE TABLE IF NOT EXISTS {self.HISTORY_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                changed_at TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                before_json TEXT NOT NULL,
                after_json TEXT NOT NULL
            )"""
        )
        self.con.execute(
            f"""CREATE TRIGGER IF NOT EXISTS {self.HISTORY_TABLE}_no_update
                BEFORE UPDATE ON {self.HISTORY_TABLE}
                BEGIN SELECT RAISE(ABORT, 'edit history is append-only'); END"""
        )
        self.con.execute(
            f"""CREATE TRIGGER IF NOT EXISTS {self.HISTORY_TABLE}_no_delete
                BEFORE DELETE ON {self.HISTORY_TABLE}
                BEGIN SELECT RAISE(ABORT, 'edit history is append-only'); END"""
        )
        self.con.commit()

    def close(self) -> None:
        self.con.close()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    def _audit(self, action: str, entity_type: str, entity_id: str | int, before: Any, after: Any) -> None:
        self.con.execute(
            f"""INSERT INTO {self.HISTORY_TABLE}
                (changed_at, action, entity_type, entity_id, before_json, after_json)
                VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().astimezone().isoformat(timespec="seconds"),
                action,
                entity_type,
                str(entity_id),
                self._json(before),
                self._json(after),
            ),
        )

    def set_actual_scope(self, segment_id: int, actual_scope: str) -> None:
        self.update_segment(segment_id, {"actual_scope": str(actual_scope or "").strip()})

    def update_segment(self, segment_id: int, fields: dict[str, Any]) -> None:
        """Update supported segment fields; each update is audited in the same transaction."""
        allowed_json = {
            "category", "subject", "material", "position", "unit", "scope", "actual_scope", "notes"
        }
        allowed_columns = {"start_at", "end_at", "active"}
        unknown = set(fields) - allowed_json - allowed_columns
        if unknown:
            raise ValueError(f"Unsupported segment fields: {', '.join(sorted(unknown))}")

        with self.con:
            row = self.con.execute(
                "SELECT id, session_id, start_at, end_at, active, row_json FROM segments WHERE id=?",
                (int(segment_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"segment not found: {segment_id}")
            before_payload = json.loads(row["row_json"])
            linked_timestamps = []
            new_start = fields.get("start_at")
            has_timestamps_table = self.con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='timestamps'"
            ).fetchone() is not None
            if new_start is not None and str(new_start) != str(row["start_at"]) and has_timestamps_table:
                linked_timestamps = self.con.execute(
                    "SELECT id, session_id, segment_start_at, at, location, unit, subject, material "
                    "FROM timestamps WHERE session_id=? AND segment_start_at=?",
                    (row["session_id"], row["start_at"]),
                ).fetchall()
            before = {
                "id": row["id"], "session_id": row["session_id"],
                "start_at": row["start_at"], "end_at": row["end_at"],
                "active": row["active"], "row_json": before_payload,
            }
            payload = dict(before_payload)
            columns: dict[str, Any] = {}
            for key, value in fields.items():
                if key in allowed_json:
                    payload[key] = value
                else:
                    columns[key] = value
            if "start_at" in columns:
                try:
                    payload["date"] = datetime.fromisoformat(str(columns["start_at"])).strftime("%Y.%m.%d")
                except ValueError:
                    pass
            if "start_at" in columns and "end_at" in columns:
                if str(columns["end_at"]) <= str(columns["start_at"]):
                    raise ValueError("終了日時は開始日時より後にしてください。")
            elif "start_at" in columns or "end_at" in columns:
                start = columns.get("start_at", row["start_at"])
                end = columns.get("end_at", row["end_at"])
                if str(end) <= str(start):
                    raise ValueError("終了日時は開始日時より後にしてください。")
            set_parts = ["row_json=?"]
            params: list[Any] = [json.dumps(payload, ensure_ascii=False)]
            for key, value in columns.items():
                set_parts.append(f"{key}=?")
                params.append(value)
            params.append(int(segment_id))
            self.con.execute(f"UPDATE segments SET {', '.join(set_parts)} WHERE id=?", params)
            if linked_timestamps and new_start is not None:
                for timestamp_row in linked_timestamps:
                    timestamp_before = dict(timestamp_row)
                    self.con.execute(
                        "UPDATE timestamps SET segment_start_at=? WHERE id=?",
                        (new_start, timestamp_row["id"]),
                    )
                    timestamp_after = dict(timestamp_before)
                    timestamp_after["segment_start_at"] = new_start
                    self._audit("relink", "timestamp", timestamp_row["id"], timestamp_before, timestamp_after)
            after = dict(before)
            after.update(columns)
            after["row_json"] = payload
            self._audit("update", "segment", segment_id, before, after)

    def update_timestamp(self, timestamp_id: int, fields: dict[str, Any]) -> None:
        allowed = {"at", "location", "unit", "subject", "material"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unsupported timestamp fields: {', '.join(sorted(unknown))}")
        if not fields:
            return
        with self.con:
            row = self.con.execute(
                "SELECT id, session_id, segment_start_at, at, location, unit, subject, material "
                "FROM timestamps WHERE id=?",
                (int(timestamp_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"timestamp not found: {timestamp_id}")
            before = dict(row)
            assignments = ", ".join(f"{key}=?" for key in fields)
            params = list(fields.values()) + [int(timestamp_id)]
            self.con.execute(f"UPDATE timestamps SET {assignments} WHERE id=?", params)
            after = dict(before)
            after.update(fields)
            self._audit("update", "timestamp", timestamp_id, before, after)

    def read_history(self, limit: int = 1000) -> list[dict[str, Any]]:
        rows = self.con.execute(
            f"SELECT id, changed_at, action, entity_type, entity_id, before_json, after_json "
            f"FROM {self.HISTORY_TABLE} ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 10000)),),
        ).fetchall()
        return [dict(row) for row in rows]
