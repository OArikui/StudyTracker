from types import SimpleNamespace

from PySide6.QtCore import QObject
from shiboken6 import delete

from study_tracker.ui import MainWindow, _is_live_qobject


def test_qobject_liveness_guard_detects_deleted_objects():
    obj = QObject()
    assert _is_live_qobject(obj)

    delete(obj)

    assert not _is_live_qobject(obj)
    assert not _is_live_qobject(None)


def test_media_status_callback_ignores_deleted_label():
    label = QObject()
    delete(label)
    target = SimpleNamespace(media_status=label, _media_status_text="old")

    MainWindow._on_media_status(target, "new status")

    assert target._media_status_text == "new status"


def test_media_sessions_callback_ignores_deleted_combo():
    combo = QObject()
    delete(combo)
    target = SimpleNamespace(
        media_priority=combo,
        _media_sessions=[],
        session_id=None,
        snapshot_recorded=False,
    )
    target._record_media_snapshot = lambda: setattr(target, "snapshot_recorded", True)

    MainWindow._on_media_sessions(target, [{"app_id": "example.player"}])

    assert target._media_sessions == [{"app_id": "example.player"}]
    assert target.snapshot_recorded
