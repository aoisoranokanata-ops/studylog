"""計測モジュール。"""

from __future__ import annotations

from ...module_registry import FeatureModule
from .view import TimerView

MODULE = FeatureModule(
    id="timer",
    title="計測",
    order=10,
    factory=TimerView,
    description="ストップウォッチで勉強時間を測る",
)
