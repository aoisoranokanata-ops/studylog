"""勉強記録のリポジトリ。集計もここで行う（SQLite側で計算させる）。"""

from __future__ import annotations

from datetime import date

from ..domain.models import DailyTotal, Session, SessionFilter
from .base import BaseRepository


class SessionRepository(BaseRepository):
    table = "sessions"

    def _where(self, filters: SessionFilter) -> tuple[str, list]:
        clauses = ["deleted_at IS NULL"]
        params: list = []
        if filters.date_from:
            clauses.append("study_date >= ?")
            params.append(filters.date_from.isoformat())
        if filters.date_to:
            clauses.append("study_date <= ?")
            params.append(filters.date_to.isoformat())
        if filters.exam_id:
            clauses.append("exam_id = ?")
            params.append(filters.exam_id)
        if filters.material_id:
            clauses.append("material_id = ?")
            params.append(filters.material_id)
        if filters.subject_id:
            clauses.append("subject_id = ?")
            params.append(filters.subject_id)
        if filters.unclassified_only:
            clauses.append("unclassified = 1")
        if filters.keyword:
            clauses.append("memo LIKE ?")
            params.append(f"%{filters.keyword}%")
        return " AND ".join(clauses), params

    def list(self, filters: SessionFilter | None = None) -> list[Session]:
        filters = filters or SessionFilter()
        where, params = self._where(filters)
        sql = f"SELECT * FROM sessions WHERE {where} ORDER BY started_at DESC"
        if filters.limit:
            sql += " LIMIT ?"
            params.append(int(filters.limit))
        return [Session.from_row(row) for row in self.query(sql, params)]

    def get(self, session_id: str) -> Session | None:
        row = self.row(session_id)
        return Session.from_row(row) if row and row["deleted_at"] is None else None

    def total_seconds(self, filters: SessionFilter | None = None) -> int:
        filters = filters or SessionFilter()
        where, params = self._where(filters)
        row = self.conn.execute(
            f"SELECT COALESCE(SUM(active_seconds), 0) AS total FROM sessions WHERE {where}",
            params,
        ).fetchone()
        return int(row["total"])

    def daily_totals(self, date_from: date, date_to: date, exam_id: str | None = None) -> list[DailyTotal]:
        filters = SessionFilter(date_from=date_from, date_to=date_to, exam_id=exam_id)
        where, params = self._where(filters)
        rows = self.query(
            f"SELECT study_date AS d, SUM(active_seconds) AS total FROM sessions "
            f"WHERE {where} GROUP BY study_date ORDER BY study_date",
            params,
        )
        return [DailyTotal(day=date.fromisoformat(row["d"]), seconds=int(row["total"])) for row in rows]

    def count(self, filters: SessionFilter | None = None) -> int:
        filters = filters or SessionFilter()
        where, params = self._where(filters)
        row = self.conn.execute(f"SELECT COUNT(*) AS n FROM sessions WHERE {where}", params).fetchone()
        return int(row["n"])

    def study_days(self, date_from: date, date_to: date) -> list[date]:
        rows = self.query(
            "SELECT DISTINCT study_date AS d FROM sessions "
            "WHERE deleted_at IS NULL AND study_date BETWEEN ? AND ? ORDER BY study_date",
            (date_from.isoformat(), date_to.isoformat()),
        )
        return [date.fromisoformat(row["d"]) for row in rows]

    def last_used(self) -> dict[str, str | None]:
        """直近の記録の分類。次に記録するときの初期値に使う。"""
        row = self.conn.execute(
            "SELECT exam_id, material_id, subject_id FROM sessions "
            "WHERE deleted_at IS NULL AND unclassified = 0 ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return {"exam_id": None, "material_id": None, "subject_id": None}
        return {
            "exam_id": row["exam_id"],
            "material_id": row["material_id"],
            "subject_id": row["subject_id"],
        }

    def recompute_study_dates(self, day_change_hour: int) -> int:
        """日付変更時刻が変わったときに、全記録の学習日を計算し直す。"""
        from ..core import clock

        rows = self.query("SELECT id, started_at, study_date FROM sessions")
        changed = 0
        for row in rows:
            new_value = clock.study_date_str(clock.from_db(row["started_at"]), day_change_hour)
            if new_value != row["study_date"]:
                self.conn.execute(
                    "UPDATE sessions SET study_date = ? WHERE id = ?", (new_value, row["id"])
                )
                changed += 1
        return changed
