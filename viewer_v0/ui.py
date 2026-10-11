from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QDate, QDateTime
from PySide6.QtGui import QFontMetrics, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .analysis import daily_seconds, filter_segments, format_duration, group_seconds, period_bounds, summarize, study_rate_series
from .writer import StudyTrackerWriter
from .charts import BarChart, LineChart, RateChart, TimelineChart
from .reader import Segment, StudyTrackerReader

VERSION = "0.8.1"


class ViewerWindow(QMainWindow):
    def __init__(self, database_path: str | Path, parent=None):
        super().__init__(parent)
        self.database_path = Path(database_path).expanduser().resolve()
        if not self.database_path.is_file():
            raise FileNotFoundError(f"StudyTracker本体の設定DBが見つかりません: {self.database_path}")
        self.reader: StudyTrackerReader | None = None
        self.all_segments: list[Segment] = []
        self.filtered: list[Segment] = []
        self.writer: StudyTrackerWriter | None = None
        self.actual_scopes: dict[int, str] = {}
        self.timestamps = []
        self._db_path_text = ""
        self.filters_pinned = False
        self._date_syncing = False
        self._tab_history: list[int] = [0]
        self._tab_history_index = 0
        self._ignore_tab_history = False
        self.setWindowTitle(f"StudyTracker ViewerPack v{VERSION}")
        self.resize(1520, 980)
        self._build()
        # The host owns the database path. The Viewer has no independent DB selector.
        self._open_db(self.database_path)

    def closeEvent(self, event):
        if self.reader:
            self.reader.close()
        if self.writer:
            self.writer.close()
        super().closeEvent(event)

    def _build(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        top = QHBoxLayout()
        self.back_btn = QPushButton("← 戻る")
        self.back_btn.setToolTip("直前に表示していたタブへ戻る")
        self.back_btn.setEnabled(False)
        self.back_btn.clicked.connect(self._navigate_back)
        self.forward_btn = QPushButton("進む →")
        self.forward_btn.setToolTip("次に表示していたタブへ進む")
        self.forward_btn.setEnabled(False)
        self.forward_btn.clicked.connect(self._navigate_forward)
        self.path_label = QLabel("データベース: 未選択")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setMinimumWidth(220)
        self.path_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.path_label.setToolTip("")
        refresh_btn = QPushButton("再読み込み")
        refresh_btn.clicked.connect(self._reload)
        edit_btn = QPushButton("実施範囲")
        edit_btn.clicked.connect(self._edit_selected_actual_scope)
        record_edit_btn = QPushButton("記録を編集")
        record_edit_btn.clicked.connect(self._edit_selected_segment)
        timestamp_edit_btn = QPushButton("タイムスタンプ編集")
        timestamp_edit_btn.clicked.connect(self._edit_selected_timestamps)
        history_btn = QPushButton("更新履歴")
        history_btn.clicked.connect(self._show_history)
        self.version_label = QLabel(f"v{VERSION}")
        self.version_label.setToolTip("StudyTracker Viewer version")
        top.addWidget(self.back_btn)
        top.addWidget(self.forward_btn)
        top.addWidget(self.path_label, 1)
        top.addWidget(refresh_btn)
        top.addWidget(edit_btn)
        top.addWidget(record_edit_btn)
        top.addWidget(timestamp_edit_btn)
        top.addWidget(history_btn)
        top.addWidget(self.version_label)
        outer.addLayout(top)

        self.status = QLabel("StudyTracker本体と共有するSQLite DBを開きます。タイムスタンプと実施範囲は同じDBを使用します。")
        outer.addWidget(self.status)

        filter_header = QHBoxLayout()
        self.filter_tab_button = QToolButton()
        self.filter_tab_button.setText("☰ フィルター")
        self.filter_tab_button.setCheckable(True)
        self.filter_tab_button.setChecked(False)
        self.filter_tab_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.filter_tab_button.clicked.connect(self._toggle_filter_panel)
        self.filter_tab_button.setMinimumHeight(30)

        self.filter_pin_button = QToolButton()
        self.filter_pin_button.setText("📌 ピン留め")
        self.filter_pin_button.setCheckable(True)
        self.filter_pin_button.setChecked(False)
        self.filter_pin_button.clicked.connect(self._toggle_filter_pin)
        self.filter_pin_button.setVisible(False)

        self.filter_summary = QLabel("フィルター: 収納中（全期間 / 全科目 / 全教材）")
        self.filter_summary.setStyleSheet("color: palette(mid); padding-left: 6px;")
        filter_header.addWidget(self.filter_tab_button)
        filter_header.addWidget(self.filter_pin_button)
        filter_header.addWidget(self.filter_summary, 1)
        outer.addLayout(filter_header)

        self.filters = self._build_filter_panel()
        self.filters.setVisible(False)
        outer.addWidget(self.filters)

        self.kpi = QGroupBox("概要")
        kg = QGridLayout(self.kpi)
        kg.setContentsMargins(8, 6, 8, 6)
        self.kpi_labels: dict[str, QLabel] = {}
        specs = [
            ("total", "総勉強時間"),
            ("days", "学習日数"),
            ("sessions", "セッション数"),
            ("segments", "区間数"),
            ("avg", "平均区間"),
            ("longest", "最長区間"),
        ]
        for i, (key, title) in enumerate(specs):
            box = QVBoxLayout()
            t = QLabel(title)
            v = QLabel("—")
            v.setStyleSheet("font-size: 19px; font-weight: 600;")
            box.addWidget(t)
            box.addWidget(v)
            container = QWidget()
            container.setLayout(box)
            kg.addWidget(container, 0, i)
            self.kpi_labels[key] = v
        outer.addWidget(self.kpi)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)

        # グラフタブ: 各推移グラフに科目選択と折れ線/棒グラフ切替を設ける
        chart_scroll = QScrollArea()
        chart_scroll.setWidgetResizable(True)
        chart_scroll.setFrameShape(QFrame.Shape.NoFrame)
        chart_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        chart_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        chart_area = QWidget()
        chart_area.setMinimumWidth(860)
        dg = QGridLayout(chart_area)
        dg.setContentsMargins(8, 8, 8, 8)
        dg.setSpacing(12)
        self.daily_chart = LineChart("日別勉強時間の推移")
        self.subject_chart = BarChart("科目別勉強時間")
        self.material_chart = BarChart("教材別勉強時間")
        self.rate_chart = RateChart("時間当たりの勉強量の推移")
        for widget, height in ((self.daily_chart, 430), (self.rate_chart, 450), (self.subject_chart, 440), (self.material_chart, 440)):
            widget.setMinimumHeight(height)

        self.daily_subject = QComboBox()
        self.daily_subject.addItem("全科目")
        self.daily_mode = QComboBox()
        self.daily_mode.addItems(["折れ線", "棒グラフ"])
        self.rate_subject = QComboBox()
        self.rate_subject.addItem("全科目")
        self.rate_alias = QComboBox()
        self.rate_alias.addItem("全別名")
        self.rate_mode = QComboBox()
        self.rate_mode.addItems(["折れ線", "棒グラフ"])

        daily_panel = self._make_trend_panel(self.daily_chart, self.daily_subject, self.daily_mode)
        rate_panel = self._make_trend_panel(self.rate_chart, self.rate_subject, self.rate_mode, alias_selector=self.rate_alias)
        for selector in (self.daily_subject, self.daily_mode, self.rate_subject, self.rate_alias, self.rate_mode):
            selector.currentTextChanged.connect(self._refresh_trend_charts)
        dg.addWidget(daily_panel, 0, 0, 1, 2)
        dg.addWidget(rate_panel, 1, 0, 1, 2)
        dg.addWidget(self.subject_chart, 2, 0)
        dg.addWidget(self.material_chart, 2, 1)
        dg.setColumnStretch(0, 1)
        dg.setColumnStretch(1, 1)
        dg.setRowStretch(0, 0)
        dg.setRowStretch(1, 0)
        dg.setRowStretch(2, 0)
        chart_scroll.setWidget(chart_area)
        self.tabs.addTab(chart_scroll, "グラフ")

        # テーブルタブ: 24時間軸タイムラインはマウスホイールで操作
        table_page = QWidget()
        page_layout = QVBoxLayout(table_page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(6)

        timeline_box = QGroupBox("タイムライン（各日を縦に表示 / 横軸は時刻）")
        timeline_layout = QVBoxLayout(timeline_box)
        timeline_layout.setContentsMargins(6, 6, 6, 6)
        timeline_toolbar = QHBoxLayout()
        timeline_toolbar.addWidget(QLabel("ホイール: 拡大/縮小　Shift+ホイール: 横移動　ドラッグ: 範囲拡大　日付の上下移動: 右スクロールバー"), 1)
        self.timeline_reset = QPushButton("24時間全体")
        self.timeline_reset.setToolTip("00:00～24:00を表示")
        self.timeline_reset.clicked.connect(self._reset_timeline_view)
        timeline_toolbar.addWidget(self.timeline_reset)
        timeline_layout.addLayout(timeline_toolbar)
        self.timeline = TimelineChart()
        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setWidgetResizable(True)
        self.timeline_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.timeline_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.timeline_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.timeline_scroll.setWidget(self.timeline)
        timeline_layout.addWidget(self.timeline_scroll, 1)

        table_box = QGroupBox("学習記録（学習予定範囲と実施範囲）")
        table_layout = QVBoxLayout(table_box)
        table_layout.setContentsMargins(4, 4, 4, 4)
        self.table = QTableWidget(0, 14)
        self.table.setHorizontalHeaderLabels([
            "ID", "開始", "終了", "時間", "状態", "学習区分", "科目", "教材",
            "学習位置", "学習単位", "学習予定範囲", "実施範囲", "備考", "時間バー"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        self.table.horizontalScrollBar().setValue(0)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(56)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        widths = [60, 110, 110, 72, 74, 112, 90, 145, 104, 104, 150, 150, 170, 190]
        for col, width in enumerate(widths):
            header.resizeSection(col, width)
        header.setSectionsMovable(False)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.cellDoubleClicked.connect(self._detail)
        table_layout.addWidget(self.table, 1)

        table_splitter = QSplitter(Qt.Orientation.Vertical)
        table_splitter.setHandleWidth(8)
        table_splitter.setChildrenCollapsible(False)
        table_splitter.setOpaqueResize(False)
        timeline_box.setMinimumHeight(230)
        table_box.setMinimumHeight(260)
        table_splitter.addWidget(timeline_box)
        table_splitter.addWidget(table_box)
        table_splitter.setSizes([390, 520])
        table_splitter.setStretchFactor(0, 1)
        table_splitter.setStretchFactor(1, 2)
        page_layout.addWidget(table_splitter, 1)
        self.tabs.addTab(table_page, "テーブル")
        self.timeline.segment_clicked = self._select_segment_from_timeline
        self.timeline.timestamp_clicked = self._edit_timestamp_record
        self.timeline.range_selected = self._zoom_timeline_range
        self.tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self.tabs, 1)

        bottom = QHBoxLayout()
        self.visible_count = QLabel("0件")
        bottom.addWidget(self.visible_count)
        bottom.addWidget(QLabel(f"StudyTracker Viewer v{VERSION}"))
        bottom.addStretch(1)
        export_btn = QPushButton("表示中の記録をCSV出力")
        export_btn.clicked.connect(self._export_csv)
        bottom.addWidget(export_btn)
        outer.addLayout(bottom)

        self.setCentralWidget(root)

    def _make_trend_panel(self, chart: QWidget, subject_selector: QComboBox, mode_selector: QComboBox, alias_selector: QComboBox | None = None) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("科目"))
        controls.addWidget(subject_selector)
        if alias_selector is not None:
            controls.addSpacing(10)
            controls.addWidget(QLabel("学習単位/別名"))
            controls.addWidget(alias_selector)
        controls.addSpacing(12)
        controls.addWidget(QLabel("表示形式"))
        controls.addWidget(mode_selector)
        controls.addStretch(1)
        layout.addLayout(controls)
        layout.addWidget(chart, 1)
        return panel

    def _build_filter_panel(self) -> QWidget:
        filters = QGroupBox("フィルター")
        fg = QGridLayout(filters)
        fg.setContentsMargins(8, 6, 8, 8)
        fg.setHorizontalSpacing(8)
        fg.setVerticalSpacing(8)
        self.period = QComboBox()
        self.period.addItems(["今日", "今週", "直近7日", "直近30日", "今月", "カスタム", "全期間"])
        self.period.currentTextChanged.connect(self._period_changed)
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy/MM/dd")
        self.start_date.setDate(QDate.currentDate())
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy/MM/dd")
        self.end_date.setDate(QDate.currentDate())
        self.start_date.dateChanged.connect(self._custom_dates_changed)
        self.end_date.dateChanged.connect(self._custom_dates_changed)

        self.category = QComboBox()
        self.category.currentTextChanged.connect(self._apply)
        self.subject = QComboBox()
        self.subject.currentTextChanged.connect(self._apply)
        self.material = QComboBox()
        self.material.currentTextChanged.connect(self._apply)
        self.query = QLineEdit()
        self.query.setPlaceholderText("科目・教材・位置・単位・予定範囲・実施範囲・メモを検索")
        self.query.textChanged.connect(self._apply)
        self.active_only = QComboBox()
        self.active_only.addItems(["すべて", "Activeのみ", "Passiveのみ"])
        self.active_only.currentTextChanged.connect(self._apply)

        fg.addWidget(QLabel("期間"), 0, 0)
        fg.addWidget(self.period, 0, 1)
        fg.addWidget(QLabel("開始"), 0, 2)
        fg.addWidget(self.start_date, 0, 3)
        fg.addWidget(QLabel("終了"), 0, 4)
        fg.addWidget(self.end_date, 0, 5)

        fg.addWidget(QLabel("学習区分"), 1, 0)
        fg.addWidget(self.category, 1, 1)
        fg.addWidget(QLabel("科目"), 1, 2)
        fg.addWidget(self.subject, 1, 3)
        fg.addWidget(QLabel("教材"), 1, 4)
        fg.addWidget(self.material, 1, 5)

        fg.addWidget(QLabel("状態"), 2, 0)
        fg.addWidget(self.active_only, 2, 1)
        fg.addWidget(QLabel("キーワード"), 2, 2)
        fg.addWidget(self.query, 2, 3, 1, 3)
        for col in (1, 3, 5):
            fg.setColumnStretch(col, 1)
        return filters

    def _period_changed(self, kind: str):
        if self._date_syncing or kind == "カスタム":
            self._apply()
            return
        start, end = period_bounds(kind, self.all_segments)
        if start is None or end is None:
            start = end = date.today()
        self._date_syncing = True
        try:
            for widget, value in ((self.start_date, start), (self.end_date, end)):
                widget.blockSignals(True)
                widget.setDate(QDate(value.year, value.month, value.day))
                widget.blockSignals(False)
        finally:
            self._date_syncing = False
        self._apply()

    def _custom_dates_changed(self, *_):
        if self._date_syncing:
            return
        if self.period.currentText() != "カスタム":
            self.period.blockSignals(True)
            self.period.setCurrentText("カスタム")
            self.period.blockSignals(False)
        self._apply()

    def _on_tab_changed(self, index: int):
        if self._ignore_tab_history or index < 0:
            return
        if self._tab_history_index < len(self._tab_history) - 1:
            self._tab_history = self._tab_history[: self._tab_history_index + 1]
        if not self._tab_history or self._tab_history[-1] != index:
            self._tab_history.append(index)
            self._tab_history_index = len(self._tab_history) - 1
        self._update_navigation_buttons()

    def _update_navigation_buttons(self):
        self.back_btn.setEnabled(self._tab_history_index > 0)
        self.forward_btn.setEnabled(self._tab_history_index < len(self._tab_history) - 1)

    def _navigate_to_history(self, step: int):
        target = self._tab_history_index + step
        if target < 0 or target >= len(self._tab_history):
            return
        self._tab_history_index = target
        self._ignore_tab_history = True
        self.tabs.setCurrentIndex(self._tab_history[target])
        self._ignore_tab_history = False
        self._update_navigation_buttons()

    def _navigate_back(self):
        self._navigate_to_history(-1)

    def _navigate_forward(self):
        self._navigate_to_history(1)

    def _toggle_filter_panel(self, checked: bool):
        self.filters.setVisible(checked)
        self.filter_pin_button.setVisible(checked)
        self.filter_tab_button.setText("☰ フィルター ▾" if checked else "☰ フィルター")
        if not checked:
            self.filter_pin_button.setChecked(False)
            self.filters_pinned = False
        self._update_filter_summary()

    def _toggle_filter_pin(self, checked: bool):
        self.filters_pinned = checked
        self.filter_pin_button.setText("📌 ピン留め解除" if checked else "📌 ピン留め")
        self.filter_summary.setText(
            "フィルター: ピン留め中" if checked else "フィルター: 展開中（ピン留めなし）"
        )

    def _update_filter_summary(self):
        period = self.period.currentText() or "—"
        subject = self.subject.currentText() or "—"
        material = self.material.currentText() or "—"
        if not self.filters.isVisible():
            start = self.start_date.date().toString("yyyy/MM/dd") if hasattr(self, "start_date") else "—"
            end = self.end_date.date().toString("yyyy/MM/dd") if hasattr(self, "end_date") else "—"
            self.filter_summary.setText(f"フィルター: 収納中（{period} {start}～{end} / {subject} / {material}）")
        elif self.filters_pinned:
            self.filter_summary.setText("フィルター: ピン留め中")
        else:
            self.filter_summary.setText("フィルター: 展開中（ピン留めなし）")

    def _open_db(self, path: Path):
        path = Path(path).expanduser().resolve()
        if path != self.database_path:
            QMessageBox.warning(
                self,
                "DBパスは変更できません",
                "ViewerはStudyTracker本体のdb_path設定を使用します。変更は本体の設定画面から行ってください。",
            )
            return
        old = self.reader
        try:
            reader = StudyTrackerReader(path)
            segments = reader.read_segments()
        except Exception as exc:
            QMessageBox.critical(self, "DBを開けません", str(exc))
            return
        self.reader = reader
        self.all_segments = segments
        self.actual_scopes = {x.segment_id: x.actual_scope for x in segments if x.actual_scope}
        if self.writer:
            self.writer.close()
        try:
            self.writer = StudyTrackerWriter(path)
        except Exception as exc:
            self.writer = None
            self.status.setText(f"DBは読み込めましたが書き込みを開けません: {exc}")
        self.timestamps = reader.read_timestamps()
        if old:
            old.close()
        self._db_path_text = str(path)
        self._update_path_label()
        self.path_label.setToolTip(str(path))
        self.status.setText(f"{len(segments):,}区間 / {len(self.timestamps):,}タイムスタンプを読み込みました。実施範囲は共有DBへ保存できます。")
        self._reload_filters()

    def _reload(self):
        if not self.reader:
            return
        try:
            self.all_segments = self.reader.read_segments()
            self.actual_scopes = {x.segment_id: x.actual_scope for x in self.all_segments if x.actual_scope}
            self.timestamps = self.reader.read_timestamps()
            self.status.setText(f"{len(self.all_segments):,}区間 / {len(self.timestamps):,}タイムスタンプを再読み込みしました。")
            self._reload_filters()
        except Exception as exc:
            QMessageBox.critical(self, "再読み込み失敗", str(exc))

    def _reload_filters(self):
        self._fill_combo(self.category, sorted({s.category for s in self.all_segments if s.category}), keep=True)
        self._fill_combo(self.subject, sorted({s.subject for s in self.all_segments if s.subject}), keep=True)
        self._fill_combo(self.material, sorted({s.material for s in self.all_segments if s.material}), keep=True)
        subject_values = sorted({s.subject or "(未設定)" for s in self.all_segments})
        for combo in (self.daily_subject, self.rate_subject):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("全科目")
            combo.addItems(subject_values)
            combo.setCurrentText(current if current and combo.findText(current) >= 0 else "全科目")
            combo.blockSignals(False)
        alias_values = sorted({value for value in ([s.unit for s in self.all_segments] + [t.unit for t in self.timestamps]) if value})
        current_alias = self.rate_alias.currentText()
        self.rate_alias.blockSignals(True)
        self.rate_alias.clear()
        self.rate_alias.addItem("全別名")
        self.rate_alias.addItems(alias_values)
        self.rate_alias.setCurrentText(current_alias if current_alias and self.rate_alias.findText(current_alias) >= 0 else "全別名")
        self.rate_alias.blockSignals(False)
        self.period.blockSignals(True)
        self.period.setCurrentText("全期間" if self.all_segments else "今日")
        self.period.blockSignals(False)
        self._period_changed(self.period.currentText())

    @staticmethod
    def _fill_combo(combo: QComboBox, values: list[str], keep: bool):
        current = combo.currentText() if keep else ""
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("すべて")
        combo.addItems(values)
        idx = combo.findText(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _apply(self, *_):
        if not self.all_segments:
            self._render([])
            self._update_filter_summary()
            return
        if self.period.currentText() == "カスタム":
            start = self.start_date.date().toPython()
            end = self.end_date.date().toPython()
            if start > end:
                start, end = end, start
        else:
            start, end = period_bounds(self.period.currentText(), self.all_segments)
        rows = filter_segments(
            self.all_segments,
            start=start,
            end=end,
            category="" if self.category.currentText() in ("", "すべて") else self.category.currentText(),
            subject="" if self.subject.currentText() in ("", "すべて") else self.subject.currentText(),
            material="" if self.material.currentText() in ("", "すべて") else self.material.currentText(),
            query=self.query.text(),
            active_only=self.active_only.currentText() == "Activeのみ",
        )
        if self.active_only.currentText() == "Passiveのみ":
            rows = [segment for segment in rows if not segment.active]
        if self.query.text().strip():
            needle = self.query.text().strip().casefold()
            rows = [
                s for s in rows
                if needle in " ".join(
                    (s.category, s.subject, s.material, s.position, s.unit, s.scope,
                     s.actual_scope, *s.notes,
                     *(t.location for t in self.timestamps if t.session_id == s.session_id and s.start <= t.at <= s.end))
                ).casefold()
            ]
        self._render(rows)
        self._update_filter_summary()

    def _render(self, rows: list[Segment]):
        self.filtered = rows
        summary = summarize(rows)
        self.kpi_labels["total"].setText(format_duration(summary.total_seconds))
        self.kpi_labels["days"].setText(f"{summary.study_days:,}日")
        self.kpi_labels["sessions"].setText(f"{summary.sessions:,}")
        self.kpi_labels["segments"].setText(f"{summary.segments:,}")
        self.kpi_labels["avg"].setText(format_duration(summary.average_seconds))
        self.kpi_labels["longest"].setText(format_duration(summary.longest_seconds))
        filtered_timestamp = [
            t for t in self.timestamps
            if any(segment.session_id == t.session_id and segment.start <= t.at <= segment.end for segment in rows)
        ]
        self.subject_chart.set_data(group_seconds(rows, "subject"))
        self.material_chart.set_data(group_seconds(rows, "material"))
        self.timeline.set_data(rows, filtered_timestamp)
        self._refresh_trend_charts()
        self._fill_table(rows)
        self.visible_count.setText(f"{len(rows):,}件")

    def _refresh_trend_charts(self, *_):
        rows = self.filtered
        daily_subject = self.daily_subject.currentText() if hasattr(self, "daily_subject") else "全科目"
        rate_subject = self.rate_subject.currentText() if hasattr(self, "rate_subject") else "全科目"
        if daily_subject and daily_subject != "全科目":
            daily_rows = [s for s in rows if (s.subject or "(未設定)") == daily_subject]
        else:
            daily_rows = rows
        self.daily_chart.set_data(
            daily_seconds(daily_rows),
            display_mode="bar" if self.daily_mode.currentText() == "棒グラフ" else "line",
        )

        if rate_subject and rate_subject != "全科目":
            rate_rows = [s for s in rows if (s.subject or "(未設定)") == rate_subject]
        else:
            rate_rows = rows
        selected_alias = self.rate_alias.currentText() if hasattr(self, "rate_alias") else "全別名"
        if selected_alias and selected_alias != "全別名":
            alias_segment_keys = {
                (t.session_id, t.segment_start_at)
                for t in self.timestamps if t.unit == selected_alias
            }
            rate_rows = [
                s for s in rate_rows
                if s.unit == selected_alias or (s.session_id, s.start) in alias_segment_keys
            ]
        rate_timestamps = [
            t for t in self.timestamps
            if any(s.session_id == t.session_id and s.start <= t.at <= s.end for s in rate_rows)
            and (selected_alias == "全別名" or t.unit == selected_alias)
        ]
        actual_rate, planned_rate = study_rate_series(rate_rows, rate_timestamps)
        self.rate_chart.set_data(
            actual_rate,
            planned_rate,
            display_mode="bar" if self.rate_mode.currentText() == "棒グラフ" else "line",
        )
        if hasattr(self, "filter_summary"):
            self._update_filter_summary()

    def _zoom_timeline_range(self, start_hour: float, end_hour: float):
        self.timeline.set_view_hours(start_hour, end_hour)
        self.status.setText(f"タイムラインの表示範囲を {start_hour:02.2f}時～{end_hour:02.2f}時に変更しました。ホイールで拡大/縮小、Shift+ホイールで横移動できます。")

    def _reset_timeline_view(self):
        self.timeline.reset_view()
        self.status.setText("タイムラインを00:00～24:00の全体表示へ戻しました。")

    def _update_path_label(self):
        if not self._db_path_text:
            self.path_label.setText("データベース: 未選択")
            return
        fm = QFontMetrics(self.path_label.font())
        available = max(120, self.path_label.width() - 8)
        text = fm.elidedText(
            f"データベース: {self._db_path_text}",
            Qt.TextElideMode.ElideMiddle,
            available,
        )
        self.path_label.setText(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_path_label()

    def _display_dt(self, dt) -> str:
        return dt.astimezone().strftime("%m/%d %H:%M:%S")

    def _fill_table(self, rows: list[Segment]):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        max_duration = max((int(round(s.duration_seconds)) for s in rows), default=1) or 1
        active_bg = QColor(225, 244, 231)
        passive_bg = QColor(232, 237, 245)
        for i, segment in enumerate(reversed(rows)):
            vals = [
                str(segment.segment_id),
                self._display_dt(segment.start),
                self._display_dt(segment.end),
                format_duration(segment.duration_seconds),
                "Active" if segment.active else "Passive",
                segment.category,
                segment.subject,
                segment.material,
                segment.position,
                segment.unit,
                segment.scope,
                segment.actual_scope,
                " / ".join(note for note in segment.notes if note),
            ]
            row_bg = active_bg if segment.active else passive_bg
            for col, value in enumerate(vals):
                item = QTableWidgetItem(value)
                item.setBackground(row_bg)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, segment.segment_id)
                if col in (1, 2):
                    item.setToolTip(segment.start.isoformat(sep=" ") if col == 1 else segment.end.isoformat(sep=" "))
                self.table.setItem(i, col, item)
            duration_bar = QProgressBar()
            duration_bar.setRange(0, max_duration)
            duration_bar.setValue(min(max_duration, int(round(segment.duration_seconds))))
            duration_bar.setFormat(f"{format_duration(segment.duration_seconds)}  (%p%)")
            duration_bar.setTextVisible(True)
            duration_bar.setToolTip(f"この区間の長さ: {format_duration(segment.duration_seconds)}")
            duration_bar.setMinimumWidth(150)
            self.table.setCellWidget(i, 13, duration_bar)
            self.table.setRowHeight(i, 36)
        self.table.setSortingEnabled(True)

    def _selected_segment(self) -> Segment | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        segment_id = item.data(Qt.ItemDataRole.UserRole)
        if segment_id is None:
            try:
                segment_id = int(item.text())
            except ValueError:
                return None
        return next((s for s in self.filtered if s.segment_id == int(segment_id)), None)

    def _select_segment_from_timeline(self, segment: Segment):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            sid = item.data(Qt.ItemDataRole.UserRole)
            if sid == segment.segment_id:
                self.table.setCurrentCell(row, 0)
                self.table.selectRow(row)
                self.table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
                return

    def _detail(self, row: int, _column: int):
        if row < 0 or row >= self.table.rowCount():
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        segment_id = item.data(Qt.ItemDataRole.UserRole)
        if segment_id is None:
            return
        s = next((item for item in self.filtered if item.segment_id == int(segment_id)), None)
        if s is None:
            return
        timestamp_lines = [
            f"{t.at.astimezone().strftime('%H:%M:%S')}  {t.location}"
            for t in self.timestamps
            if t.session_id == s.session_id and s.start <= t.at <= s.end
        ]
        lines = [
            f"Segment ID: {s.segment_id}",
            f"Session ID: {s.session_id}",
            f"開始: {s.start.astimezone().isoformat(sep=' ', timespec='seconds')}",
            f"終了: {s.end.astimezone().isoformat(sep=' ', timespec='seconds')}",
            f"時間: {format_duration(s.duration_seconds)}",
            f"状態: {'Active' if s.active else 'Passive'}",
            f"学習区分: {s.category}",
            f"科目: {s.subject}",
            f"教材: {s.material}",
            f"学習位置: {s.position}",
            f"学習単位: {s.unit}",
            f"学習予定範囲: {s.scope}",
            f"実施範囲: {s.actual_scope or '(未入力)'}",
            "タイムスタンプ:",
            *(timestamp_lines if timestamp_lines else ["(なし)"]),
            f"備考: {' / '.join(s.notes)}",
        ]
        box = QMessageBox(self)
        box.setWindowTitle("学習記録詳細")
        box.setText("\n".join(lines))
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        edit_scope = box.addButton("実施範囲を編集", QMessageBox.ButtonRole.ActionRole)
        edit_record = box.addButton("記録を編集", QMessageBox.ButtonRole.ActionRole)
        edit_timestamps = box.addButton("タイムスタンプ編集", QMessageBox.ButtonRole.ActionRole)
        box.exec()
        if box.clickedButton() is edit_scope:
            self._edit_actual_scope(s)
        elif box.clickedButton() is edit_record:
            self._edit_segment(s)
        elif box.clickedButton() is edit_timestamps:
            self._edit_selected_timestamps_for(s)

    def _edit_selected_segment(self):
        segment = self._selected_segment()
        if segment is None:
            QMessageBox.information(self, "記録を編集", "先に学習記録を選択してください。")
            return
        self._edit_segment(segment)

    def _edit_segment(self, segment: Segment):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"学習記録を編集 - Segment {segment.segment_id}")
        dialog.resize(680, 700)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        start_edit = QDateTimeEdit()
        start_edit.setCalendarPopup(True)
        start_edit.setDisplayFormat("yyyy/MM/dd HH:mm:ss")
        start_edit.setDateTime(QDateTime.fromSecsSinceEpoch(int(segment.start.timestamp())))
        end_edit = QDateTimeEdit()
        end_edit.setCalendarPopup(True)
        end_edit.setDisplayFormat("yyyy/MM/dd HH:mm:ss")
        end_edit.setDateTime(QDateTime.fromSecsSinceEpoch(int(segment.end.timestamp())))
        active_edit = QComboBox()
        active_edit.addItems(["Active", "Passive"])
        active_edit.setCurrentText("Active" if segment.active else "Passive")

        editors: dict[str, QLineEdit] = {}
        fields = [
            ("category", "学習区分", segment.category),
            ("subject", "科目", segment.subject),
            ("material", "教材", segment.material),
            ("position", "学習位置", segment.position),
            ("unit", "学習単位", segment.unit),
            ("scope", "学習予定範囲", segment.scope),
            ("actual_scope", "実施範囲", segment.actual_scope),
        ]
        form.addRow("開始日時", start_edit)
        form.addRow("終了日時", end_edit)
        form.addRow("状態", active_edit)
        for key, label, value in fields:
            editor = QLineEdit(value)
            editors[key] = editor
            form.addRow(label, editor)
        notes_edit = QPlainTextEdit()
        notes_edit.setPlainText("\n".join(segment.notes))
        notes_edit.setMaximumHeight(100)
        form.addRow("備考（1行ごと）", notes_edit)
        layout.addLayout(form)
        hint = QLabel("保存すると変更前・変更後の値を更新履歴に追記します。履歴はこの画面から編集・削除できません。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not self.writer:
            QMessageBox.warning(self, "保存できません", "StudyTracker DBを更新できる状態ではありません。")
            return
        start_dt = datetime.fromtimestamp(start_edit.dateTime().toSecsSinceEpoch()).astimezone()
        end_dt = datetime.fromtimestamp(end_edit.dateTime().toSecsSinceEpoch()).astimezone()
        if end_dt <= start_dt:
            QMessageBox.warning(self, "日時の入力エラー", "終了日時は開始日時より後にしてください。")
            return
        updates = {
            "start_at": start_dt.isoformat(timespec="seconds"),
            "end_at": end_dt.isoformat(timespec="seconds"),
            "active": 1 if active_edit.currentText() == "Active" else 0,
            **{key: editor.text().strip() for key, editor in editors.items()},
            "notes": [line.strip() for line in notes_edit.toPlainText().splitlines() if line.strip()],
        }
        try:
            self.writer.update_segment(segment.segment_id, updates)
            self._reload()
            self.status.setText(f"Segment {segment.segment_id} を更新し、変更履歴へ記録しました。")
        except Exception as exc:
            QMessageBox.critical(self, "記録の保存失敗", str(exc))

    def _edit_selected_timestamps_for(self, segment: Segment):
        timestamps = [
            item for item in self.timestamps
            if item.session_id == segment.session_id
            and (item.segment_start_at == segment.start or segment.start <= item.at <= segment.end)
        ]
        if not timestamps:
            QMessageBox.information(self, "タイムスタンプ編集", "選択した記録に属するタイムスタンプがありません。")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"タイムスタンプ - Segment {segment.segment_id}")
        dialog.resize(800, 420)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["ID", "時刻", "学習位置", "学習単位", "科目 / 教材"])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setColumnHidden(0, True)
        for timestamp in timestamps:
            row = table.rowCount()
            table.insertRow(row)
            values = [str(timestamp.timestamp_id), self._display_dt(timestamp.at), timestamp.location, timestamp.unit, f"{timestamp.subject} / {timestamp.material}"]
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(value))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        table.doubleClicked.connect(lambda *_: self._edit_timestamp_from_table(table, timestamps, dialog))
        layout.addWidget(table, 1)
        buttons_row = QHBoxLayout()
        edit_button = QPushButton("選択したタイムスタンプを編集")
        edit_button.clicked.connect(lambda: self._edit_timestamp_from_table(table, timestamps, dialog))
        buttons_row.addWidget(edit_button)
        buttons_row.addStretch(1)
        close_button = QPushButton("閉じる")
        close_button.clicked.connect(dialog.accept)
        buttons_row.addWidget(close_button)
        layout.addLayout(buttons_row)
        dialog.exec()

    def _edit_selected_timestamps(self):
        segment = self._selected_segment()
        if segment is None:
            QMessageBox.information(self, "タイムスタンプ編集", "先に学習記録を選択してください。")
            return
        self._edit_selected_timestamps_for(segment)

    def _edit_timestamp_from_table(self, table: QTableWidget, timestamps, parent_dialog: QDialog):
        row = table.currentRow()
        if row < 0:
            return
        item = table.item(row, 0)
        if item is None:
            return
        timestamp_id = int(item.text())
        timestamp = next((t for t in timestamps if t.timestamp_id == timestamp_id), None)
        if timestamp is not None:
            self._edit_timestamp_record(timestamp)
            parent_dialog.accept()

    def _edit_timestamp_record(self, timestamp):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"タイムスタンプを編集 - ID {timestamp.timestamp_id}")
        dialog.resize(520, 380)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        at_edit = QDateTimeEdit()
        at_edit.setCalendarPopup(True)
        at_edit.setDisplayFormat("yyyy/MM/dd HH:mm:ss")
        at_edit.setDateTime(QDateTime.fromSecsSinceEpoch(int(timestamp.at.timestamp())))
        location_edit = QLineEdit(timestamp.location)
        unit_edit = QLineEdit(timestamp.unit)
        subject_edit = QLineEdit(timestamp.subject)
        material_edit = QLineEdit(timestamp.material)
        form.addRow("時刻", at_edit)
        form.addRow("学習位置", location_edit)
        form.addRow("学習単位", unit_edit)
        form.addRow("科目", subject_edit)
        form.addRow("教材", material_edit)
        layout.addLayout(form)
        layout.addWidget(QLabel("更新履歴に変更前・変更後の値を保存します。"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not self.writer:
            QMessageBox.warning(self, "保存できません", "StudyTracker DBを更新できる状態ではありません。")
            return
        at = datetime.fromtimestamp(at_edit.dateTime().toSecsSinceEpoch()).astimezone()
        linked_segment = next((
            segment for segment in self.all_segments
            if segment.session_id == timestamp.session_id and segment.start == timestamp.segment_start_at
        ), None)
        if linked_segment is not None and not (linked_segment.start <= at <= linked_segment.end):
            QMessageBox.warning(self, "時刻の入力エラー", "タイムスタンプの時刻は、関連する学習記録の開始～終了時刻内にしてください。")
            return
        try:
            self.writer.update_timestamp(timestamp.timestamp_id, {
                "at": at.isoformat(timespec="seconds"),
                "location": location_edit.text().strip(),
                "unit": unit_edit.text().strip(),
                "subject": subject_edit.text().strip(),
                "material": material_edit.text().strip(),
            })
            self._reload()
            self.status.setText(f"タイムスタンプ {timestamp.timestamp_id} を更新し、変更履歴へ記録しました。")
        except Exception as exc:
            QMessageBox.critical(self, "タイムスタンプの保存失敗", str(exc))

    def _show_history(self):
        if not self.writer:
            QMessageBox.information(self, "更新履歴", "先に書き込み可能なStudyTracker DBを開いてください。")
            return
        entries = self.writer.read_history()
        dialog = QDialog(self)
        dialog.setWindowTitle("更新履歴（新しい順）")
        dialog.resize(1150, 560)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["履歴ID", "変更日時", "操作", "対象", "対象ID", "変更内容（前 → 後）"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for entry in entries:
            row = table.rowCount()
            table.insertRow(row)
            before = entry["before_json"]
            after = entry["after_json"]
            values = [entry["id"], entry["changed_at"], entry["action"], entry["entity_type"], entry["entity_id"], f"{before}  →  {after}"]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if col == 5:
                    cell.setToolTip(f"変更前:\n{before}\n\n変更後:\n{after}")
                table.setItem(row, col, cell)
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, 1)
        close_button = QPushButton("閉じる")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def _edit_selected_actual_scope(self):
        segment = self._selected_segment()
        if segment is None:
            QMessageBox.information(self, "実施範囲", "先に学習記録を選択してください。")
            return
        self._edit_actual_scope(segment)

    def _edit_actual_scope(self, segment: Segment):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"実施範囲 - Segment {segment.segment_id}")
        dialog.resize(620, 360)
        layout = QVBoxLayout(dialog)
        info = QFormLayout()
        info.addRow("科目", QLabel(segment.subject or "(未設定)"))
        info.addRow("教材", QLabel(segment.material or "(未設定)"))
        info.addRow("学習位置", QLabel(segment.position or "(未設定)"))
        info.addRow("学習単位", QLabel(segment.unit or "(未設定)"))
        planned = QLabel(segment.scope or "(未設定)")
        planned.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        planned.setWordWrap(True)
        info.addRow("学習予定範囲", planned)
        layout.addLayout(info)
        layout.addWidget(QLabel("実施範囲"))
        editor = QPlainTextEdit()
        editor.setPlaceholderText("例: p.21-30, p.33 / 問1-20 / section 2-3")
        editor.setPlainText(self.actual_scopes.get(segment.segment_id, ""))
        layout.addWidget(editor, 1)
        hint = QLabel("実施範囲はStudyTracker本体と共有するSQLite DBへ保存されます。StudyTracker実行中に保存できない場合は再試行してください。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        clear_btn = buttons.addButton("実施範囲を消去", QDialogButtonBox.ButtonRole.ResetRole)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        clear_btn.clicked.connect(editor.clear)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        value = editor.toPlainText().strip()
        if not self.writer:
            QMessageBox.warning(self, "保存できません", "StudyTracker DBを更新できる状態ではありません。")
            return
        try:
            self.writer.set_actual_scope(segment.segment_id, value)
            self.actual_scopes[segment.segment_id] = value
            self._reload()
            self.status.setText(f"Segment {segment.segment_id} の実施範囲を共有DBへ保存しました。")
        except Exception as exc:
            QMessageBox.critical(self, "実施範囲の保存失敗", str(exc))

    def _export_csv(self):
        if not self.filtered:
            QMessageBox.information(self, "CSV出力", "出力対象がありません。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "CSV保存", "study_records.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow([
                    "ID", "開始", "終了", "時間秒", "Active", "学習区分", "科目", "教材",
                    "学習位置", "学習単位", "学習予定範囲", "実施範囲", "備考", "Session", "Day"
                ])
                for s in self.filtered:
                    w.writerow([
                        s.segment_id, s.start.isoformat(), s.end.isoformat(), round(s.duration_seconds, 3), int(s.active),
                        s.category, s.subject, s.material, s.position, s.unit, s.scope,
                        self.actual_scopes.get(s.segment_id, ""), " / ".join(n for n in s.notes if n),
                        s.session_id, s.day.isoformat(),
                    ])
            self.status.setText(f"CSVを保存しました: {path}")
        except OSError as exc:
            QMessageBox.critical(self, "CSV出力失敗", str(exc))
