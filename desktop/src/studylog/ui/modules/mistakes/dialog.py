"""誤答の追加・編集ダイアログ。"""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ....context import AppContext
from ....domain import enums
from ....domain.models import Mistake
from ...widgets.classification import ClassificationPicker
from ...widgets.common import NONE_VALUE


class MistakeDialog(QDialog):
    def __init__(self, ctx: AppContext, mistake: Mistake | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.mistake = mistake
        self.setWindowTitle("誤答の編集" if mistake else "誤答を追加")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.question_ref = QLineEdit(mistake.question_ref if mistake else "", self)
        self.question_ref.setPlaceholderText("例：p.52 問3")
        form.addRow("問題の識別", self.question_ref)

        self.memo = QPlainTextEdit(mistake.memo if mistake else "", self)
        self.memo.setPlaceholderText("どこで間違えたか（子機で入れた一言メモ）")
        self.memo.setFixedHeight(64)
        form.addRow("メモ", self.memo)

        self.answer_memo = QPlainTextEdit(mistake.answer_memo if mistake else "", self)
        self.answer_memo.setPlaceholderText("正解と、覚えておきたいポイント")
        self.answer_memo.setFixedHeight(80)
        form.addRow("正解・ポイント", self.answer_memo)

        self.reason = QComboBox(self)
        self.reason.addItem("（未選択）", NONE_VALUE)
        for key, label in enums.MISTAKE_REASON.items():
            self.reason.addItem(label, key)
        if mistake and mistake.reason:
            self.reason.setCurrentIndex(max(0, self.reason.findData(mistake.reason)))
        form.addRow("誤答の理由", self.reason)

        self.picker = ClassificationPicker(ctx.masters, self)
        if mistake:
            self.picker.set_values(
                {"exam_id": mistake.exam_id, "material_id": mistake.material_id, "subject_id": mistake.subject_id}
            )
        else:
            self.picker.set_values(ctx.sessions.initial_classification())
        form.addRow(self.picker)

        if mistake:
            self.mastery = QComboBox(self)
            for key, label in enums.MASTERY.items():
                self.mastery.addItem(label, key)
            self.mastery.setCurrentIndex(max(0, self.mastery.findData(mistake.mastery)))
            form.addRow("習熟", self.mastery)

            self.has_next = QCheckBox("次回の復習日を決める", self)
            self.next_review = QDateEdit(self)
            self.next_review.setCalendarPopup(True)
            self.next_review.setDisplayFormat("yyyy-MM-dd")
            today = ctx.mistakes.today()
            target = mistake.next_review_on or today
            self.next_review.setDate(QDate(target.year, target.month, target.day))
            self.has_next.setChecked(mistake.next_review_on is not None)
            self.next_review.setEnabled(self.has_next.isChecked())
            self.has_next.toggled.connect(self.next_review.setEnabled)
            form.addRow("", self.has_next)
            form.addRow("次回の復習日", self.next_review)

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
        reason = self.reason.currentData()
        classification = self.picker.values()
        values = {
            "question_ref": self.question_ref.text().strip(),
            "memo": self.memo.toPlainText().strip(),
            "answer_memo": self.answer_memo.toPlainText().strip(),
            "reason": None if reason == NONE_VALUE else reason,
            "exam_id": classification["exam_id"],
            "material_id": classification["material_id"],
            "subject_id": classification["subject_id"],
        }
        if self.mistake:
            values["mastery"] = self.mastery.currentData()
            values["next_review_on"] = (
                self.next_review.date().toPython() if self.has_next.isChecked() else None
            )
        return values
