"""予定のリポジトリ。繰り返しの展開は services/plan_service.py で行う。"""

from __future__ import annotations

from datetime import date

from ..domain.models import Plan
from .base import BaseRepository


class PlanRepository(BaseRepository):
    table = "plans"

    def list_all(self) -> list[Plan]:
        rows = self.query(
            "SELECT * FROM plans WHERE deleted_at IS NULL ORDER BY date, time_of_day, created_at"
        )
        return [Plan.from_row(row) for row in rows]

    def list_candidates(self, date_from: date, date_to: date) -> list[Plan]:
        """その期間に関係しうる予定（単発はその期間のもの、繰り返しは期間と重なるもの）。"""
        rows = self.query(
            "SELECT * FROM plans WHERE deleted_at IS NULL AND ("
            "  (COALESCE(repeat_rule, 'none') = 'none' AND date BETWEEN ? AND ?)"
            "  OR (COALESCE(repeat_rule, 'none') <> 'none'"
            "      AND COALESCE(repeat_from, date) <= ?"
            "      AND (repeat_until IS NULL OR repeat_until >= ?))"
            ") ORDER BY time_of_day, created_at",
            (date_from.isoformat(), date_to.isoformat(), date_to.isoformat(), date_from.isoformat()),
        )
        return [Plan.from_row(row) for row in rows]

    def get(self, plan_id: str) -> Plan | None:
        row = self.row(plan_id)
        return Plan.from_row(row) if row and row["deleted_at"] is None else None


class PlanExceptionRepository(BaseRepository):
    table = "plan_exceptions"

    def dates_for(self, plan_ids: list[str]) -> set[tuple[str, str]]:
        if not plan_ids:
            return set()
        marks = ", ".join("?" * len(plan_ids))
        rows = self.query(
            f"SELECT plan_id, date FROM plan_exceptions "
            f"WHERE deleted_at IS NULL AND plan_id IN ({marks})",
            plan_ids,
        )
        return {(row["plan_id"], row["date"]) for row in rows}

    def add(self, plan_id: str, day: date) -> None:
        existing = self.query(
            "SELECT id FROM plan_exceptions WHERE plan_id = ? AND date = ?",
            (plan_id, day.isoformat()),
        )
        if existing:
            self.restore(existing[0]["id"])
            return
        self.insert({"plan_id": plan_id, "date": day.isoformat()})

    def remove(self, plan_id: str, day: date) -> None:
        rows = self.query(
            "SELECT id FROM plan_exceptions WHERE plan_id = ? AND date = ?",
            (plan_id, day.isoformat()),
        )
        for row in rows:
            self.hard_delete(row["id"])
