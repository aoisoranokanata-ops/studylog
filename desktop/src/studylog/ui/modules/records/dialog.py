"""記録の手動追加・編集ダイアログ。"""

from __future__ import annotations

from datetime import timedelta

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

from ....context import AppContext
from ....core import clock
from ....domain import enums
from ....domain.models import Session
from ...widgets.classification import ClassificationPicker
from ...widgets.common import (
    NONE_VALUE,
    DurationEdit,
    OptionalSpinBox,
    from_qdatetime,
    to_qdatetime,
)


class SessionDialog(QDialog):
    def __init__(
        self, ctx: AppContext, session: Session | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.session = session
        self.setWindowTitle("記録の編集" if session else "記録を追加")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        now = clock.now_utc()
        started = session.started_at if session else now - timedelta(hours=1)
        ended = session.ended_at if session else now

        self.started_at = QDateTimeEdit(self)
        self.started_at.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.started_at.setDateTime(to_qdatetime(started))
        self.ended_at = QDateTimeEdit(self)
        self.ended_at.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.ended_at.setDateTime(to_qdatetime(ended))
        form.addRow("開始", self.started_at)
        form.addRow("終了", self.ended_at)

        self.duration = DurationEdit(self)
        self.duration.set_seconds(
            session.active_seconds if session else int((ended - started).total_seconds())
        )
        form.addRow("勉強時間", self.duration)

        self.picker = ClassificationPicker(ctx.masters, self)
        if session:
            self.picker.set_values(
                {
                    "exam_id": session.exam_id,
                    "material_id": session.material_id,
                    "subject_id": session.subject_id,
                }
            )
        else:
            self.picker.set_values(ctx.sessions.initial_classification())
        form.addRow(self.picker)

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

        self.memo = QLineEdit(self)
        form.addRow("メモ", self.memo)

        if session:
            self.range_unit.setCurrentIndex(max(0, self.range_unit.findData(session.range_unit)))
            self.range_from.set_value_or_none(session.range_from)
            self.range_to.set_value_or_none(session.range_to)
            self.correct.set_value_or_none(session.correct)
            self.attempted.set_value_or_none(session.attempted)
            if session.focus:
                self.focus.setCurrentIndex(max(0, self.focus.findData(session.focus)))
            self.memo.setText(session.memo)

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

        self.started_at.dateTimeChanged.connect(self._sync_duration)
        self.ended_at.dateTimeChanged.connect(self._sync_duration)

    def _sync_duration(self) -> None:
        """開始・終了を動かしたら、勉強時間もその長さに合わせる（あとから手で直せる）。"""
        span = int((self.ended_datetime() - self.started_datetime()).total_seconds())
        self.duration.set_seconds(max(0, span))

    def started_datetime(self):
        return from_qdatetime(self.started_at.dateTime())

    def ended_datetime(self):
        return from_qdatetime(self.ended_at.dateTime())

    def values(self) -> dict:
        unit = self.range_unit.currentData()
        focus = self.focus.currentData()
        classification = self.picker.values()
        return {
            "started_at": self.started_datetime(),
            "ended_at": self.ended_datetime(),
            "active_seconds": self.duration.seconds(),
            "exam_id": classification["exam_id"],
            "material_id": classification["material_id"],
            "subject_id": classification["subject_id"],
            "range_unit": None if unit == NONE_VALUE else unit,
            "range_from": self.range_from.value_or_none(),
            "range_to": self.range_to.value_or_none(),
            "correct": self.correct.value_or_none(),
            "attempted": self.attempted.value_or_none(),
            "focus": None if focus == NONE_VALUE else int(focus),
            "memo": self.memo.text().strip(),
        }
