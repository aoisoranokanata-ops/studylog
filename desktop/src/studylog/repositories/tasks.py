"""課題のリポジトリ（管理画面はフェーズ5。いまはダッシュボードの「期限が近い課題」に使う）。"""

from __future__ import annotations

from datetime import date, timedelta

from .base import BaseRepository


class TaskRepository(BaseRepository):
    table = "tasks"

    def due_soon(self, today: date, days: int = 7) -> list:
        """未完了で、期限切れか days 日以内に期限が来るもの（期限の近い順）。"""
        return self.query(
            "SELECT * FROM tasks WHERE deleted_at IS NULL AND done = 0 AND due_on IS NOT NULL "
            "AND due_on <= ? ORDER BY due_on, priority",
            ((today + timedelta(days=days)).isoformat(),),
        )
