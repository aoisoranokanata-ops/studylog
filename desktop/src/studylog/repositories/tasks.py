"""課題のリポジトリ（管理画面はフェーズ5。いまはダッシュボードの「期限が近い課題」に使う）。"""

from __future__ import annotations

from datetime import date, timedelta

from .base import BaseRepository


class TaskRepository(BaseRepository):
    table = "tasks"

    def list(self, *, include_done: bool = True, exam_id: str | None = None) -> list:
        """期限の近い順。期限なしは最後。完了は下に回す。"""
        sql = "SELECT * FROM tasks WHERE deleted_at IS NULL"
        params: list = []
        if not include_done:
            sql += " AND done = 0"
        if exam_id:
            sql += " AND exam_id = ?"
            params.append(exam_id)
        sql += " ORDER BY done, COALESCE(due_on, '9999-12-31'), priority, created_at"
        return self.query(sql, params)

    def count_open(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE deleted_at IS NULL AND done = 0"
        ).fetchone()
        return int(row["n"])

    def due_soon(self, today: date, days: int = 7) -> list:
        """未完了で、期限切れか days 日以内に期限が来るもの（期限の近い順）。"""
        return self.query(
            "SELECT * FROM tasks WHERE deleted_at IS NULL AND done = 0 AND due_on IS NOT NULL "
            "AND due_on <= ? ORDER BY due_on, priority",
            ((today + timedelta(days=days)).isoformat(),),
        )
