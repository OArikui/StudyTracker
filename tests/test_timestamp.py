import json
from datetime import datetime, timedelta, timezone

from study_tracker.db import Database
from study_tracker.models import build_actual_scope

JST = timezone(timedelta(hours=9))


def test_timestamp_round_trip_and_actual_scope(tmp_path):
    db = Database(tmp_path / "study.sqlite3")
    t0 = datetime(2026, 10, 5, 10, 0, tzinfo=JST)
    sid = db.start_session(t0)
    db.add_timestamp(sid, t0, t0 + timedelta(minutes=5), "21", "p", "数学", "青チャート")
    db.add_timestamp(sid, t0, t0 + timedelta(minutes=10), "30", "p", "数学", "青チャート")
    rows = db.timestamps_for_segment(sid, t0, t0 + timedelta(minutes=20))
    assert [r["location"] for r in rows] == ["21", "30"]
    assert build_actual_scope("p", "21-42", [r["location"] for r in rows]) == "p(21-30)"
    db.close()


def test_update_segment_actual_scope(tmp_path):
    db = Database(tmp_path / "study.sqlite3")
    t0 = datetime(2026, 10, 5, 10, 0, tzinfo=JST)
    sid = db.start_session(t0)
    db.add_segment(
        sid, t0, t0 + timedelta(minutes=1), True,
        {
            "date": "2026.10.05", "start": "10:00:00.00", "end": "10:01:00.00",
            "timezone": "Asia/Tokyo", "category": "通常", "subject": "数学",
            "material": "青チャート", "position": "数列", "unit": "p",
            "scope": "21-30", "notes": [], "branch_fields": [],
        },
    )
    db.update_segment_actual_scope(1, "p(21-25)")
    payload = json.loads(db.segments()[0]["row_json"])
    assert payload["actual_scope"] == "p(21-25)"
    db.close()


def test_timestamps_can_be_retrieved_across_state_segments(tmp_path):
    db = Database(tmp_path / "study.sqlite3")
    t0 = datetime(2026, 10, 5, 10, 0, tzinfo=JST)
    sid = db.start_session(t0)
    db.add_timestamp(sid, t0, t0 + timedelta(minutes=5), "21", "p", "数学", "青チャート")
    segment2 = t0 + timedelta(minutes=10)
    db.add_event(sid, segment2, "passive")
    db.add_timestamp(sid, segment2, segment2 + timedelta(minutes=1), "30", "p", "数学", "青チャート")
    rows = db.timestamps_for_session(sid, t0, t0 + timedelta(minutes=20))
    assert [row["location"] for row in rows] == ["21", "30"]
    db.close()
