"""目標。週目標（全体・資格別）と、資格ごとの総勉強時間の目標。

週目標は、設定しなかった週は前の週の値を引き継ぐ。
資格の総目標は、試験日から逆算して「1日あたり必要な時間」を出す。
"""

from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ....context import AppContext
from ....core import clock
from ...widgets.charts import TEXT_MUTED, ColumnChart, Meter, Panel
from ...widgets.common import heading, show_info


def _hours_spin(parent: QWidget, maximum: float = 168.0) -> QDoubleSpinBox:
    spin = QDoubleSpinBox(parent)
    spin.setRange(0, maximum)
    spin.setDecimals(1)
    spin.setSingleStep(0.5)
    spin.setSuffix(" 時間")
    spin.setSpecialValueText("未設定")
    return spin


def _reset_table(table: QTableWidget, rows: int) -> None:
    """表を作り直す。セルの入力欄は deleteLater だと次の描画まで残って重なるので、先に隠す。"""
    for row in range(table.rowCount()):
        for column in range(table.columnCount()):
            widget = table.cellWidget(row, column)
            if widget is not None:
                widget.hide()
                table.removeCellWidget(row, column)
    table.setRowCount(0)
    table.setRowCount(rows)


def _item(text: str, *, right: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    if right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


class GoalsView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(heading("目標"))

        # --- 週目標 ---
        week_panel = Panel("週目標")
        pick = QHBoxLayout()
        today = ctx.goals.today()
        self.week = QDateEdit(QDate(today.year, today.month, today.day), self)
        self.week.setCalendarPopup(True)
        self.week.setDisplayFormat("yyyy-MM-dd")
        self.week.dateChanged.connect(self.refresh)
        self.week_label = QLabel()
        pick.addWidget(QLabel("対象の週"))
        pick.addWidget(self.week)
        pick.addWidget(self.week_label)
        pick.addStretch(1)
        week_panel.body.addLayout(pick)

        total_row = QHBoxLayout()
        self.total_goal = _hours_spin(self)
        self.total_status = QLabel()
        self.total_status.setStyleSheet(f"color: {TEXT_MUTED.name()};")
        total_row.addWidget(QLabel("全体の目標"))
        total_row.addWidget(self.total_goal)
        total_row.addWidget(self.total_status, 1)
        week_panel.body.addLayout(total_row)
        self.week_meter = Meter(height=10)
        week_panel.body.addWidget(self.week_meter)
        self.week_actual = QLabel()
        week_panel.body.addWidget(self.week_actual)

        self.exam_week_table = QTableWidget(0, 3, self)
        self.exam_week_table.setHorizontalHeaderLabels(["資格", "この週の目標", "この週の実績"])
        self.exam_week_table.verticalHeader().setVisible(False)
        self.exam_week_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.exam_week_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.exam_week_table.setColumnWidth(1, 150)
        self.exam_week_table.setColumnWidth(2, 140)
        week_panel.body.addWidget(QLabel("資格ごとの週目標（任意）"))
        week_panel.body.addWidget(self.exam_week_table)

        buttons = QHBoxLayout()
        save_week = QPushButton("週目標を保存", self)
        save_week.clicked.connect(self._save_week)
        buttons.addStretch(1)
        buttons.addWidget(save_week)
        week_panel.body.addLayout(buttons)
        week_panel.body.addWidget(
            self._note("0（未設定）にして保存すると、その週は前の週の目標を引き継ぎます。")
        )
        layout.addWidget(week_panel)

        # --- 直近の週 ---
        history_panel = Panel("直近8週の実績と目標（時間）")
        self.history_chart = ColumnChart()
        self.history_chart.setMinimumHeight(240)
        history_panel.body.addWidget(self.history_chart)
        layout.addWidget(history_panel)

        # --- 資格ごとの総目標 ---
        exam_panel = Panel("資格ごとの総勉強時間の目標")
        self.exam_table = QTableWidget(0, 7, self)
        self.exam_table.setHorizontalHeaderLabels(
            ["資格", "試験日", "残り日数", "総目標", "累計", "残り", "1日あたり必要"]
        )
        self.exam_table.verticalHeader().setVisible(False)
        self.exam_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.exam_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.exam_table.setColumnWidth(3, 150)
        exam_panel.body.addWidget(self.exam_table)
        exam_buttons = QHBoxLayout()
        save_exams = QPushButton("総目標を保存", self)
        save_exams.clicked.connect(self._save_exam_goals)
        exam_buttons.addStretch(1)
        exam_buttons.addWidget(save_exams)
        exam_panel.body.addLayout(exam_buttons)
        exam_panel.body.addWidget(self._note("試験日は「マスタ」の資格の編集で設定します。"))
        layout.addWidget(exam_panel)
        layout.addStretch(1)

        self._exam_spins: dict[str, QDoubleSpinBox] = {}
        self._exam_week_spins: dict[str, QDoubleSpinBox] = {}
        self.refresh()

    @staticmethod
    def _note(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(f"color: {TEXT_MUTED.name()};")
        label.setWordWrap(True)
        return label

    def _week_start(self):
        return self.ctx.goals.week_start(self.week.date().toPython())

    # --- 表示 ---------------------------------------------------------------

    def refresh(self) -> None:
        goals = self.ctx.goals
        week_start = self._week_start()
        week_end = week_start + timedelta(days=6)
        self.week_label.setText(f"{week_start.isoformat()}（{'月火水木金土日'[week_start.weekday()]}）〜 {week_end.isoformat()}")

        progress = goals.week_progress(week_start)
        goal = progress.goal
        # 引き継いだ値は薄く案内し、入力欄にはその週に直接設定した値だけを出す
        exact = goals.goals.exact(week_start)
        self.total_goal.setValue(exact["goal_seconds"] / 3600 if exact else 0)
        if goal.inherited_from:
            self.total_status.setText(
                f"未設定のため {goal.inherited_from.isoformat()} の週の目標（{clock.format_hm(goal.seconds)}）を引き継いでいます"
            )
        elif not goal.is_set:
            self.total_status.setText("目標はまだありません")
        else:
            self.total_status.setText("")
        self.week_meter.setVisible(goal.is_set)
        self.week_meter.set_ratio(progress.ratio)
        self.week_actual.setText(
            f"実績 {clock.format_hm(progress.actual)}"
            + (f"（目標の {progress.ratio:.0%}）" if goal.is_set else "")
        )

        exams = self.ctx.masters.list_exams()
        _reset_table(self.exam_week_table, len(exams))
        self._exam_week_spins = {}
        for row, exam in enumerate(exams):
            self.exam_week_table.setItem(row, 0, _item(exam.name))
            spin = _hours_spin(self)
            exam_exact = goals.goals.exact(week_start, exam.id)
            spin.setValue(exam_exact["goal_seconds"] / 3600 if exam_exact else 0)
            inherited = goals.week_goal(week_start, exam.id)
            if not exam_exact and inherited.is_set:
                spin.setToolTip(f"未設定のため {clock.format_hm(inherited.seconds)} を引き継いでいます")
            self.exam_week_table.setCellWidget(row, 1, spin)
            self._exam_week_spins[exam.id] = spin
            actual = goals.week_progress(week_start, exam.id).actual
            text = clock.format_hm(actual)
            if inherited.is_set:
                text += f"（{actual / inherited.seconds:.0%}）"
            self.exam_week_table.setItem(row, 2, _item(text, right=True))
        self.exam_week_table.setFixedHeight(min(220, 34 + 32 * max(1, len(exams))))

        history = list(reversed(goals.week_history(8, week_start)))
        self.history_chart.set_data(
            [f"{h.week_start.month}/{h.week_start.day}〜" for h in history],
            [h.actual for h in history],
            goal_seconds=[h.goal.seconds for h in history],
        )

        plans = goals.exam_plans()
        _reset_table(self.exam_table, len(plans))
        self._exam_spins = {}
        for row, plan in enumerate(plans):
            self.exam_table.setItem(row, 0, _item(plan.exam.name))
            self.exam_table.setItem(row, 1, _item(plan.exam_date.isoformat() if plan.exam_date else "—"))
            self.exam_table.setItem(
                row, 2, _item(f"{plan.days_left}日" if plan.days_left is not None else "—", right=True)
            )
            spin = _hours_spin(self, maximum=99999)
            spin.setDecimals(0)
            spin.setSingleStep(10)
            spin.setValue((plan.total_goal or 0) / 3600)
            self.exam_table.setCellWidget(row, 3, spin)
            self._exam_spins[plan.exam.id] = spin
            self.exam_table.setItem(row, 4, _item(clock.format_hm(plan.studied), right=True))
            self.exam_table.setItem(
                row, 5, _item(clock.format_hm(plan.remaining) if plan.remaining is not None else "—", right=True)
            )
            self.exam_table.setItem(
                row, 6,
                _item(clock.format_hm(plan.per_day_needed) if plan.per_day_needed else "—", right=True),
            )
        self.exam_table.setFixedHeight(min(260, 34 + 32 * max(1, len(plans))))

    # --- 保存 ---------------------------------------------------------------

    def _save_week(self) -> None:
        week_start = self._week_start()
        goals = self.ctx.goals
        seconds = int(self.total_goal.value() * 3600)
        if seconds:
            goals.set_week_goal(week_start, seconds)
        else:
            goals.goals.clear(week_start)
        for exam_id, spin in self._exam_week_spins.items():
            value = int(spin.value() * 3600)
            if value:
                goals.set_week_goal(week_start, value, exam_id)
            else:
                goals.goals.clear(week_start, exam_id)
        self.refresh()
        show_info(self, "週目標を保存しました。")

    def _save_exam_goals(self) -> None:
        for exam_id, spin in self._exam_spins.items():
            hours = int(spin.value())
            self.ctx.goals.set_exam_total_goal(exam_id, hours * 3600 if hours else None)
        self.refresh()
        show_info(self, "総目標を保存しました。")
