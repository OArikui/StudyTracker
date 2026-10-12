from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QMessageBox, QLabel, QTextEdit, QFormLayout,
    QComboBox, QLineEdit, QDialogButtonBox, QDateEdit, QTableWidget,
    QTableWidgetItem, QCheckBox, QFileDialog, QWidget, QScrollArea, QGroupBox, QSpinBox
)
from .models import COLUMNS


def _report_main_window_error(widget, message):
    current = widget
    while current is not None:
        reporter = getattr(current, "report_error", None)
        if callable(reporter):
            reporter(message)
            return
        current = current.parent() if hasattr(current, "parent") else None


def _clear_main_window_error(widget):
    current = widget
    while current is not None:
        clearer = getattr(current, "clear_error", None)
        if callable(clearer):
            clearer()
            return
        current = current.parent() if hasattr(current, "parent") else None


class PresetEntryDialog(QDialog):
    """Keep entered preset data visible until the database save succeeds."""

    def __init__(
        self, *, title: str, docstring: str, on_save, parent=None,
        window_title="プリセット登録", require_docstring=False,
    ):
        super().__init__(parent)
        self.on_save = on_save
        self.require_docstring = require_docstring
        self.setWindowTitle(window_title)
        self.resize(560, 420)

        root = QVBoxLayout(self)
        form = QFormLayout()
        self.title_input = QLineEdit(title)
        self.title_input.setPlaceholderText("必須")
        form.addRow("タイトル *", self.title_input)
        self.doc_input = QTextEdit()
        self.doc_input.setPlainText(docstring)
        self.doc_input.setPlaceholderText(
            "必須：学習単位エイリアスの説明" if require_docstring
            else "必要に応じて説明を入力"
        )
        form.addRow("Docstring *" if require_docstring else "Docstring（任意）", self.doc_input)
        root.addLayout(form)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #b42318; font-weight: 600;")
        self.error_label.hide()
        root.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("登録・保存")
        buttons.accepted.connect(self._attempt_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._save_shortcuts = []
        for sequence in ("Ctrl+Return", "Ctrl+Enter"):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(self._attempt_save)
            self._save_shortcuts.append(shortcut)

    def _attempt_save(self):
        title = self.title_input.text().strip()
        docstring = self.doc_input.toPlainText().strip()
        if not title:
            self.show_error("タイトルは必須です。")
            self.title_input.setFocus()
            return
        if self.require_docstring and not docstring:
            self.show_error("Docstringは必須です。入力内容は保持されています。")
            self.doc_input.setFocus()
            return
        try:
            self.on_save(title, docstring)
        except Exception as exc:
            logging.getLogger("study_tracker.presets").exception("Preset save failed")
            self.show_error(f"保存できませんでした: {exc}\n入力を修正して、もう一度お試しください。")
            return
        _clear_main_window_error(self)
        self.accept()

    def show_error(self, message):
        self.error_label.setText(message)
        self.error_label.show()
        _report_main_window_error(self, message)


class PresetManagerDialog(QDialog):
    """
    Preset editor.

    For dependent presets, the left sidebar shows sibling parent presets.
    Current V2.x has material -> subject as the dependent relationship.
    """

    PARENT_KIND = {
        "material": "subject",
    }

    def __init__(self, db, kind, parent_name="", alias_mode=False, parent=None):
        super().__init__(parent)
        self.db = db
        self.kind = kind
        self.parent_name = parent_name
        self.alias_mode = alias_mode
        self.parent_kind = self.PARENT_KIND.get(kind) if not alias_mode else None

        self.setWindowTitle("プリセット編集")
        self.resize(980 if self.parent_kind else 720, 560)

        root = QVBoxLayout(self)

        if alias_mode:
            root.addWidget(QLabel(
                "学習単位エイリアスはDocstring必須。"
                "タイトルとDocstringを別々に編集できます。"
            ))
            self._build_alias_view(root)
        elif self.parent_kind:
            self._build_dependent_view(root)
        else:
            root.addWidget(QLabel(
                f"項目: {kind} / 親: {parent_name or 'なし'}"
            ))
            self._build_item_view(root)

        self.reload()

    # ---------- layout ----------
    def _build_alias_view(self, root):
        self.list = QListWidget()
        root.addWidget(self.list)
        self._build_action_row(root)

    def _build_item_view(self, root):
        self.list = QListWidget()
        root.addWidget(self.list)
        self._build_action_row(root)

    def _build_dependent_view(self, root):
        split = QHBoxLayout()

        left_box = QVBoxLayout()
        left_box.addWidget(QLabel(f"親の一覧（{self.parent_kind}）"))
        self.parent_list = QListWidget()
        self.parent_list.currentItemChanged.connect(self._parent_changed)
        left_box.addWidget(self.parent_list)

        parent_buttons = QHBoxLayout()
        self.parent_edit_button = QPushButton("親を編集")
        self.parent_edit_button.clicked.connect(self._edit_parent)
        parent_buttons.addWidget(self.parent_edit_button)
        left_box.addLayout(parent_buttons)

        left_widget = QWidget()
        left_widget.setLayout(left_box)

        right_box = QVBoxLayout()
        self.child_header = QLabel()
        self.child_header.setStyleSheet("font-weight: bold;")
        right_box.addWidget(self.child_header)

        self.list = QListWidget()
        right_box.addWidget(self.list)
        self._build_action_row(right_box)

        right_widget = QWidget()
        right_widget.setLayout(right_box)

        split.addWidget(left_widget, 1)
        split.addWidget(right_widget, 2)

        container = QWidget()
        container.setLayout(split)
        root.addWidget(container)

    def _build_action_row(self, parent_layout):
        row = QHBoxLayout()
        for text, fn in [
            ("追加", self.add),
            ("編集", self.edit),
            ("上へ", lambda: self.move(-1)),
            ("下へ", lambda: self.move(1)),
            ("削除", self.delete),
        ]:
            button = QPushButton(text)
            button.clicked.connect(fn)
            row.addWidget(button)
        parent_layout.addLayout(row)

    # ---------- data ----------
    def _rows(self):
        if self.alias_mode:
            return self.db.aliases()
        return self.db.presets(self.kind, self.parent_name)

    def reload(self):
        if self.parent_kind:
            self._reload_parents()
            self._reload_children()
        else:
            self._reload_children()

    def _reload_parents(self):
        self.parent_list.blockSignals(True)
        self.parent_list.clear()

        parents = self.db.presets(self.parent_kind)
        selected_row = None
        for row in parents:
            item = QListWidgetItem(f'{row["title"]} — {row["docstring"]}')
            item.setData(Qt.ItemDataRole.UserRole, row["title"])
            self.parent_list.addItem(item)
            if row["title"] == self.parent_name:
                selected_row = item

        if selected_row is not None:
            self.parent_list.setCurrentItem(selected_row)
        elif self.parent_list.count() > 0 and not self.parent_name:
            self.parent_list.setCurrentRow(0)
            self.parent_name = self.parent_list.currentItem().data(Qt.ItemDataRole.UserRole)

        self.parent_list.blockSignals(False)

    def _reload_children(self):
        self.list.clear()
        if self.parent_kind:
            self.child_header.setText(
                f'{self.kind}: {self.parent_name or "親未選択"}'
            )

        for row in self._rows():
            item = QListWidgetItem(f'{row["title"]} — {row["docstring"]}')
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            self.list.addItem(item)

    def _parent_changed(self, current, previous):
        if current is None:
            return
        self.parent_name = current.data(Qt.ItemDataRole.UserRole)
        self._reload_children()

    def _edit_parent(self):
        if not self.parent_kind:
            return
        PresetManagerDialog(
            self.db,
            self.parent_kind,
            parent=self.parent(),
        ).exec()
        self.reload()

    # ---------- CRUD ----------
    def add(self):
        if self.parent_kind and not self.parent_name:
            QMessageBox.warning(
                self,
                "親が必要です",
                f"{self.kind}を追加するには、先に{self.parent_kind}を選択してください。",
            )
            return

        def save(title, doc):
            if self.alias_mode:
                self.db.add_alias(title, doc)
            else:
                self.db.add_preset(self.kind, title, doc, self.parent_name)

        dlg = PresetEntryDialog(
            title="", docstring="", on_save=save,
            require_docstring=self.alias_mode,
            window_title="学習単位エイリアス追加" if self.alias_mode else "プリセット追加",
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def edit(self):
        item = self.list.currentItem()
        if not item:
            return

        pid = item.data(Qt.ItemDataRole.UserRole)
        row = next((r for r in self._rows() if r["id"] == pid), None)
        if row is None:
            return

        def save(title, doc):
            if self.alias_mode:
                self.db.edit_alias(pid, title, doc)
            else:
                self.db.edit_preset(pid, title, doc)

        dlg = PresetEntryDialog(
            title=row["title"], docstring=row["docstring"], on_save=save,
            require_docstring=self.alias_mode,
            window_title="学習単位エイリアス編集" if self.alias_mode else "プリセット編集",
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def delete(self):
        item = self.list.currentItem()
        if not item:
            return

        if QMessageBox.question(
            self,
            "確認",
            "選択したプリセットを削除しますか？",
        ) != QMessageBox.StandardButton.Yes:
            return

        pid = item.data(Qt.ItemDataRole.UserRole)

        try:
            if self.alias_mode:
                self.db.delete_alias(pid)
            else:
                self.db.delete_preset(pid)
        except Exception as exc:
            QMessageBox.warning(self, "削除失敗", str(exc))
            logging.getLogger("study_tracker.presets").exception("Preset deletion failed")
            _report_main_window_error(self, f"プリセットを削除できませんでした: {exc}")
            return

        self.reload()

    def move(self, delta):
        item = self.list.currentItem()
        if item and not self.alias_mode:
            self.db.move_preset(
                item.data(Qt.ItemDataRole.UserRole),
                delta,
            )
            self.reload()



class QuickRegisterDialog(QDialog):
    """
    Quick registration dialog.

    Unit aliases are special: registration is blocked until a non-empty
    Docstring has been entered for every selected alias.
    """

    def __init__(self, db, missing, similar, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("未登録プリセットのクイック登録")
        self.resize(760, 560)

        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "登録対象を選択してください。"
            "学習単位エイリアスを登録する場合はDocstringが必須です。"
        ))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        self.entries = []

        for kind, parent_name, value in missing:
            group = QGroupBox(
                f"{kind}: {value}"
                + (f"  / 親: {parent_name}" if parent_name else "")
            )
            group_layout = QVBoxLayout(group)

            enabled = QCheckBox("登録する")
            enabled.setChecked(True)
            group_layout.addWidget(enabled)

            if kind == "unit":
                doc = QTextEdit()
                doc.setPlaceholderText(
                    "Docstringを入力してください（必須）"
                )
                doc.setMinimumHeight(70)
                group_layout.addWidget(QLabel("Docstring *"))
                group_layout.addWidget(doc)
            else:
                doc = None

            group_layout.addWidget(
                QLabel("現在の値をプリセットとして登録します。")
            )
            content_layout.addWidget(group)

            self.entries.append({
                "kind": kind,
                "parent": parent_name,
                "value": value,
                "enabled": enabled,
                "doc": doc,
                "group": group,
            })

        if similar:
            lines = ["類似候補:"]
            for kind, value, candidate in similar:
                lines.append(f"  {kind}: {value} → {candidate}")
            content_layout.addWidget(QLabel("\n".join(lines)))

        content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("登録")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._register_shortcuts = []
        for sequence in ("Ctrl+Return", "Ctrl+Enter"):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(self.accept)
            self._register_shortcuts.append(shortcut)

    def accept(self):
        selected_aliases = [
            entry
            for entry in self.entries
            if entry["enabled"].isChecked() and entry["kind"] == "unit"
        ]

        invalid_aliases = [
            entry
            for entry in selected_aliases
            if not entry["doc"].toPlainText().strip()
        ]

        if invalid_aliases:
            _report_main_window_error(
                self, "学習単位エイリアスのDocstringは必須です。入力内容を確認してください。"
            )
            QMessageBox.warning(
                self,
                "Docstringが必要です",
                "選択した学習単位エイリアスには、すべてDocstringを入力してください。",
            )
            invalid_aliases[0]["doc"].setFocus()
            return

        failed = []

        for entry in self.entries:
            if not entry["enabled"].isChecked():
                continue

            try:
                kind = entry["kind"]
                value = entry["value"]
                parent_name = entry["parent"]

                if kind == "unit":
                    self.db.add_alias(
                        value,
                        entry["doc"].toPlainText().strip(),
                    )
                else:
                    self.db.add_preset(
                        kind,
                        value,
                        "",
                        parent_name,
                    )
                entry["enabled"].setChecked(False)
            except Exception as exc:
                logging.getLogger("study_tracker.presets").exception(
                    "Quick-register failed for %s: %s", entry["kind"], entry["value"]
                )
                failed.append(
                    f'{entry["kind"]}: {entry["value"]} ({exc})'
                )

        if failed:
            _report_main_window_error(
                self, "一部のプリセットを登録できませんでした。入力欄のエラーを確認してください。"
            )
            QMessageBox.warning(
                self,
                "一部登録できませんでした",
                "\n".join(failed) + "\n失敗した項目は入力内容を保持しています。修正して再度登録してください。",
            )
            return

        _clear_main_window_error(self)
        super().accept()


class ManicTimeSettingsDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("ManicTime連携設定")
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.mode = QComboBox()
        self.mode.addItem("教材のみ", "material")
        self.mode.addItem("教材 + 学習位置", "material_position")
        current = db.get_setting("mt_document_mode", "material")
        i = max(0, self.mode.findData(current))
        self.mode.setCurrentIndex(i)

        self.url = QLineEdit(db.get_setting("mt_server_url", ""))
        form.addRow("MTCドキュメント表示", self.mode)
        form.addRow("ManicTime Server URL（任意）", self.url)
        root.addLayout(form)
        root.addWidget(QLabel(
            "Windowsクライアントでは、現在のアプリケーションとウィンドウタイトルが追跡されます。\n"
            "本ソフトは偽のキーボード/マウス入力を生成しません。"
        ))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def accept(self):
        self.db.set_setting("mt_document_mode", self.mode.currentData())
        self.db.set_setting("mt_server_url", self.url.text().strip())
        super().accept()


class StatisticsDialog(QDialog):
    def __init__(self, db, current_subject="", current_material="", parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("学習時間集計")
        self.resize(620, 420)
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.key = QComboBox()
        self.key.addItems(["科目", "教材"])
        self.key.currentIndexChanged.connect(self.refresh_value_choices)

        self.value = QComboBox()
        self.value.setEditable(True)

        self.period = QComboBox()
        self.period.addItems(["day", "week", "month", "all", "custom"])
        self.period.currentIndexChanged.connect(self.refresh_custom)

        self.start = QDateEdit()
        self.start.setCalendarPopup(True)
        self.end = QDateEdit()
        self.end.setCalendarPopup(True)

        form.addRow("集計単位", self.key)
        form.addRow("対象", self.value)
        form.addRow("期間", self.period)
        form.addRow("開始日", self.start)
        form.addRow("終了日", self.end)
        root.addLayout(form)

        self.result = QLabel()
        self.result.setStyleSheet("font-size: 26px; font-weight: bold;")
        root.addWidget(self.result)
        self.refresh_value_choices()
        self.refresh_custom()
        self.calculate = QPushButton("集計")
        self.calculate.clicked.connect(self.calc)
        root.addWidget(self.calculate)
        self.calc()

    def refresh_value_choices(self):
        self.value.clear()
        vals = self.db.active_seconds
        rows = self.db.segments(active_only=True)
        seen = []
        field = "subject" if self.key.currentIndex() == 0 else "material"
        for r in rows:
            d = __import__("json").loads(r["row_json"])
            if d[field] not in seen:
                seen.append(d[field])
        self.value.addItems(seen)

    def refresh_custom(self):
        custom = self.period.currentText() == "custom"
        self.start.setEnabled(custom)
        self.end.setEnabled(custom)

    def calc(self):
        now = datetime.now().astimezone()
        p = self.period.currentText()
        start = end = None
        if p == "day":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif p == "week":
            monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            start = monday
            end = monday + timedelta(days=7)
        elif p == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)
        elif p == "custom":
            q1 = self.start.date().toPython()
            q2 = self.end.date().toPython()
            start = datetime(q1.year, q1.month, q1.day, tzinfo=now.tzinfo)
            end = datetime(q2.year, q2.month, q2.day, tzinfo=now.tzinfo) + timedelta(days=1)

        target = self.value.currentText().strip()
        if self.key.currentIndex() == 0:
            sec = self.db.active_seconds(subject=target, start=start, end=end)
        else:
            sec = self.db.active_seconds(material=target, start=start, end=end)
        h = int(sec // 3600)
        m = int(sec % 3600 // 60)
        s = int(sec % 60)
        self.result.setText(f"{h:02d}:{m:02d}:{s:02d}")


class DirectorySettingsDialog(QDialog):
    """Inspect and edit the application's configured file and directory paths."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from .paths import APP_ROOT, APP_CONFIG_DIR, load_config, default_config, get_config_dir, get_config_path
        self._load_config = load_config
        self._defaults = default_config()
        self._config = load_config()
        self.setWindowTitle("使用ディレクトリ・ViewerPack設定")
        self.resize(900, 420)
        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "アプリ本体のルートは実行場所に固定です。設定・DB・ログ・出力先・ViewerPack ZIPはここで確認・変更できます。"
        ))
        form = QFormLayout()
        self.edits = {}
        self.browse_buttons = {}
        entries = [
            ("app_root", "StudyTracker root（参照のみ）", str(APP_ROOT), False, "dir"),
            ("config_dir", "設定ディレクトリ", str(get_config_dir()), True, "dir"),
            ("config_path", "設定ファイル（参照のみ）", str(get_config_path()), False, "file"),
            ("db_path", "SQLiteデータベース", self._config["db_path"], True, "db"),
            ("log_dir", "ログディレクトリ", self._config["log_dir"], True, "dir"),
            ("export_dir", "エクスポートディレクトリ", self._config["export_dir"], True, "dir"),
            ("ViewerPackPath", "ViewerPack ZIP（任意）", self._config.get("ViewerPackPath", self._config.get("viewer_pack_path", self._defaults["ViewerPackPath"])), True, "zip"),
            ("ViewerFolderPath", "展開済みViewerPackフォルダ（任意）", self._config.get("ViewerFolderPath", ""), True, "viewer_dir"),
        ]
        for key, label, value, editable, kind in entries:
            edit = QLineEdit(value)
            edit.setReadOnly(not editable)
            self.edits[key] = edit
            row = QHBoxLayout()
            row.addWidget(edit)
            if editable:
                button = QPushButton("参照...")
                button.clicked.connect(lambda checked=False, k=key, t=kind: self._browse(k, t))
                row.addWidget(button)
            wrapper = QWidget()
            wrapper.setLayout(row)
            form.addRow(label, wrapper)
        root.addLayout(form)
        help_label = QLabel(
            "ViewerPackはZIP、またはGitHubから展開したフォルダを指定できます。"
            "GitHubのタグZIPは viewer_v0/ が複数階層の下に入っていても認識します。\n"
            "導入手順: https://github.com/OArikui/StudyTracker/blob/main/README.md#viewerpack-の導入"
        )
        help_label.setWordWrap(True)
        help_label.setOpenExternalLinks(True)
        root.addWidget(help_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _browse(self, key, kind):
        current = self.edits[key].text().strip()
        if kind in {"dir", "viewer_dir"}:
            selected = QFileDialog.getExistingDirectory(self, "ディレクトリを選択", current or str(Path.home()))
        else:
            filters = "SQLite (*.sqlite3 *.db);;All files (*)" if kind == "db" else "ZIP files (*.zip);;All files (*)"
            selected, _ = QFileDialog.getOpenFileName(self, "ファイルを選択", current or str(Path.home()), filters)
            if kind == "db" and not selected:
                selected = ""
        if selected:
            self.edits[key].setText(selected)

    def _save(self):
        from .paths import save_config
        cfg = self._load_config()
        for key in ("config_dir", "db_path", "log_dir", "export_dir", "ViewerPackPath", "ViewerFolderPath"):
            value = self.edits[key].text().strip()
            if not value and key in {"ViewerPackPath", "ViewerFolderPath"}:
                cfg[key] = ""
                continue
            if not value:
                QMessageBox.warning(self, "入力エラー", f"{key} は空欄にできません。")
                return
            cfg[key] = str(Path(value).expanduser())
        db_path = Path(cfg["db_path"])
        if db_path.suffix.lower() not in {".sqlite3", ".db"}:
            QMessageBox.warning(self, "入力エラー", "SQLiteデータベースは .sqlite3 または .db ファイルを指定してください。")
            return
        pack_value = cfg["ViewerPackPath"].strip()
        folder_value = cfg["ViewerFolderPath"].strip()
        if not pack_value and not folder_value:
            QMessageBox.warning(self, "入力エラー", "ViewerPack ZIPまたは展開済みフォルダを指定してください。")
            return
        if pack_value and Path(pack_value).suffix.lower() != ".zip":
            QMessageBox.warning(self, "入力エラー", "ViewerPackPathにはZIPファイルを指定してください。")
            return
        if folder_value:
            try:
                from .viewerpack import resolve_viewer_package_parent
                resolve_viewer_package_parent(folder_value)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Viewerフォルダを確認できません", f"{exc}")
                return
        target_db = Path(cfg["db_path"]).expanduser().resolve()
        current_db = getattr(getattr(self.parent(), "db", None), "path", None)
        if target_db.is_file() and current_db is not None and target_db != Path(current_db).expanduser().resolve():
            answer = QMessageBox.warning(
                self, "既存の学習記録を開きます",
                f"指定先には既存のDBがあります。\n{target_db}\n\n"
                "このファイルは上書きされません。保存後は指定先の既存記録に切り替わります。続行しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            save_config(cfg)
        except OSError as exc:
            QMessageBox.critical(self, "保存エラー", f"設定を保存できませんでした。\n{exc}")
            return
        self.accept()


class MediaSettingsDialog(QDialog):
    """Compact opt-in settings for Windows-wide media controls."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Windowsメディア操作設定")
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        self.enabled = QCheckBox("Windowsメディア操作を有効にする")
        self.enabled.setChecked(db.get_setting("media_enabled", "0") == "1")
        root.addWidget(self.enabled)
        root.addWidget(QLabel(
            "有効時は学習画面に小さな操作欄を表示し、グローバルショートカットを登録します。"
            "再生・前後操作は選択したWindowsメディアセッションを優先します。"
        ))
        root.addWidget(QLabel(
            "再生 / 一時停止: Ctrl+Alt+Space\n"
            "前のメディア: Ctrl+Alt+Left\n"
            "次のメディア: Ctrl+Alt+Right"
        ))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def accept(self):
        self.db.set_setting("media_enabled", "1" if self.enabled.isChecked() else "0")
        super().accept()


class BackupSettingsDialog(QDialog):
    """Configure automatic SQLite backups and create an immediate snapshot."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("定期バックアップ設定")
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "SQLite の整合性を保つ方法でバックアップします。古い世代の削除は、新しいバックアップの作成成功後に行います。\n"
            "user_data や元のDBとは別の場所を選択し、可能なら別ドライブに保存してください。"
        ))

        self.enabled = QCheckBox("定期バックアップを有効にする")
        self.enabled.setChecked(db.get_setting("backup_enabled", "0") == "1")
        root.addWidget(self.enabled)

        form = QFormLayout()
        self.interval = QComboBox()
        for label, hours in (
            ("6時間ごと", 6),
            ("12時間ごと", 12),
            ("毎日", 24),
            ("毎週", 168),
        ):
            self.interval.addItem(label, hours)
        try:
            interval_hours = int(db.get_setting("backup_interval_hours", "24"))
        except (TypeError, ValueError):
            interval_hours = 24
        interval_index = self.interval.findData(interval_hours)
        self.interval.setCurrentIndex(interval_index if interval_index >= 0 else 2)
        form.addRow("実行間隔", self.interval)

        self.directory = QLineEdit(
            db.get_setting("backup_dir", str(Path.home() / "StudyTrackerBackups"))
        )
        choose = QPushButton("参照...")
        choose.clicked.connect(self.choose_directory)
        directory_row = QHBoxLayout()
        directory_row.addWidget(self.directory, 1)
        directory_row.addWidget(choose)
        directory_widget = QWidget()
        directory_widget.setLayout(directory_row)
        form.addRow("保存先", directory_widget)

        self.retention = QSpinBox()
        self.retention.setRange(1, 365)
        try:
            retained = int(db.get_setting("backup_retention_count", "14"))
        except (TypeError, ValueError):
            retained = 14
        self.retention.setValue(max(1, min(365, retained)))
        form.addRow("保持する世代数", self.retention)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        backup_now = QPushButton("今すぐバックアップ")
        backup_now.clicked.connect(self.create_now)
        button_row = QHBoxLayout()
        button_row.addWidget(backup_now)
        button_row.addStretch()
        button_row.addWidget(buttons)
        root.addLayout(button_row)

    def choose_directory(self):
        current = self.directory.text().strip() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(
            self, "バックアップ保存先を選択", current
        )
        if selected:
            self.directory.setText(selected)

    def create_now(self):
        destination = self.directory.text().strip()
        if not destination:
            QMessageBox.warning(self, "入力エラー", "バックアップ保存先を指定してください。")
            return
        try:
            from .backup import create_backup
            output = create_backup(
                self.db.path, destination, self.retention.value()
            )
            self.db.set_setting("backup_last_at", datetime.now().astimezone().isoformat())
            QMessageBox.information(
                self, "バックアップ完了", f"バックアップを作成しました。\n{output}"
            )
        except Exception as exc:
            logging.getLogger("study_tracker.backup").exception("Manual backup failed")
            QMessageBox.critical(
                self, "バックアップ失敗", f"バックアップを作成できませんでした。\n{exc}"
            )

    def accept(self):
        destination = self.directory.text().strip()
        if not destination:
            QMessageBox.warning(self, "入力エラー", "バックアップ保存先を指定してください。")
            return
        from .paths import USER_DATA_DIR
        target = Path(destination).expanduser().resolve()
        database_path = self.db.path.expanduser().resolve()
        try:
            inside_user_data = target == USER_DATA_DIR.resolve() or USER_DATA_DIR.resolve() in target.parents
        except OSError:
            inside_user_data = False
        same_drive = bool(target.drive and database_path.drive and target.drive.lower() == database_path.drive.lower())
        if inside_user_data or same_drive:
            answer = QMessageBox.warning(
                self, "バックアップ先の確認",
                "バックアップ先が user_data 内、または元のDBと同じドライブです。\n"
                "元データと同時に失われるリスクを下げるため、別ドライブを推奨します。\n\nこの保存先を使用しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.db.set_setting("backup_enabled", "1" if self.enabled.isChecked() else "0")
        self.db.set_setting("backup_interval_hours", self.interval.currentData())
        self.db.set_setting("backup_dir", str(Path(destination).expanduser()))
        self.db.set_setting("backup_retention_count", self.retention.value())
        super().accept()
