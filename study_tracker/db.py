from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self):
        self.con.executescript("""
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS presets (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,
            parent TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            docstring TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            UNIQUE(kind, parent, title)
        );

        CREATE TABLE IF NOT EXISTS aliases (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL UNIQUE,
            docstring TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS recent_positions (
            id INTEGER PRIMARY KEY,
            material TEXT NOT NULL,
            position TEXT NOT NULL,
            last_used TEXT NOT NULL,
            UNIQUE(material, position)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY,
            session_id INTEGER NOT NULL,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            active INTEGER NOT NULL,
            row_json TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            session_id INTEGER NOT NULL,
            at TEXT NOT NULL,
            event TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS timestamps (
            id INTEGER PRIMARY KEY,
            session_id INTEGER NOT NULL,
            segment_start_at TEXT NOT NULL,
            at TEXT NOT NULL,
            location TEXT NOT NULL,
            unit TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            material TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_timestamps_session_segment
            ON timestamps(session_id, segment_start_at, at, id);

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)
        self.con.commit()

    def close(self):
        self.con.close()

    # ---- settings ----
    def get_setting(self, key, default=None):
        r = self.con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_setting(self, key, value):
        self.con.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value))
        )
        self.con.commit()

    # ---- presets ----
    def presets(self, kind, parent=""):
        return self.con.execute(
            "SELECT * FROM presets WHERE kind=? AND parent=? ORDER BY sort_order,id",
            (kind, parent)
        ).fetchall()

    def preset_titles(self, kind, parent=""):
        return [r["title"] for r in self.presets(kind, parent)]

    def add_preset(self, kind, title, docstring="", parent=""):
        row = self.con.execute(
            "SELECT COALESCE(MAX(sort_order), -1)+1 FROM presets WHERE kind=? AND parent=?",
            (kind, parent)
        ).fetchone()
        self.con.execute(
            "INSERT INTO presets(kind,parent,title,docstring,sort_order) VALUES(?,?,?,?,?)",
            (kind, parent, title, docstring, row[0])
        )
        self.con.commit()

    def edit_preset(self, pid, title, docstring):
        old = self.con.execute("SELECT kind,title FROM presets WHERE id=?", (pid,)).fetchone()
        if not old:
            return
        self.con.execute(
            "UPDATE presets SET title=?, docstring=? WHERE id=?",
            (title, docstring, pid)
        )
        if old["kind"] == "subject" and old["title"] != title:
            self.con.execute(
                "UPDATE presets SET parent=? WHERE kind='material' AND parent=?",
                (title, old["title"])
            )
        self.con.commit()

    def delete_preset(self, pid):
        self.con.execute("DELETE FROM presets WHERE id=?", (pid,))
        self.con.commit()

    def move_preset(self, pid, delta):
        rows = self.con.execute("SELECT * FROM presets ORDER BY kind,parent,sort_order,id").fetchall()
        idx = next((i for i, r in enumerate(rows) if r["id"] == pid), None)
        if idx is None:
            return
        target = idx + delta
        if target < 0 or target >= len(rows):
            return
        a, b = rows[idx], rows[target]
        if (a["kind"], a["parent"]) != (b["kind"], b["parent"]):
            return
        self.con.execute("UPDATE presets SET sort_order=? WHERE id=?", (b["sort_order"], a["id"]))
        self.con.execute("UPDATE presets SET sort_order=? WHERE id=?", (a["sort_order"], b["id"]))
        self.con.commit()

    # ---- aliases ----
    def aliases(self):
        return self.con.execute("SELECT * FROM aliases ORDER BY id").fetchall()

    def add_alias(self, title, docstring):
        self.con.execute("INSERT INTO aliases(title,docstring) VALUES(?,?)", (title, docstring))
        self.con.commit()

    def edit_alias(self, aid, title, docstring):
        self.con.execute("UPDATE aliases SET title=?,docstring=? WHERE id=?", (title, docstring, aid))
        self.con.commit()

    def delete_alias(self, aid):
        self.con.execute("DELETE FROM aliases WHERE id=?", (aid,))
        self.con.commit()

    # ---- recents ----
    def touch_position(self, material, position, at):
        if not material or not position:
            return
        self.con.execute(
            "INSERT INTO recent_positions(material,position,last_used) VALUES(?,?,?) "
            "ON CONFLICT(material,position) DO UPDATE SET last_used=excluded.last_used",
            (material, position, at.isoformat())
        )
        self.con.commit()

    def recent_positions(self, material, limit=10):
        return self.con.execute(
            "SELECT position,last_used FROM recent_positions "
            "WHERE material=? ORDER BY last_used DESC LIMIT ?",
            (material, limit)
        ).fetchall()

    # ---- sessions / segments ----
    def start_session(self, at):
        cur = self.con.execute(
            "INSERT INTO sessions(started_at,active) VALUES(?,1)", (at.isoformat(),)
        )
        self.con.commit()
        return cur.lastrowid

    def close_session(self, sid, at):
        self.con.execute(
            "UPDATE sessions SET ended_at=?,active=0 WHERE id=?",
            (at.isoformat(), sid)
        )
        self.con.commit()

    def add_event(self, sid, at, event, payload=None):
        self.con.execute(
            "INSERT INTO events(session_id,at,event,payload_json) VALUES(?,?,?,?)",
            (sid, at.isoformat(), event, json.dumps(payload or {}, ensure_ascii=False))
        )
        self.con.commit()

    def add_segment(self, sid, start, end, active, row):
        row = dict(row)
        row.setdefault("actual_scope", "")
        self.con.execute(
            "INSERT INTO segments(session_id,start_at,end_at,active,row_json) VALUES(?,?,?,?,?)",
            (
                sid, start.isoformat(), end.isoformat(), int(active),
                json.dumps(row, ensure_ascii=False)
            )
        )
        self.con.commit()

    def update_segment_actual_scope(self, segment_id, actual_scope):
        row = self.con.execute(
            "SELECT row_json FROM segments WHERE id=?", (int(segment_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"segment not found: {segment_id}")
        payload = json.loads(row[0])
        payload["actual_scope"] = str(actual_scope or "").strip()
        self.con.execute(
            "UPDATE segments SET row_json=? WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), int(segment_id)),
        )
        self.con.commit()

    def add_timestamp(self, sid, segment_start_at, at, location, unit="", subject="", material=""):
        location = str(location).strip()
        if not location:
            raise ValueError("location is required")
        cur = self.con.execute(
            "INSERT INTO timestamps(session_id,segment_start_at,at,location,unit,subject,material) VALUES(?,?,?,?,?,?,?)",
            (
                sid,
                segment_start_at.isoformat(),
                at.isoformat(),
                location,
                str(unit or "").strip(),
                str(subject or "").strip(),
                str(material or "").strip(),
            ),
        )
        self.con.commit()
        return cur.lastrowid

    def timestamps_for_segment(self, sid, start, end=None):
        params = [sid, start.isoformat()]
        query = "SELECT * FROM timestamps WHERE session_id=? AND segment_start_at=?"
        if end is not None:
            query += " AND at <= ?"
            params.append(end.isoformat())
        query += " ORDER BY at, id"
        return self.con.execute(query, params).fetchall()

    def timestamps_for_session(self, sid, start, end=None):
        """Return timestamps within a content interval, including state toggles."""
        params = [sid, start.isoformat()]
        query = "SELECT * FROM timestamps WHERE session_id=? AND at >= ?"
        if end is not None:
            query += " AND at <= ?"
            params.append(end.isoformat())
        query += " ORDER BY at, id"
        return self.con.execute(query, params).fetchall()

    def segments(self, active_only=False):
        q = "SELECT * FROM segments"
        if active_only:
            q += " WHERE active=1"
        q += " ORDER BY start_at"
        return self.con.execute(q).fetchall()

    def segments_overlapping(self, start, end):
        """Return recorded segments overlapping the half-open time interval."""
        return self.con.execute(
            "SELECT * FROM segments WHERE start_at < ? AND end_at > ? ORDER BY start_at",
            (end.isoformat(), start.isoformat()),
        ).fetchall()

    def recover_open_session(self):
        r = self.con.execute(
            "SELECT * FROM sessions WHERE active=1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return r

    def archive_rows(self, active_only=True):
        from .models import StudyRow
        rows = []
        for r in self.segments(active_only=active_only):
            d = json.loads(r["row_json"])
            rows.append(StudyRow(
                date=d["date"], start=d["start"], end=d["end"],
                timezone=d["timezone"], category=d["category"],
                subject=d["subject"], material=d["material"],
                position=d["position"], unit=d["unit"], scope=d["scope"],
                actual_scope=d.get("actual_scope", ""),
                notes=d.get("notes", []),
                branch_fields=set(d.get("branch_fields", [])),
                start_auto_at=d.get("start_auto_at"),
                end_auto_at=d.get("end_auto_at"),
            ))
        return rows

    # ---- statistics ----
    @staticmethod
    def _parse_dt(value):
        return datetime.fromisoformat(value)

    def active_seconds(self, subject="", material="", start=None, end=None):
        total = 0.0
        for r in self.segments(active_only=True):
            d = json.loads(r["row_json"])
            if subject and d["subject"] != subject:
                continue
            if material and d["material"] != material:
                continue
            a = self._parse_dt(r["start_at"])
            b = self._parse_dt(r["end_at"])
            if start and b <= start:
                continue
            if end and a >= end:
                continue
            aa = max(a, start) if start else a
            bb = min(b, end) if end else b
            if bb > aa:
                total += (bb - aa).total_seconds()
        return total

    def all_segment_rows(self):
        return self.con.execute(
            "SELECT id, session_id, start_at, end_at, active, row_json "
            "FROM segments ORDER BY start_at"
        ).fetchall()
