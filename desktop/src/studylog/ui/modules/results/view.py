"""結果：受験回ごとの合否と、合格した資格の実績。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
from ...widgets.charts import GOOD, TEXT_MUTED, Panel
from ...widgets.common import combo_id, confirm, fill_combo, heading, show_error, show_info
from .dialogs import ResultDialog, SittingDialog, SummaryDialog

SITTING_COLUMNS = ["回", "試験日", "点数", "合否", "合格証", "メモ"]
ACHIEVEMENT_COLUMNS = ["資格", "回", "試験日", "点数", "合格証"]
STATUS_LABELS = {"planned": "予定", "active": "勉強中", "passed": "合格", "failed": "不合格"}


def _pass_text(passed: bool | None) -> str:
    return "—" if passed is None else ("合格" if passed else "不合格")


class ResultsView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._sittings: list = []
        self._achievements: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(heading("結果"))

        picker = QHBoxLayout()
        self.exam = QComboBox(self)
        self.exam.setMinimumWidth(200)
        self.exam.currentIndexChanged.connect(self.refresh_sittings)
        self.status = QLabel(self)
        self.status.setStyleSheet(f"color: {TEXT_MUTED.name()};")
        picker.addWidget(QLabel("資格"))
        picker.addWidget(self.exam)
        picker.addWidget(self.status)
        picker.addStretch(1)
        summary_button = QPushButton("振り返りを見る", self)
        summary_button.clicked.connect(self._show_summary)
        picker.addWidget(summary_button)
        layout.addLayout(picker)

        sittings_panel = Panel("受験回", self)
        self.table = QTableWidget(0, len(SITTING_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(SITTING_COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._record)
        sittings_panel.body.addWidget(self.table)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for text, slot in (
            ("受験回を追加", self._add),
            ("編集", self._edit),
            ("結果を記録", self._record),
            ("この回を本番にする", self._make_primary),
            ("削除", self._delete),
        ):
            button = QPushButton(text, self)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        sittings_panel.body.addLayout(buttons)
        layout.addWidget(sittings_panel, 3)

        achievements_panel = Panel("実績（合格した資格）", self)
        self.achievements = QTableWidget(0, len(ACHIEVEMENT_COLUMNS), self)
        self.achievements.setHorizontalHeaderLabels(ACHIEVEMENT_COLUMNS)
        self.achievements.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.achievements.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.achievements.verticalHeader().setVisible(False)
        self.achievements.doubleClicked.connect(self._open_achievement)
        achievements_panel.body.addWidget(self.achievements)
        layout.addWidget(achievements_panel, 2)

        self.refresh()

    # --- 表示 ---------------------------------------------------------------

    def refresh(self) -> None:
        current = combo_id(self.exam)
        self.exam.blockSignals(True)
        fill_combo(
            self.exam,
            [(exam.id, exam.name) for exam in self.ctx.masters.list_exams(include_archived=True)],
            current=current,
        )
        self.exam.blockSignals(False)
        self.refresh_sittings()
        self.refresh_achievements()

    def refresh_sittings(self) -> None:
        exam_id = combo_id(self.exam)
        self._sittings = self.ctx.results.sittings_for(exam_id) if exam_id else []
        primary = self.ctx.masters.sittings.primary(exam_id) if exam_id else None
        primary_id = primary["id"] if primary is not None else None
        self.table.setRowCount(len(self._sittings))
        for row, sitting in enumerate(self._sittings):
            mark = "★ " if sitting.id == primary_id else ""
            values = [
                mark + (sitting.label or "（名前なし）"),
                sitting.exam_date.isoformat() if sitting.exam_date else "未定",
                "—" if sitting.score is None else str(sitting.score),
                _pass_text(sitting.passed),
                sitting.certificate_on.isoformat() if sitting.certificate_on else "—",
                " ".join(sitting.memo.split()),
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 3 and sitting.passed:
                    item.setForeground(GOOD)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        exam = self.ctx.masters.exams.get(exam_id) if exam_id else None
        if exam is None:
            self.status.setText("資格を登録すると受験回を記録できます")
        else:
            self.status.setText(f"いまの状態：{STATUS_LABELS.get(exam.status, exam.status)}")

    def refresh_achievements(self) -> None:
        self._achievements = self.ctx.results.achievements()
        self.achievements.setRowCount(len(self._achievements))
        for row, (exam, sitting) in enumerate(self._achievements):
            values = [
                exam.name,
                sitting.label or "—",
                sitting.exam_date.isoformat() if sitting.exam_date else "—",
                "—" if sitting.score is None else str(sitting.score),
                sitting.certificate_on.isoformat() if sitting.certificate_on else "未受領",
            ]
            for column, text in enumerate(values):
                self.achievements.setItem(row, column, QTableWidgetItem(text))
        self.achievements.resizeColumnsToContents()
        self.achievements.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def _selected(self):
        row = self.table.currentRow()
        return self._sittings[row] if 0 <= row < len(self._sittings) else None

    # --- 操作 ---------------------------------------------------------------

    def _add(self) -> None:
        exam_id = combo_id(self.exam)
        if exam_id is None:
            show_error(self, "先に資格を登録してください")
            return
        dialog = SittingDialog(self.ctx.tasks.today(), parent=self)
        if not dialog.exec():
            return
        values = dialog.values()
        self.ctx.results.add_sitting(exam_id, values["exam_date"], values["label"])
        self.refresh_sittings()

    def _edit(self) -> None:
        sitting = self._selected()
        if sitting is None:
            show_error(self, "受験回を選んでください")
            return
        dialog = SittingDialog(self.ctx.tasks.today(), sitting, parent=self)
        if not dialog.exec():
            return
        self.ctx.results.update_sitting(sitting.id, **dialog.values())
        self.refresh_sittings()

    def _record(self) -> None:
        sitting = self._selected()
        if sitting is None:
            show_error(self, "受験回を選んでください")
            return
        dialog = ResultDialog(self.ctx.tasks.today(), sitting, parent=self)
        if not dialog.exec():
            return
        summary = self.ctx.results.record_result(sitting.id, **dialog.values())
        self.refresh()
        if summary is not None:
            SummaryDialog(summary, parent=self).exec()

    def _make_primary(self) -> None:
        sitting = self._selected()
        if sitting is None:
            show_error(self, "受験回を選んでください")
            return
        self.ctx.results.set_primary(sitting.id)
        self.refresh_sittings()

    def _delete(self) -> None:
        sitting = self._selected()
        if sitting is None:
            show_error(self, "受験回を選んでください")
            return
        name = sitting.label or (sitting.exam_date.isoformat() if sitting.exam_date else "この受験回")
        if confirm(self, f"「{name}」を削除しますか？"):
            self.ctx.results.delete_sitting(sitting.id)
            self.refresh()

    def _show_summary(self) -> None:
        exam_id = combo_id(self.exam)
        if exam_id is None:
            show_error(self, "資格を選んでください")
            return
        summary = self.ctx.results.summary(exam_id)
        if summary is None:
            show_error(self, "資格が見つかりません")
            return
        if summary.total_seconds == 0:
            show_info(self, "まだ勉強の記録がありません。")
            return
        SummaryDialog(summary, congratulate=summary.exam.status == "passed", parent=self).exec()

    def _open_achievement(self) -> None:
        row = self.achievements.currentRow()
        if not (0 <= row < len(self._achievements)):
            return
        exam, _sitting = self._achievements[row]
        index = self.exam.findData(exam.id)
        if index >= 0:
            self.exam.setCurrentIndex(index)
        summary = self.ctx.results.summary(exam.id)
        if summary is not None:
            SummaryDialog(summary, parent=self).exec()
