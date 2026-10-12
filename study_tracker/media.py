"""Windows-wide media keys and optional GSMTC session metadata."""
from __future__ import annotations

import asyncio
import ctypes
import logging
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
    Session metadata and timeline data are read independently, so an unsupported
    timeline property does not make the title/artist information disappear.
    """

    sessions_changed = Signal(list)
    status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stopping = False
        self._session_errors: list[str] = []

    def stop(self) -> None:
        self._stopping = True
        self.wait(2500)

    def _note_session_error(self, app_id: str, field: str, exc: Exception) -> None:
        detail = f"{app_id or '不明なセッション'}: {field} ({type(exc).__name__}: {exc})"
        self._session_errors.append(detail)
        logging.getLogger("study_tracker.media").debug(
            "Could not read media session field: %s", detail, exc_info=True
        )

    def _read_text_property(self, obj, field: str, app_id: str) -> str:
        if obj is None:
            return ""
        try:
            return str(getattr(obj, field, "") or "")
        except Exception as exc:
            self._note_session_error(app_id, field, exc)
            return ""

    async def _read_sessions(self) -> list[dict]:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager

        manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        output = []
        self._session_errors = []

        for index, session in enumerate(manager.get_sessions(), start=1):
            app_id = self._read_text_property(session, "source_app_user_model_id", "")
            title = ""
            artist = ""
            album = ""
            status = "Unknown"
            position = 0.0
            duration = 0.0

            # A player may expose its session while temporarily failing to return
            # media properties. Keep the session visible and retry on the next poll.
            try:
                props = await session.try_get_media_properties_async()
            except Exception as exc:
                props = None
                self._note_session_error(app_id, "メディア詳細", exc)

            title = self._read_text_property(props, "title", app_id)
            artist = self._read_text_property(props, "artist", app_id)
            album = self._read_text_property(props, "album_title", app_id)

            try:
                playback = session.get_playback_info()
                playback_status = getattr(playback, "playback_status", "Unknown")
                status = str(playback_status).rsplit(".", 1)[-1]
            except Exception as exc:
                self._note_session_error(app_id, "再生状態", exc)

            # Timeline access is deliberately isolated from metadata access.
            # Some sessions do not implement useful timeline/seek information.
            try:
                timeline = session.get_timeline_properties()
                position = _timespan_seconds(getattr(timeline, "position", None))
                start_time = _timespan_seconds(getattr(timeline, "start_time", None))
                end_time = _timespan_seconds(getattr(timeline, "end_time", None))
                duration = max(0.0, end_time - start_time)
                position = max(0.0, position - start_time)
            except Exception as exc:
                self._note_session_error(app_id, "再生位置", exc)

            output.append({
                "app_id": app_id,
                "title": title,
                "artist": artist,
                "album": album,
                "status": status,
                "position": position,
                "duration": duration,
            })

        return output

    async def _poll(self) -> None:
        logger = logging.getLogger("study_tracker.media")
        while not self._stopping:
            try:
                sessions = await self._read_sessions()
                self.sessions_changed.emit(sessions)
                if not sessions:
                    self.status_changed.emit(
                        "Windowsメディアセッションがありません。対応プレーヤーで再生を開始してください。"
                    )
                elif self._session_errors:
                    first_error = self._session_errors[0]
                    if len(first_error) > 100:
                        first_error = first_error[:97] + "..."
                    self.status_changed.emit(
                        f"{len(sessions)}件検出（情報の一部を取得できません: {first_error}）"
                    )
                else:
                    self.status_changed.emit(f"Windowsメディアセッションを{len(sessions)}件検出")
            except ImportError as exc:
                self.sessions_changed.emit([])
                self.status_changed.emit(
                    "メディア情報用の winrt が読み込めません。"
                    "同じ Python 環境で python -m pip install -e \".[windows-media]\" を実行してください。"
                )
                logger.warning("Windows media projection could not be imported: %s", exc)
            except Exception as exc:
                self.sessions_changed.emit([])
                self.status_changed.emit(f"メディア情報を取得できません: {type(exc).__name__}: {exc}")
                logger.exception("Could not enumerate Windows media sessions")
            await asyncio.sleep(2.0)

    def run(self) -> None:
        """Run WinRT polling in an explicitly initialized worker-thread apartment."""
        apartment_initialized = False
        try:
            try:
                from winrt.runtime import ApartmentType, init_apartment
            except ImportError:
                # Older projections may initialize the apartment automatically.
                pass
            else:
                try:
                    init_apartment(ApartmentType.MULTI_THREADED)
                    apartment_initialized = True
                except Exception:
                    # Let the polling path surface the actual GSMTC/API error if
                    # this thread was already initialized by the host runtime.
                    logging.getLogger("study_tracker.media").debug(
                        "WinRT MTA initialization was not applied", exc_info=True
                    )
            asyncio.run(self._poll())
        finally:
            if apartment_initialized:
                try:
                    from winrt.runtime import uninit_apartment

                    uninit_apartment()
                except Exception:
                    logging.getLogger("study_tracker.media").debug(
                        "WinRT apartment cleanup failed", exc_info=True
                    )


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
            logging.getLogger("study_tracker.media").debug("Media seek failed", exc_info=True)

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
            logging.getLogger("study_tracker.media").debug("Session action failed", exc_info=True)
            fallback = {"toggle": VK_MEDIA_PLAY_PAUSE, "previous": VK_MEDIA_PREV_TRACK,
                        "next": VK_MEDIA_NEXT_TRACK}.get(action)
            if fallback is not None:
                send_media_key(fallback)

    threading.Thread(target=worker, daemon=True).start()
