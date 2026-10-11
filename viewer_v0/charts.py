from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QSizePolicy, QWidget


JST = timezone(timedelta(hours=9))


class BaseChart(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.setMinimumSize(480, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._empty = True

    def _setup(self, p: QPainter):
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), self.palette().base())
        p.setPen(self.palette().text().color())
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSize(max(10, f.pointSize() + 1))
        p.setFont(f)
        p.drawText(QRectF(14, 10, self.width() - 28, 24), Qt.AlignmentFlag.AlignLeft, self.title)

    def _empty_message(self, p: QPainter):
        p.setFont(self.font())
        p.setPen(self.palette().mid().color())
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "データなし")


class BarChart(BaseChart):
    """Horizontal/vertical bar chart with explicit axes and value labels."""

    def __init__(self, title: str, horizontal: bool = True, parent=None):
        super().__init__(title, parent)
        self.horizontal = horizontal
        self.items: list[tuple[str, float]] = []

    def set_data(self, items: list[tuple[str, float]]):
        self.items = items[:12]
        self._empty = not self.items
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        self._setup(p)
        if not self.items:
            self._empty_message(p)
            return

        text_color = self.palette().text().color()
        grid_color = self.palette().mid().color()
        bar_color = self.palette().highlight()
        maxv = max(v for _, v in self.items) or 1.0

        if self.horizontal:
            left = 156
            right = 92
            top = 48
            bottom = 48
            plot = QRectF(
                left, top,
                max(80.0, self.width() - left - right),
                max(80.0, self.height() - top - bottom),
            )
            row_h = plot.height() / len(self.items)
            fm = QFontMetrics(p.font())

            p.setPen(QPen(grid_color, 1))
            p.drawLine(plot.bottomLeft(), plot.bottomRight())
            for tick in range(4):
                ratio = tick / 3
                x = plot.left() + plot.width() * ratio
                p.drawLine(x, plot.top(), x, plot.bottom())
                p.setPen(text_color)
                p.drawText(
                    QRectF(x - 38, plot.bottom() + 7, 76, 20),
                    Qt.AlignmentFlag.AlignHCenter,
                    _duration(maxv * ratio),
                )
                p.setPen(QPen(grid_color, 1))

            for i, (label, value) in enumerate(self.items):
                y = plot.top() + i * row_h + row_h * 0.18
                h = max(16.0, row_h * 0.62)
                w = plot.width() * value / maxv
                label_rect = QRectF(8, y, plot.left() - 18, h)
                value_rect = QRectF(self.width() - right + 4, y, right - 8, h)
                label_text = fm.elidedText(label, Qt.TextElideMode.ElideRight, int(label_rect.width()))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(bar_color)
                p.drawRoundedRect(QRectF(plot.left(), y, max(3.0, w), h), 4, 4)
                p.setPen(text_color)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, label_text)
                p.drawText(value_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, _duration(value))
        else:
            left = 50
            right = 24
            top = 48
            bottom = 62
            plot = QRectF(
                left, top,
                max(80.0, self.width() - left - right),
                max(80.0, self.height() - top - bottom),
            )
            bar_w = plot.width() / len(self.items)
            base = plot.bottom()
            fm = QFontMetrics(p.font())

            p.setPen(QPen(grid_color, 1))
            p.drawLine(plot.bottomLeft(), plot.bottomRight())
            for tick in range(4):
                ratio = tick / 3
                y = plot.bottom() - plot.height() * ratio
                p.drawLine(plot.left(), y, plot.right(), y)
                p.setPen(text_color)
                p.drawText(
                    QRectF(4, y - 10, left - 10, 20),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    _duration(maxv * ratio),
                )
                p.setPen(QPen(grid_color, 1))

            for i, (label, value) in enumerate(self.items):
                x = plot.left() + i * bar_w + bar_w * 0.2
                w = bar_w * 0.6
                h = plot.height() * value / maxv
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(bar_color)
                p.drawRoundedRect(QRectF(x, base - h, w, h), 3, 3)
                p.setPen(text_color)
                label_text = fm.elidedText(label, Qt.TextElideMode.ElideRight, int(w + 20))
                p.drawText(QRectF(x - 10, base + 6, w + 20, 24), Qt.AlignmentFlag.AlignHCenter, label_text)


class LineChart(BaseChart):
    """Daily trend chart with line/bar display options and adequate axis space."""

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.items: list[tuple[date, float]] = []
        self.display_mode = "line"

    def set_data(self, items: list[tuple[date, float]], display_mode: str = "line"):
        self.items = sorted(items)
        self.display_mode = display_mode if display_mode in ("line", "bar") else "line"
        self._empty = not self.items
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        self._setup(p)
        if not self.items:
            self._empty_message(p)
            return

        left, right, top, bottom = 76, 26, 48, 76
        plot = QRectF(left, top, max(120.0, self.width() - left - right), max(100.0, self.height() - top - bottom))
        maxv = max(v for _, v in self.items) or 1.0
        text_color = self.palette().text().color()
        grid_color = self.palette().mid().color()
        accent = self.palette().highlight().color()

        for tick in range(5):
            ratio = tick / 4
            y = plot.bottom() - plot.height() * ratio
            p.setPen(QPen(grid_color, 1))
            p.drawLine(plot.left(), y, plot.right(), y)
            p.setPen(text_color)
            p.drawText(QRectF(2, y - 10, left - 10, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, _duration(maxv * ratio))

        p.setPen(QPen(text_color, 1.4))
        p.drawLine(plot.bottomLeft(), plot.bottomRight())
        p.drawLine(plot.bottomLeft(), plot.topLeft())
        count = len(self.items)
        coords = []
        for i, (day, value) in enumerate(self.items):
            x = plot.left() + plot.width() * (i / max(1, count - 1))
            y = plot.bottom() - plot.height() * value / maxv
            coords.append((x, y, value))

        if self.display_mode == "bar":
            slot = plot.width() / max(1, count)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent)
            for i, (x, y, _value) in enumerate(coords):
                bar_w = max(3.0, min(34.0, slot * 0.62))
                p.drawRoundedRect(QRectF(x - bar_w / 2, y, bar_w, plot.bottom() - y), 3, 3)
        else:
            p.setPen(QPen(accent, 2.5))
            for a, b in zip(coords, coords[1:]):
                p.drawLine(a[0], a[1], b[0], b[1])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent)
            for x, y, _value in coords:
                p.drawEllipse(QRectF(x - 3.5, y - 3.5, 7, 7))

        max_labels = max(2, min(8, int(plot.width() / 95)))
        if count <= max_labels:
            indices = list(range(count))
        else:
            step = (count - 1) / (max_labels - 1)
            indices = sorted({round(i * step) for i in range(max_labels)})
        for i in indices:
            day = self.items[i][0]
            x = coords[i][0]
            p.setPen(text_color)
            p.drawLine(x, plot.bottom(), x, plot.bottom() + 5)
            p.drawText(QRectF(x - 45, plot.bottom() + 9, 90, 22), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, day.strftime("%m/%d"))

        p.drawText(QRectF(plot.left(), self.height() - 25, plot.width(), 18), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, "日付")
        p.drawText(QRectF(plot.left(), plot.top() - 20, plot.width(), 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "勉強時間")

def _duration(seconds: float) -> str:
    sec = int(round(seconds))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}" if h else f"{m}:{s:02d}"


class RateChart(BaseChart):
    """Study-rate line chart with time ticks and hover details."""

    def __init__(self, title: str = "時間当たりの勉強量の推移", parent=None):
        super().__init__(title, parent)
        self.items: list[tuple[datetime, float]] = []
        self.planned_items: list[tuple[datetime, float]] = []
        self._actual_coords: list[tuple[float, float, datetime, float]] = []
        self._planned_coords: list[tuple[float, float, datetime, float]] = []
        self._hover_key: tuple[str, datetime] | None = None
        self._hover_x: float | None = None
        self._hover_y: float | None = None
        self._last_plot: QRectF | None = None
        self._x_min: datetime | None = None
        self._x_max: datetime | None = None
        self._base_x_min: datetime | None = None
        self._base_x_max: datetime | None = None
        self._view_zoom = 1.0
        self._view_position = 0.0
        self.display_mode = "line"
        self.setToolTip("マウスホイール: 時間軸を拡大/縮小、Shift+ホイール: 時間軸を移動")
        self.setMouseTracking(True)

    def set_data(self, items, planned_items=(), display_mode: str = "line"):
        self.items = sorted(items, key=lambda x: x[0])
        self.planned_items = sorted(planned_items, key=lambda x: x[0])
        self.display_mode = display_mode if display_mode in ("line", "bar") else "line"
        self._view_zoom = 1.0
        self._view_position = 0.0
        self._empty = not self.items and not self.planned_items
        self._hover_key = None
        self._hover_x = None
        self._hover_y = None
        QToolTip.hideText()
        self.update()

    @staticmethod
    def _nice_step(total_seconds: float, pixels: float) -> int:
        """Choose a human-friendly time tick interval sized to the chart width."""
        if total_seconds <= 1:
            return 1
        target_ticks = max(3, min(10, int(pixels / 90)))
        target = total_seconds / target_ticks
        candidates = [
            1, 2, 5, 10, 15, 30,
            60, 2 * 60, 5 * 60, 10 * 60, 15 * 60, 30 * 60,
            60 * 60, 2 * 60 * 60, 3 * 60 * 60, 6 * 60 * 60, 12 * 60 * 60,
            24 * 60 * 60,
        ]
        return min(candidates, key=lambda x: abs(math.log(max(1.0, x) / target)))

    @staticmethod
    def _floor_local(dt: datetime, step_seconds: int) -> datetime:
        local = dt.astimezone()
        base = local.replace(second=0, microsecond=0)
        if step_seconds < 60:
            epoch = int(local.timestamp())
            floored = epoch - (epoch % step_seconds)
            return datetime.fromtimestamp(floored, tz=local.tzinfo)
        if step_seconds % 60 == 0:
            minutes_step = max(1, step_seconds // 60)
            total_minutes = local.hour * 60 + local.minute
            floored_minutes = total_minutes - (total_minutes % minutes_step)
            day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
            return day_start + timedelta(minutes=floored_minutes)
        return base

    @classmethod
    def _time_ticks(cls, x_min: datetime, x_max: datetime, width: float):
        total = max(1.0, (x_max - x_min).total_seconds())
        step = cls._nice_step(total, width)
        first = cls._floor_local(x_min, step)
        if first < x_min:
            first += timedelta(seconds=step)
        ticks: list[datetime] = []
        current = first
        limit = x_max + timedelta(milliseconds=1)
        guard = 0
        while current <= limit and guard < 1000:
            ticks.append(current)
            current += timedelta(seconds=step)
            guard += 1
        if not ticks:
            ticks = [x_min, x_max] if x_min != x_max else [x_min]
        return ticks, step

    @staticmethod
    def _time_label(at: datetime, step: int) -> str:
        local = at.astimezone()
        if step < 60:
            return local.strftime("%H:%M:%S")
        if step >= 24 * 60 * 60:
            return local.strftime("%m/%d")
        if local.hour == 0 and local.minute == 0 and step >= 60 * 60:
            return local.strftime("%m/%d\n%H:%M")
        return local.strftime("%H:%M")

    def _draw_series(self, p, points, plot, maxv, color, *, dashed=False, point_radius=3.5):
        if not points:
            return []
        x_min = self._x_min
        x_max = self._x_max
        if x_min is None or x_max is None:
            return []
        total = max(1.0, (x_max - x_min).total_seconds())
        coords = []
        for at, value in points:
            x = plot.left() if total <= 1 else plot.left() + plot.width() * (at - x_min).total_seconds() / total
            y = plot.bottom() - plot.height() * max(0.0, value) / maxv
            coords.append((x, y, at, value))
        pen = QPen(color, 2.4)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        for prev, cur in zip(coords, coords[1:]):
            p.drawLine(prev[0], prev[1], cur[0], cur[1])
        if not dashed:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            for x, y, _at, _value in coords:
                p.drawEllipse(QRectF(x - point_radius, y - point_radius, point_radius * 2, point_radius * 2))
        return coords

    def _nearest_point(self, pos):
        candidates = []
        for kind, coords in (("actual", self._actual_coords), ("planned", self._planned_coords)):
            for x, y, at, value in coords:
                dx = abs(pos.x() - x)
                if dx <= max(18.0, self.width() / 25.0):
                    candidates.append((dx, abs(pos.y() - y), kind, x, y, at, value))
        if not candidates:
            return None
        return min(candidates, key=lambda v: (v[0], v[1]))

    @staticmethod
    def _tooltip_text(nearest, actual_coords, planned_coords):
        _dx, _dy, kind, x, y, at, value = nearest
        local = at.astimezone()
        lines = [
            f"時刻: {local.strftime('%Y/%m/%d %H:%M:%S')}",
        ]
        same_actual = min(actual_coords, key=lambda p: abs((p[2] - at).total_seconds()), default=None)
        same_planned = min(planned_coords, key=lambda p: abs((p[2] - at).total_seconds()), default=None)
        tolerance = 1.0
        if same_actual is not None and abs((same_actual[2] - at).total_seconds()) <= tolerance:
            lines.append(f"実績: {same_actual[3]:.2f} 学習単位/時")
        elif kind == "actual":
            lines.append(f"実績: {value:.2f} 学習単位/時")
        if same_planned is not None and abs((same_planned[2] - at).total_seconds()) <= tolerance:
            lines.append(f"予定: {same_planned[3]:.2f} 学習単位/時")
        elif kind == "planned":
            lines.append(f"予定: {value:.2f} 学習単位/時")
        return "\n".join(lines)

    def mouseMoveEvent(self, event):
        nearest = self._nearest_point(event.position())
        if nearest is None:
            if self._hover_key is not None:
                self._hover_key = None
                self._hover_x = None
                self._hover_y = None
                QToolTip.hideText()
                self.update()
            super().mouseMoveEvent(event)
            return
        _dx, _dy, kind, x, y, at, _value = nearest
        key = (kind, at)
        self._hover_key = key
        self._hover_x = x
        self._hover_y = y
        QToolTip.showText(
            self.mapToGlobal(event.position().toPoint()),
            self._tooltip_text(nearest, self._actual_coords, self._planned_coords),
            self,
        )
        self.update()
        event.accept()

    def leaveEvent(self, event):
        self._hover_key = None
        self._hover_x = None
        self._hover_y = None
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        all_points = self.items + self.planned_items
        if not all_points or self._last_plot is None:
            super().wheelEvent(event)
            return
        base_start = min(at for at, _ in all_points)
        base_end = max(at for at, _ in all_points)
        full_span = max(1.0, (base_end - base_start).total_seconds())
        view_span = max(1.0, full_span / self._view_zoom)
        current_start = base_start + timedelta(seconds=(full_span - view_span) * self._view_position)
        current_end = current_start + timedelta(seconds=view_span)
        delta = event.angleDelta().y()
        if not delta:
            super().wheelEvent(event)
            return
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            direction = -1 if delta > 0 else 1
            new_start = current_start + timedelta(seconds=direction * view_span * 0.12)
            new_end = new_start + timedelta(seconds=view_span)
        else:
            ratio = max(0.0, min(1.0, (event.position().x() - self._last_plot.left()) / max(1.0, self._last_plot.width())))
            anchor = current_start + (current_end - current_start) * ratio
            new_span = max(min(60.0, full_span), min(full_span, view_span * (0.8 if delta > 0 else 1.25)))
            new_start = anchor - timedelta(seconds=new_span * ratio)
            new_end = new_start + timedelta(seconds=new_span)
        if new_start < base_start:
            new_end += base_start - new_start
            new_start = base_start
        if new_end > base_end:
            new_start -= new_end - base_end
            new_end = base_end
        new_start = max(base_start, new_start)
        new_end = min(base_end, new_end)
        effective_span = max(1.0, (new_end - new_start).total_seconds())
        self._view_zoom = max(1.0, full_span / effective_span)
        available = max(1.0, full_span - effective_span)
        self._view_position = max(0.0, min(1.0, (new_start - base_start).total_seconds() / available))
        self._hover_key = None
        self._hover_x = None
        self._hover_y = None
        QToolTip.hideText()
        self.update()
        event.accept()

    def paintEvent(self, _event):
        p = QPainter(self)
        self._setup(p)
        self._actual_coords = []
        self._planned_coords = []
        if not self.items and not self.planned_items:
            p.setFont(self.font())
            p.setPen(self.palette().mid().color())
            p.drawText(
                QRectF(16, 42, self.width() - 32, self.height() - 52),
                Qt.AlignmentFlag.AlignCenter,
                "実施範囲またはタイムスタンプから時間当たりの勉強量を計算できません",
            )
            return

        left, right, top, bottom = 72, 28, 48, 68
        plot = QRectF(
            left, top,
            max(140.0, self.width() - left - right),
            max(110.0, self.height() - top - bottom),
        )
        self._last_plot = plot
        all_points = self.items + self.planned_items
        self._base_x_min = min(at for at, _ in all_points)
        self._base_x_max = max(at for at, _ in all_points)
        full_span = max(1.0, (self._base_x_max - self._base_x_min).total_seconds())
        view_span = max(1.0, full_span / self._view_zoom)
        view_offset = max(0.0, full_span - view_span) * self._view_position
        self._x_min = self._base_x_min + timedelta(seconds=view_offset)
        self._x_max = min(self._base_x_max, self._x_min + timedelta(seconds=view_span))
        visible_items = [(at, value) for at, value in self.items if self._x_min <= at <= self._x_max]
        visible_planned = [(at, value) for at, value in self.planned_items if self._x_min <= at <= self._x_max]
        visible_points = visible_items + visible_planned
        maxv = max((v for _, v in visible_points), default=max((v for _, v in all_points), default=1.0)) or 1.0
        text_color = self.palette().text().color()
        grid_color = self.palette().mid().color()
        accent = self.palette().highlight().color()
        planned_color = self.palette().link().color()

        for tick in range(5):
            ratio = tick / 4
            y = plot.bottom() - plot.height() * ratio
            p.setPen(QPen(grid_color, 1))
            p.drawLine(plot.left(), y, plot.right(), y)
            p.setPen(text_color)
            p.drawText(
                QRectF(2, y - 10, left - 10, 20),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{maxv * ratio:.0f}",
            )

        p.setPen(QPen(text_color, 1.4))
        p.drawLine(plot.bottomLeft(), plot.bottomRight())
        p.drawLine(plot.bottomLeft(), plot.topLeft())

        self._planned_coords = self._draw_series(p, visible_planned, plot, maxv, planned_color, dashed=True)
        if self.display_mode == "bar" and visible_items:
            total_for_bars = max(1.0, (self._x_max - self._x_min).total_seconds())
            self._actual_coords = []
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent)
            bar_width = max(4.0, min(18.0, plot.width() / max(1, len(visible_items)) * 0.55))
            for at, value in visible_items:
                x = plot.left() + plot.width() * (at - self._x_min).total_seconds() / total_for_bars
                y = plot.bottom() - plot.height() * max(0.0, value) / maxv
                p.drawRoundedRect(QRectF(x - bar_width / 2, y, bar_width, max(1.0, plot.bottom() - y)), 2, 2)
                self._actual_coords.append((x, y, at, value))
        else:
            self._actual_coords = self._draw_series(p, visible_items, plot, maxv, accent, dashed=False)

        ticks, step = self._time_ticks(self._x_min, self._x_max, plot.width())
        total = max(1.0, (self._x_max - self._x_min).total_seconds())
        for at in ticks:
            x = plot.left() if total <= 1 else plot.left() + plot.width() * (at - self._x_min).total_seconds() / total
            if x < plot.left() - 1 or x > plot.right() + 1:
                continue
            p.setPen(QPen(grid_color, 1))
            p.drawLine(x, plot.top(), x, plot.bottom())
            p.setPen(text_color)
            p.drawLine(x, plot.bottom(), x, plot.bottom() + 5)
            label = self._time_label(at, step)
            p.drawText(
                QRectF(x - 46, plot.bottom() + 8, 92, 34),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label,
            )

        if self._hover_x is not None and self._hover_y is not None:
            p.setPen(QPen(text_color, 1, Qt.PenStyle.DashLine))
            p.drawLine(self._hover_x, plot.top(), self._hover_x, plot.bottom())
            p.setBrush(self.palette().base())
            p.drawEllipse(QRectF(self._hover_x - 6, self._hover_y - 6, 12, 12))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(accent, 2.5))
            p.drawEllipse(QRectF(self._hover_x - 5, self._hover_y - 5, 10, 10))

        legend_y = 28
        if self.items:
            p.setPen(QPen(accent, 2.4))
            p.drawLine(plot.right() - 250, legend_y, plot.right() - 220, legend_y)
            p.setPen(text_color)
            p.drawText(QRectF(plot.right() - 214, legend_y - 9, 90, 18), Qt.AlignmentFlag.AlignLeft, "実績")
        if self.planned_items:
            pen = QPen(planned_color, 2.2)
            pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(plot.right() - 110, legend_y, plot.right() - 80, legend_y)
            p.setPen(text_color)
            p.drawText(QRectF(plot.right() - 74, legend_y - 9, 74, 18), Qt.AlignmentFlag.AlignLeft, "予定")

        p.setPen(text_color)
        p.drawText(
            QRectF(plot.left(), self.height() - 24, plot.width(), 18),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "時刻",
        )
        p.drawText(
            QRectF(plot.left(), plot.top() - 20, plot.width(), 18),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "学習単位/時",
        )
        p.drawText(
            QRectF(plot.left(), 28, 300, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "ホイール: 拡大/縮小　Shift+ホイール: 横移動",
        )


class TimelineChart(BaseChart):
    """Day rows over a 24-hour clock axis; wheel zooms and Shift+wheel pans."""

    def __init__(self, title: str = "タイムライン", parent=None):
        super().__init__(title, parent)
        self.segments = []
        self.timestamps = []
        self._hits: list[tuple[object, QRectF]] = []
        self._timestamp_hits: list[tuple[object, QRectF]] = []
        self._hover_segment = None
        self._hover_timestamp = None
        self.segment_clicked = None
        self.timestamp_clicked = None
        self.range_selected = None
        self._hour_start = 0.0
        self._hour_end = 24.0
        self._last_plot: QRectF | None = None
        self._last_days = []
        self._drag_origin_x: float | None = None
        self._drag_current_x: float | None = None
        self.setMinimumSize(520, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    def set_data(self, segments, timestamps=()):
        self.segments = list(segments)
        self.timestamps = list(timestamps)
        self._hits = []
        self._timestamp_hits = []
        self._hover_segment = None
        self._hover_timestamp = None
        self._drag_origin_x = None
        self._drag_current_x = None
        self._hour_start, self._hour_end = 0.0, 24.0
        self.setMinimumHeight(max(260, min(1400, len(self._days_for_segments(self.segments)) * 34 + 105)))
        self.setToolTip("マウスホイール: 時刻方向に拡大/縮小、Shift+ホイール: 時刻方向に移動")
        self.update()

    def reset_view(self):
        self._hour_start, self._hour_end = 0.0, 24.0
        self.update()

    def set_view_hours(self, start_hour: float, end_hour: float):
        start = max(0.0, min(24.0, float(start_hour)))
        end = max(0.0, min(24.0, float(end_hour)))
        if end <= start:
            return
        if end - start < 0.25:
            end = min(24.0, start + 0.25)
            start = max(0.0, end - 0.25)
        self._hour_start, self._hour_end = start, end
        self.update()

    def _hour_for_x(self, x: float) -> float:
        if self._last_plot is None:
            return 0.0
        ratio = max(0.0, min(1.0, (x - self._last_plot.left()) / max(1.0, self._last_plot.width())))
        return self._hour_start + (self._hour_end - self._hour_start) * ratio

    @staticmethod
    def _days_for_segments(segments):
        days = set()
        for segment in segments:
            first = segment.start.astimezone(JST).date()
            last_instant = max(segment.start, segment.end - timedelta(microseconds=1))
            last = last_instant.astimezone(JST).date()
            current = first
            while current <= last:
                days.add(current)
                current += timedelta(days=1)
        return sorted(days)

    @staticmethod
    def _local_interval(segment, day):
        """Yield the part of a segment intersecting a local calendar day in seconds."""
        local_start = segment.start.astimezone(JST)
        local_end = segment.end.astimezone(JST)
        day_start = datetime.combine(day, datetime.min.time(), tzinfo=JST)
        day_end = day_start + timedelta(days=1)
        begin = max(local_start, day_start)
        finish = min(local_end, day_end)
        if finish <= begin:
            return None
        start_seconds = (begin - day_start).total_seconds()
        end_seconds = (finish - day_start).total_seconds()
        return start_seconds, end_seconds

    @staticmethod
    def _timestamp_text(t) -> str:
        local = t.at.astimezone().strftime("%Y/%m/%d %H:%M:%S")
        return "\n".join((
            local,
            f"学習位置: {t.location}",
            f"学習単位: {t.unit or '(未設定)'}",
            f"科目: {t.subject or '(未設定)'}",
            f"教材: {t.material or '(未設定)'}",
            "クリックしてタイムスタンプを編集できます。",
        ))

    @staticmethod
    def _segment_text(segment, timestamps):
        lines = [
            f"{segment.subject or '(科目未設定)'} / {segment.material or '(教材未設定)'}",
            f"開始: {segment.start.astimezone().strftime('%Y/%m/%d %H:%M:%S')}",
            f"終了: {segment.end.astimezone().strftime('%Y/%m/%d %H:%M:%S')}",
            f"時間: {_duration(segment.duration_seconds)}",
            f"状態: {'Active' if segment.active else 'Passive'}",
            f"学習位置: {segment.position or '(未設定)'}",
            f"学習単位: {segment.unit or '(未設定)'}",
            f"学習予定範囲: {segment.scope or '(未設定)'}",
            f"実施範囲: {segment.actual_scope or '(未入力)'}",
        ]
        relevant = [t for t in timestamps if t.session_id == segment.session_id and segment.start <= t.at <= segment.end]
        if relevant:
            lines.append("タイムスタンプ: " + ", ".join(f"{t.at.astimezone().strftime('%H:%M:%S')} → {t.location}" for t in relevant))
        return "\n".join(lines)

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._drag_origin_x is not None and self._last_plot is not None:
            self._drag_current_x = max(self._last_plot.left(), min(self._last_plot.right(), pos.x()))
            QToolTip.hideText()
            self.update()
            return
        for timestamp, rect in reversed(self._timestamp_hits):
            if rect.contains(pos):
                if self._hover_timestamp != timestamp.timestamp_id:
                    self._hover_timestamp = timestamp.timestamp_id
                    self._hover_segment = None
                    QToolTip.showText(self.mapToGlobal(pos.toPoint()), self._timestamp_text(timestamp), self)
                    self.update()
                return
        for segment, rect in reversed(self._hits):
            if rect.contains(pos):
                if self._hover_segment != segment.segment_id:
                    self._hover_segment = segment.segment_id
                    self._hover_timestamp = None
                    QToolTip.showText(self.mapToGlobal(pos.toPoint()), self._segment_text(segment, self.timestamps), self)
                    self.update()
                return
        if self._hover_segment is not None or self._hover_timestamp is not None:
            self._hover_segment = None
            self._hover_timestamp = None
            QToolTip.hideText()
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_segment = None
        self._hover_timestamp = None
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        if self._last_plot is None or not self.segments:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if not delta:
            super().wheelEvent(event)
            return
        span = max(0.05, self._hour_end - self._hour_start)
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            shift = -1 if delta > 0 else 1
            move = max(0.25, span * 0.12) * shift
            new_start = self._hour_start + move
            new_end = self._hour_end + move
            if new_start < 0:
                new_end -= new_start
                new_start = 0.0
            if new_end > 24:
                new_start -= (new_end - 24)
                new_end = 24.0
            self._hour_start = max(0.0, new_start)
            self._hour_end = min(24.0, new_end)
        else:
            anchor = self._hour_for_x(event.position().x())
            factor = 0.80 if delta > 0 else 1.25
            new_span = max(0.25, min(24.0, span * factor))
            relative = (anchor - self._hour_start) / span if span else 0.5
            new_start = anchor - relative * new_span
            new_end = new_start + new_span
            if new_start < 0:
                new_end -= new_start
                new_start = 0.0
            if new_end > 24:
                new_start -= new_end - 24
                new_end = 24.0
            self._hour_start = max(0.0, new_start)
            self._hour_end = min(24.0, new_end)
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._last_plot is not None and self._last_plot.contains(event.position()):
            self._drag_origin_x = max(self._last_plot.left(), min(self._last_plot.right(), event.position().x()))
            self._drag_current_x = self._drag_origin_x
            QToolTip.hideText()
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_origin_x is not None:
            start_x = self._drag_origin_x
            end_x = self._drag_current_x if self._drag_current_x is not None else start_x
            self._drag_origin_x = None
            self._drag_current_x = None
            if abs(end_x - start_x) >= 8:
                start_hour = self._hour_for_x(min(start_x, end_x))
                end_hour = self._hour_for_x(max(start_x, end_x))
                if end_hour > start_hour and self.range_selected is not None:
                    self.range_selected(start_hour, end_hour)
                self.update()
                event.accept()
                return
            pos = event.position()
            for timestamp, rect in reversed(self._timestamp_hits):
                if rect.contains(pos):
                    if self.timestamp_clicked is not None:
                        self.timestamp_clicked(timestamp)
                    self.update()
                    event.accept()
                    return
            for segment, rect in reversed(self._hits):
                if rect.contains(pos):
                    if self.segment_clicked is not None:
                        self.segment_clicked(segment)
                    break
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        self._setup(p)
        self._hits = []
        self._timestamp_hits = []
        if not self.segments:
            self._empty_message(p)
            return

        local_days = self._days_for_segments(self.segments)
        if not local_days:
            self._empty_message(p)
            return
        self._last_days = local_days
        left, right, top, bottom = 92, 22, 48, 38
        plot = QRectF(left, top, max(120.0, self.width() - left - right), max(120.0, self.height() - top - bottom))
        self._last_plot = plot
        self._last_view_range = (self._hour_start, self._hour_end)
        lane_h = max(28.0, min(36.0, plot.height() / max(1, len(local_days))))
        text_color = self.palette().text().color()
        grid_color = self.palette().mid().color()
        active_color = self.palette().highlight()
        passive_color = self.palette().mid()
        hover_color = self.palette().link().color()
        fm = QFontMetrics(p.font())
        visible_hours = max(0.01, self._hour_end - self._hour_start)

        for row, day in enumerate(local_days):
            y = plot.top() + row * lane_h
            p.setPen(QPen(grid_color, 1))
            p.drawLine(plot.left(), y + lane_h, plot.right(), y + lane_h)
            p.setPen(text_color)
            p.drawText(QRectF(4, y, left - 12, lane_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, day.strftime('%Y/%m/%d'))

        tick_candidates = [0.25, 0.5, 1, 2, 3, 4, 6, 8, 12]
        tick_step = min(tick_candidates, key=lambda n: abs((plot.width() * n / visible_hours) - 100))
        first_tick = math.ceil((self._hour_start - 1e-9) / tick_step) * tick_step
        for hour in [first_tick + i * tick_step for i in range(100) if first_tick + i * tick_step <= self._hour_end + 1e-8]:
            x = plot.left() + plot.width() * (hour - self._hour_start) / visible_hours
            p.setPen(QPen(grid_color, 1))
            p.drawLine(x, plot.top(), x, plot.top() + lane_h * len(local_days))
            p.setPen(text_color)
            total_minutes = round(hour * 60)
            hour_label, minute_label = divmod(total_minutes, 60)
            label = f"{hour_label:02d}:{minute_label:02d}"
            p.drawText(QRectF(x - 34, plot.bottom() + 5, 68, 20), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)

        def x_for(seconds: float) -> float:
            hour = seconds / 3600.0
            return plot.left() + plot.width() * (hour - self._hour_start) / visible_hours

        for segment in self.segments:
            for row, day in enumerate(local_days):
                interval = self._local_interval(segment, day)
                if interval is None:
                    continue
                sec_start, sec_end = interval
                if sec_end / 3600 < self._hour_start or sec_start / 3600 > self._hour_end:
                    continue
                clipped_start = max(sec_start, self._hour_start * 3600)
                clipped_end = min(sec_end, self._hour_end * 3600)
                if clipped_end <= clipped_start:
                    continue
                y = plot.top() + row * lane_h + max(2.0, lane_h * 0.18)
                h = max(15.0, lane_h * 0.62)
                x1, x2 = x_for(clipped_start), x_for(clipped_end)
                rect = QRectF(x1, y, max(4.0, x2 - x1), h)
                self._hits.append((segment, rect))
                is_hover = self._hover_segment == segment.segment_id
                p.setPen(QPen(hover_color, 2) if is_hover else Qt.PenStyle.NoPen)
                p.setBrush(active_color if segment.active else passive_color)
                p.drawRoundedRect(rect, 4, 4)
                label = segment.subject or segment.material or '(未設定)'
                label = fm.elidedText(label, Qt.TextElideMode.ElideRight, max(0, int(rect.width() - 8)))
                if rect.width() >= 38:
                    p.setPen(self.palette().highlightedText().color() if segment.active else text_color)
                    p.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)

        segment_map = {(s.session_id, s.start): s for s in self.segments}
        for timestamp in self.timestamps:
            segment = segment_map.get((timestamp.session_id, timestamp.segment_start_at))
            if segment is None or not (segment.start <= timestamp.at <= segment.end):
                continue
            local_at = timestamp.at.astimezone(JST)
            row = local_at.date()
            if row not in local_days:
                continue
            hour = local_at.hour + local_at.minute / 60 + local_at.second / 3600
            if not self._hour_start <= hour <= self._hour_end:
                continue
            row_index = local_days.index(row)
            y = plot.top() + row_index * lane_h + max(2.0, lane_h * 0.18)
            h = max(15.0, lane_h * 0.62)
            x = x_for(hour * 3600)
            marker_color = self.palette().link().color()
            p.setPen(QPen(marker_color, 2))
            p.drawLine(x, y - 5, x, y + h + 5)
            marker_rect = QRectF(x - 7, y - 10, 14, h + 20)
            self._timestamp_hits.append((timestamp, marker_rect))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(marker_color)
            p.drawEllipse(QRectF(x - 4, y - 8, 8, 8))
            if len(self.timestamps) <= 48 or self.width() >= 1000:
                p.setPen(text_color)
                p.drawText(QRectF(x - 27, y - 28, 54, 18), Qt.AlignmentFlag.AlignHCenter, fm.elidedText(str(timestamp.location), Qt.TextElideMode.ElideRight, 54))

        if self._drag_origin_x is not None and self._drag_current_x is not None:
            x1, x2 = sorted((self._drag_origin_x, self._drag_current_x))
            selection = QRectF(x1, plot.top(), max(1.0, x2 - x1), lane_h * len(local_days))
            p.setPen(QPen(self.palette().link().color(), 1.5, Qt.PenStyle.DashLine))
            p.setBrush(self.palette().link().color())
            p.setOpacity(0.12)
            p.drawRect(selection)
            p.setOpacity(1.0)
            p.setBrush(Qt.BrushStyle.NoBrush)

        p.setPen(text_color)
        start_min = round(self._hour_start * 60)
        end_min = round(self._hour_end * 60)
        start_h, start_m = divmod(start_min, 60)
        end_h, end_m = divmod(end_min, 60)
        p.drawText(QRectF(plot.left(), 27, plot.width(), 16), Qt.AlignmentFlag.AlignLeft, f"時刻: {start_h:02d}:{start_m:02d}～{end_h:02d}:{end_m:02d}")
        p.drawText(QRectF(plot.right() - 330, 27, 330, 16), Qt.AlignmentFlag.AlignRight, "ホイール: 拡大/縮小　Shift+ホイール: 横移動　ドラッグ: 範囲拡大")

