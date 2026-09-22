"""課題（やることリスト）。期限と優先度を持ち、チェックで完了にする。"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ....context import AppContext
from ....services.task_service import PRIORITIES
from ...widgets.charts import TEXT_MUTED
from ...widgets.common import combo_id, confirm, fill_combo, heading, show_error

COLUMNS = ["完了", "内容", "資格", "期限", "残り", "優先度"]


class TaskDialog(QDialog):
    def __init__(self, ctx: AppContext, task=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.task = task
        self.setWindowTitle("課題の編集" if task else "課題を追加")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.content = QLineEdit(task["content"] if task else "", self)
        self.content.setPlaceholderText("例：模試の申し込み")
        form.addRow("内容", self.content)

        self.has_due = QCheckBox("期限を決める", self)
        self.due = QDateEdit(self)
        self.due.setCalendarPopup(True)
        self.due.setDisplayFormat("yyyy-MM-dd")
        today = ctx.tasks.today()
        due_value = date.fromisoformat(task["due_on"]) if task and task["due_on"] else today
        self.due.setDate(QDate(due_value.year, due_value.month, due_value.day))
        self.has_due.setChecked(bool(task and task["due_on"]) or task is None)
        self.due.setEnabled(self.has_due.isChecked())
        self.has_due.toggled.connect(self.due.setEnabled)
        form.addRow("", self.has_due)
        form.addRow("期限", self.due)

        self.priority = QComboBox(self)
        for value, label in PRIORITIES.items():
            self.priority.addItem(label, value)
        self.priority.setCurrentIndex(max(0, self.priority.findData(task["priority"] if task else 2)))
        form.addRow("優先度", self.priority)

        self.exam = QComboBox(self)
        fill_combo(
            self.exam,
            [(exam.id, exam.name) for exam in ctx.masters.list_exams(include_archived=True)],
            current=task["exam_id"] if task else None,
            empty_label="（指定なし）",
        )
        form.addRow("資格", self.exam)

        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, parent=self
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("やめる")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "content": self.content.text().strip(),
            "due_on": self.due.date().toPython() if self.has_due.isChecked() else None,
            "priority": self.priority.currentData(),
            "exam_id": combo_id(self.exam),
        }


class TasksView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._rows: list = []
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(heading("課題"))

        filters = QHBoxLayout()
        self.exam = QComboBox(self)
        self.exam.currentIndexChanged.connect(self.refresh)
        self.hide_done = QCheckBox("完了を隠す", self)
        self.hide_done.stateChanged.connect(self.refresh)
        filters.addWidget(QLabel("資格"))
        filters.addWidget(self.exam)
        filters.addWidget(self.hide_done)
        filters.addStretch(1)
        layout.addLayout(filters)

        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.doubleClicked.connect(self._edit)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.summary = QLabel(self)
        self.summary.setStyleSheet(f"color: {TEXT_MUTED.name()};")
        buttons.addWidget(self.summary)
        buttons.addStretch(1)
        for text, slot in (("追加", self._add), ("編集", self._edit), ("削除", self._delete)):
            button = QPushButton(text, self)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.refresh()

    # --- 表示 ---------------------------------------------------------------

    def refresh(self) -> None:
        self._updating = True
        current = combo_id(self.exam)
        self.exam.blockSignals(True)
        fill_combo(
            self.exam,
            [(exam.id, exam.name) for exam in self.ctx.masters.list_exams(include_archived=True)],
            current=current,
            empty_label="すべて",
        )
        self.exam.blockSignals(False)

        today = self.ctx.tasks.today()
        self._rows = self.ctx.tasks.list(
            include_done=not self.hide_done.isChecked(), exam_id=combo_id(self.exam)
        )
        self.table.setRowCount(len(self._rows))
        for row, task in enumerate(self._rows):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            check.setCheckState(Qt.CheckState.Checked if task["done"] else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, check)

            exam = self.ctx.masters.exams.get(task["exam_id"]) if task["exam_id"] else None
            due = date.fromisoformat(task["due_on"]) if task["due_on"] else None
            if due is None:
                remaining = "—"
            else:
                days = (due - today).days
                remaining = "今日まで" if days == 0 else (f"{-days}日超過" if days < 0 else f"あと{days}日")
            values = [
                task["content"],
                exam.name if exam else "",
                due.isoformat() if due else "—",
                remaining,
                PRIORITIES.get(task["priority"], ""),
            ]
            for column, text in enumerate(values, start=1):
                item = QTableWidgetItem(text)
                if task["done"]:
                    item.setForeground(Qt.GlobalColor.gray)
                elif column == 4 and due is not None and (due - today).days < 0:
                    item.setForeground(Qt.GlobalColor.red)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        open_count = self.ctx.tasks.count_open()
        soon = len(self.ctx.tasks.due_soon())
        self.summary.setText(f"未完了 {open_count}件　（期限が近い・過ぎた {soon}件）")
        self._updating = False

    def _selected(self):
        row = self.table.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    # --- 操作 ---------------------------------------------------------------

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or item.column() != 0:
            return
        task = self._rows[item.row()] if 0 <= item.row() < len(self._rows) else None
        if task is None:
            return
        self.ctx.tasks.set_done(task["id"], item.checkState() == Qt.CheckState.Checked)
        self.refresh()

    def _add(self) -> None:
        dialog = TaskDialog(self.ctx, parent=self)
        if not dialog.exec():
            return
        try:
            self.ctx.tasks.create(**dialog.values())
        except ValueError as error:
            show_error(self, str(error))
            return
        self.refresh()

    def _edit(self) -> None:
        task = self._selected()
        if task is None:
            show_error(self, "課題を選んでください")
            return
        dialog = TaskDialog(self.ctx, task, parent=self)
        if not dialog.exec():
            return
        try:
            self.ctx.tasks.update(task["id"], dialog.values())
        except ValueError as error:
            show_error(self, str(error))
            return
        self.refresh()

    def _delete(self) -> None:
        task = self._selected()
        if task is None:
            show_error(self, "課題を選んでください")
            return
        if confirm(self, f"「{task['content']}」を削除しますか？"):
            self.ctx.tasks.delete(task["id"])
            self.refresh()
