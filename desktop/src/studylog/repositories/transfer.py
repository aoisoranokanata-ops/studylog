"""子機・取り込み済みパッケージ・転送履歴のリポジトリ。"""

from __future__ import annotations

import json
from datetime import timedelta

from ..core import clock
from .base import BaseRepository

ACK_WINDOW_DAYS = 30


class DeviceRepository(BaseRepository):
    table = "devices"

    def upsert(self, device_id: str, name: str, package_id: str | None = None) -> None:
        now = clock.db_now()
        values = {"name": name, "last_received_at": now, "last_package_id": package_id}
        if self.row(device_id) is None:
            self.insert({**values, "id": device_id})
        else:
            self.update(device_id, values)

    def list(self) -> list:
        return self.query(
            "SELECT * FROM devices WHERE deleted_at IS NULL ORDER BY last_received_at DESC"
        )


class ImportedPackageRepository(BaseRepository):
    table = "imported_packages"

    def was_imported(self, package_id: str) -> bool:
        return self.row(package_id) is not None

    def record(self, package_id: str, device_id: str | None, included_ids: list[str]) -> None:
        now = clock.db_now()
        values = {
            "device_id": device_id,
            "imported_at": now,
            "included_ids": json.dumps(included_ids, ensure_ascii=False),
        }
        if self.was_imported(package_id):
            self.update(package_id, values)
        else:
            self.insert({**values, "id": package_id})

    def recent_ids(self, days: int = ACK_WINDOW_DAYS) -> list[str]:
        """acks に入れる packageId（取り込み日時から指定日数以内）。"""
        since = clock.to_db(clock.now_utc() - timedelta(days=days))
        rows = self.query(
            "SELECT id FROM imported_packages WHERE imported_at >= ? ORDER BY imported_at",
            (since,),
        )
        return [row["id"] for row in rows]


class TransferLogRepository(BaseRepository):
    table = "transfer_log"

    def record(
        self,
        *,
        direction: str,
        package_id: str | None,
        device_id: str | None = None,
        variant: str | None = None,
        counts: dict | None = None,
        result: str = "ok",
        message: str = "",
    ) -> str:
        return self.insert(
            {
                "direction": direction,
                "package_id": package_id,
                "occurred_at": clock.db_now(),
                "device_id": device_id,
                "variant": variant,
                "counts": json.dumps(counts or {}, ensure_ascii=False),
                "result": result,
                "message": message,
            }
        )

    def recent(self, limit: int = 100) -> list:
        return self.query(
            "SELECT * FROM transfer_log WHERE deleted_at IS NULL "
            "ORDER BY occurred_at DESC LIMIT ?",
            (int(limit),),
        )
