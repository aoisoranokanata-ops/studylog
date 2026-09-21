"""設定モジュール。"""

from __future__ import annotations

from ...module_registry import FeatureModule
from .view import SettingsView

MODULE = FeatureModule(
    id="settings",
    title="設定",
    order=90,
    factory=SettingsView,
    description="日付変更時刻・週の開始・バックアップなど",
)
