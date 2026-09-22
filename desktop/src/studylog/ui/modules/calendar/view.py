"""カレンダー。月表示と週表示で、予定と実績を重ねて見る。

- 試験日は赤いラベルで強調する
- 日を選ぶと右に内訳が出て、そこから予定の編集・計測の開始・ノルマへの追加ができる
- 表示中の期間を .ics に書き出せる
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ....context import AppContext
from ....core import clock
from ....domain.models import SessionFilter
from ....services import ics_export
from ....services.plan_service import format_repeat
from ...widgets.calendar_grid import CalendarGrid, DayInfo
from ...widgets.charts import TEXT_MUTED, TEXT_SECONDARY, Panel, clear_layout
from ...widgets.common import confirm, heading, show_error, show_info


def _muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {TEXT_MUTED.name()};")
    label.setWordWrap(True)
    return label


class CalendarView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.mode = "month"
        self.anchor = ctx.stats.today()
        self.selected = self.anchor

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # --- 見出しと操作 ---
        top = QHBoxLayout()
        top.addWidget(heading("カレンダー"))
        self.range_label = QLabel()
        self.range_label.setStyleSheet(f"color: {TEXT_SECONDARY.name()}; font-weight: 600;")
        top.addSpacing(12)
        prev_button = QPushButton("◀", self)
        prev_button.setFixedWidth(36)
        prev_button.clicked.connect(lambda: self._move(-1))
        next_button = QPushButton("▶", self)
        next_button.setFixedWidth(36)
        next_button.clicked.connect(lambda: self._move(1))
        today_button = QPushButton("今日", self)
        today_button.clicked.connect(self._go_today)
        top.addWidget(prev_button)
        top.addWidget(next_button)
        top.addWidget(today_button)
        top.addWidget(self.range_label)
        top.addStretch(1)

        self.month_button = QPushButton("月", self)
        self.week_button = QPushButton("週", self)
        group = QButtonGroup(self)
        for button, mode in ((self.month_button, "month"), (self.week_button, "week")):
            button.setCheckable(True)
            button.setFixedWidth(48)
            group.addButton(button)
            button.clicked.connect(lambda _=False, m=mode: self._set_mode(m))
        self.month_button.setChecked(True)
        top.addWidget(self.month_button)
        top.addWidget(self.week_button)

        export = QPushButton("表示中の期間を .ics に書き出す", self)
        export.clicked.connect(self._export_ics)
        top.addWidget(export)
        layout.addLayout(top)

        # --- カレンダーと右の内訳 ---
        middle = QHBoxLayout()
        middle.setSpacing(12)
        self.grid = CalendarGrid(self)
        self.grid.daySelected.connect(self._on_day_selected)
        middle.addWidget(self.grid, 3)

        side = QScrollArea(self)
        side.setWidgetResizable(True)
        side.setFrameShape(QScrollArea.Shape.NoFrame)
        side.setMinimumWidth(320)
        side.setMaximumWidth(420)
        side_content = QWidget()
        side.setWidget(side_content)
        self.side_layout = QVBoxLayout(side_content)
        self.side_layout.setContentsMargins(0, 0, 0, 0)
        self.side_layout.setSpacing(10)

        self.day_panel = Panel("選んだ日")
        self.day_body = QVBoxLayout()
        self.day_panel.body.addLayout(self.day_body)
        add_button = QPushButton("この日に予定を追加", self)
        add_button.clicked.connect(self._add_plan)
        self.day_panel.body.addWidget(add_button)
        quota_button = QPushButton("この日の予定からノルマを作る", self)
        quota_button.clicked.connect(self._build_quotas)
        self.day_panel.body.addWidget(quota_button)
        self.side_layout.addWidget(self.day_panel)

        self.records_panel = Panel("その日の記録")
        self.records_body = QVBoxLayout()
        self.records_panel.body.addLayout(self.records_body)
        self.side_layout.addWidget(self.records_panel)
        self.side_layout.addStretch(1)
        middle.addWidget(side, 1)
        layout.addLayout(middle)

        self.refresh()

    # --- 期間 ---------------------------------------------------------------

    def _range(self) -> tuple[date, date]:
        """表示している期間（月表示は前後の空白も含む）。"""
        if self.mode == "week":
            start = clock.week_start(self.anchor, self.ctx.settings.week_starts_on)
            return start, start + timedelta(days=6)
        first = self.anchor.replace(day=1)
        last = first.replace(day=monthrange(first.year, first.month)[1])
        week_starts_on = self.ctx.settings.week_starts_on
        start = clock.week_start(first, week_starts_on)
        end = clock.week_start(last, week_starts_on) + timedelta(days=6)
        return start, end

    def _move(self, direction: int) -> None:
        if self.mode == "week":
            self.anchor += timedelta(days=7 * direction)
        else:
            first = self.anchor.replace(day=1)
            self.anchor = (
                (first - timedelta(days=1)).replace(day=1)
                if direction < 0
                else (first + timedelta(days=32)).replace(day=1)
            )
        self.refresh()

    def _go_today(self) -> None:
        self.anchor = self.ctx.stats.today()
        self.selected = self.anchor
        self.refresh()

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        # 画面から呼ばれたときもボタンの状態を合わせる
        self.month_button.setChecked(mode == "month")
        self.week_button.setChecked(mode == "week")
        self.refresh()

    # --- 表示 ---------------------------------------------------------------

    def refresh(self) -> None:
        ctx = self.ctx
        start, end = self._range()
        today = ctx.stats.today()
        month = self.anchor.replace(day=1)

        plans = ctx.plans.by_day(start, end)
        totals = {row.day: row.seconds for row in ctx.session_repo.daily_totals(start, end)}
        exams: dict[date, list[str]] = {}
        for exam in ctx.masters.list_exams():
            exam_date = ctx.masters.exam_date(exam.id)
            if exam_date and start <= date.fromisoformat(exam_date) <= end:
                exams.setdefault(date.fromisoformat(exam_date), []).append(exam.name)

        days: list[DayInfo] = []
        day = start
        while day <= end:
            days.append(
                DayInfo(
                    date=day,
                    in_focus=(self.mode == "week") or (day.year, day.month) == (month.year, month.month),
                    is_today=day == today,
                    exams=exams.get(day, []),
                    plans=plans.get(day, []),
                    actual_seconds=totals.get(day, 0),
                )
            )
            day += timedelta(days=1)

        if self.mode == "week":
            self.range_label.setText(f"{start.isoformat()} 〜 {end.isoformat()}")
        else:
            self.range_label.setText(f"{month.year}年{month.month}月")
        self.grid.select(self.selected)
        self.grid.set_days(
            days,
            week_starts_on=ctx.settings.week_starts_on,
            max_plans=3 if self.mode == "month" else 10,
        )
        self._fill_side()

    def _on_day_selected(self, day: date) -> None:
        self.selected = day
        self._fill_side()

    def _fill_side(self) -> None:
        clear_layout(self.day_body)
        clear_layout(self.records_body)
        day = self.selected
        self.day_panel.title.setText(
            f"{day.isoformat()}（{'月火水木金土日'[day.weekday()]}）の予定"
        )

        occurrences = self.ctx.plans.for_day(day)
        if not occurrences:
            self.day_body.addWidget(_muted("予定はありません。"))
        for occurrence in occurrences:
            self.day_body.addWidget(self._plan_row(occurrence))

        sessions = self.ctx.sessions.list(SessionFilter(date_from=day, date_to=day))
        total = sum(session.active_seconds for session in sessions)
        self.records_panel.title.setText(
            f"その日の記録（{len(sessions)}件・{clock.format_hm(total)}）"
        )
        if not sessions:
            self.records_body.addWidget(_muted("記録はありません。"))
        for session in sessions:
            labels = self.ctx.masters.labels_for(session.exam_id, session.material_id, session.subject_id)
            name = "　".join(part for part in (labels["exam"], labels["material"], labels["subject"]) if part)
            row = QHBoxLayout()
            row.addWidget(QLabel(name or "未分類"), 1)
            value = QLabel(clock.format_hm(session.active_seconds))
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(value)
            self.records_body.addLayout(row)

    def _plan_row(self, occurrence) -> QWidget:
        plan = occurrence.plan
        holder = QWidget(self)
        box = QVBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 6)
        box.setSpacing(2)

        head = QLabel(f"{plan.time_of_day + '　' if plan.time_of_day else ''}{plan.title}")
        head.setStyleSheet("font-weight: 600;")
        head.setWordWrap(True)
        box.addWidget(head)

        details = [f"予定 {clock.format_hm(plan.planned_seconds)}"]
        described = self.ctx.plans.describe(plan)
        if described:
            details.append(described)
        if plan.repeats:
            details.append(format_repeat(plan.repeat_rule))
        box.addWidget(_muted("　".join(details)))
        if plan.note:
            box.addWidget(_muted(plan.note))

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        start = QPushButton("計測", holder)
        start.setToolTip("この予定の内容で計測を始めます")
        start.clicked.connect(lambda: self._start_timer(occurrence))
        edit = QPushButton("編集", holder)
        edit.clicked.connect(lambda: self._edit_plan(occurrence))
        delete = QPushButton("削除", holder)
        delete.clicked.connect(lambda: self._delete_plan(occurrence))
        for button in (start, edit, delete):
            button.setFixedHeight(26)
            buttons.addWidget(button)
        buttons.addStretch(1)
        box.addLayout(buttons)
        return holder

    # --- 操作 ---------------------------------------------------------------

    def _add_plan(self) -> None:
        from .plan_dialog import PlanDialog

        dialog = PlanDialog(self.ctx, self.selected, parent=self)
        if not dialog.exec():
            return
        try:
            self.ctx.plans.create(**dialog.values())
        except ValueError as error:
            show_error(self, str(error))
            return
        self.refresh()

    def _edit_plan(self, occurrence) -> None:
        from .plan_dialog import PlanDialog

        plan = occurrence.plan
        if plan.repeats and not confirm(
            self,
            "この予定は繰り返しです。編集すると、すべての回に反映されます。続けますか？\n"
            "（1回だけ休みたいときは「削除」→「この回だけ休む」を選んでください）",
            "繰り返しの予定",
        ):
            return
        dialog = PlanDialog(self.ctx, occurrence.date, plan, parent=self)
        if not dialog.exec():
            return
        try:
            self.ctx.plans.update(plan.id, dialog.update_values())
        except ValueError as error:
            show_error(self, str(error))
            return
        self.refresh()

    def _delete_plan(self, occurrence) -> None:
        plan = occurrence.plan
        if not plan.repeats:
            if confirm(self, f"「{plan.title}」を削除しますか？"):
                self.ctx.plans.delete(plan.id)
                self.refresh()
            return

        from PySide6.QtWidgets import QMessageBox

        box = QMessageBox(self)
        box.setWindowTitle("繰り返しの予定")
        box.setText(f"「{plan.title}」（{format_repeat(plan.repeat_rule)}）をどうしますか？")
        skip = box.addButton("この回だけ休む", QMessageBox.ButtonRole.AcceptRole)
        future = box.addButton("この回から先をやめる", QMessageBox.ButtonRole.AcceptRole)
        whole = box.addButton("すべて削除", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("やめる", QMessageBox.ButtonRole.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked is skip:
            self.ctx.plans.skip(plan.id, occurrence.date)
        elif clicked is future:
            self.ctx.plans.end_repeat_on(plan.id, occurrence.date)
        elif clicked is whole:
            self.ctx.plans.delete(plan.id)
        else:
            return
        self.refresh()

    def _start_timer(self, occurrence) -> None:
        plan = occurrence.plan
        if self.ctx.timer.current() is not None:
            show_error(self, "すでに計測中です。先に終了してください。")
            self.ctx.open_module("timer")
            return
        self.ctx.timer.start(
            exam_id=plan.exam_id,
            material_id=plan.material_id,
            subject_id=plan.subject_id,
            memo=plan.title,
        )
        self.ctx.open_module("timer")

    def _build_quotas(self) -> None:
        created = self.ctx.quotas.build_from_plans(self.selected)
        self.refresh()
        show_info(
            self,
            f"{self.selected.isoformat()} の予定から{created}件のノルマを作りました。"
            if created
            else "作るノルマがありませんでした（資格を設定した予定が必要です／すでに作成済みです）。",
        )

    def _export_ics(self) -> None:
        start, end = self._range()
        occurrences = self.ctx.plans.occurrences(start, end)
        events = [
            ics_export.plan_event(occurrence, self.ctx.plans.describe(occurrence.plan))
            for occurrence in occurrences
        ]
        for exam in self.ctx.masters.list_exams():
            exam_date = self.ctx.masters.exam_date(exam.id)
            if exam_date:
                events.append(ics_export.exam_event(exam.id, exam.name, date.fromisoformat(exam_date)))
        if not events:
            show_error(self, "書き出す予定がありません。")
            return

        suggested = f"studylog-{start.isoformat()}-{end.isoformat()}.ics"
        chosen, _ = QFileDialog.getSaveFileName(self, "カレンダーに書き出す", suggested, "iCalendar (*.ics)")
        if not chosen:
            return
        from pathlib import Path

        path = ics_export.write(Path(chosen), events)
        show_info(
            self,
            f"{len(events)}件を書き出しました（予定 {len(occurrences)}件と試験日）。\n{path}",
        )
