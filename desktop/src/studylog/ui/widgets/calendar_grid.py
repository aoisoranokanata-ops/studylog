"""カレンダーのマス目。月表示（6行×7列）と週表示（1行×7列）で同じ部品を使う。

1マスに「予定」と「実績」を重ねて出す：
    上に日付（今日は強調、試験日は赤いラベル）、真ん中に予定、下に実績のメーターと時間。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ...core import clock
from ...domain.models import PlanOccurrence
from .charts import BORDER, SERIES, SURFACE, TEXT, TEXT_MUTED, TEXT_SECONDARY, Meter

EXAM_COLOR = "#d03b3b"   # 状態を表す色（critical）。系列の色とは別に使う
WEEKDAY_LABELS = ("月", "火", "水", "木", "金", "土", "日")


@dataclass(slots=True)
class DayInfo:
    date: date
    in_focus: bool = True          # 表示中の月に入っているか
    is_today: bool = False
    exams: list[str] = field(default_factory=list)
    plans: list[PlanOccurrence] = field(default_factory=list)
    actual_seconds: int = 0
    session_count: int = 0

    @property
    def planned_seconds(self) -> int:
        return sum(occurrence.plan.planned_seconds for occurrence in self.plans)


class DayCell(QFrame):
    clicked = Signal(object)  # date

    def __init__(self, *, max_plans: int = 3, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("daycell")
        self.max_plans = max_plans
        self.info: DayInfo | None = None
        self.selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(8, 6, 8, 6)
        self.body.setSpacing(3)

        self.header = QLabel(self)
        self.exam_label = QLabel(self)
        self.exam_label.setStyleSheet(
            f"background: {EXAM_COLOR}; color: white; border-radius: 6px; padding: 0 6px;"
        )
        self.exam_label.setVisible(False)
        self.plans_box = QVBoxLayout()
        self.plans_box.setSpacing(2)
        self.meter = Meter(self, height=6)
        self.actual = QLabel(self)
        self.actual.setStyleSheet(f"color: {TEXT_SECONDARY.name()}; font-size: 11px;")

        self.body.addWidget(self.header)
        self.body.addWidget(self.exam_label)
        self.body.addLayout(self.plans_box)
        self.body.addStretch(1)
        self.body.addWidget(self.meter)
        self.body.addWidget(self.actual)

    # --- 表示 ---------------------------------------------------------------

    def set_info(self, info: DayInfo) -> None:
        self.info = info
        weekday = info.date.isoweekday()
        color = TEXT.name() if info.in_focus else TEXT_MUTED.name()
        if info.in_focus and weekday == 7:
            color = EXAM_COLOR
        elif info.in_focus and weekday == 6:
            color = "#2a78d6"
        weight = "700" if info.is_today else "500"
        prefix = "今日 " if info.is_today else ""
        self.header.setText(f"{prefix}{info.date.day}")
        self.header.setStyleSheet(f"color: {color}; font-weight: {weight};")

        self.exam_label.setVisible(bool(info.exams))
        if info.exams:
            self.exam_label.setText("　".join(f"{name} 試験日" for name in info.exams))

        while self.plans_box.count():
            widget = self.plans_box.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        for occurrence in info.plans[: self.max_plans]:
            plan = occurrence.plan
            text = f"{plan.time_of_day + ' ' if plan.time_of_day else ''}{plan.title}"
            chip = QLabel(text, self)
            chip.setToolTip(f"{text}（予定 {clock.format_hm(plan.planned_seconds)}）")
            chip.setStyleSheet(
                f"background: #eef3fb; color: {TEXT.name()}; border-left: 3px solid {SERIES.name()};"
                f" border-radius: 3px; padding: 1px 4px; font-size: 11px;"
            )
            chip.setFixedHeight(18)
            chip.setTextFormat(Qt.TextFormat.PlainText)
            self.plans_box.addWidget(chip)
        hidden = len(info.plans) - self.max_plans
        if hidden > 0:
            more = QLabel(f"ほか {hidden}件", self)
            more.setStyleSheet(f"color: {TEXT_MUTED.name()}; font-size: 11px;")
            self.plans_box.addWidget(more)

        planned = info.planned_seconds
        has_any = info.actual_seconds or planned
        self.meter.setVisible(bool(has_any))
        self.actual.setVisible(bool(has_any))
        if has_any:
            self.meter.set_ratio(info.actual_seconds / planned if planned else 1.0)
            self.actual.setText(
                f"{clock.format_hm(info.actual_seconds)} / {clock.format_hm(planned)}"
                if planned
                else clock.format_hm(info.actual_seconds)
            )
        self._paint_border()

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self._paint_border()

    def _paint_border(self) -> None:
        info = self.info
        background = SURFACE.name() if (info and info.in_focus) else "#f4f4f2"
        border = f"1px solid {BORDER}"
        if info and info.is_today:
            border = f"2px solid {SERIES.name()}"
        if self.selected:
            border = f"2px solid {TEXT.name()}"
        self.setStyleSheet(
            f"#daycell {{ background: {background}; border: {border}; border-radius: 8px; }}"
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.info is not None:
            self.clicked.emit(self.info.date)
        super().mousePressEvent(event)


class CalendarGrid(QWidget):
    """曜日の見出し＋マス目。日付を選ぶと daySelected を出す。"""

    daySelected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        self.cells: list[DayCell] = []
        self.selected: date | None = None
        self._week_starts_on = 1

        for column in range(7):
            self.grid.setColumnStretch(column, 1)

    def _ensure(self, rows: int, max_plans: int) -> None:
        needed = rows * 7
        while len(self.cells) < needed:
            cell = DayCell(max_plans=max_plans)
            cell.clicked.connect(self._on_clicked)
            self.cells.append(cell)
        # 曜日の見出し（週の開始に合わせて回す）
        for column in range(7):
            item = self.grid.itemAtPosition(0, column)
            index = (self._week_starts_on - 1 + column) % 7
            if item is None:
                label = QLabel(WEEKDAY_LABELS[index])
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.grid.addWidget(label, 0, column)
            else:
                item.widget().setText(WEEKDAY_LABELS[index])
            widget = self.grid.itemAtPosition(0, column).widget()
            color = EXAM_COLOR if index == 6 else ("#2a78d6" if index == 5 else TEXT_SECONDARY.name())
            widget.setStyleSheet(f"color: {color}; font-weight: 600;")

        for position, cell in enumerate(self.cells):
            row, column = divmod(position, 7)
            if position < needed:
                if self.grid.itemAtPosition(row + 1, column) is None:
                    self.grid.addWidget(cell, row + 1, column)
                cell.max_plans = max_plans
                cell.show()
            else:
                cell.hide()
        for row in range(1, 8):
            self.grid.setRowStretch(row, 1 if row <= rows else 0)

    def set_days(self, days: list[DayInfo], *, week_starts_on: int = 1, max_plans: int = 3) -> None:
        self._week_starts_on = week_starts_on
        rows = max(1, -(-len(days) // 7))
        self._ensure(rows, max_plans)
        for index, info in enumerate(days):
            cell = self.cells[index]
            cell.set_info(info)
            cell.set_selected(info.date == self.selected)
        for cell in self.cells[len(days):]:
            cell.hide()

    def select(self, day: date | None) -> None:
        self.selected = day
        for cell in self.cells:
            cell.set_selected(cell.info is not None and cell.info.date == day)

    def _on_clicked(self, day: date) -> None:
        self.select(day)
        self.daySelected.emit(day)
