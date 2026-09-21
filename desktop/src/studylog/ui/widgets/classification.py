"""資格・参考書・分野を選ぶ3連のコンボボックス。

資格を変えると、参考書と分野の候補もその資格のものに絞り込む。
タイマー・記録の編集・あとで作る分類画面で共通に使う。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QWidget

from ...services.master_service import MasterService
from .common import combo_id, fill_combo


class ClassificationPicker(QWidget):
    changed = Signal()

    def __init__(self, masters: MasterService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.masters = masters

        self.exam = QComboBox(self)
        self.material = QComboBox(self)
        self.subject = QComboBox(self)

        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow("資格", self.exam)
        layout.addRow("参考書", self.material)
        layout.addRow("分野", self.subject)

        self.exam.currentIndexChanged.connect(self._on_exam_changed)
        for combo in (self.material, self.subject):
            combo.currentIndexChanged.connect(lambda _: self.changed.emit())

        self.reload()

    # --- 読み込み -----------------------------------------------------------

    def reload(self, values: dict | None = None) -> None:
        values = values or self.values()
        exams = [(exam.id, exam.name) for exam in self.masters.list_exams()]
        fill_combo(self.exam, exams, current=values.get("exam_id"), empty_label="（未分類）")
        self._reload_children(values)

    def _reload_children(self, values: dict | None = None) -> None:
        values = values or {}
        exam_id = combo_id(self.exam)
        materials = [(m.id, m.name) for m in self.masters.list_materials(exam_id)] if exam_id else []
        subjects = (
            [(s.id, self.masters.subjects.tree_label(s.id)) for s in self.masters.list_subjects(exam_id)]
            if exam_id
            else []
        )
        fill_combo(self.material, materials, current=values.get("material_id"), empty_label="（指定なし）")
        fill_combo(self.subject, subjects, current=values.get("subject_id"), empty_label="（指定なし）")

    def _on_exam_changed(self) -> None:
        self._reload_children()
        self.changed.emit()

    # --- 値 -----------------------------------------------------------------

    def values(self) -> dict[str, str | None]:
        return {
            "exam_id": combo_id(self.exam),
            "material_id": combo_id(self.material),
            "subject_id": combo_id(self.subject),
        }

    def set_values(self, values: dict) -> None:
        self.reload(values)

    def set_enabled(self, enabled: bool) -> None:
        for combo in (self.exam, self.material, self.subject):
            combo.setEnabled(enabled)
