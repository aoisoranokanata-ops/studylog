"""ノルマの追加・編集ダイアログ。"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ....context import AppContext
from ....domain import enums
from ....domain.models import Quota
from ...widgets.classification import ClassificationPicker
from ...widgets.common import NONE_VALUE, DurationEdit, OptionalSpinBox


class QuotaDialog(QDialog):
    def __init__(
        self,
        ctx: AppContext,
        day: date,
        quota: Quota | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.quota = quota
        self.setWindowTitle("ノルマの編集" if quota else "ノルマを追加")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        target_day = quota.date if quota else day
        self.date = QDateEdit(QDate(target_day.year, target_day.month, target_day.day), self)
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        form.addRow("日付", self.date)

        self.picker = ClassificationPicker(ctx.masters, self)
        if quota:
            self.picker.set_values(
                {
                    "exam_id": quota.exam_id,
                    "material_id": quota.material_id,
                    "subject_id": quota.subject_id,
                }
            )
        else:
            self.picker.set_values(ctx.sessions.initial_classification())
        form.addRow(self.picker)

        self.title = QLineEdit(quota.title if quota else "", self)
        self.title.setPlaceholderText("空のままなら分野と参考書から作ります")
        form.addRow("内容", self.title)

        self.target = DurationEdit(self)
        self.target.set_seconds(quota.target_seconds if quota else 3600)
        form.addRow("目標時間", self.target)

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

        self.note = QLineEdit(quota.note if quota else "", self)
        form.addRow("メモ", self.note)

        if quota:
            self.range_unit.setCurrentIndex(max(0, self.range_unit.findData(quota.range_unit)))
            self.range_from.set_value_or_none(quota.range_from)
            self.range_to.set_value_or_none(quota.range_to)

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

    def values(self) -> dict:
        unit = self.range_unit.currentData()
        classification = self.picker.values()
        return {
            "day": self.date.date().toPython(),
            "title": self.title.text().strip(),
            "target_seconds": self.target.seconds(),
            "exam_id": classification["exam_id"],
            "material_id": classification["material_id"],
            "subject_id": classification["subject_id"],
            "range_unit": None if unit == NONE_VALUE else unit,
            "range_from": self.range_from.value_or_none(),
            "range_to": self.range_to.value_or_none(),
            "note": self.note.text().strip(),
        }

    def update_values(self) -> dict:
        """編集時にリポジトリへ渡す形。"""
        values = self.values()
        values["date"] = values.pop("day")
        return values
