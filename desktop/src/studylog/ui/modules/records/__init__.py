"""記録モジュール。"""

from __future__ import annotations

from ...module_registry import FeatureModule
from .view import RecordsView

MODULE = FeatureModule(
    id="records",
    title="記録",
    order=20,
    factory=RecordsView,
    description="勉強記録の一覧・手動追加・編集",
)
