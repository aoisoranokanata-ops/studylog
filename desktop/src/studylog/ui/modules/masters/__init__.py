"""マスタ管理モジュール。"""

from __future__ import annotations

from ...module_registry import FeatureModule
from .view import MastersView

MODULE = FeatureModule(
    id="masters",
    title="マスタ",
    order=30,
    factory=MastersView,
    description="資格・参考書・分野の管理",
)
