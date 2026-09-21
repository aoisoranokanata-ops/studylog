"""マスタの入力ダイアログ。"""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ....domain import enums
from ....services.master_service import MasterService
from ...widgets.common import NONE_VALUE, combo_id, fill_combo


class _BaseDialog(QDialog):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self._layout = QVBoxLayout(self)
        self.form = QFormLayout()
        self._layout.addLayout(self.form)

    def add_buttons(self) -> None:
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("やめる")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._layout.addWidget(buttons)


class ExamDialog(_BaseDialog):
    def __init__(self, exam=None, exam_date: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__("資格の編集" if exam else "資格を追加", parent)
        self.color = exam.color if exam else "#4a6fa5"

        self.name = QLineEdit(exam.name if exam else "", self)
        self.color_button = QPushButton(self.color, self)
        self.color_button.clicked.connect(self._pick_color)
        self._paint_button()

        self.status = QComboBox(self)
        for key, label in enums.EXAM_STATUS.items():
            self.status.addItem(label, key)
        if exam:
            self.status.setCurrentIndex(max(0, self.status.findData(exam.status)))

        self.has_exam_date = QCheckBox("試験日を設定する", self)
        self.exam_date = QDateEdit(self)
        self.exam_date.setCalendarPopup(True)
        self.exam_date.setDisplayFormat("yyyy-MM-dd")
        self.exam_date.setDate(
            QDate.fromString(exam_date, "yyyy-MM-dd") if exam_date else QDate.currentDate()
        )
        self.has_exam_date.setChecked(bool(exam_date))
        self.exam_date.setEnabled(bool(exam_date))
        self.has_exam_date.toggled.connect(self.exam_date.setEnabled)

        self.goal_note = QLineEdit(exam.goal_note if exam else "", self)
        self.goal_hours = QSpinBox(self)
        self.goal_hours.setRange(0, 9999)
        self.goal_hours.setSuffix(" 時間")
        if exam and exam.goal_total_seconds:
            self.goal_hours.setValue(exam.goal_total_seconds // 3600)
        self.archived = QCheckBox("アーカイブする", self)
        self.archived.setChecked(bool(exam.archived) if exam else False)

        self.form.addRow("名称", self.name)
        self.form.addRow("色", self.color_button)
        self.form.addRow("ステータス", self.status)
        self.form.addRow("", self.has_exam_date)
        self.form.addRow("試験日", self.exam_date)
        self.form.addRow("目標メモ", self.goal_note)
        self.form.addRow("総勉強時間の目標", self.goal_hours)
        self.form.addRow("", self.archived)
        self.add_buttons()

    def _pick_color(self) -> None:
        chosen = QColorDialog.getColor(QColor(self.color), self, "色を選ぶ")
        if chosen.isValid():
            self.color = chosen.name()
            self.color_button.setText(self.color)
            self._paint_button()

    def _paint_button(self) -> None:
        self.color_button.setStyleSheet(f"background-color: {self.color}; color: #fff;")

    def exam_date_value(self) -> str | None:
        if not self.has_exam_date.isChecked():
            return None
        return self.exam_date.date().toString("yyyy-MM-dd")

    def values(self) -> dict:
        hours = self.goal_hours.value()
        return {
            "name": self.name.text().strip(),
            "color": self.color,
            "status": self.status.currentData(),
            "goal_note": self.goal_note.text().strip(),
            "goal_total_seconds": hours * 3600 if hours else None,
            "archived": 1 if self.archived.isChecked() else 0,
        }


class MaterialDialog(_BaseDialog):
    def __init__(
        self,
        masters: MasterService,
        material=None,
        default_exam_id: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("参考書の編集" if material else "参考書を追加", parent)

        self.exam = QComboBox(self)
        fill_combo(
            self.exam,
            [(exam.id, exam.name) for exam in masters.list_exams(include_archived=True)],
            current=material.exam_id if material else default_exam_id,
        )
        self.name = QLineEdit(material.name if material else "", self)
        self.type = QComboBox(self)
        for key, label in enums.MATERIAL_TYPE.items():
            self.type.addItem(label, key)
        if material:
            self.type.setCurrentIndex(max(0, self.type.findData(material.type)))
        self.unit_label = QLineEdit(material.unit_label if material else "ページ", self)
        self.total = QSpinBox(self)
        self.total.setRange(0, 999999)
        self.current = QSpinBox(self)
        self.current.setRange(0, 999999)
        if material:
            self.total.setValue(material.total)
            self.current.setValue(material.current)
        self.archived = QCheckBox("アーカイブする", self)
        self.archived.setChecked(bool(material.archived) if material else False)

        self.form.addRow("資格", self.exam)
        self.form.addRow("名称", self.name)
        self.form.addRow("種別", self.type)
        self.form.addRow("単位", self.unit_label)
        self.form.addRow("総量", self.total)
        self.form.addRow("現在位置", self.current)
        self.form.addRow("", self.archived)
        self.add_buttons()

    def values(self) -> dict:
        return {
            "exam_id": combo_id(self.exam),
            "name": self.name.text().strip(),
            "type": self.type.currentData(),
            "unit_label": self.unit_label.text().strip() or "ページ",
            "total": self.total.value(),
            "current": self.current.value(),
            "archived": 1 if self.archived.isChecked() else 0,
        }


class SubjectDialog(_BaseDialog):
    def __init__(
        self,
        masters: MasterService,
        subject=None,
        default_exam_id: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("分野の編集" if subject else "分野を追加", parent)
        self.masters = masters

        self.exam = QComboBox(self)
        fill_combo(
            self.exam,
            [(exam.id, exam.name) for exam in masters.list_exams(include_archived=True)],
            current=subject.exam_id if subject else default_exam_id,
        )
        self.parent_combo = QComboBox(self)
        self.name = QLineEdit(subject.name if subject else "", self)
        self.sort_order = QSpinBox(self)
        self.sort_order.setRange(0, 999)
        self.archived = QCheckBox("アーカイブする", self)
        if subject:
            self.sort_order.setValue(subject.sort_order)
            self.archived.setChecked(bool(subject.archived))
        self._subject_id = subject.id if subject else None

        self.form.addRow("資格", self.exam)
        self.form.addRow("親の分野", self.parent_combo)
        self.form.addRow("名称", self.name)
        self.form.addRow("並び順", self.sort_order)
        self.form.addRow("", self.archived)
        self.add_buttons()

        self.exam.currentIndexChanged.connect(self._reload_parents)
        self._reload_parents(subject.parent_id if subject else None)

    def _reload_parents(self, current: str | None = None) -> None:
        exam_id = combo_id(self.exam)
        candidates = [
            (subject.id, subject.name)
            for subject in self.masters.list_subjects(exam_id, include_archived=True)
            if subject.parent_id is None and subject.id != self._subject_id
        ]
        fill_combo(
            self.parent_combo,
            candidates,
            current=current if isinstance(current, str) else None,
            empty_label="（なし・大分類）",
        )

    def values(self) -> dict:
        parent_id = self.parent_combo.currentData()
        return {
            "exam_id": combo_id(self.exam),
            "parent_id": None if parent_id == NONE_VALUE else parent_id,
            "name": self.name.text().strip(),
            "sort_order": self.sort_order.value(),
            "archived": 1 if self.archived.isChecked() else 0,
        }
