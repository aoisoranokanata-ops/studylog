"""画面づくりの小道具。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from PySide6.QtCore import QDate, QDateTime, QTime, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QWidget,
)

from ...core import clock

NONE_VALUE = "__none__"


# --- コンボボックス ---------------------------------------------------------

def fill_combo(
    combo: QComboBox,
    items: Sequence[tuple[str, str]],
    *,
    current: str | None = None,
    empty_label: str | None = None,
) -> None:
    """(id, 表示名) の並びを入れ直す。empty_label を渡すと「選ばない」を先頭に置く。"""
    combo.blockSignals(True)
    combo.clear()
    if empty_label is not None:
        combo.addItem(empty_label, NONE_VALUE)
    for value, label in items:
        combo.addItem(label, value)
    if current:
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
    else:
        combo.setCurrentIndex(0)
    combo.blockSignals(False)


def combo_id(combo: QComboBox) -> str | None:
    value = combo.currentData()
    return None if value in (None, NONE_VALUE) else str(value)


# --- 日時 -------------------------------------------------------------------

def to_qdatetime(value: datetime) -> QDateTime:
    local = clock.to_local(value)
    return QDateTime(
        QDate(local.year, local.month, local.day),
        QTime(local.hour, local.minute, local.second),
    )


def from_qdatetime(value: QDateTime) -> datetime:
    """入力された日時を、ローカル時刻として解釈する。"""
    naive = value.toPython()
    if isinstance(naive, datetime):
        return naive.replace(microsecond=0).astimezone()
    raise TypeError(f"日時として読めない: {value!r}")


# --- 所要時間 ---------------------------------------------------------------

class DurationEdit(QWidget):
    """「1時間30分」のように時と分で入力する。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.hours = QSpinBox(self)
        self.hours.setRange(0, 23)
        self.hours.setSuffix(" 時間")
        self.minutes = QSpinBox(self)
        self.minutes.setRange(0, 59)
        self.minutes.setSuffix(" 分")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.hours)
        layout.addWidget(self.minutes)
        layout.addStretch(1)

    def seconds(self) -> int:
        return self.hours.value() * 3600 + self.minutes.value() * 60

    def set_seconds(self, seconds: int) -> None:
        seconds = max(0, int(seconds))
        self.hours.setValue(min(23, seconds // 3600))
        self.minutes.setValue(seconds % 3600 // 60)


class OptionalSpinBox(QSpinBox):
    """未入力（None）を表せる数値入力。最小値の1つ下を「―」として使う。"""

    def __init__(self, minimum: int = 0, maximum: int = 99999, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRange(minimum - 1, maximum)
        self.setSpecialValueText("―")
        self.setValue(minimum - 1)
        self._empty = minimum - 1

    def value_or_none(self) -> int | None:
        value = self.value()
        return None if value == self._empty else value

    def set_value_or_none(self, value: int | None) -> None:
        self.setValue(self._empty if value is None else int(value))


# --- メッセージ -------------------------------------------------------------

def show_error(parent: QWidget | None, message: str, title: str = "エラー") -> None:
    QMessageBox.warning(parent, title, message)


def show_info(parent: QWidget | None, message: str, title: str = "お知らせ") -> None:
    QMessageBox.information(parent, title, message)


def confirm(parent: QWidget | None, message: str, title: str = "確認") -> bool:
    answer = QMessageBox.question(
        parent,
        title,
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def heading(text: str, parent: QWidget | None = None) -> QLabel:
    label = QLabel(text, parent)
    font = label.font()
    font.setPointSize(font.pointSize() + 3)
    font.setBold(True)
    label.setFont(font)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return label
