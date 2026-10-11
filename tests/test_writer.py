import json
import sqlite3

from viewer_v0.writer import StudyTrackerWriter


def test_writer_updates_shared_actual_scope(tmp_path):
    db = tmp_path / "study.sqlite3"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE segments (id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, start_at TEXT NOT NULL, end_at TEXT NOT NULL, active INTEGER NOT NULL, row_json TEXT NOT NULL)")
    con.execute(
        "INSERT INTO segments VALUES (1, 10, '2026-10-10T10:00:00+09:00', '2026-10-10T11:00:00+09:00', 1, ?)",
        (json.dumps({"subject": "数学", "scope": "21-42"}, ensure_ascii=False),),
    )
    con.commit()
    con.close()

    writer = StudyTrackerWriter(db)
    writer.set_actual_scope(1, "p(21-30)")
    history = writer.read_history()
    writer.close()

    con = sqlite3.connect(db)
    payload = json.loads(con.execute("SELECT row_json FROM segments WHERE id=1").fetchone()[0])
    con.close()
    assert payload["actual_scope"] == "p(21-30)"
    assert len(history) == 1
    assert history[0]["entity_type"] == "segment"
    assert json.loads(history[0]["before_json"])["row_json"]["scope"] == "21-42"


def test_writer_audits_record_and_timestamp_edits(tmp_path):
    db = tmp_path / "study.sqlite3"
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE segments (id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, start_at TEXT NOT NULL, end_at TEXT NOT NULL, active INTEGER NOT NULL, row_json TEXT NOT NULL);
    CREATE TABLE timestamps (id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, segment_start_at TEXT NOT NULL, at TEXT NOT NULL, location TEXT NOT NULL, unit TEXT NOT NULL, subject TEXT NOT NULL, material TEXT NOT NULL);
    INSERT INTO segments VALUES (1, 10, '2026-10-10T10:00:00+09:00', '2026-10-10T11:00:00+09:00', 1, '{"subject":"数学"}');
    INSERT INTO timestamps VALUES (2, 10, '2026-10-10T10:00:00+09:00', '2026-10-10T10:20:00+09:00', '10', 'p', '数学', '教材');
    """)
    con.commit()
    con.close()
    writer = StudyTrackerWriter(db)
    writer.update_segment(1, {"subject": "英語", "active": 0})
    writer.update_timestamp(2, {"location": "12"})
    history = writer.read_history()
    writer.close()
    assert len(history) == 2
    assert {entry["entity_type"] for entry in history} == {"segment", "timestamp"}


def test_history_is_append_only(tmp_path):
    db = tmp_path / "study.sqlite3"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE segments (id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, start_at TEXT NOT NULL, end_at TEXT NOT NULL, active INTEGER NOT NULL, row_json TEXT NOT NULL)")
    con.execute("INSERT INTO segments VALUES (1, 1, '2026-10-10T10:00:00+09:00', '2026-10-10T11:00:00+09:00', 1, '{}')")
    con.commit()
    con.close()
    writer = StudyTrackerWriter(db)
    writer.set_actual_scope(1, "p.1-3")
    writer.close()
    con = sqlite3.connect(db)
    try:
        con.execute("UPDATE viewer_edit_history SET after_json='{}' WHERE id=1")
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("history update should be blocked by the audit trigger")
    try:
        con.execute("DELETE FROM viewer_edit_history WHERE id=1")
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("history deletion should be blocked by the audit trigger")
    con.close()


def test_segment_start_update_relinks_timestamps_and_date_metadata(tmp_path):
    db = tmp_path / "study.sqlite3"
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE segments (id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, start_at TEXT NOT NULL, end_at TEXT NOT NULL, active INTEGER NOT NULL, row_json TEXT NOT NULL);
    CREATE TABLE timestamps (id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, segment_start_at TEXT NOT NULL, at TEXT NOT NULL, location TEXT NOT NULL, unit TEXT NOT NULL, subject TEXT NOT NULL, material TEXT NOT NULL);
    INSERT INTO segments VALUES (1, 10, '2026-10-10T10:00:00+09:00', '2026-10-10T11:00:00+09:00', 1, '{"date":"2026.10.10","subject":"数学"}');
    INSERT INTO timestamps VALUES (2, 10, '2026-10-10T10:00:00+09:00', '2026-10-10T10:20:00+09:00', '10', 'p', '数学', '教材');
    """)
    con.commit()
    con.close()
    writer = StudyTrackerWriter(db)
    writer.update_segment(1, {
        "start_at": "2026-10-11T10:00:00+09:00",
        "end_at": "2026-10-11T11:00:00+09:00",
    })
    writer.close()
    con = sqlite3.connect(db)
    segment = con.execute("SELECT start_at, row_json FROM segments WHERE id=1").fetchone()
    timestamp = con.execute("SELECT segment_start_at FROM timestamps WHERE id=2").fetchone()[0]
    con.close()
    assert segment[0] == "2026-10-11T10:00:00+09:00"
    assert json.loads(segment[1])["date"] == "2026.10.11"
    assert timestamp == "2026-10-11T10:00:00+09:00"
