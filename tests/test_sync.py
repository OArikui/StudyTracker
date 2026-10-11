from study_tracker.db import Database
from study_tracker.models import StudyRow
from study_tracker.sync import validate, validate_for_apply


def test_sync_is_permissive_but_apply_is_strict(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.add_preset("category", "通常")
    db.add_preset("subject", "物理")
    db.add_preset("material", "リードα", parent="物理")
    db.add_alias("p", "ページ")

    row = StudyRow(
        category="通常",
        subject="物理",
        material="リードα",
        position="波動",
        date="2026.10.04",
        start="15:00:00.00",
        end="--:--:--",
    )
    assert validate(db, [row]).errors == []
    assert validate_for_apply(db, [row]).ok is False
    db.close()
