from __future__ import annotations
import logging
import math
import platform
import ctypes
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QKeySequence, QShortcut, QIntValidator
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem,
    QSplitter, QMessageBox, QGroupBox, QCheckBox, QFileDialog, QTabWidget,
    QAbstractItemView, QHeaderView, QDialog, QListWidget, QSlider, QSpinBox, QFrame, QApplication
)

from .backup import create_backup
from .models import COLUMNS, StudyRow, build_actual_scope
from .parser import parse, render, is_time_placeholder
from .sync import validate, validate_for_apply
from .export import export_csv, export_xlsx
from .dialogs import PresetManagerDialog, QuickRegisterDialog, ManicTimeSettingsDialog, StatisticsDialog, DirectorySettingsDialog, MediaSettingsDialog, BackupSettingsDialog
from .media import (HOTKEYS, WM_HOTKEY, VK_VOLUME_UP, VK_VOLUME_DOWN, VK_VOLUME_MUTE, MediaSessionReader, send_media_key, send_session_action, register_global_hotkeys, unregister_global_hotkeys, seek_session_position)
from .manictime import ManicTimeAdapter, ManicTimeConfig
from .timestamps import assess_timestamp
from .logging_utils import export_log


JST = timezone(timedelta(hours=9))



def now_jst():
    return datetime.now(JST)


def fmt_duration(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


class AnalogStudyClock(QWidget):
    """Text-free analog clock with a subtle 24-hour study activity ring."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(150, 150)
        self.setMaximumSize(220, 220)
        self.setAccessibleName("今日の学習履歴付きアナログ時計")
        self._segments = []
        self._live_start = None
        self._live_active = False

    def set_day_segments(self, segments, live_start=None, live_active=False):
        self._segments = list(segments)
        self._live_start = live_start
        self._live_active = live_active
        self.update()

    @staticmethod
    def _time_fraction(value, day_start):
        return max(0.0, min(1.0, (value - day_start).total_seconds() / 86400.0))

    def _draw_activity_arc(self, painter, rect, radius, start, end, active, day_start):
        tomorrow = day_start + timedelta(days=1)
        left, right = max(start, day_start), min(end, tomorrow)
        if right <= left:
            return
        start_fraction = self._time_fraction(left, day_start)
        end_fraction = self._time_fraction(right, day_start)
        start_angle = int((90.0 - start_fraction * 360.0) * 16)
        span_angle = -max(1, int((end_fraction - start_fraction) * 360.0 * 16))
        color = QColor("#7fa9d8" if active else "#d8c69c")
        color.setAlpha(125 if active else 90)
        painter.setPen(QPen(color, max(5, int(radius * 0.075)), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, start_angle, span_angle)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        cx = self.width() / 2
        cy = self.height() / 2
        radius = side / 2 - 9
        ring_rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        painter.setPen(QPen(QColor("#e8edf2"), max(5, int(radius * 0.075))))
        face_color = QColor("#fbfcfd")
        face_color.setAlpha(125)
        painter.setBrush(QBrush(face_color))
        painter.drawEllipse(ring_rect)

        now = now_jst()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for segment in self._segments:
            try:
                start = datetime.fromisoformat(segment["start_at"]).astimezone(JST)
                end = datetime.fromisoformat(segment["end_at"]).astimezone(JST)
                self._draw_activity_arc(
                    painter, ring_rect, radius, start, end, bool(segment["active"]), day_start
                )
            except (KeyError, TypeError, ValueError):
                continue
        if self._live_start is not None:
            self._draw_activity_arc(
                painter, ring_rect, radius, self._live_start, now, self._live_active, day_start
            )

        face_radius = radius * 0.78
        face = QRectF(cx - face_radius, cy - face_radius, face_radius * 2, face_radius * 2)
        painter.setPen(QPen(QColor("#d8dee6"), 1.3))
        face_color = QColor("#ffffff")
        face_color.setAlpha(150)
        painter.setBrush(QBrush(face_color))
        painter.drawEllipse(face)

        for tick in range(60):
            angle = (90 - tick * 6) * 3.141592653589793 / 180
            major = tick % 5 == 0
            if not major:
                continue
            outer = face_radius - 5
            inner = outer - 10
            painter.setPen(QPen(QColor("#596675"), 1.8))
            painter.drawLine(
                QPointF(cx + inner * math.cos(angle), cy - inner * math.sin(angle)),
                QPointF(cx + outer * math.cos(angle), cy - outer * math.sin(angle)),
            )

        second = now.second + now.microsecond / 1_000_000
        minute = now.minute + second / 60
        hour = (now.hour % 12) + minute / 60

        def hand(angle_degrees, length, color, width):
            angle = (90 - angle_degrees) * 3.141592653589793 / 180
            painter.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(
                QPointF(cx, cy),
                QPointF(cx + length * math.cos(angle), cy - length * math.sin(angle)),
            )

        hand(hour * 30, face_radius * 0.48, "#263746", max(2, int(radius * 0.035)))
        hand(minute * 6, face_radius * 0.68, "#263746", max(1, int(radius * 0.022)))
        hand(second * 6, face_radius * 0.73, "#c16d63", 1.2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#263746")))
        painter.drawEllipse(QPointF(cx, cy), 3.5, 3.5)
        painter.end()


class MainWindow(QMainWindow):
    def __init__(self, db, forced_subject=None):
        super().__init__()
        self.db = db
        self.forced_subject = forced_subject
        self.session_id = None
        self.current_rows: list[StudyRow] = []
        self.segment_started = None
        self.last_edit_at = None
        self.current_content_started_at = None
        self.current_active_accumulated = 0.0
        self.active = True
        self.timestamp_locations: list[tuple[datetime, str]] = []
        self.view_mode = "clock"
        self._history_window = None
        self._last_analog_refresh = None
        self._last_error_message = None
        self._media_reader = None
        self._media_registered_hotkeys = []
        self._media_sessions = []
        self._media_last_payload = None
        self._media_status_text = "メディア情報を待機中"
        self._backup_retry_at = None
        self._fullscreen_window = None
        self._fullscreen_blackout = False
        self._timer_deadline = None
        self._timer_remaining_seconds = 25 * 60
        self._timer_running = False
        self._timer_has_started = False
        self._media_seek_dragging = False

        self.mtc = ManicTimeAdapter(ManicTimeConfig(
            document_mode=db.get_setting("mt_document_mode", "material"),
            server_url=db.get_setting("mt_server_url", "")
        ))

        self.setWindowTitle("Study Tracker")
        self.resize(1280, 800)
        self.setMinimumSize(1000, 650)
        self.statusBar().showMessage("準備完了")
        self.build_home()
        self._apply_app_theme()
        self._escape_fullscreen = QShortcut(QKeySequence("Escape"), self)
        self._escape_fullscreen.activated.connect(self.exit_fullscreen)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(250)

        self.backup_timer = QTimer(self)
        self.backup_timer.timeout.connect(self._maybe_run_scheduled_backup)
        self.backup_timer.start(60_000)
        QTimer.singleShot(1500, self._maybe_run_scheduled_backup)
        self._apply_media_settings()

    # ---- Menu ----
    def rebuild_menu(self):
        self.menuBar().clear()

        preset_menu = self.menuBar().addMenu("プリセット")
        for label, kind in [
            ("学習区分", "category"),
            ("科目", "subject"),
        ]:
            a = preset_menu.addAction(label)
            a.triggered.connect(lambda _, k=kind: self.open_preset(k))

        material_action = preset_menu.addAction("教材（科目別）")
        material_action.triggered.connect(self.open_material_preset)

        unit_action = preset_menu.addAction("学習単位エイリアス")
        unit_action.triggered.connect(self.open_unit_aliases)

        tools = self.menuBar().addMenu("ツール")
        stats = tools.addAction("学習時間集計")
        stats.triggered.connect(self.open_stats)
        history = tools.addAction("学習記録アーカイブ")
        history.triggered.connect(self.show_history)

        viewer = tools.addAction("学習記録ビューアー")
        viewer.triggered.connect(self.open_viewer)
        load_data = tools.addAction("バックアップ / エクスポートを読み込む")
        load_data.triggered.connect(self.load_data_file)
        csv_a = tools.addAction("CSV出力")
        csv_a.triggered.connect(self.save_csv)
        xlsx_a = tools.addAction("XLSX出力")
        xlsx_a.triggered.connect(self.save_xlsx)

        settings = self.menuBar().addMenu("設定")
        mt = settings.addAction("ManicTime連携")
        mt.triggered.connect(self.open_mtc_settings)

        paths_action = settings.addAction("使用ディレクトリ・ViewerPack設定")
        paths_action.triggered.connect(self.open_directory_settings)

        media_action = settings.addAction("Windowsメディア操作")
        media_action.triggered.connect(self.open_media_settings)
        media_help_action = settings.addAction("メディア取得の案内")
        media_help_action.triggered.connect(self.show_media_help)

        backup_action = settings.addAction("定期バックアップ")
        backup_action.triggered.connect(self.open_backup_settings)

        theme_menu = settings.addMenu("外観")
        dark_action = theme_menu.addAction("ダークモード")
        dark_action.triggered.connect(lambda: self._set_app_theme("dark"))
        light_action = theme_menu.addAction("ライトモード")
        light_action.triggered.connect(lambda: self._set_app_theme("light"))

        log_action = settings.addAction("エラーログをエクスポート")
        log_action.triggered.connect(self.save_error_log)

    def _set_app_theme(self, theme):
        theme = "light" if theme == "light" else "dark"
        self.db.set_setting("app_theme", theme)
        self._apply_app_theme()
        self.statusBar().showMessage("外観を変更しました。", 4000)

    def _apply_app_theme(self):
        theme = self.db.get_setting("app_theme", "dark")
        app = QApplication.instance()
        if app is None:
            return
        if theme == "light":
            app.setStyleSheet("""
                QWidget { background-color: #f7f8fa; color: #20252b; }
                QLineEdit, QTextEdit, QComboBox, QSpinBox, QTableWidget, QListWidget {
                    background-color: #ffffff; color: #20252b; border: 1px solid #cbd2da;
                    border-radius: 4px; padding: 4px;
                }
                QPushButton { background-color: #e8edf2; color: #20252b; border: 1px solid #c4ccd5;
                    border-radius: 5px; padding: 7px 10px; }
                QPushButton:hover { background-color: #dce5ee; }
                QMenuBar, QMenu { background-color: #f7f8fa; color: #20252b; }
                QHeaderView::section { background-color: #e8edf2; color: #20252b; padding: 5px; }
            """)
        else:
            app.setStyleSheet("""
                QWidget { background-color: #171a1f; color: #e7ebf0; }
                QLineEdit, QTextEdit, QComboBox, QSpinBox, QTableWidget, QListWidget {
                    background-color: #222831; color: #e7ebf0; border: 1px solid #414b58;
                    border-radius: 4px; padding: 4px;
                }
                QPushButton { background-color: #2b333d; color: #f0f3f7; border: 1px solid #46515e;
                    border-radius: 5px; padding: 7px 10px; }
                QPushButton:hover { background-color: #374454; }
                QMenuBar, QMenu { background-color: #20252c; color: #e7ebf0; }
                QHeaderView::section { background-color: #2b333d; color: #e7ebf0; padding: 5px; }
            """)

    def report_error(self, message):
        """Show errors in both the persistent footer and the current screen header."""
        text = str(message).strip() or "原因不明のエラーが発生しました。"
        self._last_error_message = text
        logging.getLogger("study_tracker.ui").error(text)
        self.statusBar().showMessage(f"エラー: {text}")
        banner = getattr(self, "error_banner", None)
        if banner is not None:
            try:
                banner.setText(f"エラー: {text}")
                banner.show()
            except RuntimeError:
                self.error_banner = None

    def clear_error(self):
        self._last_error_message = None
        banner = getattr(self, "error_banner", None)
        if banner is not None:
            try:
                banner.clear()
                banner.hide()
            except RuntimeError:
                self.error_banner = None
        self.statusBar().showMessage("準備完了")

    def _add_error_banner(self, layout):
        self.error_banner = QLabel()
        self.error_banner.setWordWrap(True)
        self.error_banner.setStyleSheet(
            "QLabel { color: #9f1d16; background: #fff0ef; border: 1px solid #f2b8b5; "
            "border-radius: 5px; padding: 6px 10px; }"
        )
        if self._last_error_message:
            self.error_banner.setText(f"エラー: {self._last_error_message}")
            self.error_banner.show()
        else:
            self.error_banner.hide()
        layout.addWidget(self.error_banner)

    def save_error_log(self):
        from .paths import get_path
        default_dir = get_path("export_dir")
        default_dir.mkdir(parents=True, exist_ok=True)
        default = str(default_dir / "study_tracker_error.log")
        path, _ = QFileDialog.getSaveFileName(
            self, "エラーログをエクスポート", default, "Log files (*.log);;Text files (*.txt)"
        )
        if not path:
            return
        try:
            export_log(path)
            self.clear_error()
            self.statusBar().showMessage(f"ログをエクスポートしました: {path}", 8000)
        except Exception as exc:
            logging.getLogger("study_tracker.ui").exception("Log export failed")
            self.report_error(f"ログを出力できませんでした: {exc}")

    def open_preset(self, kind):
        PresetManagerDialog(self.db, kind, parent=self).exec()
        self.build_home()

    def open_material_preset(self):
        subject = self.home_subject.currentText().strip()
        if not subject:
            QMessageBox.warning(self, "科目が必要です", "先に科目を選択してください。")
            return
        PresetManagerDialog(self.db, "material", subject, parent=self).exec()
        self.build_home()

    def open_unit_aliases(self):
        PresetManagerDialog(self.db, "unit", alias_mode=True, parent=self).exec()

    def open_viewer(self):
        from .paths import get_viewer_pack_path, get_viewer_folder_path
        from .viewerpack import MANUAL_URL, resolve_viewer_package_parent, _archive_package_prefix
        import zipfile

        folder = get_viewer_folder_path()
        pack = get_viewer_pack_path()
        if folder is not None and str(folder).strip():
            try:
                resolve_viewer_package_parent(folder)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(
                    self, "展開済みViewerPackを確認できません",
                    f"{exc}\n\n設定からフォルダを選び直してください。\n導入マニュアル: {MANUAL_URL}"
                )
                self.open_directory_settings()
                return
            launch_args = ["--viewer-folder", str(folder)]
        else:
            if not pack.is_file() or not zipfile.is_zipfile(pack):
                QMessageBox.warning(
                    self, "ViewerPackが未設定です",
                    f"ViewerPack ZIPが見つからないか、ZIP形式ではありません。\n{pack}\n\n"
                    f"設定 > 使用ディレクトリ・ViewerPack設定 でZIPまたは展開済みフォルダを指定してください。\n"
                    f"導入マニュアル: {MANUAL_URL}"
                )
                self.open_directory_settings()
                return
            try:
                with zipfile.ZipFile(pack) as archive:
                    _archive_package_prefix(archive)
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                QMessageBox.warning(
                    self, "ViewerPack ZIPを確認できません",
                    f"{exc}\n導入マニュアル: {MANUAL_URL}"
                )
                self.open_directory_settings()
                return
            launch_args = ["--viewer-zip", str(pack)]

        try:
            if getattr(sys, "frozen", False):
                command = [sys.executable, *launch_args]
            else:
                command = [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "main.py"),
                    *launch_args,
                ]
            subprocess.Popen(command, cwd=str(Path(__file__).resolve().parents[1]))
        except Exception as exc:
            QMessageBox.critical(
                self, "Viewer起動エラー",
                f"ViewerPackを起動できませんでした。\n{exc}\n\n導入マニュアル: {MANUAL_URL}"
            )
    def open_directory_settings(self):
        if self.session_id:
            QMessageBox.warning(self, "変更できません", "学習中はパス設定を変更できません。学習を終了してから開いてください。")
            return
        old_db = self.db.path.resolve()
        if DirectorySettingsDialog(self).exec() != QDialog.DialogCode.Accepted:
            return

        from .paths import get_db_path, load_config, save_config
        new_db = get_db_path().resolve()
        if new_db == old_db:
            QMessageBox.information(self, "設定", "パス設定を保存しました。")
            return

        if new_db.is_file():
            answer = QMessageBox.warning(
                self, "既存DBへの切り替え",
                f"指定先には既存の学習記録があります。\n{new_db}\n\n"
                "このファイルは上書きしません。指定先のDBへ切り替えますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                cfg = load_config()
                cfg["db_path"] = str(old_db)
                save_config(cfg)
                return
        else:
            answer = QMessageBox.question(
                self, "DB保存先の変更",
                f"DB保存先が変更されました。\n現在: {old_db}\n新規: {new_db}\n\n"
                "現在のDBを新しい場所へコピーしますか？\n"
                "コピーしない場合、新しい空のDBを作成します。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

        try:
            new_db.parent.mkdir(parents=True, exist_ok=True)
            if answer == QMessageBox.StandardButton.Yes and old_db.is_file() and not new_db.exists():
                import sqlite3
                target = sqlite3.connect(str(new_db), timeout=30)
                try:
                    self.db.con.backup(target)
                    integrity = target.execute("PRAGMA integrity_check").fetchone()
                    if integrity is None or integrity[0] != "ok":
                        raise sqlite3.DatabaseError(f"DBコピーの整合性チェックに失敗しました: {integrity!r}")
                finally:
                    target.close()
            self.db.close()
            from .db import Database
            self.db = Database(new_db)
            self.mtc.config.document_mode = self.db.get_setting("mt_document_mode", "material")
            self.mtc.config.server_url = self.db.get_setting("mt_server_url", "")
            self.build_home()
            QMessageBox.information(self, "設定", "パス設定を保存しました。")
        except Exception as exc:
            logging.getLogger("study_tracker.paths").exception("Database path switch failed")
            from .db import Database
            try:
                self.db = Database(old_db)
            except Exception:
                self.report_error(f"DB保存先の切替に失敗し、元のDBも開けませんでした: {exc}")
                QMessageBox.critical(self, "DB切替エラー", f"{exc}")
                return
            cfg = load_config()
            cfg["db_path"] = str(old_db)
            save_config(cfg)
            self.report_error(f"DB保存先を切り替えられませんでした: {exc}")
            QMessageBox.critical(self, "DB切替エラー", str(exc))
    def open_stats(self):
        StatisticsDialog(
            self.db,
            current_subject=self.home_subject.currentText().strip(),
            current_material=self.home_material.currentText().strip(),
            parent=self
        ).exec()

    def open_mtc_settings(self):
        ManicTimeSettingsDialog(self.db, parent=self).exec()
        self.mtc.config.document_mode = self.db.get_setting("mt_document_mode", "material")
        self.mtc.config.server_url = self.db.get_setting("mt_server_url", "")

    def show_media_help(self):
        QMessageBox.information(
            self,
            "Windowsメディア情報の取得",
            "メディア情報を取得するには、Windows 10/11 のメディアセッション (GSMTC) と "
            "任意依存関係が必要です。\n\n"
            "1. PowerShell で、StudyTracker を起動するものと同じ Python に対して次を実行します。\n"
            "   python -m pip install -e \".[windows-media]\"\n"
            "   または: python -m pip install winrt-runtime winrt-Windows.Media.Control\n\n"
            "2. StudyTracker を再起動し、「設定」→「Windowsメディア操作」を有効にします。\n"
            "3. ブラウザや音楽プレーヤーで実際にメディアを再生し、メディアセッションが "
            "Windows の音量ミキサー / メディアフライアウトに表示されることを確認します。\n"
            "4. 複数のセッションがある場合は、学習画面の「メディア優先対象」で選択します。\n\n"
            "情報が出ない場合:\n"
            "• 対応するプレーヤーを使用してください。すべてのアプリがセッション情報を公開するわけではありません。\n"
            "• Python が複数ある場合は、起動時と同じ python.exe で依存関係をインストールします。\n"
            "• StudyTracker を完全に終了して起動し直し、プレーヤーで再生を開始します。\n"
            "• winrt 依存関係がない場合は、表示された案内に従ってインストールします。\n\n"
            "依存関係がない場合も標準 Windows メディアキーによる再生操作は利用できます。"
        )

    def open_media_settings(self):
        if MediaSettingsDialog(self.db, parent=self).exec() == QDialog.DialogCode.Accepted:
            self._apply_media_settings()

    def open_backup_settings(self):
        if BackupSettingsDialog(self.db, parent=self).exec() == QDialog.DialogCode.Accepted:
            self._backup_retry_at = None
            self._maybe_run_scheduled_backup()

    def _maybe_run_scheduled_backup(self):
        if self.db.get_setting("backup_enabled", "0") != "1":
            return

        now = datetime.now().astimezone()
        if self._backup_retry_at is not None and now < self._backup_retry_at:
            return

        last_value = self.db.get_setting("backup_last_at", "")
        if last_value:
            try:
                last_backup = datetime.fromisoformat(last_value)
                if last_backup.tzinfo is None:
                    last_backup = last_backup.replace(tzinfo=now.tzinfo)
                try:
                    interval_hours = max(1, int(self.db.get_setting("backup_interval_hours", "24")))
                except (TypeError, ValueError):
                    interval_hours = 24
                if (now - last_backup).total_seconds() < interval_hours * 3600:
                    return
            except (TypeError, ValueError):
                logging.getLogger("study_tracker.backup").warning(
                    "Invalid backup_last_at value; scheduling a backup now."
                )

        try:
            destination = self.db.get_setting(
                "backup_dir", str(Path.home() / "StudyTrackerBackups")
            )
            try:
                retention = int(self.db.get_setting("backup_retention_count", "14"))
            except (TypeError, ValueError):
                retention = 14
            output = create_backup(self.db.path, destination, retention, now=now)
            self.db.set_setting("backup_last_at", now.isoformat())
            self._backup_retry_at = None
            logging.getLogger("study_tracker.backup").info(
                "Scheduled backup created: %s", output
            )
            self.statusBar().showMessage(f"バックアップを作成しました: {output}", 10000)
        except Exception as exc:
            self._backup_retry_at = now + timedelta(minutes=15)
            logging.getLogger("study_tracker.backup").exception("Scheduled backup failed")
            self.report_error(f"定期バックアップに失敗しました: {exc}")

    def _apply_media_settings(self):
        enabled = self.db.get_setting("media_enabled", "0") == "1"
        panel = getattr(self, "media_panel", None)
        if panel is not None:
            panel.setVisible(enabled)
        if enabled and self._media_reader is None:
            self._media_reader = MediaSessionReader(self)
            self._media_reader.sessions_changed.connect(self._on_media_sessions)
            self._media_reader.status_changed.connect(self._on_media_status)
            self._media_reader.start()
            self._media_registered_hotkeys = register_global_hotkeys(int(self.winId()))
            if len(self._media_registered_hotkeys) < len(HOTKEYS):
                self.statusBar().showMessage("一部のグローバルショートカットは他アプリと競合して登録できません。", 8000)
        elif not enabled:
            if self._media_reader is not None:
                self._media_reader.stop()
                self._media_reader = None
            if self._media_registered_hotkeys:
                unregister_global_hotkeys(int(self.winId()), self._media_registered_hotkeys)
                self._media_registered_hotkeys = []
        if hasattr(self, "media_status"):
            self.media_status.setText(self._media_status_text)

    def _on_media_status(self, status):
        self._media_status_text = status
        if hasattr(self, "media_status"):
            self.media_status.setText(status)

    def _on_media_sessions(self, sessions):
        self._media_sessions = list(sessions)
        combo = getattr(self, "media_priority", None)
        if combo is None:
            self._record_media_snapshot()
            return
        previous = self.db.get_setting("media_priority", "")
        combo.blockSignals(True)
        combo.clear()
        for session in self._media_sessions:
            label = " — ".join(x for x in (session.get("title", ""), session.get("artist", ""), session.get("app_id", "")) if x)
            combo.addItem(label or session.get("app_id", "Unknown media session"), session.get("app_id", ""))
        idx = combo.findData(previous)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif combo.count():
            combo.setCurrentIndex(0)
            self.db.set_setting("media_priority", combo.currentData() or "")
        combo.blockSignals(False)
        self._record_media_snapshot()

    def _record_media_snapshot(self):
        if not self.session_id:
            return
        priority = self.db.get_setting("media_priority", "")
        selected = next((s for s in self._media_sessions if s.get("app_id") == priority), None)
        if selected is None and self._media_sessions:
            selected = self._media_sessions[0]
        payload = dict(selected or {"app_id": "", "title": "", "artist": "", "album": "", "status": "Unavailable"})
        payload["priority_app_id"] = priority
        if payload != self._media_last_payload:
            self._media_last_payload = payload
            self.db.add_event(self.session_id, now_jst(), "media_state", payload)

    def _media_priority_changed(self, _index):
        if not hasattr(self, "media_priority"):
            return
        self.db.set_setting("media_priority", self.media_priority.currentData() or "")
        self._record_media_snapshot()

    def _selected_media_app_id(self):
        combo = getattr(self, "media_priority", None)
        return str(combo.currentData() or "") if combo is not None else ""

    def _media_control(self, action):
        app_id = self._selected_media_app_id()
        if action in {"toggle", "previous", "next"}:
            send_session_action(app_id, action)
        elif action == "volume_up":
            send_media_key(VK_VOLUME_UP)
        elif action == "volume_down":
            send_media_key(VK_VOLUME_DOWN)
        elif action == "mute":
            send_media_key(VK_VOLUME_MUTE)

    def nativeEvent(self, event_type, message):
        result = super().nativeEvent(event_type, message)
        try:
            msg = ctypes.cast(int(message), ctypes.POINTER(ctypes.wintypes.MSG)).contents
            if msg.message == WM_HOTKEY and self.db.get_setting("media_enabled", "0") == "1":
                action = {1: "toggle", 2: "previous", 3: "next"}.get(int(msg.wParam))
                if action:
                    self._media_control(action)
                    return True, 0
        except (ValueError, TypeError, OSError, AttributeError):
            pass
        return result

    # ---- Home ----
    def _combo(self, editable=True):
        c = QComboBox()
        c.setEditable(editable)
        return c

    def build_home(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        if not self.session_id:
            self.setWindowTitle("Study Tracker V3.5.4")

        self._add_error_banner(layout)

        title = QLabel("Study Tracker V3.5.4")
        title.setStyleSheet("font-size: 30px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel(
            "MTCには科目・教材を大まかに記録し、本アプリでは11項目の学習情報を詳細に保存します。"
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        form = QFormLayout()
        self.home_category = self._combo()
        self.home_subject = self._combo()
        self.home_material = self._combo()
        self.home_category.currentTextChanged.connect(self.refresh_home_materials)
        self.home_subject.currentTextChanged.connect(self.refresh_home_materials)
        form.addRow("学習区分", self.home_category)
        form.addRow("科目", self.home_subject)
        form.addRow("教材", self.home_material)
        layout.addLayout(form)

        controls = QHBoxLayout()
        edit = QPushButton("カレント学習内容を設定")
        edit.clicked.connect(self.open_editor)
        controls.addWidget(edit)

        start = QPushButton("学習開始")
        start.setMinimumHeight(48)
        start.clicked.connect(self.start)
        controls.addWidget(start)
        layout.addLayout(controls)

        status = QLabel(
            "プリセットは初期状態では空です。\n"
            "メニュー → プリセット から登録してください。\n"
            "学習位置はプリセット必須ではなく、過去の教材使用履歴から候補化されます。"
        )
        status.setWordWrap(True)
        layout.addWidget(status)
        layout.addStretch()

        self.setCentralWidget(root)
        self.rebuild_menu()
        self.refresh_home_presets()

    def refresh_home_presets(self):
        self.home_category.clear()
        self.home_subject.clear()
        self.home_material.clear()
        self.home_category.addItems(self.db.preset_titles("category"))
        self.home_subject.addItems(self.db.preset_titles("subject"))
        if self.forced_subject:
            self.home_subject.setCurrentText(self.forced_subject)
            self.home_subject.setEnabled(False)
            self.home_subject.setToolTip("この起動ファイルはMTC用に科目固定です")
        self.refresh_home_materials()

    def refresh_home_materials(self):
        subject = self.home_subject.currentText().strip()
        self.home_material.blockSignals(True)
        self.home_material.clear()
        self.home_material.addItems(self.db.preset_titles("material", subject))
        self.home_material.blockSignals(False)

    # ---- Editor ----
    def open_editor(self, waiting=False):
        dlg = EditorWindow(self, waiting=waiting)
        dlg.exec()

    # ---- Session ----
    def _new_session_row_start(self):
        return now_jst()

    def start(self):
        if not self.current_rows:
            self.open_editor(False)
        if not self.current_rows:
            return

        start_at = now_jst()
        self.session_id = self.db.start_session(start_at)
        self._media_last_payload = None
        self.segment_started = start_at
        self.current_content_started_at = start_at
        self.last_edit_at = self.segment_started
        self.current_active_accumulated = 0.0
        self.active = True
        self.timestamp_locations = []

        self.db.add_event(self.session_id, self.segment_started, "session_start")
        self.update_title()

        self.show_waiting()

    def _finish_current_segment(self, end=None):
        if not self.session_id or not self.segment_started:
            return
        end = end or now_jst()
        if end <= self.segment_started:
            return

        timestamp_start = self.current_content_started_at or self.segment_started
        timestamps = self.db.timestamps_for_session(self.session_id, timestamp_start, end)
        timestamp_locations = [str(r["location"]) for r in timestamps]

        if self.current_rows:
            for row in self.current_rows:
                actual_scope = build_actual_scope(row.unit, row.scope, timestamp_locations)
                actual_start = self.segment_started.strftime("%H:%M:%S.%f")[:-4]
                actual_end = end.strftime("%H:%M:%S.%f")[:-4]
                d = {
                    "date": row.date,
                    "start": actual_start,
                    "end": actual_end,
                    "display_start": row.start,
                    "display_end": row.end,
                    "timezone": row.timezone,
                    "category": row.category,
                    "subject": row.subject,
                    "material": row.material,
                    "position": row.position,
                    "unit": row.unit,
                    "scope": row.scope,
                    "actual_scope": actual_scope,
                    "notes": row.notes,
                    "branch_fields": sorted(row.branch_fields),
                    "start_auto_at": (
                        self.segment_started.isoformat()
                        if is_time_placeholder(row.start)
                        else row.start_auto_at
                    ),
                    "end_auto_at": (
                        end.isoformat()
                        if is_time_placeholder(row.end)
                        else row.end_auto_at
                    ),
                }
                self.db.add_segment(
                    self.session_id,
                    self.segment_started,
                    end,
                    self.active,
                    d
                )
                self.db.touch_position(row.material, row.position, end)
        self.refresh_analog_clock(force=True)

    def apply_rows(self, rows):
        now = now_jst()
        if self.session_id and self.segment_started:
            self._finish_current_segment(now)
            self.db.add_event(self.session_id, now, "content_edit")
            self.segment_started = now
        self.current_rows = rows
        self.last_edit_at = now
        self.current_content_started_at = now
        self.current_active_accumulated = 0.0
        self.timestamp_locations = []
        self.update_title()

    def _update_active_button_visual(self):
        button = getattr(self, "active_button", None)
        if button is None:
            return
        button.setText("ACTIVE" if self.active else "PASSIVE")
        button.setChecked(self.active)
        if self.active:
            button.setStyleSheet(
                "QPushButton { background-color: #16834a; color: #ffffff; "
                "border: 1px solid #106a3a; border-radius: 5px; "
                "font-weight: 700; padding: 7px 10px; }"
                "QPushButton:hover { background-color: #1a9958; }"
            )
        else:
            button.setStyleSheet(
                "QPushButton { background-color: #b58a2a; color: #1b1e22; "
                "border: 1px solid #8e6a1d; border-radius: 5px; "
                "font-weight: 700; padding: 7px 10px; }"
                "QPushButton:hover { background-color: #c89b39; }"
            )

    def toggle_active(self):
        if not self.session_id:
            return
        now = now_jst()
        if self.active and self.segment_started:
            self.current_active_accumulated += max(0, (now - self.segment_started).total_seconds())
        self._finish_current_segment(now)
        self.active = not self.active
        self.segment_started = now
        self.db.add_event(
            self.session_id,
            now,
            "active" if self.active else "passive"
        )
        # Keep the waiting screen alive when Active/Passive changes. Rebuilding
        # it would discard the in-progress timestamp input (and reset view controls).
        if hasattr(self, "active_button"):
            self._update_active_button_visual()
        if hasattr(self, "timestamp_input"):
            self.timestamp_input.setEnabled(self.active)
        if hasattr(self, "awake"):
            self.apply_keep_awake(self.active and self.awake.isChecked())
        self.refresh_analog_clock(force=True)
        self._render_timestamp_history()
        self.tick()
        if self.active and hasattr(self, "timestamp_input"):
            self.timestamp_input.setFocus()

    def end_session(self, completion_position=None):
        if not self.session_id:
            self.build_home()
            return
        now = now_jst()
        completion_details = None
        if completion_position is not None and self.current_rows:
            row = self.current_rows[0]
            active_seconds = self.current_active_accumulated
            if self.active and self.segment_started:
                active_seconds += max(0, (now - self.segment_started).total_seconds())
            section_start = self.current_content_started_at or self.segment_started or now
            timestamps = [value for _, value in self.timestamp_locations]
            actual_scope = build_actual_scope(row.unit, row.scope, timestamps)
            completion_details = (
                f"学習予定範囲の完了、おめでとうございます！\n\n"
                f"科目: {row.subject or '(未設定)'}\n"
                f"教材: {row.material or '(未設定)'}\n"
                f"学習位置: {row.position or '(未設定)'}\n"
                f"学習単位・予定範囲: {row.unit}({row.scope})\n"
                f"実施範囲: {actual_scope or f'{row.unit}({completion_position})'}\n"
                f"完了位置: {completion_position}\n"
                f"この内容の経過時間: {fmt_duration((now - section_start).total_seconds())}\n"
                f"Active時間: {fmt_duration(active_seconds)}\n"
                f"開始: {section_start.astimezone(JST).strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"終了: {now.astimezone(JST).strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self.db.add_event(
                self.session_id, now, "planned_scope_complete",
                {"position": str(completion_position), "actual_scope": actual_scope},
            )
        self._finish_current_segment(now)
        self.db.close_session(self.session_id, now)
        self.session_id = None
        self.segment_started = None
        self.last_edit_at = None
        self.current_content_started_at = None
        self.current_active_accumulated = 0.0
        self.current_rows = []
        self.timestamp_locations = []
        self.release_keep_awake()
        self.build_home()
        if completion_details:
            QMessageBox.information(self, "学習範囲を完了しました", completion_details)

    def closeEvent(self, event):
        if hasattr(self, "backup_timer"):
            self.backup_timer.stop()
        if self._media_reader is not None:
            self._media_reader.stop()
            self._media_reader = None
        if self._media_registered_hotkeys:
            unregister_global_hotkeys(int(self.winId()), self._media_registered_hotkeys)
            self._media_registered_hotkeys = []
        if self.session_id:
            now = now_jst()
            self._finish_current_segment(now)
            self.db.close_session(self.session_id, now)
            self.session_id = None
            self.current_content_started_at = None
            self.release_keep_awake()
        event.accept()

    # ---- Waiting ----
    def show_waiting(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        self._add_error_banner(layout)

        self.mode = QComboBox()
        self.mode.addItems(["日本標準時", "カレント勉強時間", "合計勉強時間"])
        self.mode.currentTextChanged.connect(lambda _: self.tick())
        self.mode.setToolTip("時計表示を選択")

        layout.addWidget(self.mode, 0, Qt.AlignmentFlag.AlignHCenter)
        clock_row = QHBoxLayout()
        self.clock = QLabel()
        self.clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock.setMinimumHeight(150)
        self.clock.setStyleSheet("font-size: 44px; font-weight: 650; padding: 12px;")
        clock_row.addWidget(self.clock, 1)

        self.analog_clock_widget = AnalogStudyClock()
        self.analog_clock_widget.setToolTip(
            "針は現在時刻、外周の薄い色は今日の学習区間（青: Active、黄灰: Passive）"
        )
        self.analog_clock_widget.setVisible(False)
        clock_row.addWidget(self.analog_clock_widget, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(clock_row)

        self.active_button = QPushButton("ACTIVE" if self.active else "PASSIVE")
        self.active_button.setCheckable(True)
        self.active_button.setChecked(self.active)
        self.active_button.clicked.connect(self.toggle_active)
        self._update_active_button_visual()

        state_row = QHBoxLayout()
        state_row.addWidget(self.active_button)

        edit = QPushButton("学習内容を編集・適用")
        edit.clicked.connect(lambda: self.open_editor(True))
        state_row.addWidget(edit)

        end = QPushButton("セクション終了 → ホーム")
        end.clicked.connect(lambda: self.end_session())
        state_row.addWidget(end)

        self.analog_toggle = QCheckBox("アナログ時計を表示")
        self.analog_toggle.setChecked(False)
        state_row.addSpacing(10)
        self.analog_toggle.toggled.connect(self.analog_clock_widget.setVisible)
        state_row.addWidget(self.analog_toggle)

        self.awake = QCheckBox("Active中はWindowsのスリープを防止")
        self.awake.setChecked(True)
        self.awake.toggled.connect(self.apply_keep_awake)
        state_row.addSpacing(10)
        state_row.addWidget(self.awake)
        state_row.addStretch(1)

        layout.addLayout(state_row)
        fullscreen_row = QHBoxLayout()
        fullscreen_row.addStretch(1)
        self.fullscreen_button = QPushButton("全画面表示")
        self.fullscreen_button.setMinimumSize(180, 44)
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        fullscreen_row.addWidget(self.fullscreen_button)
        fullscreen_row.addStretch(1)
        layout.addLayout(fullscreen_row)

        self.media_panel = QWidget()
        media_layout = QHBoxLayout(self.media_panel)
        media_layout.setContentsMargins(0, 2, 0, 2)
        self.media_priority = QComboBox()
        self.media_priority.setMinimumWidth(150)
        self.media_priority.setMaximumWidth(220)
        self.media_priority.setToolTip("複数セッションがある場合に操作・記録の優先対象を選択")
        self.media_priority.currentIndexChanged.connect(self._media_priority_changed)
        media_layout.addWidget(QLabel("メディア優先対象"))
        media_layout.addWidget(self.media_priority, 1)
        for label, action in [("再生 / 一時停止", "toggle"), ("前", "previous"), ("次", "next"),
                              ("音量−", "volume_down"), ("音量+", "volume_up"), ("ミュート", "mute")]:
            button = QPushButton(label)
            button.setMinimumHeight(36)
            button.setMinimumWidth(72)
            button.setMaximumWidth(112)
            button.clicked.connect(lambda checked=False, a=action: self._media_control(a))
            media_layout.addWidget(button)
        self.media_status = QLabel(self._media_status_text)
        self.media_status.setMaximumWidth(190)
        self.media_status.setWordWrap(True)
        media_layout.addWidget(self.media_status)
        self.media_panel.setVisible(self.db.get_setting("media_enabled", "0") == "1")
        self._apply_media_settings()

        study_stamp_row = QHBoxLayout()
        study_stamp_row.setContentsMargins(0, 0, 0, 0)
        study_stamp_row.setSpacing(12)
        study_stamp_row.addStretch(1)

        study_panel = QGroupBox("カレント学習内容")
        study_layout = QVBoxLayout(study_panel)
        study_layout.setContentsMargins(12, 16, 12, 12)
        self.current = QLabel()
        self.current.setWordWrap(True)
        self.current.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.current.setMaximumWidth(440)
        self.current.setStyleSheet("font-size: 18px; padding: 4px;")
        study_panel.setMinimumWidth(440)
        study_panel.setMaximumWidth(520)
        study_layout.addWidget(self.current)
        study_stamp_row.addWidget(study_panel)

        timestamp_box = QGroupBox("学習タイムスタンプ")
        timestamp_layout = QVBoxLayout(timestamp_box)
        timestamp_input_panel = QWidget()
        input_layout = QVBoxLayout(timestamp_input_panel)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.addWidget(QLabel("現在の学習単位位置"))
        timestamp_row = QHBoxLayout()
        self.timestamp_input = QLineEdit()
        self.timestamp_input.setPlaceholderText("テンキーで位置を入力して Enter")
        self.timestamp_input.setValidator(QIntValidator(0, 999999, self.timestamp_input))
        self.timestamp_input.returnPressed.connect(self.record_timestamp)
        timestamp_row.addWidget(self.timestamp_input, 1)
        record_button = QPushButton("記録")
        record_button.clicked.connect(self.record_timestamp)
        timestamp_row.addWidget(record_button)
        input_layout.addLayout(timestamp_row)
        self.timestamp_status = QLabel("まだタイムスタンプはありません。")
        self.timestamp_status.setWordWrap(True)
        self.timestamp_status.setMaximumWidth(280)
        self.timestamp_status.setMaximumHeight(42)
        input_layout.addWidget(self.timestamp_status)
        timestamp_layout.addWidget(timestamp_input_panel)
        timestamp_layout.addWidget(QLabel("タイムスタンプ履歴"))
        self.timestamp_list = QListWidget()
        self.timestamp_list.setMinimumHeight(65)
        self.timestamp_list.setMaximumHeight(115)
        self.timestamp_list.setMaximumWidth(300)
        timestamp_box.setMinimumWidth(350)
        timestamp_box.setMaximumWidth(380)
        timestamp_layout.addWidget(self.timestamp_list, 1)
        study_stamp_row.addWidget(timestamp_box)
        study_stamp_row.addStretch(1)
        layout.addLayout(study_stamp_row)

        hint = QLabel(
            "Passive中は学習時間に加算しません。Active/Passiveの切替は区間として保存されます。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        media_separator = QFrame()
        media_separator.setFrameShape(QFrame.Shape.HLine)
        media_separator.setFrameShadow(QFrame.Shadow.Plain)
        media_separator.setStyleSheet("color: #707780; max-height: 1px;")
        layout.addWidget(media_separator)
        layout.addWidget(self.media_panel)

        self.setCentralWidget(root)
        self.apply_keep_awake(self.active and self.awake.isChecked())
        self.update_title()
        self.refresh_analog_clock(force=True)
        self._render_timestamp_history()
        self.tick()
        self.timestamp_input.setEnabled(self.active)
        if self.active:
            self.timestamp_input.setFocus()

    def _format_media_time(self, seconds):
        seconds = max(0, int(seconds or 0))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _fullscreen_timer_text(self):
        remaining = self._timer_remaining_seconds
        if self._timer_running and self._timer_deadline is not None:
            remaining = max(0, int((self._timer_deadline - now_jst()).total_seconds() + 0.999))
        return f"{remaining // 60:02d}:{remaining % 60:02d}"

    def _toggle_countdown(self):
        if self._timer_running:
            self._timer_remaining_seconds = max(
                0, int((self._timer_deadline - now_jst()).total_seconds() + 0.5)
            ) if self._timer_deadline else self._timer_remaining_seconds
            self._timer_running = False
            self._timer_deadline = None
        else:
            if not self._timer_has_started or self._timer_remaining_seconds <= 0:
                spin = getattr(self, "fullscreen_timer_minutes", None)
                minutes = spin.value() if spin is not None else 25
                self._timer_remaining_seconds = minutes * 60
            self._timer_deadline = now_jst() + timedelta(seconds=self._timer_remaining_seconds)
            self._timer_running = True
            self._timer_has_started = True
        self._refresh_fullscreen_clock()

    def _reset_countdown(self):
        self._timer_running = False
        self._timer_deadline = None
        spin = getattr(self, "fullscreen_timer_minutes", None)
        self._timer_remaining_seconds = (spin.value() if spin is not None else 25) * 60
        self._timer_has_started = False
        self._refresh_fullscreen_clock()

    def _update_countdown(self):
        if self._timer_running and self._timer_deadline is not None:
            remaining = max(0, int((self._timer_deadline - now_jst()).total_seconds() + 0.999))
            self._timer_remaining_seconds = remaining
            if remaining == 0:
                self._timer_running = False
                self._timer_deadline = None
                try:
                    from PySide6.QtWidgets import QApplication
                    QApplication.beep()
                except RuntimeError:
                    pass

    def _set_fullscreen_blackout(self, enabled):
        self._fullscreen_blackout = bool(enabled)
        window = self._fullscreen_window
        if window is None:
            return
        content = getattr(window, "_study_content", None)
        if content is not None:
            content.setVisible(not self._fullscreen_blackout)
        media_content = getattr(window, "_media_content", None)
        if media_content is not None:
            media_content.setVisible(not self._fullscreen_blackout)
        mode_selector = getattr(window, "_mode_selector", None)
        if mode_selector is not None:
            mode_selector.setVisible(not self._fullscreen_blackout)
        if self._fullscreen_blackout:
            popup = getattr(self, "fullscreen_stamp_popup", None)
            if popup is not None:
                popup.hide()
            window.setStyleSheet("background: #000000;")
        elif self.db.get_setting("app_theme", "dark") == "light":
            window.setStyleSheet("background: #f7f8fa; color: #20252b;")
        else:
            window.setStyleSheet("background: #101318; color: #e9edf2;")
        window.setCursor(Qt.CursorShape.BlankCursor if self._fullscreen_blackout else Qt.CursorShape.ArrowCursor)

    def _toggle_fullscreen_blackout(self):
        self._set_fullscreen_blackout(not self._fullscreen_blackout)

    def _build_fullscreen_clock(self):
        from PySide6.QtWidgets import QFrame

        window = QWidget(self, Qt.WindowType.Window)
        window.setWindowTitle("StudyTracker — デジタル時計")
        is_light = self.db.get_setting("app_theme", "dark") == "light"
        window.setStyleSheet(
            "background: #f7f8fa; color: #20252b;" if is_light
            else "background: #101318; color: #e9edf2;"
        )
        root = QVBoxLayout(window)
        root.setContentsMargins(24, 14, 24, 12)
        root.setSpacing(8)

        content = QWidget(window)
        content.setStyleSheet(
            "background: transparent; color: #20252b;" if is_light
            else "background: transparent; color: #e9edf2;"
        )
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        self.fullscreen_mode = QComboBox()
        self.fullscreen_mode.addItems(["日本標準時", "カレント勉強時間", "合計勉強時間"])
        self.fullscreen_mode.setCurrentText(self.mode.currentText())
        self.fullscreen_mode.currentTextChanged.connect(lambda value: (self.mode.setCurrentText(value), self._refresh_fullscreen_clock()))
        self.fullscreen_mode.setMaximumWidth(200)
        root.addWidget(self.fullscreen_mode, 0, Qt.AlignmentFlag.AlignHCenter)
        window._mode_selector = self.fullscreen_mode

        self.fullscreen_date = QLabel()
        self.fullscreen_date.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fullscreen_date.setStyleSheet(
            "font-size: 20px; color: #707984;" if is_light else "font-size: 20px; color: #929ba8;"
        )
        content_layout.addWidget(self.fullscreen_date)

        self.fullscreen_clock = QLabel()
        self.fullscreen_clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fullscreen_clock.setMinimumHeight(180)
        self.fullscreen_clock.setStyleSheet(
            "font-size: 110px; font-weight: 300; letter-spacing: 2px; color: "
            + ("#20252b;" if is_light else "#f3f5f7;")
        )
        content_layout.addWidget(self.fullscreen_clock, 1)

        self.fullscreen_study_time = QLabel()
        self.fullscreen_study_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fullscreen_study_time.setStyleSheet(
            "font-size: 18px; color: #707984;" if is_light else "font-size: 18px; color: #87919f;"
        )
        content_layout.addWidget(self.fullscreen_study_time)

        timer_frame = QFrame()
        timer_frame.setStyleSheet(
            "QFrame { background: #e8edf2; border-radius: 10px; }" if is_light
            else "QFrame { background: #191e25; border-radius: 10px; }"
        )
        timer_row = QHBoxLayout(timer_frame)
        timer_row.setContentsMargins(12, 8, 12, 8)
        timer_row.addStretch(1)
        timer_row.addWidget(QLabel("タイマー"))
        self.fullscreen_timer_minutes = QSpinBox()
        self.fullscreen_timer_minutes.setRange(1, 999)
        self.fullscreen_timer_minutes.setValue(25)
        self.fullscreen_timer_minutes.setSuffix(" 分")
        self.fullscreen_timer_minutes.setFixedWidth(95)
        timer_row.addWidget(self.fullscreen_timer_minutes)
        self.fullscreen_timer_value = QLabel("25:00")
        self.fullscreen_timer_value.setMinimumWidth(90)
        self.fullscreen_timer_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fullscreen_timer_value.setStyleSheet("font-size: 22px; font-weight: 600;")
        timer_row.addWidget(self.fullscreen_timer_value)
        self.fullscreen_timer_start = QPushButton("開始")
        self.fullscreen_timer_start.clicked.connect(self._toggle_countdown)
        timer_row.addWidget(self.fullscreen_timer_start)
        timer_reset = QPushButton("リセット")
        timer_reset.clicked.connect(self._reset_countdown)
        timer_row.addWidget(timer_reset)
        timer_row.addStretch(1)
        content_layout.addWidget(timer_frame)
        root.addWidget(content, 1)
        window._study_content = content

        media_frame = QFrame()
        media_frame.setStyleSheet(
            "QFrame { background: #e8edf2; border: 1px solid #c4ccd5; border-radius: 12px; }"
            if is_light else
            "QFrame { background: #191e25; border: 1px solid #2c333d; border-radius: 12px; }"
        )
        media_layout = QVBoxLayout(media_frame)
        media_layout.setContentsMargins(16, 10, 16, 10)
        media_layout.setSpacing(6)
        self.fullscreen_media_title = QLabel("Windows メディア")
        self.fullscreen_media_title.setStyleSheet("font-size: 13px; color: #aab3bf;")
        media_layout.addWidget(self.fullscreen_media_title)

        self.fullscreen_media_position = QSlider(Qt.Orientation.Horizontal)
        self.fullscreen_media_position.setRange(0, 1)
        self.fullscreen_media_position.setEnabled(False)
        self.fullscreen_media_position.sliderPressed.connect(
            lambda: setattr(self, "_media_seek_dragging", True)
        )
        self.fullscreen_media_position.sliderReleased.connect(self._seek_fullscreen_media)
        media_layout.addWidget(self.fullscreen_media_position)

        time_row = QHBoxLayout()
        self.fullscreen_media_elapsed = QLabel("00:00")
        self.fullscreen_media_elapsed.setStyleSheet("color: #929ba8;")
        self.fullscreen_media_duration = QLabel("--:--")
        self.fullscreen_media_duration.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.fullscreen_media_duration.setStyleSheet("color: #929ba8;")
        time_row.addWidget(self.fullscreen_media_elapsed)
        time_row.addStretch(1)
        time_row.addWidget(self.fullscreen_media_duration)
        media_layout.addLayout(time_row)

        controls = QHBoxLayout()
        controls.addStretch(1)
        for label, action in [("前の曲", "previous"), ("再生 / 一時停止", "toggle"), ("次の曲", "next")]:
            button = QPushButton(label)
            button.setMinimumHeight(34)
            button.setMinimumWidth(88 if action != "toggle" else 118)
            button.clicked.connect(lambda checked=False, a=action: self._media_control(a))
            controls.addWidget(button)
            if action == "toggle":
                self.fullscreen_playback_button = button
        self.fullscreen_media_status = QLabel(self._media_status_text)
        self.fullscreen_media_status.setMaximumWidth(150)
        self.fullscreen_media_status.setStyleSheet("color: #7f8996; font-size: 11px;")
        controls.addWidget(self.fullscreen_media_status, 1)
        self.fullscreen_stamp_input = QLineEdit()
        self.fullscreen_stamp_input.setPlaceholderText("学習位置を入力して Enter")
        self.fullscreen_stamp_input.setValidator(QIntValidator(0, 999999, self.fullscreen_stamp_input))
        self.fullscreen_stamp_input.setFixedWidth(130)
        self.fullscreen_stamp_input.returnPressed.connect(self._record_fullscreen_stamp)
        controls.addWidget(self.fullscreen_stamp_input)
        stamp_save = QPushButton("記録")
        stamp_save.clicked.connect(self._record_fullscreen_stamp)
        controls.addWidget(stamp_save)
        stamp_history_button = QPushButton("履歴を表示")
        stamp_history_button.clicked.connect(self._toggle_fullscreen_stamp_history)
        self.fullscreen_stamp_history_button = stamp_history_button
        controls.addWidget(stamp_history_button)
        blackout_button = QPushButton("画面を暗転 (B)")
        blackout_button.setMinimumHeight(40)
        blackout_button.clicked.connect(self._toggle_fullscreen_blackout)
        controls.addWidget(blackout_button)
        exit_button = QPushButton("終了 (Esc)")
        exit_button.clicked.connect(self.exit_fullscreen)
        controls.addWidget(exit_button)
        controls.addStretch(1)
        media_layout.addLayout(controls)
        self.fullscreen_stamp_history = QListWidget(media_frame)
        self.fullscreen_stamp_history.setMaximumHeight(120)
        self.fullscreen_stamp_history.hide()
        media_layout.addWidget(self.fullscreen_stamp_history)
        root.addWidget(media_frame, 0)
        window._media_content = media_frame

        escape = QShortcut(QKeySequence("Escape"), window)
        escape.setContext(Qt.ShortcutContext.WindowShortcut)
        escape.activated.connect(self.exit_fullscreen)
        blackout = QShortcut(QKeySequence("B"), window)
        blackout.setContext(Qt.ShortcutContext.WindowShortcut)
        blackout.activated.connect(self._toggle_fullscreen_blackout)
        play_pause = QShortcut(QKeySequence("Space"), window)
        play_pause.setContext(Qt.ShortcutContext.WindowShortcut)
        play_pause.activated.connect(lambda: self._media_control("toggle"))
        window.destroyed.connect(self._fullscreen_window_closed)
        self._fullscreen_window = window
        self._set_fullscreen_blackout(False)
        self._refresh_fullscreen_clock()
        self._render_fullscreen_stamp_history()
        window.showFullScreen()

    def _build_fullscreen_stamp_popup(self, window):
        popup = QDialog(window, Qt.WindowType.Popup)
        popup.setWindowTitle("学習スタンプ")
        popup.setMinimumWidth(360)
        popup_layout = QVBoxLayout(popup)
        popup_layout.addWidget(QLabel("現在の学習単位位置を入力"))
        self.fullscreen_stamp_input = QLineEdit(popup)
        self.fullscreen_stamp_input.setPlaceholderText("例: 120")
        self.fullscreen_stamp_input.setValidator(QIntValidator(0, 999999, self.fullscreen_stamp_input))
        self.fullscreen_stamp_input.returnPressed.connect(self._record_fullscreen_stamp)
        popup_layout.addWidget(self.fullscreen_stamp_input)
        stamp_actions = QHBoxLayout()
        stamp_save = QPushButton("記録", popup)
        stamp_save.clicked.connect(self._record_fullscreen_stamp)
        stamp_actions.addWidget(stamp_save)
        history_button = QPushButton("履歴を表示", popup)
        history_button.clicked.connect(self._toggle_fullscreen_stamp_history)
        stamp_actions.addWidget(history_button)
        popup_layout.addLayout(stamp_actions)
        self.fullscreen_stamp_history = QListWidget(popup)
        self.fullscreen_stamp_history.setMaximumHeight(180)
        self.fullscreen_stamp_history.hide()
        popup_layout.addWidget(self.fullscreen_stamp_history)
        self.fullscreen_stamp_history_button = history_button
        self.fullscreen_stamp_popup = popup
        self._render_fullscreen_stamp_history()

    def _show_fullscreen_stamp_popup(self):
        popup = getattr(self, "fullscreen_stamp_popup", None)
        window = self._fullscreen_window
        if popup is None or window is None:
            return
        if popup.isVisible():
            popup.hide()
            return
        popup.adjustSize()
        popup.move(
            window.geometry().center().x() - popup.width() // 2,
            window.geometry().center().y() - popup.height() // 2,
        )
        popup.show()
        self.fullscreen_stamp_input.setFocus()

    def _toggle_fullscreen_stamp_history(self):
        history = getattr(self, "fullscreen_stamp_history", None)
        if history is None:
            return
        visible = not history.isVisible()
        history.setVisible(visible)
        button = getattr(self, "fullscreen_stamp_history_button", None)
        if button is not None:
            button.setText("履歴を隠す" if visible else "履歴を表示")
        if visible:
            self._render_fullscreen_stamp_history()

    def _record_fullscreen_stamp(self):
        value = self.fullscreen_stamp_input.text().strip()
        if not value:
            self.fullscreen_stamp_input.setFocus()
            return
        self.timestamp_input.setText(value)
        self.record_timestamp()
        self.fullscreen_stamp_input.clear()
        self._render_fullscreen_stamp_history()
        self.fullscreen_stamp_input.setFocus()

    def _render_fullscreen_stamp_history(self):
        history = getattr(self, "fullscreen_stamp_history", None)
        if history is None:
            return
        history.clear()
        timestamp_start = self.current_content_started_at or self.segment_started
        if not self.session_id or timestamp_start is None:
            return
        for row in self.db.timestamps_for_session(self.session_id, timestamp_start, now_jst()):
            at = datetime.fromisoformat(row["at"]).astimezone(JST)
            history.addItem(f"{at.strftime('%H:%M:%S')}    {row['location']}")

    def _fullscreen_window_closed(self, *_args):
        self._fullscreen_window = None
        self._fullscreen_blackout = False
        if hasattr(self, "fullscreen_button"):
            self.fullscreen_button.setText("全画面表示")

    def _seek_fullscreen_media(self):
        self._media_seek_dragging = False
        app_id = self._selected_media_app_id()
        if not app_id:
            return
        selected = next((item for item in self._media_sessions if item.get("app_id") == app_id), None)
        if not selected:
            return
        seek_session_position(app_id, float(self.fullscreen_media_position.value()))

    def _refresh_fullscreen_clock(self):
        if self._fullscreen_window is None:
            return
        now = now_jst()
        current_seconds = self.current_active_accumulated
        if self.segment_started and self.active:
            current_seconds += max(0, (now - self.segment_started).total_seconds())
        if self.current_rows:
            row = self.current_rows[0]
            total_seconds = self.db.active_seconds(subject=row.subject, material=row.material)
            if self.segment_started and self.active:
                total_seconds += max(0, (now - self.segment_started).total_seconds())
        else:
            total_seconds = 0

        self.fullscreen_date.setText(now.strftime("%Y年%m月%d日 (%a)"))
        display_mode = self.fullscreen_mode.currentText() if hasattr(self, "fullscreen_mode") else self.mode.currentText()
        if display_mode == "カレント勉強時間":
            self.fullscreen_clock.setText(fmt_duration(current_seconds))
        elif display_mode == "合計勉強時間":
            self.fullscreen_clock.setText(fmt_duration(total_seconds))
        else:
            self.fullscreen_clock.setText(now.strftime("%H:%M:%S"))
        self.fullscreen_study_time.setText(
            f"Current  {fmt_duration(current_seconds)}    Total  {fmt_duration(total_seconds)}"
        )
        self.fullscreen_study_time.setVisible(display_mode == "日本標準時")
        self._update_countdown()
        self.fullscreen_timer_value.setText(
            "終了" if self._timer_remaining_seconds == 0 and not self._timer_running
            else self._fullscreen_timer_text()
        )
        self.fullscreen_timer_start.setText(
            "一時停止" if self._timer_running else "再開" if self._timer_has_started else "開始"
        )
        selected = next(
            (item for item in self._media_sessions if item.get("app_id") == self._selected_media_app_id()),
            self._media_sessions[0] if self._media_sessions else None,
        )
        if hasattr(self, "fullscreen_playback_button"):
            status = str(selected.get("status", "")).rsplit(".", 1)[-1].lower() if selected else ""
            if status in {"playing", "4"}:
                state_text = "再生中"
                state_style = (
                    "QPushButton { background-color: #16834a; color: #ffffff; "
                    "border: 1px solid #106a3a; border-radius: 5px; font-weight: 700; }"
                )
            elif status in {"paused", "5"}:
                state_text = "一時停止中"
                state_style = (
                    "QPushButton { background-color: #b58a2a; color: #1b1e22; "
                    "border: 1px solid #8e6a1d; border-radius: 5px; font-weight: 700; }"
                )
            elif status in {"stopped", "3"}:
                state_text = "停止中"
                state_style = (
                    "QPushButton { background-color: #586474; color: #ffffff; "
                    "border: 1px solid #414b58; border-radius: 5px; font-weight: 600; }"
                )
            else:
                state_text = "状態不明"
                state_style = (
                    "QPushButton { background-color: #687382; color: #ffffff; "
                    "border: 1px solid #515d6b; border-radius: 5px; font-weight: 600; }"
                )
            self.fullscreen_playback_button.setText("再生 / 一時停止")
            self.fullscreen_playback_button.setStyleSheet(state_style)
            self.fullscreen_playback_button.setToolTip(
                "操作: 再生 / 一時停止\n現在の再生状態: " + state_text
            )
            self.fullscreen_media_status.setText(state_text if selected else self._media_status_text)
        else:
            self.fullscreen_media_status.setText(self._media_status_text)
        if selected:
            title = " — ".join(
                value for value in (selected.get("title", ""), selected.get("artist", "")) if value
            ) or selected.get("app_id", "Windows メディア")
            self.fullscreen_media_title.setText(title)
            duration = max(0, int(selected.get("duration", 0) or 0))
            position = max(0, min(duration, int(selected.get("position", 0) or 0)))
            if not self._media_seek_dragging:
                self.fullscreen_media_position.setRange(0, max(1, duration))
                self.fullscreen_media_position.setValue(position)
            self.fullscreen_media_position.setEnabled(duration > 0 and bool(selected.get("app_id")))
            self.fullscreen_media_elapsed.setText(self._format_media_time(position))
            self.fullscreen_media_duration.setText(self._format_media_time(duration) if duration else "--:--")
        else:
            self.fullscreen_media_title.setText("再生中のメディアなし")
            self.fullscreen_media_position.setRange(0, 1)
            self.fullscreen_media_position.setValue(0)
            self.fullscreen_media_position.setEnabled(False)
            self.fullscreen_media_elapsed.setText("00:00")
            self.fullscreen_media_duration.setText("--:--")

    def exit_fullscreen(self):
        window = self._fullscreen_window
        if window is not None:
            self._fullscreen_window = None
            self._fullscreen_blackout = False
            window.close()
        elif self.isFullScreen():
            self.showNormal()
        if hasattr(self, "fullscreen_button"):
            self.fullscreen_button.setText("全画面表示")

    def toggle_fullscreen(self):
        if self._fullscreen_window is not None:
            self.exit_fullscreen()
        else:
            self._build_fullscreen_clock()
            if hasattr(self, "fullscreen_button"):
                self.fullscreen_button.setText("ウィンドウ表示")

    def refresh_analog_clock(self, force=False):
        if not hasattr(self, "analog_clock_widget"):
            return
        now = now_jst()
        if not force and self._last_analog_refresh is not None:
            if now - self._last_analog_refresh < timedelta(seconds=30):
                self.analog_clock_widget.set_day_segments(
                    self.analog_clock_widget._segments, self.segment_started, self.active
                )
                return
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        segments = self.db.segments_overlapping(day_start, day_start + timedelta(days=1))
        self.analog_clock_widget.set_day_segments(segments, self.segment_started, self.active)
        self._last_analog_refresh = now

    def record_timestamp(self):
        if not self.session_id or not self.segment_started:
            return
        if not self.active:
            QMessageBox.information(self, "タイムスタンプ", "Passive中はタイムスタンプを記録できません。Activeに切り替えてください。")
            return
        location = self.timestamp_input.text().strip()
        if not location:
            return
        row = self.current_rows[0] if self.current_rows else None
        assessment = assess_timestamp(
            location,
            row.scope if row else "",
            [value for _, value in self.timestamp_locations],
        )
        if assessment.warnings:
            message = "\n".join(assessment.warnings)
            message += "\n\nこの位置をタイムスタンプとして記録しますか？"
            answer = QMessageBox.warning(
                self,
                "タイムスタンプの確認",
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.timestamp_input.setFocus()
                return

        now = now_jst()
        unit = row.unit if row else ""
        subject = row.subject if row else ""
        material = row.material if row else ""
        try:
            self.db.add_timestamp(
                self.session_id, self.segment_started, now, location, unit, subject, material
            )
        except Exception as exc:
            logging.getLogger("study_tracker.timestamps").exception("Timestamp save failed")
            self.report_error(f"タイムスタンプを保存できませんでした: {exc}")
            return
        self.timestamp_locations.append((now, location))
        actual_scope = build_actual_scope(unit, row.scope if row else "", [x[1] for x in self.timestamp_locations])
        self.timestamp_status.setText(f"最新: {now.astimezone(JST).strftime('%H:%M:%S')} / {location} → 実施範囲 {actual_scope or '(未判定)'}")
        self.timestamp_input.clear()
        self._render_timestamp_history()
        self.timestamp_input.setFocus()
        self.refresh_analog_clock(force=True)
        if assessment.completes_scope:
            self.end_session(completion_position=location)

    def _render_timestamp_history(self):
        if not hasattr(self, "timestamp_list"):
            return
        self.timestamp_list.clear()
        if not self.session_id or not self.segment_started:
            self.timestamp_status.setText("まだタイムスタンプはありません。")
            return
        timestamp_start = self.current_content_started_at or self.segment_started
        rows = self.db.timestamps_for_session(self.session_id, timestamp_start, now_jst())
        unit = self.current_rows[0].unit if self.current_rows else ""
        locations = [str(r["location"]) for r in rows]
        actual_scope = build_actual_scope(unit, self.current_rows[0].scope if self.current_rows else "", locations)
        if not rows:
            self.timestamp_status.setText("まだタイムスタンプはありません。")
        else:
            latest = rows[-1]
            at = datetime.fromisoformat(latest["at"]).astimezone(JST)
            self.timestamp_status.setText(f"実施範囲: {actual_scope or '(未判定)'} / 最新 {at.strftime('%H:%M:%S')} → {latest['location']}")
        for r in rows:
            at = datetime.fromisoformat(r["at"]).astimezone(JST)
            self.timestamp_list.addItem(f"{at.strftime('%H:%M:%S')}    {r['location']}")
        self._render_fullscreen_stamp_history()

    def current_text(self):
        if not self.current_rows:
            return "未設定"
        text = render(self.current_rows)
        return text

    def tick(self):
        if not self.session_id or not hasattr(self, "clock"):
            return
        now = now_jst()
        current_seconds = self.current_active_accumulated
        if self.segment_started and self.active:
            current_seconds += max(0, (now - self.segment_started).total_seconds())
        if self.current_rows:
            subject = self.current_rows[0].subject
            material = self.current_rows[0].material
            total_seconds = self.db.active_seconds(subject=subject, material=material)
            if self.segment_started and self.active:
                total_seconds += max(0, (now - self.segment_started).total_seconds())
        else:
            total_seconds = 0
        self._current_display_seconds = current_seconds
        self._total_display_seconds = total_seconds
        display_mode = self.mode.currentText()
        if display_mode == "カレント勉強時間":
            clock_text = fmt_duration(current_seconds)
        elif display_mode == "合計勉強時間":
            clock_text = fmt_duration(total_seconds)
        else:
            clock_text = f"{now.strftime('%H:%M:%S')} JST"
        self.clock.setText(clock_text)

        self.current.setText(self.current_text())
        self.refresh_analog_clock()
        self._refresh_fullscreen_clock()

    def update_title(self):
        if self.current_rows:
            r = self.current_rows[0]
            self.setWindowTitle(self.mtc.window_title(r.material, r.position))
        else:
            self.setWindowTitle("Study Tracker V3.5.4")

    # ---- keep awake ----
    def apply_keep_awake(self, enabled):
        if not enabled:
            self.release_keep_awake()
            return
        if platform.system() != "Windows":
            return
        try:
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ES_DISPLAY_REQUIRED = 0x00000002
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )
        except Exception:
            pass

    def release_keep_awake(self):
        if platform.system() != "Windows":
            return
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        except Exception:
            pass

    # ---- History & export ----
    def _history_rows(self):
        return self.db.archive_rows(active_only=True)

    def show_history(self):
        dlg = QMainWindow(self)
        dlg.setWindowTitle("学習記録アーカイブ")
        dlg.resize(1400, 650)

        table = QTableWidget()
        rows = self._history_rows()
        table.setRowCount(len(rows))
        table.setColumnCount(len(COLUMNS))
        table.setHorizontalHeaderLabels(COLUMNS)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        for i, row in enumerate(rows):
            for j, val in enumerate(row.table_values()):
                table.setItem(i, j, QTableWidgetItem(val))

        dlg.setCentralWidget(table)
        dlg.show()
        self._history_window = dlg

    def save_csv(self):
        from .paths import get_path
        export_dir = get_path("export_dir")
        export_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "CSV出力", str(export_dir / "study_archive.csv"), "CSV (*.csv)")
        if path:
            export_csv(self._history_rows(), path)

    def save_xlsx(self):
        from .paths import get_path
        export_dir = get_path("export_dir")
        export_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "XLSX出力", str(export_dir / "study_archive.xlsx"), "Excel (*.xlsx)")
        if path:
            export_xlsx(self._history_rows(), self.db.aliases(), path)


    def load_data_file(self):
        """Import a SQLite backup or append an exported CSV/XLSX without data loss."""
        if self.session_id:
            QMessageBox.warning(
                self, "読み込みできません",
                "学習中はデータを読み込めません。セクションを終了してから実行してください。"
            )
            return

        from .paths import get_path
        initial_dir = get_path("export_dir")
        initial_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "バックアップ / エクスポートを読み込む",
            str(initial_dir),
            "StudyTracker data (*.sqlite3 *.db *.sqlite *.csv *.xlsx);;"
            "SQLite backups (*.sqlite3 *.db *.sqlite);;CSV exports (*.csv);;Excel exports (*.xlsx)",
        )
        if not path:
            return

        source = Path(path).expanduser().resolve()
        database_path = self.db.path.expanduser().resolve()
        backup_dir = Path(
            self.db.get_setting("backup_dir", str(Path.home() / "StudyTrackerBackups"))
        ).expanduser().resolve()

        if source.suffix.lower() in {".sqlite3", ".db", ".sqlite"}:
            if source == database_path:
                QMessageBox.information(self, "読み込み不要", "選択したファイルは現在使用中のDBです。")
                return
            answer = QMessageBox.warning(
                self,
                "バックアップから復元",
                f"次のバックアップの内容に切り替えます。\n{source}\n\n"
                "現在のDBは別名のSQLiteバックアップとして保存してから置き換えます。\n"
                "復元後は、現在のDBにあった記録は保存済みバックアップから参照できます。続行しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

            self.db.close()
            try:
                from .import_export import restore_database_snapshot
                preserved = restore_database_snapshot(source, database_path, backup_dir)
            except Exception as exc:
                from .db import Database
                self.db = Database(database_path)
                logging.getLogger("study_tracker.import").exception("Database backup restore failed")
                self.report_error(f"バックアップを読み込めませんでした: {exc}")
                QMessageBox.critical(self, "読み込み失敗", f"現在のDBは置き換えられていません。\n{exc}")
                return

            from .db import Database
            self.db = Database(database_path)
            self.mtc.config.document_mode = self.db.get_setting("mt_document_mode", "material")
            self.mtc.config.server_url = self.db.get_setting("mt_server_url", "")
            self.build_home()
            QMessageBox.information(
                self, "復元完了",
                f"バックアップを読み込みました。\n{source}\n\n"
                f"読み込み前のDBは別名で保管しました。\n{preserved}"
            )
            return

        if source.suffix.lower() not in {".csv", ".xlsx"}:
            QMessageBox.warning(self, "形式が未対応です", "SQLite、CSV、XLSXファイルを指定してください。")
            return

        try:
            from .import_export import import_export_file, preserve_database
            preserved = preserve_database(database_path, backup_dir)
            summary = import_export_file(self.db, source)
        except Exception as exc:
            logging.getLogger("study_tracker.import").exception("Export import failed")
            self.report_error(f"エクスポートを読み込めませんでした: {exc}")
            QMessageBox.critical(
                self, "読み込み失敗",
                f"既存データは維持されています。\n{exc}"
            )
            return

        self.build_home()
        details = (
            f"読み込み件数: {summary.imported}\n"
            f"読み飛ばし: {summary.skipped}\n"
            f"新規エイリアス: {summary.aliases_added}\n\n"
            f"読み込み前のDBバックアップ: {preserved}"
        )
        if summary.warnings:
            details += "\n\n注意:\n" + "\n".join(summary.warnings[:8])
            if len(summary.warnings) > 8:
                details += f"\nほか {len(summary.warnings) - 8} 件"
            QMessageBox.warning(self, "エクスポート読み込み結果", details)
        else:
            QMessageBox.information(self, "エクスポート読み込み完了", details)

class EditorWindow(QDialog):
    def __init__(self, main: MainWindow, waiting=False):
        super().__init__(main)
        self.main = main
        self.waiting = waiting
        self.rows: list[StudyRow] = []
        self.synced = False
        self._loading = False
        self._last_changed_view = "table"

        self.setWindowTitle("カレント学習内容の設定")
        self.resize(1450, 800)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)

        # Left: text
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("テキスト形式"))
        self.text = QTextEdit()
        self.text.setPlaceholderText(
            "yyyy.mm.dd HH:MM:SS.SS ~ HH:MM:SS.SS\n"
            "-----\n"
            "[物理]\n"
            "リードα<波動>,p(21-42,45)\n"
            "<熱力学>,section(2-4)\n"
            "/*\n備考\n*/"
        )
        self.text.textChanged.connect(self.mark_text_dirty)
        ll.addWidget(self.text)

        self.sync_t = QPushButton("同期 → テーブル")
        self.sync_t.clicked.connect(self.sync_text)
        ll.addWidget(self.sync_t)

        # Right tabs
        right = QTabWidget()

        table_page = QWidget()
        tl = QVBoxLayout(table_page)
        self.status = QLabel("未同期")
        tl.addWidget(self.status)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed |
            QAbstractItemView.EditTrigger.SelectedClicked
        )
        if self.waiting:
            for col in range(6):
                self.table.setColumnHidden(col, True)
        self.table.itemChanged.connect(self.mark_table_dirty)
        tl.addWidget(self.table)

        table_controls = QHBoxLayout()
        add_row = QPushButton("行追加")
        add_row.clicked.connect(self.add_table_row)
        del_row = QPushButton("行削除")
        del_row.clicked.connect(self.delete_table_row)
        sync_back = QPushButton("同期 ← テーブル")
        sync_back.clicked.connect(self.sync_table)
        table_controls.addWidget(add_row)
        table_controls.addWidget(del_row)
        table_controls.addWidget(sync_back)
        tl.addLayout(table_controls)
        right.addTab(table_page, "テーブル")

        preset_page = QWidget()
        pl = QVBoxLayout(preset_page)
        self.pc = QComboBox()
        self.ps = QComboBox()
        self.pm = QComboBox()
        self.pp = QComboBox()
        self.pa = QComboBox()

        self.pc.currentTextChanged.connect(lambda _: self.apply_preset_to_table(4))
        self.ps.currentTextChanged.connect(lambda _: self.apply_preset_to_table(5))
        self.pm.currentTextChanged.connect(lambda _: self.on_material_changed())
        self.pp.currentTextChanged.connect(lambda _: self.apply_preset_to_table(7))
        self.pa.currentTextChanged.connect(lambda _: self.apply_preset_to_table(8))

        form = QFormLayout()
        form.addRow("学習区分", self.pc)
        form.addRow("科目", self.ps)
        form.addRow("教材", self.pm)
        form.addRow("学習位置（recent候補）", self.pp)
        form.addRow("学習単位（エイリアス）", self.pa)
        pl.addLayout(form)

        self.preset_to_text_button = QPushButton("プリセット → テキストを同期")
        self.preset_to_text_button.clicked.connect(self.sync_presets_to_text)
        pl.addWidget(self.preset_to_text_button)

        info = QLabel(
            "プリセット選択はテーブルへ反映されます。"
            "「プリセット → テキストを同期」で、開始時刻・学習区分・科目・教材・"
            "学習位置・学習単位をテキストへ反映します。"
            "学習範囲と備考は現在のテーブル値を保持します。"
        )
        info.setWordWrap(True)
        pl.addWidget(info)
        right.addTab(preset_page, "プリセット")

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([520, 900])

        root = QVBoxLayout(self)
        root.addWidget(split)

        bottom = QHBoxLayout()
        bottom.addStretch()

        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.reject)
        bottom.addWidget(self.close_button)

        self.quick_register_button = QPushButton("未登録プリセットをクイック登録")
        self.quick_register_button.setEnabled(False)
        self.quick_register_button.clicked.connect(self.quick_register_missing)
        bottom.addWidget(self.quick_register_button)

        self.preserve_button = QPushButton("下位を保持して再設定")
        self.preserve_button.setEnabled(False)
        self.preserve_button.clicked.connect(lambda: self.apply(True))
        bottom.addWidget(self.preserve_button)

        self.sync_apply_button = QPushButton("同期して適用")
        self.sync_apply_button.setToolTip("テキストまたはテーブルの最新の編集内容を同期し、適用します。")
        self.sync_apply_button.clicked.connect(self.sync_and_apply)
        bottom.addWidget(self.sync_apply_button)

        self.apply_button = QPushButton("適用")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(lambda: self.apply(False))
        bottom.addWidget(self.apply_button)

        root.addLayout(bottom)

        self.setModal(True)
        self.load_initial()
        self.load_presets()
        self.update_apply_state()

    def load_initial(self):
        if self.main.current_rows:
            self._loading = True
            self.text.setPlainText(render(self.main.current_rows))
            self.set_table(self.main.current_rows)
            self._loading = False
            self.synced = True
        else:
            # 起動/開始時のホーム選択を、カレント学習内容の初期値として自動入力。
            n = now_jst()
            category = self.main.home_category.currentText().strip()
            subject = self.main.home_subject.currentText().strip()
            material = self.main.home_material.currentText().strip()

            row = StudyRow(
                date=n.strftime("%Y.%m.%d"),
                start=n.strftime("%H:%M:%S.%f")[:-4],
                end="--:--:--",
                timezone="Asia/Tokyo",
                category=category,
                subject=subject,
                material=material,
                position="",
                unit="",
                scope="",
                notes=[],
            )
            self._loading = True
            self.set_table([row])
            self._loading = False

            # 開始時刻・区分・科目・教材を自動入力したテキストを生成。
            self._sync_table_to_text_without_validation()
            self.synced = False

    def load_presets(self):
        self._loading = True
        self.pc.clear()
        self.ps.clear()
        self.pa.clear()

        self.pc.addItems(self.main.db.preset_titles("category"))
        self.ps.addItems(self.main.db.preset_titles("subject"))
        self.pa.addItems([a["title"] for a in self.main.db.aliases()])

        category = self.current_value(4)
        subject = self.current_value(5)
        material = self.current_value(6)
        position = self.current_value(7)
        unit = self.current_value(8)

        self.pc.setCurrentText(category)
        self.ps.setCurrentText(subject)

        self.refresh_materials(subject)
        self.pm.setCurrentText(material)

        self.refresh_positions(material)
        self.pp.setCurrentText(position)

        self.pa.setCurrentText(unit)
        self._loading = False

    def refresh_materials(self, subject):
        self.pm.clear()
        self.pm.addItems(self.main.db.preset_titles("material", subject))

    def refresh_positions(self, material):
        self.pp.clear()
        self.pp.addItems([r["position"] for r in self.main.db.recent_positions(material)])

    def on_material_changed(self):
        if self._loading:
            return
        self.refresh_positions(self.pm.currentText().strip())
        self.apply_preset_to_table(6)

    def current_value(self, col):
        item = self.table.item(0, col)
        return item.text().strip() if item else ""

    def set_table(self, rows):
        self._loading = True
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            vals = row.table_values()
            for j, value in enumerate(vals):
                self.table.setItem(i, j, QTableWidgetItem(value))
        self._loading = False

    def get_table_rows(self):
        rows = []
        for i in range(self.table.rowCount()):
            values = [
                (self.table.item(i, j).text() if self.table.item(i, j) else "")
                for j in range(len(COLUMNS))
            ]
            branch = {j for j, v in enumerate(values[:10]) if v.strip().lower() == "branch"}

            # Resolve branch cells from the previous logical row.
            if rows:
                prev = rows[-1]
                actual = values[:]
                for j in branch:
                    if j == 0:
                        actual[j] = prev.date
                    elif j == 1:
                        actual[j] = prev.start
                    elif j == 2:
                        actual[j] = prev.end
                    elif j == 3:
                        actual[j] = prev.timezone
                    elif j == 4:
                        actual[j] = prev.category
                    elif j == 5:
                        actual[j] = prev.subject
                    elif j == 6:
                        actual[j] = prev.material
                    elif j == 7:
                        actual[j] = prev.position
                    elif j == 8:
                        actual[j] = prev.unit
                    elif j == 9:
                        actual[j] = prev.scope
                values = actual

            rows.append(StudyRow(
                date=values[0], start=values[1], end=values[2],
                timezone=values[3], category=values[4], subject=values[5],
                material=values[6], position=values[7], unit=values[8],
                scope=values[9], notes=[x for x in values[10].splitlines() if x.strip()],
                branch_fields=branch,
            ))
        return rows

    def add_table_row(self):
        self.table.insertRow(self.table.rowCount())
        self.mark_table_dirty()

    def delete_table_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
            self.mark_table_dirty()

    def mark_text_dirty(self):
        if self._loading:
            return
        self._last_changed_view = "text"
        self.synced = False
        self.update_apply_state()

    def mark_table_dirty(self, *_):
        if self._loading:
            return
        self._last_changed_view = "table"
        self.synced = False
        self.update_apply_state()

    def _sync_table_to_text_without_validation(self):
        rows = self.get_table_rows()
        if not rows:
            return
        self._loading = True
        try:
            # render() is also used when fields are incomplete; this keeps the text
            # representation aligned with the current table while allowing the
            # user to fill required fields in either view.
            self.text.setPlainText(render(rows))
        finally:
            self._loading = False

    def sync_text(self):
        try:
            rows = parse(self.text.toPlainText())
        except ValueError as exc:
            self.status.setText(f"エラー: {exc}")
            self.main.report_error(f"テキストの同期に失敗しました: {exc}")
            self.update_apply_state()
            return

        selected_category = self.pc.currentText().strip()
        if selected_category:
            for row in rows:
                if not row.category:
                    row.category = selected_category

        self._loading = True
        self.set_table(rows)
        self._loading = False

        self.synced = True
        self.rows = rows
        self.refresh_preset_selection(rows[0])
        self.show_partial_validation(rows)

    def sync_table(self):
        rows = self.get_table_rows()
        if not rows:
            self.status.setText("エラー: テーブルが空です。")
            return

        self._loading = True
        self.text.setPlainText(render(rows))
        self._loading = False

        self.synced = True
        self.rows = rows
        self.show_partial_validation(rows)

    def show_partial_validation(self, rows):
        validation = validate(self.main.db, rows)
        if not validation.errors:
            self.main.clear_error()

        if validation.errors:
            self.status.setText(
                "同期済み（構造エラー）: "
                + " / ".join(validation.errors[:3])
            )
            self.main.report_error(
                "学習内容の検証エラー: " + " / ".join(validation.errors[:3])
            )
        elif validation.missing_presets:
            self.status.setText(
                "同期済み（未登録プリセット）: "
                + ", ".join(item[2] for item in validation.missing_presets)
            )
        else:
            missing_apply = []
            for field, label in (
                ("category", "学習区分"),
                ("subject", "科目"),
                ("material", "教材"),
                ("position", "学習位置"),
                ("unit", "学習単位"),
                ("scope", "学習範囲"),
            ):
                if any(not getattr(row, field).strip() for row in rows):
                    missing_apply.append(label)

            if missing_apply:
                self.status.setText(
                    "同期済み。未入力: " + ", ".join(missing_apply)
                )
            else:
                self.status.setText("同期済み・適用可能")

        self.update_apply_state()

    def sync_and_apply(self):
        """Synchronize whichever editor view changed most recently, then apply it."""
        if self._last_changed_view == "text":
            try:
                rows = parse(self.text.toPlainText())
            except ValueError as exc:
                self.status.setText(f"エラー: {exc}")
                self.main.report_error(f"テキストの同期に失敗しました: {exc}")
                return
            selected_category = self.pc.currentText().strip()
            if selected_category:
                for row in rows:
                    if not row.category:
                        row.category = selected_category
            if not rows:
                self.status.setText("エラー: テキストから学習内容を読み取れませんでした。")
                return
            self._loading = True
            self.set_table(rows)
            self.text.setPlainText(render(rows))
            self._loading = False
        else:
            rows = self.get_table_rows()
            if not rows:
                QMessageBox.warning(self, "同期できません", "テーブルに学習内容を1行以上入力してください。")
                return
            self._loading = True
            self.text.setPlainText(render(rows))
            self._loading = False

        self.rows = rows
        self.synced = True
        self.refresh_preset_selection(rows[0])
        self.show_partial_validation(rows)
        validation = validate_for_apply(self.main.db, rows)
        if not validation.ok:
            if validation.missing_presets:
                names = ", ".join(dict.fromkeys(item[2] for item in validation.missing_presets))
                QMessageBox.warning(
                    self, "未登録プリセットがあります",
                    f"同期は完了しましたが、次の項目を登録すると適用できます。\n{names}\n\n"
                    "「未登録プリセットをクイック登録」から登録してください。"
                )
            elif validation.errors:
                QMessageBox.warning(
                    self, "適用できません",
                    "同期は完了しましたが、入力内容の確認が必要です。\n"
                    + "\n".join(validation.errors[:8])
                )
            return
        self.apply(False)

    def quick_register_missing(self):
        rows = self.get_table_rows()
        validation = validate_for_apply(self.main.db, rows)
        if not validation.missing_presets:
            QMessageBox.information(self, "クイック登録", "未登録プリセットはありません。")
            self.update_apply_state()
            return

        dlg = QuickRegisterDialog(
            self.main.db,
            validation.missing_presets,
            validation.similar,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_presets()
            self.synced = True
            self.show_partial_validation(self.get_table_rows())

    def refresh_preset_selection(self, first):
        self._loading = True
        self.pc.setCurrentText(first.category)
        self.ps.setCurrentText(first.subject)
        self.refresh_materials(first.subject)
        self.pm.setCurrentText(first.material)
        self.refresh_positions(first.material)
        self.pp.setCurrentText(first.position)
        self.pa.setCurrentText(first.unit)
        self._loading = False

    def sync_presets_to_text(self):
        if self.table.rowCount() == 0:
            # プリセットのみで最初の1行を作る。
            n = now_jst()
            row = StudyRow(
                date=n.strftime("%Y.%m.%d"),
                start=n.strftime("%H:%M:%S.%f")[:-4],
                end="--:--:--",
                timezone="Asia/Tokyo",
                category=self.pc.currentText().strip(),
                subject=self.ps.currentText().strip(),
                material=self.pm.currentText().strip(),
                position=self.pp.currentText().strip(),
                unit=self.pa.currentText().strip(),
                scope="",
                notes=[],
            )
            self._loading = True
            self.set_table([row])
            self._loading = False
        else:
            # 1行目へプリセット値を適用し、下位の既存値は保持。
            values = {
                4: self.pc.currentText().strip(),
                5: self.ps.currentText().strip(),
                6: self.pm.currentText().strip(),
                7: self.pp.currentText().strip(),
                8: self.pa.currentText().strip(),
            }
            self._loading = True
            for col, value in values.items():
                if value:
                    item = self.table.item(0, col)
                    if item is None:
                        item = QTableWidgetItem()
                        self.table.setItem(0, col, item)
                    item.setText(value)
            self._loading = False

        self._sync_table_to_text_without_validation()
        self.synced = False
        self.status.setText("プリセットをテキストへ同期しました。テーブルとの同期確定後に適用できます。")
        self.update_apply_state()

    def apply_preset_to_table(self, col):
        if self._loading or self.table.rowCount() == 0:
            return

        value = {
            4: self.pc.currentText().strip(),
            5: self.ps.currentText().strip(),
            6: self.pm.currentText().strip(),
            7: self.pp.currentText().strip(),
            8: self.pa.currentText().strip(),
        }.get(col, "")

        if col == 5:
            self.refresh_materials(value)
        elif col == 6:
            self.refresh_positions(value)

        # プリセットタブからの単項目変更はテーブルに反映。
        if value:
            item = self.table.item(0, col)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(0, col, item)
            item.setText(value)

        self.synced = False
        self.update_apply_state()

    def update_apply_state(self):
        rows = self.get_table_rows() if self.table.rowCount() else []
        v = validate_for_apply(self.main.db, rows)
        enabled = self.synced and v.ok
        self.apply_button.setEnabled(enabled)
        self.preserve_button.setEnabled(enabled and self.waiting)
        if hasattr(self, "quick_register_button"):
            self.quick_register_button.setEnabled(self.synced and bool(v.missing_presets))
        if self.synced and v.errors:
            self.status.setText("適用不可: " + " / ".join(v.errors[:2]))

    def _reset_lower_fields(self, old_rows, rows):
        if not self.waiting or not old_rows or not rows:
            return rows
        old = old_rows[0]
        new = rows[0]
        changed = {
            "material": old.material != new.material,
            "position": old.position != new.position,
            "unit": old.unit != new.unit,
        }
        for r in rows:
            if changed["material"]:
                r.position = r.unit = r.scope = ""
                r.notes = []
            elif changed["position"]:
                r.unit = r.scope = ""
                r.notes = []
            elif changed["unit"]:
                r.scope = ""
                r.notes = []
        return rows

    def apply(self, preserve_lower=False):
        rows = self.get_table_rows()
        v = validate_for_apply(self.main.db, rows)
        if not self.synced or not v.ok:
            self.show_partial_validation(rows)
            return

        # Ensure text reflects the table exactly at the moment of application.
        self._loading = True
        self.text.setPlainText(render(rows))
        self._loading = False
        if not preserve_lower and self.waiting:
            rows = self._reset_lower_fields(self.main.current_rows, rows)
            self._loading = True
            self.set_table(rows)
            self.text.setPlainText(render(rows))
            self._loading = False
            v = validate(self.main.db, rows)
            if not v.ok:
                self.show_partial_validation(rows)
                return

        self.main.apply_rows(rows)
        self.accept()
