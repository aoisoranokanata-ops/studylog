"""受験回と結果の入力、それに合格したときの振り返り。"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
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
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ....core import clock
from ....services.result_service import ExamSummary, SittingResult
from ...widgets.charts import Meter, Panel, StatTile, TEXT_MUTED
from ...widgets.common import OptionalSpinBox

PASS_LABELS = [("未判定", None), ("合格", True), ("不合格", False)]


def _buttons(dialog: QDialog, save: str = "保存") -> QDialogButtonBox:
    box = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, parent=dialog
    )
    box.button(QDialogButtonBox.StandardButton.Save).setText(save)
    box.button(QDialogButtonBox.StandardButton.Cancel).setText("やめる")
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


class SittingDialog(QDialog):
    """受験回そのもの（年度と試験日）。"""

    def __init__(self, today: date, sitting: SittingResult | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("受験回の編集" if sitting else "受験回を追加")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.label = QLineEdit(sitting.label if sitting else "", self)
        self.label.setPlaceholderText("例：2026年度")
        form.addRow("回", self.label)

        self.has_date = QCheckBox("試験日が決まっている", self)
        self.exam_date = QDateEdit(self)
        self.exam_date.setCalendarPopup(True)
        self.exam_date.setDisplayFormat("yyyy-MM-dd")
        value = (sitting.exam_date if sitting else None) or today
        self.exam_date.setDate(QDate(value.year, value.month, value.day))
        self.has_date.setChecked(sitting.exam_date is not None if sitting else True)
        self.exam_date.setEnabled(self.has_date.isChecked())
        self.has_date.toggled.connect(self.exam_date.setEnabled)
        form.addRow("", self.has_date)
        form.addRow("試験日", self.exam_date)

        layout.addLayout(form)
        layout.addWidget(_buttons(self))

    def values(self) -> dict:
        return {
            "label": self.label.text().strip(),
            "exam_date": self.exam_date.date().toPython() if self.has_date.isChecked() else None,
        }


class ResultDialog(QDialog):
    """点数と合否、合格証の受領日。"""

    def __init__(self, today: date, sitting: SittingResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("結果を記録")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        title = sitting.label or (sitting.exam_date.isoformat() if sitting.exam_date else "受験回")
        layout.addWidget(QLabel(f"{title} の結果を入れます。", self))

        form = QFormLayout()
        self.score = OptionalSpinBox(0, 9999, self)
        self.score.set_value_or_none(sitting.score)
        form.addRow("点数", self.score)

        self.passed = QComboBox(self)
        for text, value in PASS_LABELS:
            self.passed.addItem(text, value)
        self.passed.setCurrentIndex(max(0, self.passed.findData(sitting.passed)))
        form.addRow("合否", self.passed)

        self.has_certificate = QCheckBox("合格証を受け取った", self)
        self.certificate = QDateEdit(self)
        self.certificate.setCalendarPopup(True)
        self.certificate.setDisplayFormat("yyyy-MM-dd")
        value = sitting.certificate_on or today
        self.certificate.setDate(QDate(value.year, value.month, value.day))
        self.has_certificate.setChecked(sitting.certificate_on is not None)
        self.certificate.setEnabled(self.has_certificate.isChecked())
        self.has_certificate.toggled.connect(self.certificate.setEnabled)
        form.addRow("", self.has_certificate)
        form.addRow("受領日", self.certificate)

        self.memo = QPlainTextEdit(sitting.memo, self)
        self.memo.setPlaceholderText("手ごたえ、次に活かすこと")
        self.memo.setFixedHeight(80)
        form.addRow("メモ", self.memo)

        layout.addLayout(form)
        layout.addWidget(_buttons(self, "記録する"))

    def values(self) -> dict:
        return {
            "score": self.score.value_or_none(),
            "passed": self.passed.currentData(),
            "memo": self.memo.toPlainText().strip(),
            "certificate_on": self.certificate.date().toPython() if self.has_certificate.isChecked() else None,
        }


class SummaryDialog(QDialog):
    """合格したときの振り返り。積み上げた数字を並べて見せる。"""

    def __init__(self, summary: ExamSummary, *, congratulate: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("振り返り")
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel(
            f"{summary.exam.name} 合格おめでとうございます" if congratulate else f"{summary.exam.name} の積み上げ",
            self,
        )
        font = title.font()
        font.setPointSize(font.pointSize() + 5)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        total = StatTile("総勉強時間", self)
        total.set(f"{clock.format_hm(summary.total_seconds)}", f"{summary.sessions}回の記録")
        days = StatTile("勉強した日数", self)
        days.set(f"{summary.study_days}日", f"1日あたり {clock.format_hm(summary.average_per_study_day)}")
        span = StatTile("学習期間", self)
        if summary.first_day and summary.last_day:
            span.set(f"{summary.span_days}日", f"{summary.first_day} 〜 {summary.last_day}")
        else:
            span.set("—", "記録がありません")
        mistakes = StatTile("克服した誤答", self)
        mistakes.set(f"{summary.mistakes_mastered}件", f"記録した誤答 {summary.mistakes_total}件")
        for tile in (total, days, span, mistakes):
            tiles.addWidget(tile)
        layout.addLayout(tiles)

        detail = Panel("いちばん時間をかけたもの", self)
        for caption, item in (("分野", summary.top_subject), ("参考書", summary.top_material)):
            text = f"{item[0]}（{clock.format_hm(item[1])}）" if item else "—"
            row = QLabel(f"{caption}：{text}", self)
            detail.body.addWidget(row)
        if summary.goal_ratio is not None:
            goal = QLabel(
                f"目標 {clock.format_hm(summary.goal_seconds or 0)} に対して {summary.goal_ratio * 100:.0f}%",
                self,
            )
            goal.setStyleSheet(f"color: {TEXT_MUTED.name()};")
            meter = Meter(self, height=12)
            meter.set_ratio(summary.goal_ratio)
            detail.body.addWidget(goal)
            detail.body.addWidget(meter)
        layout.addWidget(detail)

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        close.button(QDialogButtonBox.StandardButton.Close).setText("閉じる")
        close.rejected.connect(self.accept)
        close.accepted.connect(self.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
