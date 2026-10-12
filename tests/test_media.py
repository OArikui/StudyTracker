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
    from datetime import timedelta
    from study_tracker.media import _timespan_seconds

    assert _timespan_seconds(timedelta(seconds=42)) == 42
    assert _timespan_seconds(420_000_000) == 42
    assert _timespan_seconds(None) == 0


def test_media_seek_helper_is_importable():
    from study_tracker.media import seek_session_position

    assert callable(seek_session_position)
