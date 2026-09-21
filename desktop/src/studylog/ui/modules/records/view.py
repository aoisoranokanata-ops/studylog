"""記録の一覧。"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ....context import AppContext
from ....core import clock
from ....domain import enums
from ....domain.models import SessionFilter
from ...widgets.common import combo_id, confirm, fill_combo, heading, show_error
from .dialog import SessionDialog

COLUMNS = ["学習日", "開始", "時間", "資格", "参考書", "分野", "範囲", "正答", "集中", "方法", "メモ"]


class RecordsView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._rows: list = []

        layout = QVBoxLayout(self)
        layout.addWidget(heading("記録"))

        filters = QHBoxLayout()
        today = date.today()
        self.date_from = QDateEdit(QDate(today.year, today.month, today.day).addDays(-30), self)
        self.date_to = QDateEdit(QDate(today.year, today.month, today.day), self)
        for widget in (self.date_from, self.date_to):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("yyyy-MM-dd")
            widget.dateChanged.connect(self.refresh)
        self.exam = QComboBox(self)
        self.exam.currentIndexChanged.connect(self.refresh)
        self.unclassified_only = QCheckBox("未分類のみ", self)
        self.unclassified_only.stateChanged.connect(self.refresh)

        filters.addWidget(QLabel("期間"))
        filters.addWidget(self.date_from)
        filters.addWidget(QLabel("〜"))
        filters.addWidget(self.date_to)
        filters.addWidget(QLabel("資格"))
        filters.addWidget(self.exam)
        filters.addWidget(self.unclassified_only)
        filters.addStretch(1)
        layout.addLayout(filters)

        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch
        )
        self.table.doubleClicked.connect(self._edit)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.summary = QLabel()
        add_button = QPushButton("追加", self)
        edit_button = QPushButton("編集", self)
        delete_button = QPushButton("削除", self)
        add_button.clicked.connect(self._add)
        edit_button.clicked.connect(self._edit)
        delete_button.clicked.connect(self._delete)
        buttons.addWidget(self.summary)
        buttons.addStretch(1)
        for button in (add_button, edit_button, delete_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.refresh()

    # --- 表示 ---------------------------------------------------------------

    def refresh(self) -> None:
        current_exam = combo_id(self.exam)
        fill_combo(
            self.exam,
            [(exam.id, exam.name) for exam in self.ctx.masters.list_exams()],
            current=current_exam,
            empty_label="すべて",
        )

        filters = SessionFilter(
            date_from=self.date_from.date().toPython(),
            date_to=self.date_to.date().toPython(),
            exam_id=combo_id(self.exam),
            unclassified_only=self.unclassified_only.isChecked(),
            limit=1000,
        )
        self._rows = self.ctx.sessions.list(filters)

        self.table.setRowCount(len(self._rows))
        for row, session in enumerate(self._rows):
            labels = self.ctx.masters.labels_for(
                session.exam_id, session.material_id, session.subject_id
            )
            range_text = ""
            if session.range_from is not None or session.range_to is not None:
                unit = enums.label(enums.RANGE_UNIT, session.range_unit)
                range_text = f"{session.range_from or ''}〜{session.range_to or ''} {unit}".strip()
            score = ""
            if session.attempted is not None:
                score = f"{session.correct if session.correct is not None else '―'}/{session.attempted}"
            values = [
                session.study_date.isoformat(),
                clock.format_local(session.started_at, "%H:%M"),
                clock.format_hm(session.active_seconds),
                labels["exam"] or ("未分類" if session.unclassified else ""),
                labels["material"] or "",
                labels["subject"] or "",
                range_text,
                score,
                str(session.focus or ""),
                enums.label(enums.ENTRY_MODE, session.entry_mode),
                session.memo,
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column in (2, 7, 8):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch
        )

        total = sum(session.active_seconds for session in self._rows)
        self.summary.setText(f"{len(self._rows)}件　合計 {clock.format_hm(total)}")

    def _selected(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    # --- 操作 ---------------------------------------------------------------

    def _add(self) -> None:
        dialog = SessionDialog(self.ctx, parent=self)
        if not dialog.exec():
            return
        try:
            self.ctx.sessions.create(entry_mode="manual", **dialog.values())
        except ValueError as error:
            show_error(self, str(error))
            return
        self.refresh()

    def _edit(self) -> None:
        session = self._selected()
        if session is None:
            show_error(self, "編集する記録を選んでください")
            return
        dialog = SessionDialog(self.ctx, session, parent=self)
        if not dialog.exec():
            return
        try:
            self.ctx.sessions.update(session.id, dialog.values())
        except ValueError as error:
            show_error(self, str(error))
            return
        self.refresh()

    def _delete(self) -> None:
        session = self._selected()
        if session is None:
            show_error(self, "削除する記録を選んでください")
            return
        if not confirm(self, f"{session.study_date} の記録（{clock.format_hm(session.active_seconds)}）を削除しますか？"):
            return
        self.ctx.sessions.delete(session.id)
        self.refresh()
