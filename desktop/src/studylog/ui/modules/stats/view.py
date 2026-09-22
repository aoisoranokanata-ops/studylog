"""集計。期間ごとの勉強時間、資格・参考書・分野別の内訳、学習日数、正答率、参考書の進捗。

絞り込み（単位・期間・資格）はすべて上の1行にまとめ、画面全体に効かせる。
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ....context import AppContext
from ....core import clock
from ...widgets.charts import BarItem, BarList, ColumnChart, Panel, StatTile
from ...widgets.common import combo_id, fill_combo, heading

UNITS = {"day": "日ごと", "week": "週ごと", "month": "月ごと"}
BREAKDOWN_TABS = (("exam", "資格別"), ("material", "参考書別"), ("subject", "分野別"))


def _qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


class StatsView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._updating = False

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
        layout.addWidget(heading("集計"))

        # --- 絞り込み（1行） ---
        filters = QHBoxLayout()
        self.unit = QComboBox(self)
        for key, label in UNITS.items():
            self.unit.addItem(label, key)
        self.unit.setCurrentIndex(0)
        self.date_from = QDateEdit(self)
        self.date_to = QDateEdit(self)
        for edit in (self.date_from, self.date_to):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        self.exam = QComboBox(self)
        reset = QPushButton("標準の期間に戻す", self)
        filters.addWidget(QLabel("単位"))
        filters.addWidget(self.unit)
        filters.addWidget(QLabel("期間"))
        filters.addWidget(self.date_from)
        filters.addWidget(QLabel("〜"))
        filters.addWidget(self.date_to)
        filters.addWidget(QLabel("資格"))
        filters.addWidget(self.exam)
        filters.addWidget(reset)
        filters.addStretch(1)
        layout.addLayout(filters)

        self.unit.currentIndexChanged.connect(self._on_unit_changed)
        self.date_from.dateChanged.connect(self._on_filter_changed)
        self.date_to.dateChanged.connect(self._on_filter_changed)
        self.exam.currentIndexChanged.connect(self._on_filter_changed)
        reset.clicked.connect(self._reset_range)

        # --- 数字 ---
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.tile_total = StatTile("合計")
        self.tile_days = StatTile("学習日数")
        self.tile_average = StatTile("1日あたり（勉強した日）")
        self.tile_streak = StatTile("連続学習")
        self.tile_quota = StatTile("ノルマ達成率")
        for tile in (self.tile_total, self.tile_days, self.tile_average, self.tile_streak, self.tile_quota):
            tiles.addWidget(tile, 1)
        layout.addLayout(tiles)

        # --- 時系列（グラフと表） ---
        self.series_panel = Panel("勉強時間の推移")
        self.series_tabs = QTabWidget(self)
        self.chart = ColumnChart()
        self.chart.setMinimumHeight(260)
        self.series_table = QTableWidget(0, 2, self)
        self.series_table.setHorizontalHeaderLabels(["期間", "勉強時間"])
        self.series_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.series_table.verticalHeader().setVisible(False)
        self.series_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.series_tabs.addTab(self.chart, "グラフ")
        self.series_tabs.addTab(self.series_table, "表")
        self.series_panel.body.addWidget(self.series_tabs)
        layout.addWidget(self.series_panel)

        # --- 内訳・正答率・進捗 ---
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.breakdown_panel = Panel("内訳")
        self.breakdown_tabs = QTabWidget(self)
        self.breakdowns: dict[str, BarList] = {}
        for key, label in BREAKDOWN_TABS:
            holder = QWidget()
            holder_layout = QVBoxLayout(holder)
            holder_layout.setContentsMargins(4, 8, 4, 4)
            bar_list = BarList(holder, limit=10)
            holder_layout.addWidget(bar_list)
            holder_layout.addStretch(1)
            self.breakdowns[key] = bar_list
            self.breakdown_tabs.addTab(holder, label)
        self.breakdown_panel.body.addWidget(self.breakdown_tabs)

        self.accuracy_panel = Panel("分野別の正答率（正答数・解答数を入れた記録）")
        self.accuracy = BarList(limit=10, empty_text="正答数・解答数を入れた記録がありません")
        self.accuracy_panel.body.addWidget(self.accuracy)
        self.accuracy_panel.body.addStretch(1)

        self.progress_panel = Panel("参考書の進み具合")
        self.progress = BarList(limit=12, empty_text="総量を入れた参考書がありません（「マスタ」で設定）")
        self.progress_panel.body.addWidget(self.progress)
        self.progress_panel.body.addStretch(1)

        grid.addWidget(self.breakdown_panel, 0, 0, 2, 1)
        grid.addWidget(self.accuracy_panel, 0, 1)
        grid.addWidget(self.progress_panel, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch(1)

        self._reset_range(refresh=False)
        self.refresh()

    # --- 絞り込み -----------------------------------------------------------

    def _unit(self) -> str:
        return self.unit.currentData()

    def _range(self) -> tuple[date, date]:
        date_from = self.date_from.date().toPython()
        date_to = self.date_to.date().toPython()
        return (date_from, date_to) if date_from <= date_to else (date_to, date_from)

    def _reset_range(self, refresh: bool = True) -> None:
        date_from, date_to = self.ctx.stats.default_range(self._unit())
        self._updating = True
        self.date_from.setDate(_qdate(date_from))
        self.date_to.setDate(_qdate(date_to))
        self._updating = False
        if refresh:
            self.refresh()

    def _on_unit_changed(self) -> None:
        self._reset_range()

    def _on_filter_changed(self) -> None:
        if not self._updating:
            self.refresh()

    # --- 表示 ---------------------------------------------------------------

    def refresh(self) -> None:
        stats = self.ctx.stats
        current_exam = combo_id(self.exam)
        self._updating = True
        fill_combo(
            self.exam,
            [(exam.id, exam.name) for exam in self.ctx.masters.list_exams(include_archived=True)],
            current=current_exam,
            empty_label="すべて",
        )
        self._updating = False
        exam_id = combo_id(self.exam)
        date_from, date_to = self._range()
        unit = self._unit()

        # 数字
        total = stats.total_seconds(date_from, date_to, exam_id)
        days = stats.study_day_count(date_from, date_to)
        span = (date_to - date_from).days + 1
        self.tile_total.set(clock.format_hm(total), f"{date_from.isoformat()}〜{date_to.isoformat()}")
        self.tile_days.set(f"{days}日", f"{span}日のうち {days / span:.0%}" if span else "")
        self.tile_average.set(clock.format_hm(total // days) if days else "—", "")
        streak = stats.streak()
        self.tile_streak.set(f"{streak.current}日", f"最長 {streak.longest}日")
        achievement = stats.quota_achievement(date_from, date_to)
        if achievement.total:
            self.tile_quota.set(
                f"{achievement.rate:.0%}",
                f"{achievement.total}件：完了{achievement.done}・一部{achievement.partial}・"
                f"スキップ{achievement.skipped}・未報告{achievement.none}",
            )
        else:
            self.tile_quota.set("—", "この期間のノルマはありません")

        # 推移（週ごとのときは週目標を重ねる）
        periods = stats.period_totals(unit, date_from, date_to, exam_id)
        goals = None
        if unit == "week":
            goals = [self.ctx.goals.week_goal(p.start, exam_id).seconds for p in periods]
        self.series_panel.title.setText(f"勉強時間の推移（{UNITS[unit]}・単位は時間）")
        self.chart.set_data([p.label for p in periods], [p.seconds for p in periods], goal_seconds=goals)
        self.series_table.setRowCount(len(periods))
        for row, period in enumerate(reversed(periods)):
            label = period.label if unit == "month" else (
                period.start.isoformat() if unit == "day" else f"{period.start.isoformat()}〜{period.end.isoformat()}"
            )
            self.series_table.setItem(row, 0, QTableWidgetItem(label))
            self.series_table.setItem(row, 1, QTableWidgetItem(clock.format_hm(period.seconds)))

        # 内訳（最大のものを満杯とした相対の長さ）
        for key, bar_list in self.breakdowns.items():
            rows = stats.breakdown(key, date_from, date_to, exam_id)
            peak = max((row.seconds for row in rows), default=1) or 1
            items = [
                BarItem(row.label, row.seconds / peak, clock.format_hm(row.seconds), f"{row.share:.0%}")
                for row in rows
            ]
            other = None
            if len(rows) > bar_list.limit:
                rest = rows[bar_list.limit - 1:]
                seconds = sum(row.seconds for row in rest)
                other = BarItem(
                    f"その他（{len(rest)}件）", seconds / peak, clock.format_hm(seconds),
                    f"{sum(row.share for row in rest):.0%}",
                )
            bar_list.set_items(items, other=other)

        # 正答率（割合そのものを長さに）
        self.accuracy.set_items(
            [
                BarItem(row.label, row.rate, f"{row.rate:.0%}", f"{row.correct}/{row.attempted}")
                for row in stats.accuracy_by_subject(date_from, date_to, exam_id)
            ]
        )

        # 参考書の進み具合
        self.progress.set_items(
            [
                BarItem(
                    item.name, item.rate, f"{item.rate:.0%}", f"{item.current}/{item.total}{item.unit}",
                    tooltip=f"{item.exam}　{item.name}",
                )
                for item in stats.material_progress(exam_id)
            ]
        )
