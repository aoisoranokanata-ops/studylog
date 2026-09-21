"""誤答と復習結果のリポジトリ。"""

from __future__ import annotations

from datetime import date

from ..domain.models import Mistake
from .base import BaseRepository


class MistakeRepository(BaseRepository):
    table = "mistakes"

    def list(
        self,
        *,
        exam_id: str | None = None,
        due_on: date | None = None,
        include_mastered: bool = False,
        limit: int | None = None,
    ) -> list[Mistake]:
        sql = "SELECT * FROM mistakes WHERE deleted_at IS NULL"
        params: list = []
        if exam_id:
            sql += " AND exam_id = ?"
            params.append(exam_id)
        if due_on is not None:
            sql += " AND next_review_on IS NOT NULL AND next_review_on <= ?"
            params.append(due_on.isoformat())
        if not include_mastered:
            sql += " AND mastery <> 'mastered'"
        sql += " ORDER BY next_review_on, created_at"
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        return [Mistake.from_row(row) for row in self.query(sql, params)]

    def get(self, mistake_id: str) -> Mistake | None:
        row = self.row(mistake_id)
        return Mistake.from_row(row) if row and row["deleted_at"] is None else None

    def count_unmastered(self, exam_id: str | None = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM mistakes WHERE deleted_at IS NULL AND mastery <> 'mastered'"
        params: list = []
        if exam_id:
            sql += " AND exam_id = ?"
            params.append(exam_id)
        return int(self.conn.execute(sql, params).fetchone()["n"])


class ReviewResultRepository(BaseRepository):
    table = "review_results"

    def exists_id(self, result_id: str) -> bool:
        return self.row(result_id) is not None

    def for_mistake(self, mistake_id: str) -> list:
        return self.query(
            "SELECT * FROM review_results WHERE mistake_id = ? AND deleted_at IS NULL "
            "ORDER BY reviewed_at",
            (mistake_id,),
        )
