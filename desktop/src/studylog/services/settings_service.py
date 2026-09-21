"""設定の読み書き。既定値もここに集める。"""

from __future__ import annotations

import json
from pathlib import Path

from .. import config
from ..core import ids
from ..repositories.settings import SettingsRepository

DEFAULTS: dict[str, str] = {
    "day_change_hour": "4",
    "week_starts_on": "1",            # ISO-8601（1=月曜）
    "backup_generations": "14",
    "long_session_hours": "5",        # つけっぱなし判定
    "review_intervals": "1,3,7,14,30",
    "mastery_streak": "3",            # 連続正解で克服とみなす回数
    "sync_dir": "",                   # 空なら data/sync
    "last_exam_id": "",
    "last_material_id": "",
    "last_subject_id": "",
}


class SettingsService:
    def __init__(self, repo: SettingsRepository) -> None:
        self.repo = repo
        self._cache: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        self._cache = {**DEFAULTS, **self.repo.all()}

    # --- 基本 ---------------------------------------------------------------

    def get(self, key: str, default: str = "") -> str:
        return self._cache.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: str) -> None:
        self.repo.set(key, value)
        self._cache[key] = value

    def get_int(self, key: str) -> int:
        try:
            return int(self.get(key))
        except (TypeError, ValueError):
            return int(DEFAULTS.get(key, "0") or 0)

    # --- よく使う値 ---------------------------------------------------------

    @property
    def day_change_hour(self) -> int:
        return min(23, max(0, self.get_int("day_change_hour")))

    @property
    def week_starts_on(self) -> int:
        value = self.get_int("week_starts_on")
        return value if 1 <= value <= 7 else 1

    @property
    def backup_generations(self) -> int:
        return max(1, self.get_int("backup_generations"))

    @property
    def long_session_seconds(self) -> int:
        return max(1, self.get_int("long_session_hours")) * 3600

    @property
    def review_intervals(self) -> list[int]:
        parts = [p.strip() for p in self.get("review_intervals").split(",") if p.strip()]
        try:
            values = [int(p) for p in parts]
        except ValueError:
            values = [1, 3, 7, 14, 30]
        return values or [1, 3, 7, 14, 30]

    @property
    def sync_dir(self) -> Path:
        raw = self.get("sync_dir").strip()
        return Path(raw) if raw else config.default_sync_dir()

    def set_sync_dir(self, path: Path | str | None) -> None:
        self.set("sync_dir", "" if not path else str(path))

    @property
    def hub_id(self) -> str:
        """母艦の識別ID。初回に採番して保存する。"""
        value = self.get("hub_id")
        if not value:
            value = ids.new_id()
            self.set("hub_id", value)
        return value

    # --- 前回使った分類 -----------------------------------------------------

    def last_used(self) -> dict[str, str | None]:
        return {
            "exam_id": self.get("last_exam_id") or None,
            "material_id": self.get("last_material_id") or None,
            "subject_id": self.get("last_subject_id") or None,
        }

    def remember_last_used(
        self, exam_id: str | None, material_id: str | None, subject_id: str | None
    ) -> None:
        self.set("last_exam_id", exam_id or "")
        self.set("last_material_id", material_id or "")
        self.set("last_subject_id", subject_id or "")

    # --- そのほか -----------------------------------------------------------

    def get_json(self, key: str, default):
        raw = self.get(key)
        if not raw:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    def set_json(self, key: str, value) -> None:
        self.set(key, json.dumps(value, ensure_ascii=False))
