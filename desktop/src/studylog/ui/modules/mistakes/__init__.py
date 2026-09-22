"""誤答モジュール。"""

from __future__ import annotations

from ...module_registry import FeatureModule
from .view import MistakesView

MODULE = FeatureModule(
    id="mistakes",
    title="誤答",
    order=22,
    factory=MistakesView,
    description="誤答の一覧と編集、母艦での復習、苦手分析",
)
