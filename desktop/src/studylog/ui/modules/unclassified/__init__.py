"""未分類モジュール。"""

from __future__ import annotations

from ...module_registry import FeatureModule
from .view import UnclassifiedView

MODULE = FeatureModule(
    id="unclassified",
    title="未分類",
    order=50,
    factory=UnclassifiedView,
    description="子機から届いた未分類の記録に、資格・参考書・分野を割り当てる",
)
