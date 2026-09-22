"""結果モジュール。"""

from __future__ import annotations

from ...module_registry import FeatureModule
from .view import ResultsView

MODULE = FeatureModule(
    id="results",
    title="結果",
    order=28,
    factory=ResultsView,
    description="受験回の合否と実績",
)
