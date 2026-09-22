"""ダッシュボード。開いたときに「今日なにをするか・どこまで来たか」が一目でわかる画面。"""

from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ....context import AppContext
from ....core import clock
from ....domain import enums
from ...widgets.charts import (
    TEXT_MUTED,
    clear_layout,
    TEXT_SECONDARY,
    ColumnChart,
    Meter,
    Panel,
    StatTile,
)
from ...widgets.common import heading


def _muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {TEXT_MUTED.name()};")
    label.setWordWrap(True)
    return label


def _clear(layout) -> None:
    clear_layout(layout)


class DashboardView(QWidget):
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
        self.layout_ = QVBoxLayout(content)
        self.layout_.setContentsMargins(12, 12, 12, 12)
        self.layout_.setSpacing(12)

        top = QHBoxLayout()
        top.addWidget(heading("ダッシュボード"))
        top.addStretch(1)
        self.date_label = QLabel()
        self.date_label.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
        top.addWidget(self.date_label)
        self.layout_.addLayout(top)

        # --- 数字のタイル ---
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.tile_today = StatTile("今日の勉強時間")
        self.tile_week = StatTile("今週の勉強時間")
        self.tile_streak = StatTile("連続学習")
        self.tile_unclassified = StatTile("未分類の記録")
        for tile in (self.tile_today, self.tile_week, self.tile_streak, self.tile_unclassified):
            tiles.addWidget(tile, 1)
        self.layout_.addLayout(tiles)

        self.week_meter = Meter(height=10)
        self.tile_week.add_widget(self.week_meter)
        self.unclassified_button = QPushButton("分類する")
        self.unclassified_button.clicked.connect(lambda: ctx.open_module("unclassified"))
        self.tile_unclassified.add_widget(self.unclassified_button)

        # --- 直近14日 と 試験日 ---
        middle = QGridLayout()
        middle.setHorizontalSpacing(12)
        middle.setVerticalSpacing(12)
        self.recent = Panel("直近14日の勉強時間（時間）")
        self.recent_chart = ColumnChart()
        self.recent_chart.setMinimumHeight(200)
        self.recent.body.addWidget(self.recent_chart)
        self.exams = Panel("試験日まで")
        self.exams_body = QVBoxLayout()
        self.exams_body.setSpacing(10)
        self.exams.body.addLayout(self.exams_body)
        self.exams.body.addStretch(1)
        middle.addWidget(self.recent, 0, 0)
        middle.addWidget(self.exams, 0, 1)
        middle.setColumnStretch(0, 3)
        middle.setColumnStretch(1, 2)
        self.layout_.addLayout(middle)

        # --- 今日の予定・復習・課題 ---
        lower = QHBoxLayout()
        lower.setSpacing(12)
        self.plans = Panel("今日の予定とノルマ")
        self.plans_body = QVBoxLayout()
        self.plans.body.addLayout(self.plans_body)
        plan_buttons = QHBoxLayout()
        start = QPushButton("計測を始める")
        start.clicked.connect(lambda: ctx.open_module("timer"))
        send = QPushButton("ノルマを作る・送る")
        send.clicked.connect(lambda: ctx.open_module("transfer"))
        calendar = QPushButton("カレンダー")
        calendar.clicked.connect(lambda: ctx.open_module("calendar"))
        plan_buttons.addWidget(start)
        plan_buttons.addWidget(send)
        plan_buttons.addWidget(calendar)
        plan_buttons.addStretch(1)
        self.plans.body.addLayout(plan_buttons)
        self.plans.body.addStretch(1)

        self.reviews = Panel("今日の復習")
        self.reviews_body = QVBoxLayout()
        self.reviews.body.addLayout(self.reviews_body)
        self.reviews.body.addStretch(1)
        review_button = QPushButton("復習を始める")
        review_button.clicked.connect(lambda: ctx.open_module("mistakes"))
        self.reviews.body.addWidget(review_button)

        self.tasks = Panel("期限が近い課題")
        self.tasks_body = QVBoxLayout()
        self.tasks.body.addLayout(self.tasks_body)
        self.tasks.body.addStretch(1)
        task_button = QPushButton("課題を開く")
        task_button.clicked.connect(lambda: ctx.open_module("tasks"))
        self.tasks.body.addWidget(task_button)

        lower.addWidget(self.plans, 3)
        lower.addWidget(self.reviews, 2)
        lower.addWidget(self.tasks, 2)
        self.layout_.addLayout(lower)

        # --- 子機 ---
        self.devices = Panel("子機の最終受信")
        self.devices_body = QVBoxLayout()
        self.devices.body.addLayout(self.devices_body)
        self.layout_.addWidget(self.devices)
        self.layout_.addStretch(1)

        self.refresh()

    # --- 表示 ---------------------------------------------------------------

    def refresh(self) -> None:
        ctx = self.ctx
        today = ctx.stats.today()
        self.date_label.setText(f"学習日 {today.isoformat()}（{'月火水木金土日'[today.weekday()]}）")

        # タイル
        today_seconds = ctx.stats.total_seconds(today, today)
        self.tile_today.set(clock.format_hm(today_seconds), "")

        week = ctx.goals.week_progress(today)
        if week.goal.is_set:
            inherited = "（引き継ぎ）" if week.goal.inherited_from else ""
            self.tile_week.set(
                clock.format_hm(week.actual),
                f"目標 {clock.format_hm(week.goal.seconds)} の {week.ratio:.0%}{inherited}",
            )
            self.week_meter.setVisible(True)
            self.week_meter.set_ratio(week.ratio)
        else:
            self.tile_week.set(clock.format_hm(week.actual), "週目標は未設定です（「目標」で設定）")
            self.week_meter.setVisible(False)

        streak = ctx.stats.streak(today)
        studied_today = today_seconds > 0
        note = f"最長 {streak.longest}日"
        if streak.current and not studied_today:
            note += "　今日まだ記録がありません"
        self.tile_streak.set(f"{streak.current}日", note)

        from ....domain.models import SessionFilter

        unclassified = ctx.session_repo.count(SessionFilter(unclassified_only=True))
        self.tile_unclassified.set(f"{unclassified}件", "子機から届いた、資格が決まっていない記録" if unclassified else "")
        self.unclassified_button.setVisible(unclassified > 0)

        # 直近14日
        recent = ctx.stats.period_totals("day", today - timedelta(days=13), today)
        self.recent_chart.set_data([p.label for p in recent], [p.seconds for p in recent])

        self._fill_exams(today)
        self._fill_plans(today)
        self._fill_reviews(today)
        self._fill_tasks(today)
        self._fill_devices()

    def _fill_exams(self, today) -> None:
        _clear(self.exams_body)
        plans = [plan for plan in self.ctx.goals.exam_plans(today) if plan.exam_date or plan.total_goal]
        if not plans:
            self.exams_body.addWidget(_muted("試験日が登録されていません（「マスタ」で資格ごとに設定）"))
            return
        for plan in plans:
            box = QVBoxLayout()
            box.setSpacing(4)
            line = QHBoxLayout()
            name = QLabel(plan.exam.name)
            name.setStyleSheet("font-weight: 600;")
            line.addWidget(name)
            line.addStretch(1)
            if plan.days_left is not None:
                days = QLabel(
                    f"あと {plan.days_left}日" if plan.days_left >= 0 else f"{-plan.days_left}日前に終了"
                )
                days.setStyleSheet("font-weight: 600; font-size: 15px;")
                line.addWidget(days)
            box.addLayout(line)
            details = []
            if plan.exam_date:
                details.append(f"試験日 {plan.exam_date.isoformat()}")
            if plan.total_goal:
                details.append(f"累計 {clock.format_hm(plan.studied)} / 目標 {clock.format_hm(plan.total_goal)}")
            if plan.per_day_needed:
                details.append(f"1日あたり {clock.format_hm(plan.per_day_needed)} 必要")
            box.addWidget(_muted("　".join(details)))
            if plan.ratio is not None:
                meter = Meter(height=8)
                meter.set_ratio(plan.ratio)
                box.addWidget(meter)
            self.exams_body.addLayout(box)

    def _fill_plans(self, today) -> None:
        _clear(self.plans_body)

        # カレンダーの予定（まだノルマにしていないもの）
        quotas = self.ctx.quotas.list(today)
        planned_ids = {quota.plan_id for quota in quotas if quota.plan_id}
        pending = [o for o in self.ctx.plans.for_day(today) if o.plan.id not in planned_ids]
        if pending:
            for occurrence in pending:
                plan = occurrence.plan
                line = QHBoxLayout()
                title = QLabel(f"{plan.time_of_day + '　' if plan.time_of_day else ''}{plan.title}")
                title.setToolTip(plan.note or plan.title)
                line.addWidget(title, 1)
                mark = QLabel("予定")
                mark.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
                line.addWidget(mark)
                value = QLabel(clock.format_hm(plan.planned_seconds))
                value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                value.setMinimumWidth(90)
                line.addWidget(value)
                self.plans_body.addLayout(line)

        if not quotas:
            if not pending:
                self.plans_body.addWidget(_muted("今日の予定・ノルマはありません。"))
            else:
                self.plans_body.addWidget(_muted("ノルマにすると、子機へ渡せます（「転送」）。"))
            return
        for quota in quotas:
            actual = self.ctx.quotas.actual_seconds(quota.id)
            line = QHBoxLayout()
            title = QLabel(quota.title)
            title.setToolTip(quota.note or quota.title)
            line.addWidget(title, 1)
            status = QLabel(enums.label(enums.QUOTA_STATUS, quota.status))
            status.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
            line.addWidget(status)
            value = QLabel(f"{clock.format_hm(actual)} / {clock.format_hm(quota.target_seconds)}")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setMinimumWidth(90)
            line.addWidget(value)
            self.plans_body.addLayout(line)
            meter = Meter(height=6)
            meter.set_ratio(actual / quota.target_seconds if quota.target_seconds else 0)
            self.plans_body.addWidget(meter)

    def _fill_reviews(self, today) -> None:
        _clear(self.reviews_body)
        due = self.ctx.reviews.due(today)
        if not due:
            self.reviews_body.addWidget(_muted("今日の復習対象はありません。"))
            return
        count = QLabel(f"{len(due)}件")
        count.setStyleSheet("font-weight: 700; font-size: 18px;")
        self.reviews_body.addWidget(count)
        for mistake in due[:5]:
            late = (today - mistake.next_review_on).days if mistake.next_review_on else 0
            suffix = f"（{late}日遅れ）" if late > 0 else ""
            self.reviews_body.addWidget(QLabel(f"・{mistake.question_ref}{suffix}"))
        if len(due) > 5:
            self.reviews_body.addWidget(_muted(f"ほか {len(due) - 5}件"))
        self.reviews_body.addWidget(_muted("子機に送ると、外出先で復習できます。"))

    def _fill_tasks(self, today) -> None:
        _clear(self.tasks_body)
        tasks = self.ctx.task_repo.due_soon(today)
        if not tasks:
            self.tasks_body.addWidget(_muted("期限が近い課題はありません。"))
            return
        for task in tasks[:6]:
            from datetime import date

            due = date.fromisoformat(task["due_on"])
            days = (due - today).days
            when = "今日まで" if days == 0 else (f"{-days}日超過" if days < 0 else f"あと{days}日")
            line = QHBoxLayout()
            line.addWidget(QLabel(task["content"]), 1)
            label = QLabel(when)
            label.setStyleSheet(f"color: {TEXT_SECONDARY.name()};")
            line.addWidget(label)
            self.tasks_body.addLayout(line)

    def _fill_devices(self) -> None:
        _clear(self.devices_body)
        devices = self.ctx.transfer.device_list()
        if not devices:
            self.devices_body.addWidget(_muted("まだ子機から受け取っていません。"))
            return
        for device in devices:
            received = (
                clock.format_local(clock.from_db(device["last_received_at"]))
                if device["last_received_at"]
                else "—"
            )
            line = QHBoxLayout()
            line.addWidget(QLabel(device["name"] or "（名前なし）"))
            line.addStretch(1)
            line.addWidget(QLabel(received))
            self.devices_body.addLayout(line)
