"""可視化の部品。

方針（すべての画面で共通）：
- 系列の色は1色（青 #2a78d6）。時間の推移も内訳も「量の比較」なので、色で区別しない
- 文字は系列の色を使わず、文字用の色（主・副・控えめ）で書く
- 目盛り線は細く控えめに。棒は細め（最大24px）で、端を少し丸める
- 内訳は円グラフにせず、値の大きい順の横棒にする（分野が多いと円グラフは読めない）
- 時系列の棒グラフにはマウスを重ねると値が出る。数字は表でも見られるようにする
- グラフは自前で描く（QtChartsの分類軸は項目が多いとラベルを省略してしまい読めないため）
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ...core import clock

# 色（検証済みの既定パレットの明るい面用）
SERIES = QColor("#2a78d6")
SERIES_TRACK = QColor("#cde2fb")   # 同じ青の薄い段（メーターの未達部分）
SURFACE = QColor("#fcfcfb")
TEXT = QColor("#0b0b0b")
TEXT_SECONDARY = QColor("#52514e")
TEXT_MUTED = QColor("#898781")
GRID = QColor("#e1e0d9")
BASELINE = QColor("#c3c2b7")
GOOD = QColor("#0ca30c")
BORDER = "rgba(11, 11, 11, 0.10)"


def hours(seconds: int) -> float:
    return seconds / 3600


# --- 枠 ---------------------------------------------------------------------

class Panel(QFrame):
    """見出しつきの白い枠。"""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.setStyleSheet(
            f"#panel {{ background: {SURFACE.name()}; border: 1px solid {BORDER}; border-radius: 10px; }}"
        )
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 14)
        self.body.setSpacing(8)
        if title:
            self.title = QLabel(title, self)
            self.title.setStyleSheet(f"color: {TEXT_SECONDARY.name()}; font-weight: 600;")
            self.body.addWidget(self.title)


# --- 数字のタイル -----------------------------------------------------------

class StatTile(Panel):
    """ラベル・大きな値・補足の3段。"""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self.label = QLabel(label, self)
        self.label.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
        self.value = QLabel("—", self)
        font = self.value.font()
        font.setPointSize(font.pointSize() + 9)
        font.setBold(True)
        self.value.setFont(font)
        self.value.setStyleSheet(f"color: {TEXT.name()};")
        self.note = QLabel("", self)
        self.note.setStyleSheet(f"color: {TEXT_MUTED.name()};")
        self.note.setWordWrap(True)
        for widget in (self.label, self.value, self.note):
            self.body.addWidget(widget)
        self.body.addStretch(1)
        # 横に並べたタイルの高さをそろえる（中身は上詰め）
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def add_widget(self, widget: QWidget) -> None:
        """タイルの下に部品（メーターやボタン）を足す。伸縮の余白より上に入れる。"""
        self.body.insertWidget(self.body.count() - 1, widget)

    def set(self, value: str, note: str = "") -> None:
        self.value.setText(value)
        self.note.setText(note)
        self.note.setVisible(bool(note))


# --- メーター（割合の横棒） -------------------------------------------------

class Meter(QWidget):
    """割合を1本の横棒で示す。未達部分は同じ青の薄い段。1を超えた分は満杯で止める。"""

    def __init__(self, parent: QWidget | None = None, *, height: int = 10) -> None:
        super().__init__(parent)
        self.ratio = 0.0
        self.color = SERIES
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_ratio(self, ratio: float, *, color: QColor | None = None) -> None:
        self.ratio = max(0.0, float(ratio))
        self.color = color or SERIES
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(self.rect())
        radius = min(4.0, rect.height() / 2)
        painter.setBrush(SERIES_TRACK)
        painter.drawRoundedRect(rect, radius, radius)
        fill = min(1.0, self.ratio)
        if fill > 0:
            painter.setBrush(self.color)
            painter.drawRoundedRect(QRectF(rect.x(), rect.y(), rect.width() * fill, rect.height()), radius, radius)
        painter.end()


# --- 値の大きい順の横棒（内訳・進捗・正答率） -------------------------------

@dataclass(slots=True)
class BarItem:
    label: str
    ratio: float      # 棒の長さ（0〜1。最大値を1とした相対値でも、割合そのものでもよい）
    value: str        # 右に出す値
    note: str = ""    # 値の横の補足（割合など）
    tooltip: str = ""


class BarList(QWidget):
    """名前・棒・値の行を並べる。多すぎる項目は「その他」にまとめる（最大 limit 行）。"""

    def __init__(self, parent: QWidget | None = None, *, limit: int = 8, empty_text: str = "データがありません") -> None:
        super().__init__(parent)
        self.limit = limit
        self.empty_text = empty_text
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(6)
        self.grid.setColumnStretch(1, 1)

    def set_items(self, items: Sequence[BarItem], *, other: BarItem | None = None) -> None:
        clear_layout(self.grid)

        rows = list(items)
        if not rows:
            empty = QLabel(self.empty_text, self)
            empty.setStyleSheet(f"color: {TEXT_MUTED.name()};")
            self.grid.addWidget(empty, 0, 0, 1, 4)
            return
        if other is not None:
            rows = rows[: self.limit - 1] + [other]
        else:
            rows = rows[: self.limit]

        for row, item in enumerate(rows):
            name = QLabel(item.label, self)
            name.setStyleSheet(f"color: {TEXT.name()};")
            name.setMinimumWidth(90)
            name.setMaximumWidth(220)
            name.setToolTip(item.tooltip or item.label)
            meter = Meter(self, height=12)
            meter.set_ratio(item.ratio)
            meter.setToolTip(item.tooltip or f"{item.label}：{item.value}")
            value = QLabel(item.value, self)
            value.setStyleSheet(f"color: {TEXT.name()}; font-weight: 600;")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            note = QLabel(item.note, self)
            note.setStyleSheet(f"color: {TEXT_MUTED.name()};")
            note.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.grid.addWidget(name, row, 0)
            self.grid.addWidget(meter, row, 1)
            self.grid.addWidget(value, row, 2)
            self.grid.addWidget(note, row, 3)


# --- 時系列の棒グラフ -------------------------------------------------------

def nice_step(peak: float, ticks: int = 4) -> float:
    """目盛りの間隔を 1・2・2.5・5 ×10^n のきりの良い値にする。"""
    if peak <= 0:
        return 1.0
    raw = peak / ticks
    power = 10 ** math.floor(math.log10(raw))
    for factor in (1, 2, 2.5, 5, 10):
        if raw <= factor * power + 1e-12:
            return factor * power
    return 10 * power


class ColumnChart(QWidget):
    """期間ごとの勉強時間の棒グラフ（自前で描く）。

    - 単一系列なので凡例は出さない。目標線を重ねたときだけ小さな凡例を出す
    - 棒は最大24px、上端だけ4px丸め、基準線から伸ばす
    - 横軸のラベルは重ならないように間引く（値はマウスを重ねるか、表で読める）
    - マウスを重ねた棒は少し濃くし、期間と値（と目標）を出す
    """

    MAX_BAR_PX = 24
    HOVER = QColor("#256abf")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._labels: list[str] = []
        self._values: list[int] = []
        self._goals: list[int] | None = None
        self._hover = -1
        self._plot = QRectF()

    def set_data(
        self,
        labels: Sequence[str],
        seconds: Sequence[int],
        *,
        goal_seconds: Sequence[int] | None = None,
    ) -> None:
        self._labels = list(labels)
        self._values = list(seconds)
        self._goals = list(goal_seconds) if goal_seconds and any(goal_seconds) else None
        self._hover = -1
        self.update()

    # --- 目盛り -------------------------------------------------------------

    def scale(self) -> tuple[float, float]:
        """（目盛りの間隔, 縦軸の上端）を時間単位で返す。"""
        peak = max([hours(v) for v in self._values] + [hours(v) for v in (self._goals or [])] + [0.5])
        step = nice_step(peak)
        top = step * max(1, math.ceil(peak / step - 1e-9))
        return step, top

    @staticmethod
    def format_tick(value: float) -> str:
        return f"{value:.0f}" if abs(value - round(value)) < 1e-9 else f"{value:.1f}"

    def visible_label_indexes(self, slot: float, widest: float) -> list[int]:
        """重ならずに出せる横軸ラベルの位置。最後の期間から数えて一定間隔で出す。"""
        count = len(self._labels)
        every = max(1, math.ceil((widest + 12) / max(1.0, slot)))
        return sorted(index for index in range(count) if (count - 1 - index) % every == 0)

    # --- 描画 ---------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), SURFACE)
        if not self._values:
            painter.end()
            return

        metrics = painter.fontMetrics()
        line_h = metrics.height()
        step, top = self.scale()
        ticks = [step * index for index in range(int(round(top / step)) + 1)]
        legend_h = line_h + 8 if self._goals else 0
        left = max(metrics.horizontalAdvance(self.format_tick(t)) for t in ticks) + 12
        plot = QRectF(left, 8 + legend_h, self.width() - left - 10, self.height() - 22 - legend_h - line_h)
        self._plot = plot
        if plot.width() < 20 or plot.height() < 20:
            painter.end()
            return

        def y_of(value_hours: float) -> float:
            return plot.bottom() - plot.height() * (value_hours / top)

        # 目盛り線（細い実線で控えめに）と縦軸のラベル
        for tick in ticks:
            y = round(y_of(tick)) + 0.5
            painter.setPen(QPen(BASELINE if tick == 0 else GRID, 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(TEXT_MUTED)
            painter.drawText(
                QRectF(0, y - line_h / 2, left - 8, line_h),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                self.format_tick(tick),
            )

        count = len(self._values)
        slot = plot.width() / count
        bar_w = max(2.0, min(float(self.MAX_BAR_PX), slot * 0.7))

        # 棒（上端だけ丸める）
        painter.setPen(Qt.PenStyle.NoPen)
        for index, value in enumerate(self._values):
            if value <= 0:
                continue
            x = plot.left() + slot * index + (slot - bar_w) / 2
            y = y_of(hours(value))
            radius = min(4.0, bar_w / 2, plot.bottom() - y)
            path = QPainterPath()
            path.moveTo(x, plot.bottom())
            path.lineTo(x, y + radius)
            path.quadTo(x, y, x + radius, y)
            path.lineTo(x + bar_w - radius, y)
            path.quadTo(x + bar_w, y, x + bar_w, y + radius)
            path.lineTo(x + bar_w, plot.bottom())
            path.closeSubpath()
            painter.setBrush(self.HOVER if index == self._hover else SERIES)
            painter.drawPath(path)

        # 目標線（同じ縦軸。系列の色ではなく副の文字色の細線）と凡例
        if self._goals:
            points = [
                QPointF(plot.left() + slot * index + slot / 2, y_of(hours(goal)))
                for index, goal in enumerate(self._goals)
            ]
            painter.setPen(QPen(TEXT_SECONDARY, 1.5))
            for start, end in zip(points, points[1:]):
                painter.drawLine(start, end)
            painter.setBrush(SURFACE)
            for point in points:
                painter.drawEllipse(point, 3.0, 3.0)

            legend_right = plot.right()
            goal_w = metrics.horizontalAdvance("目標")
            study_w = metrics.horizontalAdvance("勉強時間")
            x = legend_right - (study_w + goal_w + 60)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(SERIES)
            painter.drawRoundedRect(QRectF(x, 4 + (line_h - 10) / 2, 10, 10), 2, 2)
            painter.setPen(TEXT_SECONDARY)
            painter.drawText(QRectF(x + 14, 4, study_w + 4, line_h), "勉強時間")
            x += 14 + study_w + 16
            painter.setPen(QPen(TEXT_SECONDARY, 1.5))
            painter.drawLine(QPointF(x, 4 + line_h / 2), QPointF(x + 16, 4 + line_h / 2))
            painter.drawText(QRectF(x + 20, 4, goal_w + 4, line_h), "目標")

        # 横軸のラベル（重ならないように間引く。最後の期間は必ず出す）
        painter.setPen(TEXT_MUTED)
        widest = max(metrics.horizontalAdvance(label) for label in self._labels)
        for index in self.visible_label_indexes(slot, widest):
            text = self._labels[index]
            width = metrics.horizontalAdvance(text) + 4
            center = plot.left() + slot * index + slot / 2
            left_edge = max(0.0, min(center - width / 2, self.width() - width))
            painter.drawText(
                QRectF(left_edge, plot.bottom() + 5, width, line_h),
                int(Qt.AlignmentFlag.AlignCenter),
                text,
            )
        painter.end()

    # --- マウス -------------------------------------------------------------

    def index_at(self, x: float) -> int:
        if not self._values or self._plot.width() <= 0:
            return -1
        if not self._plot.left() <= x <= self._plot.right():
            return -1
        slot = self._plot.width() / len(self._values)
        index = int((x - self._plot.left()) // slot)
        return index if 0 <= index < len(self._values) else -1

    def tooltip_text(self, index: int) -> str:
        text = f"{self._labels[index]}　{clock.format_hm(self._values[index])}"
        if self._goals:
            text += f"（目標 {clock.format_hm(self._goals[index])}）"
        return text

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = self.index_at(event.position().x())
        if index != self._hover:
            self._hover = index
            self.update()
        if index >= 0:
            QToolTip.showText(event.globalPosition().toPoint(), self.tooltip_text(index), self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, _event) -> None:  # noqa: N802
        self._hover = -1
        QToolTip.hideText()
        self.update()


def clear_layout(layout) -> None:
    """レイアウトの中身を消す。deleteLater だけだと次のイベント処理まで画面に残るので、すぐ外す。"""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())
            item.layout().deleteLater()


def heading_font(label: QLabel, *, delta: int = 2) -> None:
    font: QFont = label.font()
    font.setPointSize(font.pointSize() + delta)
    font.setBold(True)
    label.setFont(font)


def row(*widgets: QWidget, stretch_last: bool = False) -> QWidget:
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    for widget in widgets:
        layout.addWidget(widget, 1)
    if stretch_last:
        layout.addStretch(1)
    return holder
