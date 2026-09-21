"""資格・参考書・分野の管理画面。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ....context import AppContext
from ....domain import enums
from ...widgets.common import combo_id, confirm, fill_combo, heading, show_error
from .dialogs import ExamDialog, MaterialDialog, SubjectDialog


class _ListPanel(QWidget):
    """一覧＋追加・編集・削除のボタンという共通の形。"""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._items: list = []

        self.layout_ = QVBoxLayout(self)
        self.filter_row = QHBoxLayout()
        self.layout_.addLayout(self.filter_row)

        self.show_archived = QCheckBox("アーカイブも表示", self)
        self.show_archived.stateChanged.connect(self.refresh)
        self.filter_row.addWidget(self.show_archived)
        self.filter_row.addStretch(1)

        self.list = QListWidget(self)
        self.list.itemDoubleClicked.connect(lambda _: self.edit())
        self.layout_.addWidget(self.list, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for text, slot in (("追加", self.add), ("編集", self.edit), ("削除", self.remove)):
            button = QPushButton(text, self)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        self.layout_.addLayout(buttons)

    def selected(self):
        row = self.list.currentRow()
        return self._items[row] if 0 <= row < len(self._items) else None

    def refresh(self) -> None:  # 各パネルで実装する
        raise NotImplementedError

    def add(self) -> None:
        raise NotImplementedError

    def edit(self) -> None:
        raise NotImplementedError

    def remove(self) -> None:
        raise NotImplementedError


class ExamsPanel(_ListPanel):
    def refresh(self) -> None:
        self._items = self.ctx.masters.list_exams(include_archived=self.show_archived.isChecked())
        self.list.clear()
        for exam in self._items:
            status = enums.label(enums.EXAM_STATUS, exam.status)
            suffix = "（アーカイブ）" if exam.archived else ""
            exam_date = self.ctx.masters.exam_date(exam.id)
            date_text = f"　試験日 {exam_date}" if exam_date else ""
            item = QListWidgetItem(f"{exam.name}　[{status}]{date_text}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, exam.id)
            self.list.addItem(item)

    def add(self) -> None:
        dialog = ExamDialog(parent=self)
        if not dialog.exec():
            return
        values = dialog.values()
        try:
            exam_id = self.ctx.masters.create_exam(values.pop("name"), values.pop("color"), **values)
        except ValueError as error:
            show_error(self, str(error))
            return
        self.ctx.masters.set_exam_date(exam_id, dialog.exam_date_value())
        self.refresh()

    def edit(self) -> None:
        exam = self.selected()
        if exam is None:
            show_error(self, "資格を選んでください")
            return
        dialog = ExamDialog(exam, self.ctx.masters.exam_date(exam.id), parent=self)
        if not dialog.exec():
            return
        try:
            self.ctx.masters.update_exam(exam.id, dialog.values())
        except ValueError as error:
            show_error(self, str(error))
            return
        self.ctx.masters.set_exam_date(exam.id, dialog.exam_date_value())
        self.refresh()

    def remove(self) -> None:
        exam = self.selected()
        if exam is None:
            show_error(self, "資格を選んでください")
            return
        if not confirm(
            self,
            f"「{exam.name}」を削除しますか？\n"
            "ぶら下がっている参考書・分野も削除され、記録は未分類になります。",
        ):
            return
        result = self.ctx.masters.delete_exam(exam.id)
        self.refresh()
        if result["sessions_unclassified"]:
            show_error(
                self,
                f"{result['sessions_unclassified']}件の記録を未分類にしました。",
                title="削除しました",
            )


class _ExamFilteredPanel(_ListPanel):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.exam_filter = QComboBox(self)
        self.exam_filter.currentIndexChanged.connect(self.refresh)
        self.filter_row.insertWidget(0, QLabel("資格"))
        self.filter_row.insertWidget(1, self.exam_filter)

    def reload_exam_filter(self) -> None:
        current = combo_id(self.exam_filter)
        fill_combo(
            self.exam_filter,
            [(exam.id, exam.name) for exam in self.ctx.masters.list_exams(include_archived=True)],
            current=current,
            empty_label="すべて",
        )


class MaterialsPanel(_ExamFilteredPanel):
    def refresh(self) -> None:
        self.reload_exam_filter()
        self._items = self.ctx.masters.list_materials(
            combo_id(self.exam_filter), include_archived=self.show_archived.isChecked()
        )
        self.list.clear()
        for material in self._items:
            exam = self.ctx.masters.exams.get(material.exam_id) if material.exam_id else None
            kind = enums.label(enums.MATERIAL_TYPE, material.type)
            progress = f"{material.current}/{material.total} {material.unit_label}" if material.total else ""
            suffix = "（アーカイブ）" if material.archived else ""
            self.list.addItem(
                f"{material.name}　[{kind}]　{exam.name if exam else '―'}　{progress}{suffix}"
            )

    def add(self) -> None:
        dialog = MaterialDialog(self.ctx.masters, default_exam_id=combo_id(self.exam_filter), parent=self)
        if not dialog.exec():
            return
        values = dialog.values()
        try:
            self.ctx.masters.create_material(values.pop("exam_id"), values.pop("name"), **values)
        except ValueError as error:
            show_error(self, str(error))
            return
        self.refresh()

    def edit(self) -> None:
        material = self.selected()
        if material is None:
            show_error(self, "参考書を選んでください")
            return
        dialog = MaterialDialog(self.ctx.masters, material, parent=self)
        if not dialog.exec():
            return
        self.ctx.masters.update_material(material.id, dialog.values())
        self.refresh()

    def remove(self) -> None:
        material = self.selected()
        if material is None:
            show_error(self, "参考書を選んでください")
            return
        if not confirm(self, f"「{material.name}」を削除しますか？（記録は残り、参考書の指定だけ外れます）"):
            return
        self.ctx.masters.delete_material(material.id)
        self.refresh()


class SubjectsPanel(_ExamFilteredPanel):
    def refresh(self) -> None:
        self.reload_exam_filter()
        subjects = self.ctx.masters.list_subjects(
            combo_id(self.exam_filter), include_archived=self.show_archived.isChecked()
        )
        parents = [s for s in subjects if s.parent_id is None]
        children = {}
        for subject in subjects:
            if subject.parent_id:
                children.setdefault(subject.parent_id, []).append(subject)

        ordered: list = []
        self.list.clear()
        for parent in parents:
            ordered.append(parent)
            self.list.addItem(f"{parent.name}{'（アーカイブ）' if parent.archived else ''}")
            for child in children.get(parent.id, []):
                ordered.append(child)
                self.list.addItem(f"　└ {child.name}{'（アーカイブ）' if child.archived else ''}")
        # 親が絞り込みから外れている子も落とさない
        shown = {subject.id for subject in ordered}
        for subject in subjects:
            if subject.id not in shown:
                ordered.append(subject)
                self.list.addItem(f"（親なし）{subject.name}")
        self._items = ordered

    def add(self) -> None:
        dialog = SubjectDialog(self.ctx.masters, default_exam_id=combo_id(self.exam_filter), parent=self)
        if not dialog.exec():
            return
        values = dialog.values()
        try:
            self.ctx.masters.create_subject(
                values.pop("exam_id"), values.pop("name"), values.pop("parent_id"), **values
            )
        except ValueError as error:
            show_error(self, str(error))
            return
        self.refresh()

    def edit(self) -> None:
        subject = self.selected()
        if subject is None:
            show_error(self, "分野を選んでください")
            return
        dialog = SubjectDialog(self.ctx.masters, subject, parent=self)
        if not dialog.exec():
            return
        try:
            self.ctx.masters.update_subject(subject.id, dialog.values())
        except ValueError as error:
            show_error(self, str(error))
            return
        self.refresh()

    def remove(self) -> None:
        subject = self.selected()
        if subject is None:
            show_error(self, "分野を選んでください")
            return
        if not confirm(self, f"「{subject.name}」を削除しますか？（記録は残り、分野の指定だけ外れます）"):
            return
        self.ctx.masters.delete_subject(subject.id)
        self.refresh()


class MastersView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        layout = QVBoxLayout(self)
        layout.addWidget(heading("マスタ"))

        self.tabs = QTabWidget(self)
        self.exams = ExamsPanel(ctx, self)
        self.materials = MaterialsPanel(ctx, self)
        self.subjects = SubjectsPanel(ctx, self)
        self.tabs.addTab(self.exams, "資格")
        self.tabs.addTab(self.materials, "参考書")
        self.tabs.addTab(self.subjects, "分野")
        self.tabs.currentChanged.connect(lambda _: self.refresh())
        layout.addWidget(self.tabs, 1)

        self.refresh()

    def refresh(self) -> None:
        self.tabs.currentWidget().refresh()
