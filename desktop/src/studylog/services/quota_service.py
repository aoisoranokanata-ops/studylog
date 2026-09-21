"""ノルマ（子機に渡す今日の作業）の作成と編集。"""

from __future__ import annotations

from datetime import date

from ..core import clock
from ..db.connection import transaction
from ..domain.models import Quota
from ..repositories.quotas import QuotaRepository
from .master_service import MasterService
from .settings_service import SettingsService


class QuotaService:
    def __init__(
        self, quotas: QuotaRepository, masters: MasterService, settings: SettingsService
    ) -> None:
        self.quotas = quotas
        self.masters = masters
        self.settings = settings
        self.conn = quotas.conn

    def list(self, day: date, day_to: date | None = None) -> list[Quota]:
        return self.quotas.list(day, day_to)

    def get(self, quota_id: str) -> Quota | None:
        return self.quotas.get(quota_id)

    def create(
        self,
        *,
        day: date,
        title: str,
        target_seconds: int,
        exam_id: str | None = None,
        material_id: str | None = None,
        subject_id: str | None = None,
        range_unit: str | None = None,
        range_from: int | None = None,
        range_to: int | None = None,
        note: str = "",
        plan_id: str | None = None,
    ) -> str:
        if not exam_id:
            raise ValueError("ノルマには資格を選んでください")
        title = title.strip() or self._default_title(exam_id, material_id, subject_id)
        if range_from is not None and range_to is not None and range_from > range_to:
            raise ValueError("範囲の開始が終了より後になっています")
        return self.quotas.insert(
            {
                "date": day.isoformat(),
                "sort_order": self.quotas.next_sort_order(day),
                "exam_id": exam_id,
                "material_id": material_id,
                "subject_id": subject_id,
                "title": title,
                "target_seconds": max(0, int(target_seconds)),
                "range_unit": range_unit,
                "range_from": range_from,
                "range_to": range_to,
                "note": note,
                "plan_id": plan_id,
            }
        )

    def update(self, quota_id: str, values: dict) -> None:
        data = dict(values)
        if "date" in data and isinstance(data["date"], date):
            data["date"] = data["date"].isoformat()
        range_from = data.get("range_from")
        range_to = data.get("range_to")
        if range_from is not None and range_to is not None and range_from > range_to:
            raise ValueError("範囲の開始が終了より後になっています")
        if "exam_id" in data and not data["exam_id"]:
            raise ValueError("ノルマには資格を選んでください")
        self.quotas.update(quota_id, data)

    def delete(self, quota_id: str) -> None:
        self.quotas.soft_delete(quota_id)

    def move(self, quota_id: str, offset: int) -> None:
        """並べ替え（-1で上へ、+1で下へ）。"""
        quota = self.quotas.get(quota_id)
        if quota is None:
            return
        siblings = self.quotas.list(quota.date)
        index = next((i for i, item in enumerate(siblings) if item.id == quota_id), None)
        if index is None:
            return
        target = index + offset
        if not 0 <= target < len(siblings):
            return
        siblings[index], siblings[target] = siblings[target], siblings[index]
        with transaction(self.conn):
            for order, item in enumerate(siblings, start=1):
                self.quotas.update(item.id, {"sort_order": order})

    def build_from_plans(self, day: date) -> int:
        """その日の予定からノルマの案を作る（すでに作ってある予定は飛ばす）。"""
        plans = self.quotas.query(
            "SELECT * FROM plans WHERE deleted_at IS NULL AND date = ? ORDER BY time_of_day, created_at",
            (day.isoformat(),),
        )
        existing = {quota.plan_id for quota in self.quotas.list(day) if quota.plan_id}
        created = 0
        with transaction(self.conn):
            for plan in plans:
                if plan["id"] in existing or not plan["exam_id"]:
                    continue
                self.create(
                    day=day,
                    title=plan["title"],
                    target_seconds=plan["planned_seconds"],
                    exam_id=plan["exam_id"],
                    material_id=plan["material_id"],
                    subject_id=plan["subject_id"],
                    range_unit=plan["range_unit"],
                    range_from=plan["range_from"],
                    range_to=plan["range_to"],
                    note=plan["note"],
                    plan_id=plan["id"],
                )
                created += 1
        return created

    def copy_from(self, source_day: date, target_day: date) -> int:
        """別の日のノルマを複製する（前日と同じ内容を使いたいとき用）。"""
        created = 0
        with transaction(self.conn):
            for quota in self.quotas.list(source_day):
                self.create(
                    day=target_day,
                    title=quota.title,
                    target_seconds=quota.target_seconds,
                    exam_id=quota.exam_id,
                    material_id=quota.material_id,
                    subject_id=quota.subject_id,
                    range_unit=quota.range_unit,
                    range_from=quota.range_from,
                    range_to=quota.range_to,
                    note=quota.note,
                )
                created += 1
        return created

    def actual_seconds(self, quota_id: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(active_seconds), 0) AS total FROM sessions "
            "WHERE quota_id = ? AND deleted_at IS NULL",
            (quota_id,),
        ).fetchone()
        return int(row["total"])

    def labels_for(self, quota: Quota) -> dict[str, str | None]:
        return self.masters.labels_for(quota.exam_id, quota.material_id, quota.subject_id)

    def _default_title(
        self, exam_id: str | None, material_id: str | None, subject_id: str | None
    ) -> str:
        labels = self.masters.labels_for(exam_id, material_id, subject_id)
        parts = [labels["subject"] or labels["exam"] or "", labels["material"] or ""]
        return " ".join(part for part in parts if part).strip() or "ノルマ"

    def today(self) -> date:
        return clock.study_date(clock.now_utc(), self.settings.day_change_hour)
