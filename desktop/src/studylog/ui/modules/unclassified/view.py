"""未分類の記録を分類する画面。

子機から届いた記録のうち、資格が決まっていないものをまとめて割り当てる。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
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
from ...widgets.classification import ClassificationPicker
from ...widgets.common import confirm, heading, show_error, show_info

COLUMNS = ["学習日", "開始", "時間", "範囲", "正答", "メモ", "届いた端末"]


class UnclassifiedView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._rows: list = []

        layout = QVBoxLayout(self)
        layout.addWidget(heading("未分類"))

        self.summary = QLabel(self)
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        box = QGroupBox("選んだ記録に割り当てる", self)
        box_layout = QVBoxLayout(box)
        self.picker = ClassificationPicker(ctx.masters, box)
        box_layout.addWidget(self.picker)

        buttons = QHBoxLayout()
        select_all = QPushButton("すべて選ぶ", box)
        select_all.clicked.connect(self.table.selectAll)
        apply_button = QPushButton("割り当てる", box)
        apply_button.setMinimumHeight(36)
        apply_button.clicked.connect(self._apply)
        delete_button = QPushButton("削除", box)
        delete_button.clicked.connect(self._delete)
        buttons.addWidget(select_all)
        buttons.addStretch(1)
        buttons.addWidget(delete_button)
        buttons.addWidget(apply_button)
        box_layout.addLayout(buttons)
        layout.addWidget(box)

        self.refresh()

    # --- 表示 ---------------------------------------------------------------

    def refresh(self) -> None:
        self._rows = self.ctx.sessions.list(SessionFilter(unclassified_only=True, limit=500))
        self.table.setRowCount(len(self._rows))
        for row, session in enumerate(self._rows):
            range_text = ""
            if session.range_from is not None and session.range_to is not None:
                unit = enums.label(enums.RANGE_UNIT, session.range_unit)
                range_text = f"{session.range_from}〜{session.range_to} {unit}"
            score = ""
            if session.attempted is not None:
                score = f"{session.correct if session.correct is not None else '―'}/{session.attempted}"
            device = ""
            if session.device_id:
                device_row = self.ctx.transfer.devices.row(session.device_id)
                device = device_row["name"] if device_row else session.device_id[:8]
            values = [
                session.study_date.isoformat(),
                clock.format_local(session.started_at, "%H:%M"),
                clock.format_hm(session.active_seconds),
                range_text,
                score,
                session.memo,
                device,
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        total = sum(session.active_seconds for session in self._rows)
        self.summary.setText(
            f"未分類の記録 {len(self._rows)}件（合計 {clock.format_hm(total)}）"
            if self._rows
            else "未分類の記録はありません。"
        )
        self.picker.reload()

    def _selected(self) -> list:
        rows = {index.row() for index in self.table.selectedIndexes()}
        return [self._rows[row] for row in sorted(rows) if 0 <= row < len(self._rows)]

    # --- 操作 ---------------------------------------------------------------

    def _apply(self) -> None:
        sessions = self._selected()
        if not sessions:
            show_error(self, "分類する記録を選んでください")
            return
        values = self.picker.values()
        if not values["exam_id"]:
            show_error(self, "割り当てる資格を選んでください")
            return

        for session in sessions:
            self.ctx.sessions.update(
                session.id,
                {
                    "exam_id": values["exam_id"],
                    "material_id": values["material_id"],
                    "subject_id": values["subject_id"],
                    "unclassified": False,
                },
            )
        self.refresh()
        show_info(self, f"{len(sessions)}件を分類しました。")

    def _delete(self) -> None:
        sessions = self._selected()
        if not sessions:
            show_error(self, "削除する記録を選んでください")
            return
        if not confirm(self, f"選んだ{len(sessions)}件を削除しますか？"):
            return
        for session in sessions:
            self.ctx.sessions.delete(session.id)
        self.refresh()
