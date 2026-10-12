import asyncio
import sys
from datetime import timedelta
from types import ModuleType, SimpleNamespace

from study_tracker.media import HOTKEYS, VK_MEDIA_NEXT_TRACK, VK_MEDIA_PLAY_PAUSE, VK_VOLUME_UP


def test_global_shortcuts_are_unique_and_documented():
    assert set(HOTKEYS) == {1, 2, 3}
    assert len({(item[0], item[1]) for item in HOTKEYS.values()}) == len(HOTKEYS)
    assert all(item[2] and item[3] for item in HOTKEYS.values())


def test_windows_virtual_key_constants():
    assert VK_MEDIA_PLAY_PAUSE == 0xB3
    assert VK_MEDIA_NEXT_TRACK == 0xB0
    assert VK_VOLUME_UP == 0xAF


def test_timespan_seconds_accepts_timedelta_and_winrt_ticks():
    from study_tracker.media import _timespan_seconds

    assert _timespan_seconds(timedelta(seconds=42)) == 42
    assert _timespan_seconds(420_000_000) == 42
    assert _timespan_seconds(None) == 0


def test_media_seek_helper_is_importable():
    from study_tracker.media import seek_session_position

    assert callable(seek_session_position)


def test_timeline_failure_does_not_drop_media_metadata(monkeypatch):
    """A session must remain visible when its player does not expose a timeline."""

    class FakeSession:
        source_app_user_model_id = "example.player"

        async def try_get_media_properties_async(self):
            return SimpleNamespace(
                title="Example title",
                artist="Example artist",
                album_title="Example album",
            )

        def get_playback_info(self):
            return SimpleNamespace(playback_status="PLAYING")

        def get_timeline_properties(self):
            raise RuntimeError("timeline is unavailable")

    session = FakeSession()

    class FakeManager:
        @staticmethod
        async def request_async():
            return SimpleNamespace(get_sessions=lambda: [session])

    module_names = (
        "winrt",
        "winrt.windows",
        "winrt.windows.media",
        "winrt.windows.media.control",
    )
    modules = {}
    for name in module_names:
        module = ModuleType(name)
        module.__path__ = []
        modules[name] = module
        monkeypatch.setitem(sys.modules, name, module)
    modules["winrt.windows.media.control"].GlobalSystemMediaTransportControlsSessionManager = FakeManager

    from study_tracker.media import MediaSessionReader

    reader = MediaSessionReader()
    sessions = asyncio.run(reader._read_sessions())

    assert len(sessions) == 1
    assert sessions[0]["app_id"] == "example.player"
    assert sessions[0]["title"] == "Example title"
    assert sessions[0]["artist"] == "Example artist"
    assert sessions[0]["album"] == "Example album"
    assert sessions[0]["status"] == "PLAYING"
    assert sessions[0]["duration"] == 0
    assert any("timeline is unavailable" in error for error in reader._session_errors)
