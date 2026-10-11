import json
import sqlite3
from datetime import datetime, timezone, timedelta

from viewer_v0.analysis import filter_segments, scope_quantity, study_rate_series, summarize, timestamp_rate_points
from viewer_v0.reader import StudyTrackerReader, StudyTrackerFormatError

JST = timezone(timedelta(hours=9))


def make_db(path):
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE timestamps (
        id INTEGER PRIMARY KEY,
        session_id INTEGER NOT NULL,
        segment_start_at TEXT NOT NULL,
        at TEXT NOT NULL,
        location TEXT NOT NULL,
        unit TEXT NOT NULL,
        subject TEXT NOT NULL,
        material TEXT NOT NULL
    );
    CREATE TABLE segments (
        id INTEGER PRIMARY KEY,
        session_id INTEGER NOT NULL,
        start_at TEXT NOT NULL,
        end_at TEXT NOT NULL,
        active INTEGER NOT NULL,
        row_json TEXT NOT NULL
    );
    """)
    payload = {
        "date": "2026.10.05",
        "category": "通常学習",
        "subject": "数学",
        "material": "青チャート",
        "position": "数列",
        "unit": "p.10",
        "scope": "10-12",
        "actual_scope": "p(10-11)",
        "notes": ["メモ"],
        "branch_fields": [],
    }
    con.execute(
        "INSERT INTO timestamps VALUES (1, 2, ?, ?, ?, ?, ?, ?)",
        (
            datetime(2026, 10, 5, 10, 0, tzinfo=JST).isoformat(),
            datetime(2026, 10, 5, 10, 30, tzinfo=JST).isoformat(),
            "11", "p", "数学", "青チャート",
        ),
    )
    con.execute(
        "INSERT INTO segments VALUES (1, 2, ?, ?, 1, ?)",
        (
            datetime(2026, 10, 5, 10, 0, tzinfo=JST).isoformat(),
            datetime(2026, 10, 5, 11, 30, tzinfo=JST).isoformat(),
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    con.commit()
    con.close()


def test_read_and_summary(tmp_path):
    p = tmp_path / "study.sqlite3"
    make_db(p)
    with StudyTrackerReader(p) as reader:
        rows = reader.read_segments()
        timestamps = reader.read_timestamps()
    assert len(rows) == 1
    assert len(timestamps) == 1
    assert timestamps[0].location == "11"
    assert rows[0].subject == "数学"
    assert rows[0].actual_scope == "p(10-11)"
    assert summarize(rows).total_seconds == 5400


def test_filter_subject(tmp_path):
    p = tmp_path / "study.sqlite3"
    make_db(p)
    with StudyTrackerReader(p) as reader:
        rows = reader.read_segments()
    assert len(filter_segments(rows, subject="数学")) == 1
    assert len(filter_segments(rows, subject="英語")) == 0


def test_missing_segments(tmp_path):
    p = tmp_path / "bad.sqlite3"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE other (id INTEGER)")
    con.commit(); con.close()
    try:
        StudyTrackerReader(p)
    except StudyTrackerFormatError:
        return
    raise AssertionError("format error expected")


def test_timestamp_rate_points(tmp_path):
    p = tmp_path / "study.sqlite3"
    make_db(p)
    with StudyTrackerReader(p) as reader:
        rows = reader.read_segments()
        timestamps = reader.read_timestamps()
    extra = type(timestamps[0])(
        timestamp_id=2, session_id=2, segment_start_at=timestamps[0].segment_start_at,
        at=datetime(2026, 10, 5, 11, 0, tzinfo=JST), location="21", unit="p", subject="数学", material="青チャート"
    )
    points = timestamp_rate_points(rows, timestamps + [extra])
    assert len(points) == 2
    assert round(points[-1][1], 1) == 20.0


def test_scope_quantity():
    assert scope_quantity("p(21-42,45)") == 23
    assert scope_quantity("p.21-30") == 10
    assert scope_quantity("section(2-4)") == 3
    assert scope_quantity("") is None


def test_rate_fallback_uses_actual_scope_without_timestamps(tmp_path):
    p = tmp_path / "study.sqlite3"
    make_db(p)
    with StudyTrackerReader(p) as reader:
        rows = reader.read_segments()
    actual, planned = study_rate_series(rows, [])
    assert len(actual) == 1
    assert len(planned) == 1
    assert round(actual[0][1], 6) == round(2 / 1.5, 6)
    assert round(planned[0][1], 6) == round(3 / 1.5, 6)


def test_rate_uses_timestamps_when_present(tmp_path):
    p = tmp_path / "study.sqlite3"
    make_db(p)
    with StudyTrackerReader(p) as reader:
        rows = reader.read_segments()
        timestamps = reader.read_timestamps()
    actual, planned = study_rate_series(rows, timestamps)
    assert actual == timestamp_rate_points(rows, timestamps)
    assert len(planned) == 1
