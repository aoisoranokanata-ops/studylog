"""ダッシュボードモジュール。起動時に最初に開く。"""

from __future__ import annotations

from ...module_registry import FeatureModule
from .view import DashboardView

MODULE = FeatureModule(
    id="dashboard",
    title="ダッシュボード",
    order=5,
    factory=DashboardView,
    description="今日・今週の勉強時間、試験日まで、今日のノルマと復習",
)
