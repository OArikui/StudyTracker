from datetime import datetime, timezone, timedelta
from study_tracker.db import Database

def test_preset_and_stats(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.add_preset("subject", "物理")
    db.add_preset("material", "リードα", parent="物理")
    db.add_preset("category", "通常")
    db.add_alias("p", "ページ")
    assert "物理" in db.preset_titles("subject")
    assert "リードα" in db.preset_titles("material", "物理")
    db.close()
