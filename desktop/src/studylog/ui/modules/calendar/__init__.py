"""カレンダーモジュール。"""

from __future__ import annotations

from ...module_registry import FeatureModule
from .view import CalendarView

MODULE = FeatureModule(
    id="calendar",
    title="カレンダー",
    order=15,
    factory=CalendarView,
    description="月・週の予定と実績、繰り返し予定、.ics の書き出し",
)
