"""ノルマのリポジトリ。"""

from __future__ import annotations

from datetime import date

from ..domain.models import Quota
from .base import BaseRepository


class QuotaRepository(BaseRepository):
    table = "quotas"

    def list(self, date_from: date, date_to: date | None = None) -> list[Quota]:
        date_to = date_to or date_from
        rows = self.query(
            "SELECT * FROM quotas WHERE deleted_at IS NULL AND date BETWEEN ? AND ? "
            "ORDER BY date, sort_order",
            (date_from.isoformat(), date_to.isoformat()),
        )
        return [Quota.from_row(row) for row in rows]

    def get(self, quota_id: str) -> Quota | None:
        row = self.row(quota_id)
        return Quota.from_row(row) if row and row["deleted_at"] is None else None

    def next_sort_order(self, day: date) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM quotas "
            "WHERE date = ? AND deleted_at IS NULL",
            (day.isoformat(),),
        ).fetchone()
        return int(row["n"])

    def mark_sent(self, quota_ids: list[str], sent_at: str) -> None:
        if not quota_ids:
            return
        marks = ", ".join("?" * len(quota_ids))
        self.conn.execute(
            f"UPDATE quotas SET sent_at = ?, updated_at = ? WHERE id IN ({marks})",
            [sent_at, sent_at, *quota_ids],
        )

    def apply_status(self, quota_id: str, status: str, status_id: str, updated_at: str) -> bool:
        """子機から届いた達成状況を、新しい方だけ採用する（仕様書 第4章 処理4）。"""
        row = self.row(quota_id)
        if row is None:
            return False
        current = row["status_updated_at"]
        if current is not None and current >= updated_at:
            return False
        self.update(
            quota_id,
            {"status": status, "status_id": status_id, "status_updated_at": updated_at},
        )
        return True
