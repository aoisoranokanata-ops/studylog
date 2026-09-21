"""計測を終えるときの確認ダイアログ。入力はすべて任意。"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ....core import clock
from ....domain import enums
from ...widgets.common import (
    NONE_VALUE,
    OptionalSpinBox,
    from_qdatetime,
    to_qdatetime,
)


class FinishDialog(QDialog):
    def __init__(
        self,
        *,
        started_at: datetime,
        ended_at: datetime,
        elapsed_seconds: int,
        long_session: bool,
        memo: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("計測を終える")
        self.setMinimumWidth(420)
        self.started_at = started_at
        self.elapsed_seconds = elapsed_seconds

        layout = QVBoxLayout(self)

        if long_session:
            warning = QLabel(
                "5時間を超えています。つけっぱなしだった場合は、終了時刻を直してください。"
            )
            warning.setWordWrap(True)
            warning.setStyleSheet("color: #b34;")
            layout.addWidget(warning)

        form = QFormLayout()
        form.addRow("開始", QLabel(clock.format_local(started_at)))

        self.ended_at = QDateTimeEdit(self)
        self.ended_at.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.ended_at.setDateTime(to_qdatetime(ended_at))
        self.ended_at.dateTimeChanged.connect(self._update_duration)
        form.addRow("終了", self.ended_at)

        self.duration_label = QLabel()
        form.addRow("勉強時間", self.duration_label)

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

        self.correct = OptionalSpinBox(0, 9999, self)
        self.attempted = OptionalSpinBox(0, 9999, self)
        score_row = QWidget(self)
        score_layout = QHBoxLayout(score_row)
        score_layout.setContentsMargins(0, 0, 0, 0)
        score_layout.addWidget(self.correct)
        score_layout.addWidget(QLabel("/"))
        score_layout.addWidget(self.attempted)
        form.addRow("正答 / 解答", score_row)

        self.focus = QComboBox(self)
        self.focus.addItem("（未入力）", NONE_VALUE)
        for value, label in enums.FOCUS_LEVELS.items():
            self.focus.addItem(label, value)
        form.addRow("集中度", self.focus)

        self.memo = QLineEdit(memo, self)
        form.addRow("メモ", self.memo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("戻る")
        buttons.button(QDialogButtonBox.StandardButton.Save).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_duration()

    def _active_seconds(self) -> int:
        span = int((self.ended_datetime() - self.started_at).total_seconds())
        return max(0, min(self.elapsed_seconds, span))

    def _update_duration(self) -> None:
        self.duration_label.setText(clock.format_hms(self._active_seconds()))

    def ended_datetime(self) -> datetime:
        return from_qdatetime(self.ended_at.dateTime())

    def values(self) -> dict:
        unit = self.range_unit.currentData()
        focus = self.focus.currentData()
        return {
            "ended_at": self.ended_datetime(),
            "active_seconds": self._active_seconds(),
            "range_unit": None if unit == NONE_VALUE else unit,
            "range_from": self.range_from.value_or_none(),
            "range_to": self.range_to.value_or_none(),
            "correct": self.correct.value_or_none(),
            "attempted": self.attempted.value_or_none(),
            "focus": None if focus == NONE_VALUE else int(focus),
            "memo": self.memo.text().strip(),
        }
