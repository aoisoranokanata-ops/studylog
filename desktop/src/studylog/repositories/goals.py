"""週目標のリポジトリ。exam_id が NULL の行は全体の目標。"""

from __future__ import annotations

from datetime import date

from .base import BaseRepository


class WeeklyGoalRepository(BaseRepository):
    table = "weekly_goals"

    def _exam_clause(self, exam_id: str | None) -> tuple[str, list]:
        if exam_id is None:
            return "exam_id IS NULL", []
        return "exam_id = ?", [exam_id]

    def exact(self, week_start: date, exam_id: str | None = None):
        clause, params = self._exam_clause(exam_id)
        return self.conn.execute(
            f"SELECT * FROM weekly_goals WHERE deleted_at IS NULL AND week_start = ? AND {clause}",
            [week_start.isoformat(), *params],
        ).fetchone()

    def effective(self, week_start: date, exam_id: str | None = None):
        """その週に効いている目標。未設定の週は、それより前で最も新しい週の値を引き継ぐ。"""
        clause, params = self._exam_clause(exam_id)
        return self.conn.execute(
            f"SELECT * FROM weekly_goals WHERE deleted_at IS NULL AND week_start <= ? AND {clause} "
            f"ORDER BY week_start DESC LIMIT 1",
            [week_start.isoformat(), *params],
        ).fetchone()

    def set(self, week_start: date, seconds: int, exam_id: str | None = None) -> str:
        row = self.exact(week_start, exam_id)
        if row is None:
            return self.insert(
                {"week_start": week_start.isoformat(), "exam_id": exam_id, "goal_seconds": int(seconds)}
            )
        self.update(row["id"], {"goal_seconds": int(seconds)})
        return row["id"]

    def clear(self, week_start: date, exam_id: str | None = None) -> None:
        row = self.exact(week_start, exam_id)
        if row is not None:
            self.soft_delete(row["id"])
