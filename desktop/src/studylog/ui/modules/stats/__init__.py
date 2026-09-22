"""集計モジュール。"""

from __future__ import annotations

from ...module_registry import FeatureModule
from .view import StatsView

MODULE = FeatureModule(
    id="stats",
    title="集計",
    order=25,
    factory=StatsView,
    description="日・週・月ごとの勉強時間、内訳、学習日数、正答率、参考書の進み具合",
)
