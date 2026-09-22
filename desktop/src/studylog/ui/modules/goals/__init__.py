"""目標モジュール。"""

from __future__ import annotations

from ...module_registry import FeatureModule
from .view import GoalsView

MODULE = FeatureModule(
    id="goals",
    title="目標",
    order=27,
    factory=GoalsView,
    description="週目標（前の週を引き継ぐ）と、資格ごとの総勉強時間の目標",
)
