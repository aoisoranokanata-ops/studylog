"""課題モジュール。"""

from __future__ import annotations

from ...module_registry import FeatureModule
from .view import TasksView

MODULE = FeatureModule(
    id="tasks",
    title="課題",
    order=24,
    factory=TasksView,
    description="やること（期限・優先度つき）",
)
