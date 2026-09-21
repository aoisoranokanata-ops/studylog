"""転送モジュール。"""

from __future__ import annotations

from ...module_registry import FeatureModule
from .view import TransferView

MODULE = FeatureModule(
    id="transfer",
    title="転送",
    order=40,
    factory=TransferView,
    description="ノルマを子機へ渡し、子機の記録を取り込む",
)
