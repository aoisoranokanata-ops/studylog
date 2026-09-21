"""計測画面。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....context import AppContext
from ....core import clock
from ...widgets.classification import ClassificationPicker
from ...widgets.common import confirm, heading, show_error
from .finish_dialog import FinishDialog


class TimerView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        layout = QVBoxLayout(self)
        layout.addWidget(heading("計測"))

        self.elapsed_label = QLabel("00:00:00")
        font = self.elapsed_label.font()
        font.setPointSize(48)
        font.setBold(True)
        self.elapsed_label.setFont(font)
        self.elapsed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.elapsed_label)

        self.state_label = QLabel("停止中")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.state_label)

        box = QGroupBox("何を勉強する？", self)
        box_layout = QVBoxLayout(box)
        self.picker = ClassificationPicker(ctx.masters, box)
        self.picker.changed.connect(self._on_classification_changed)
        box_layout.addWidget(self.picker)
        self.memo = QLineEdit(box)
        self.memo.setPlaceholderText("メモ（任意）")
        box_layout.addWidget(self.memo)
        layout.addWidget(box)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("開始", self)
        self.pause_button = QPushButton("一時停止", self)
        self.finish_button = QPushButton("終了", self)
        self.discard_button = QPushButton("取り消し", self)
        for button in (self.start_button, self.pause_button, self.finish_button, self.discard_button):
            button.setMinimumHeight(40)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.start_button.clicked.connect(self._start)
        self.pause_button.clicked.connect(self._toggle_pause)
        self.finish_button.clicked.connect(self._finish)
        self.discard_button.clicked.connect(self._discard)

        self.today_label = QLabel()
        self.today_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.today_label)
        layout.addStretch(1)

        self.ticker = QTimer(self)
        self.ticker.setInterval(1000)
        self.ticker.timeout.connect(self._tick)
        self.ticker.start()

        self.refresh()

    # --- 表示 ---------------------------------------------------------------

    def refresh(self) -> None:
        self.picker.reload(self._initial_values())
        self._tick()

    def _initial_values(self) -> dict:
        state = self.ctx.timer.current()
        if state is not None:
            return {
                "exam_id": state.exam_id,
                "material_id": state.material_id,
                "subject_id": state.subject_id,
            }
        return self.ctx.sessions.initial_classification()

    def _tick(self) -> None:
        state = self.ctx.timer.current()
        self.elapsed_label.setText(clock.format_hms(self.ctx.timer.elapsed_seconds()))

        running = bool(state and state.is_running)
        has_state = state is not None
        self.start_button.setEnabled(not has_state)
        self.pause_button.setEnabled(has_state)
        self.finish_button.setEnabled(has_state)
        self.discard_button.setEnabled(has_state)
        self.pause_button.setText("一時停止" if running else "再開")
        self.picker.set_enabled(True)

        if not has_state:
            self.state_label.setText("停止中")
        elif running:
            started = clock.format_local(state.started_at, "%H:%M")
            self.state_label.setText(f"計測中（{started} 開始）")
        else:
            self.state_label.setText("一時停止中")

        today = clock.study_date(clock.now_utc(), self.ctx.settings.day_change_hour)
        seconds = self.ctx.sessions.seconds_for_day(today)
        week = self.ctx.sessions.seconds_for_week(today)
        self.today_label.setText(
            f"今日の合計 {clock.format_hm(seconds)}　/　今週 {clock.format_hm(week)}"
        )

    # --- 操作 ---------------------------------------------------------------

    def _on_classification_changed(self) -> None:
        if self.ctx.timer.current() is None:
            return
        values = self.picker.values()
        self.ctx.timer.update_classification(
            exam_id=values["exam_id"],
            material_id=values["material_id"],
            subject_id=values["subject_id"],
            memo=self.memo.text().strip(),
        )

    def _start(self) -> None:
        values = self.picker.values()
        try:
            self.ctx.timer.start(
                exam_id=values["exam_id"],
                material_id=values["material_id"],
                subject_id=values["subject_id"],
                memo=self.memo.text().strip(),
            )
        except RuntimeError as error:
            show_error(self, str(error))
        self._tick()

    def _toggle_pause(self) -> None:
        if self.ctx.timer.is_running():
            self.ctx.timer.pause()
        else:
            self.ctx.timer.resume()
        self._tick()

    def _finish(self) -> None:
        state = self.ctx.timer.current()
        if state is None:
            return
        now = clock.now_utc()
        dialog = FinishDialog(
            started_at=state.started_at,
            ended_at=now,
            elapsed_seconds=state.elapsed_seconds(now),
            long_session=self.ctx.timer.is_long(now),
            memo=self.memo.text().strip() or state.memo,
            parent=self,
        )
        if not dialog.exec():
            return

        values = self.picker.values()
        try:
            self.ctx.timer.finish(
                now=now,
                exam_id=values["exam_id"],
                material_id=values["material_id"],
                subject_id=values["subject_id"],
                **dialog.values(),
            )
        except ValueError as error:
            show_error(self, str(error))
            return
        self.memo.clear()
        self.refresh()

    def _discard(self) -> None:
        if confirm(self, "計測中の記録を捨てますか？（保存されません）"):
            self.ctx.timer.discard()
            self._tick()
