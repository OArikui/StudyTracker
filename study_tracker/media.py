"""Windows-wide media keys and optional GSMTC session metadata."""
from __future__ import annotations

import asyncio
import ctypes
import platform
from ctypes import wintypes

from PySide6.QtCore import QThread, Signal

IS_WINDOWS = platform.system() == "Windows"
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
WM_HOTKEY = 0x0312

HOTKEYS = {
    1: (MOD_CONTROL | MOD_ALT, 0x20, "Ctrl+Alt+Space", "再生 / 一時停止"),
    2: (MOD_CONTROL | MOD_ALT, 0x25, "Ctrl+Alt+Left", "前のメディア"),
    3: (MOD_CONTROL | MOD_ALT, 0x27, "Ctrl+Alt+Right", "次のメディア"),
}


def send_media_key(vk: int) -> bool:
    """Send a standard Windows media/volume key; return False off Windows."""
    if not IS_WINDOWS:
        return False
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 0x0002, 0)
        return True
    except (AttributeError, OSError):
        return False


def register_global_hotkeys(hwnd: int) -> list[int]:
    """Register built-in global shortcuts and return successfully registered IDs."""
    if not IS_WINDOWS:
        return []
    registered = []
    user32 = ctypes.windll.user32
    for hotkey_id, (modifiers, vk, _label, _action) in HOTKEYS.items():
        if user32.RegisterHotKey(wintypes.HWND(hwnd), hotkey_id, modifiers, vk):
            registered.append(hotkey_id)
    return registered


def unregister_global_hotkeys(hwnd: int, registered: list[int]) -> None:
    if not IS_WINDOWS:
        return
    user32 = ctypes.windll.user32
    for hotkey_id in registered:
        user32.UnregisterHotKey(wintypes.HWND(hwnd), hotkey_id)


def _timespan_seconds(value) -> float:
    """Convert a WinRT TimeSpan/datetime.timedelta or numeric value to seconds."""
    if value is None:
        return 0.0
    total_seconds = getattr(value, "total_seconds", None)
    if callable(total_seconds):
        try:
            return float(total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 0.0
    try:
        numeric = float(value)
        # Some WinRT projections expose TimeSpan as 100-nanosecond ticks.
        return numeric / 10_000_000 if abs(numeric) > 10_000_000 else numeric
    except (TypeError, ValueError, OverflowError):
        return 0.0


class MediaSessionReader(QThread):
    """Poll Windows GSMTC sessions without blocking the Qt UI.

    Requires optional WinRT projections. If unavailable, media keys still work.
    """
    sessions_changed = Signal(list)
    status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stopping = False

    def stop(self) -> None:
        self._stopping = True
        self.wait(2500)

    async def _read_sessions(self) -> list[dict]:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
        manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        output = []
        for session in manager.get_sessions():
            try:
                app_id = str(session.source_app_user_model_id)
                props = await session.try_get_media_properties_async()
                playback = session.get_playback_info()
                status = str(playback.playback_status).rsplit(".", 1)[-1]
                timeline = session.get_timeline_properties()
                position = _timespan_seconds(getattr(timeline, "position", None))
                end_time = _timespan_seconds(getattr(timeline, "end_time", None))
                start_time = _timespan_seconds(getattr(timeline, "start_time", None))
                duration = max(0.0, end_time - start_time)
                output.append({
                    "app_id": app_id,
                    "title": str(props.title or ""),
                    "artist": str(props.artist or ""),
                    "album": str(props.album_title or ""),
                    "status": status,
                    "position": max(0.0, position - start_time),
                    "duration": duration,
                })
            except Exception:
                continue
        return output

    async def _poll(self) -> None:
        while not self._stopping:
            try:
                self.sessions_changed.emit(await self._read_sessions())
                self.status_changed.emit("Windowsメディアセッション接続中")
            except (ImportError, ModuleNotFoundError):
                self.sessions_changed.emit([])
                self.status_changed.emit(
                    "メタデータ取得には任意依存関係 winrt が必要です。メディアキー操作は利用できます。"
                )
            except Exception as exc:
                self.status_changed.emit(f"メディア情報を取得できません: {exc}")
            await asyncio.sleep(2.0)

    def run(self) -> None:
        asyncio.run(self._poll())


async def _try_seek_session(app_id: str, position_seconds: float) -> bool:
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
    manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
    for session in manager.get_sessions():
        if str(session.source_app_user_model_id) != app_id:
            continue
        position_ticks = max(0, int(position_seconds * 10_000_000))
        await session.try_change_playback_position_async(position_ticks)
        return True
    return False


def seek_session_position(app_id: str, position_seconds: float) -> None:
    """Seek the selected Windows media session; no-op if the session API is unavailable."""
    import threading

    if not IS_WINDOWS or not app_id:
        return

    def worker():
        try:
            asyncio.run(_try_seek_session(app_id, position_seconds))
        except Exception:
            # Seeking is optional; do not disturb playback if the player does not support it.
            return

    threading.Thread(target=worker, daemon=True).start()


async def _try_session_action(app_id: str, action: str) -> bool:
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
    manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
    for session in manager.get_sessions():
        if str(session.source_app_user_model_id) != app_id:
            continue
        method_name = {
            "toggle": "try_toggle_play_pause_async",
            "previous": "try_skip_previous_async",
            "next": "try_skip_next_async",
        }.get(action)
        if not method_name:
            return False
        await getattr(session, method_name)()
        return True
    return False


def send_session_action(app_id: str, action: str) -> None:
    """Control the selected GSMTC session asynchronously, falling back to media keys."""
    import threading

    if not IS_WINDOWS or not app_id:
        fallback = {"toggle": VK_MEDIA_PLAY_PAUSE, "previous": VK_MEDIA_PREV_TRACK,
                    "next": VK_MEDIA_NEXT_TRACK}.get(action)
        if fallback is not None:
            send_media_key(fallback)
        return

    def worker():
        try:
            if not asyncio.run(_try_session_action(app_id, action)):
                fallback = {"toggle": VK_MEDIA_PLAY_PAUSE, "previous": VK_MEDIA_PREV_TRACK,
                            "next": VK_MEDIA_NEXT_TRACK}.get(action)
                if fallback is not None:
                    send_media_key(fallback)
        except Exception:
            fallback = {"toggle": VK_MEDIA_PLAY_PAUSE, "previous": VK_MEDIA_PREV_TRACK,
                        "next": VK_MEDIA_NEXT_TRACK}.get(action)
            if fallback is not None:
                send_media_key(fallback)

    threading.Thread(target=worker, daemon=True).start()
