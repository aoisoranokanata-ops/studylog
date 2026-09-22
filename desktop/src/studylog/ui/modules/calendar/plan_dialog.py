"""予定の追加・編集ダイアログ。"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QTime, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ....context import AppContext
from ....domain import enums
from ....domain.models import Plan
from ....services.plan_service import WEEKDAY_NAMES
from ...widgets.classification import ClassificationPicker
from ...widgets.common import NONE_VALUE, DurationEdit, OptionalSpinBox


class PlanDialog(QDialog):
    def __init__(
        self, ctx: AppContext, day: date, plan: Plan | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.plan = plan
        self.setWindowTitle("予定の編集" if plan else "予定を追加")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        target = plan.date if plan else day
        self.date = QDateEdit(QDate(target.year, target.month, target.day), self)
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        form.addRow("日付", self.date)

        time_row = QWidget(self)
        time_layout = QHBoxLayout(time_row)
        time_layout.setContentsMargins(0, 0, 0, 0)
        self.has_time = QCheckBox("時刻を決める", time_row)
        self.time = QTimeEdit(time_row)
        self.time.setDisplayFormat("HH:mm")
        self.time.setTime(QTime(9, 0))
        if plan and plan.time_of_day:
            hour, _, minute = plan.time_of_day.partition(":")
            self.time.setTime(QTime(int(hour), int(minute or 0)))
            self.has_time.setChecked(True)
        self.time.setEnabled(self.has_time.isChecked())
        self.has_time.toggled.connect(self.time.setEnabled)
        time_layout.addWidget(self.has_time)
        time_layout.addWidget(self.time, 1)
        form.addRow("時刻", time_row)

        self.title = QLineEdit(plan.title if plan else "", self)
        self.title.setPlaceholderText("例：民法総則 問題集 p.40-65")
        form.addRow("内容", self.title)

        self.duration = DurationEdit(self)
        self.duration.set_seconds(plan.planned_seconds if plan else 3600)
        form.addRow("予定時間", self.duration)

        self.picker = ClassificationPicker(ctx.masters, self)
        if plan:
            self.picker.set_values(
                {"exam_id": plan.exam_id, "material_id": plan.material_id, "subject_id": plan.subject_id}
            )
        else:
            self.picker.set_values(ctx.sessions.initial_classification())
        form.addRow(self.picker)

        self.range_unit = QComboBox(self)
        self.range_unit.addItem("（指定なし）", NONE_VALUE)
        for key, label in enums.RANGE_UNIT.items():
            self.range_unit.addItem(label, key)
        self.range_from = OptionalSpinBox(0, 99999, self)
        self.range_to = OptionalSpinBox(0, 99999, self)
        range_row = QWidget(self)
        range_layout = QHBoxLayout(range_row)
        range_layout.setContentsMargins(0, 0, 0, 0)
        range_layout.addWidget(self.range_unit)
        range_layout.addWidget(self.range_from)
        range_layout.addWidget(QLabel("〜"))
        range_layout.addWidget(self.range_to)
        form.addRow("範囲", range_row)

        self.note = QLineEdit(plan.note if plan else "", self)
        form.addRow("メモ", self.note)

        # --- 繰り返し ---
        self.repeat = QComboBox(self)
        self.repeat.addItem("繰り返さない", "none")
        self.repeat.addItem("毎日", "daily")
        self.repeat.addItem("曜日を選ぶ", "weekly")
        self.weekdays: dict[int, QCheckBox] = {}
        weekday_row = QWidget(self)
        weekday_layout = QHBoxLayout(weekday_row)
        weekday_layout.setContentsMargins(0, 0, 0, 0)
        for iso, name in WEEKDAY_NAMES.items():
            box = QCheckBox(name, weekday_row)
            self.weekdays[iso] = box
            weekday_layout.addWidget(box)
        weekday_layout.addStretch(1)

        self.has_until = QCheckBox("終わりを決める", self)
        self.until = QDateEdit(self)
        self.until.setCalendarPopup(True)
        self.until.setDisplayFormat("yyyy-MM-dd")
        self.until.setDate(QDate(target.year, target.month, target.day).addMonths(1))
        self.until.setEnabled(False)
        self.has_until.toggled.connect(self.until.setEnabled)
        until_row = QWidget(self)
        until_layout = QHBoxLayout(until_row)
        until_layout.setContentsMargins(0, 0, 0, 0)
        until_layout.addWidget(self.has_until)
        until_layout.addWidget(self.until, 1)

        form.addRow("繰り返し", self.repeat)
        form.addRow("曜日", weekday_row)
        form.addRow("", until_row)

        if plan:
            self.range_unit.setCurrentIndex(max(0, self.range_unit.findData(plan.range_unit)))
            self.range_from.set_value_or_none(plan.range_from)
            self.range_to.set_value_or_none(plan.range_to)
            from ....services.plan_service import parse_repeat

            kind, days = parse_repeat(plan.repeat_rule)
            self.repeat.setCurrentIndex(max(0, self.repeat.findData(kind)))
            for iso, box in self.weekdays.items():
                box.setChecked(iso in days)
            if plan.repeat_until:
                self.has_until.setChecked(True)
                self.until.setDate(
                    QDate(plan.repeat_until.year, plan.repeat_until.month, plan.repeat_until.day)
                )
        else:
            self.weekdays[target.isoweekday()].setChecked(True)

        self.repeat.currentIndexChanged.connect(self._sync_repeat)
        self._sync_repeat()
        self.weekday_row = weekday_row
        self.until_row = until_row

        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("やめる")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _sync_repeat(self) -> None:
        kind = self.repeat.currentData()
        for box in self.weekdays.values():
            box.setEnabled(kind == "weekly")
        self.has_until.setEnabled(kind != "none")
        self.until.setEnabled(kind != "none" and self.has_until.isChecked())

    def repeat_rule(self) -> str | None:
        kind = self.repeat.currentData()
        if kind == "none":
            return None
        if kind == "daily":
            return "daily"
        chosen = [str(iso) for iso, box in self.weekdays.items() if box.isChecked()]
        return "weekly:" + ",".join(chosen)

    def values(self) -> dict:
        unit = self.range_unit.currentData()
        classification = self.picker.values()
        kind = self.repeat.currentData()
        return {
            "day": self.date.date().toPython(),
            "time_of_day": self.time.time().toString("HH:mm") if self.has_time.isChecked() else None,
            "title": self.title.text().strip(),
            "planned_seconds": self.duration.seconds(),
            "exam_id": classification["exam_id"],
            "material_id": classification["material_id"],
            "subject_id": classification["subject_id"],
            "range_unit": None if unit == NONE_VALUE else unit,
            "range_from": self.range_from.value_or_none(),
            "range_to": self.range_to.value_or_none(),
            "note": self.note.text().strip(),
            "repeat_rule": self.repeat_rule(),
            "repeat_until": (
                self.until.date().toPython() if kind != "none" and self.has_until.isChecked() else None
            ),
        }

    def update_values(self) -> dict:
        """編集時にリポジトリへ渡す形（列名に合わせる）。"""
        values = self.values()
        values["date"] = values.pop("day")
        values["repeat_from"] = values["date"] if values["repeat_rule"] else None
        return values
