"""勉強記録の作成・編集・削除。入力の妥当性はここで守る。"""

from __future__ import annotations

from datetime import datetime

from ..core import clock
from ..db.connection import transaction
from ..domain.models import Session, SessionFilter
from ..repositories.masters import MaterialRepository
from ..repositories.sessions import SessionRepository
from .settings_service import SettingsService


class SessionService:
    def __init__(
        self,
        sessions: SessionRepository,
        materials: MaterialRepository,
        settings: SettingsService,
    ) -> None:
        self.sessions = sessions
        self.materials = materials
        self.settings = settings
        self.conn = sessions.conn

    # --- 検証 ---------------------------------------------------------------

    @staticmethod
    def validate(
        started_at: datetime,
        ended_at: datetime,
        active_seconds: int,
        *,
        correct: int | None = None,
        attempted: int | None = None,
        focus: int | None = None,
        range_from: int | None = None,
        range_to: int | None = None,
    ) -> None:
        if ended_at < started_at:
            raise ValueError("終了時刻が開始時刻より前になっています")
        if active_seconds < 0:
            raise ValueError("勉強時間が負になっています")
        span = int((ended_at - started_at).total_seconds())
        if active_seconds > span:
            raise ValueError("勉強時間が、開始から終了までの長さを超えています")
        if correct is not None and attempted is not None and correct > attempted:
            raise ValueError("正答数が解答数を超えています")
        if focus is not None and not 1 <= focus <= 5:
            raise ValueError("集中度は1〜5です")
        if range_from is not None and range_to is not None and range_from > range_to:
            raise ValueError("範囲の開始が終了より後になっています")

    # --- 作成・更新・削除 ---------------------------------------------------

    def create(
        self,
        *,
        started_at: datetime,
        ended_at: datetime,
        active_seconds: int,
        exam_id: str | None = None,
        material_id: str | None = None,
        subject_id: str | None = None,
        quota_id: str | None = None,
        range_unit: str | None = None,
        range_from: int | None = None,
        range_to: int | None = None,
        correct: int | None = None,
        attempted: int | None = None,
        focus: int | None = None,
        memo: str = "",
        entry_mode: str = "timer",
        source: str = "hub",
        device_id: str | None = None,
        record_id: str | None = None,
        unclassified: bool | None = None,
    ) -> str:
        self.validate(
            started_at,
            ended_at,
            active_seconds,
            correct=correct,
            attempted=attempted,
            focus=focus,
            range_from=range_from,
            range_to=range_to,
        )
        if unclassified is None:
            unclassified = exam_id is None
        values = {
            "exam_id": exam_id,
            "material_id": material_id,
            "subject_id": subject_id,
            "quota_id": quota_id,
            "unclassified": 1 if unclassified else 0,
            "started_at": clock.to_db(started_at),
            "ended_at": clock.to_db(ended_at),
            "active_seconds": int(active_seconds),
            "study_date": clock.study_date_str(started_at, self.settings.day_change_hour),
            "range_unit": range_unit,
            "range_from": range_from,
            "range_to": range_to,
            "correct": correct,
            "attempted": attempted,
            "focus": focus,
            "memo": memo,
            "entry_mode": entry_mode,
            "source": source,
            "device_id": device_id,
        }
        with transaction(self.conn):
            session_id = self.sessions.insert(values, record_id=record_id)
            if material_id and range_to:
                self.materials.advance_current(material_id, range_to)
        if exam_id:
            self.settings.remember_last_used(exam_id, material_id, subject_id)
        return session_id

    def update(self, session_id: str, values: dict) -> None:
        current = self.sessions.get(session_id)
        if current is None:
            raise ValueError("記録が見つかりません")

        started_at = values.get("started_at", current.started_at)
        ended_at = values.get("ended_at", current.ended_at)
        active_seconds = values.get("active_seconds", current.active_seconds)
        self.validate(
            started_at,
            ended_at,
            int(active_seconds),
            correct=values.get("correct", current.correct),
            attempted=values.get("attempted", current.attempted),
            focus=values.get("focus", current.focus),
            range_from=values.get("range_from", current.range_from),
            range_to=values.get("range_to", current.range_to),
        )

        data = dict(values)
        if isinstance(data.get("started_at"), datetime):
            data["started_at"] = clock.to_db(data["started_at"])
            data["study_date"] = clock.study_date_str(started_at, self.settings.day_change_hour)
        if isinstance(data.get("ended_at"), datetime):
            data["ended_at"] = clock.to_db(data["ended_at"])
        if "unclassified" in data:
            data["unclassified"] = 1 if data["unclassified"] else 0
        elif "exam_id" in data:
            data["unclassified"] = 0 if data["exam_id"] else 1

        with transaction(self.conn):
            self.sessions.update(session_id, data)
            material_id = data.get("material_id", current.material_id)
            range_to = data.get("range_to", current.range_to)
            if material_id and range_to:
                self.materials.advance_current(material_id, range_to)

    def delete(self, session_id: str) -> None:
        self.sessions.soft_delete(session_id)

    # --- 取得 ---------------------------------------------------------------

    def get(self, session_id: str) -> Session | None:
        return self.sessions.get(session_id)

    def list(self, filters: SessionFilter | None = None) -> list[Session]:
        return self.sessions.list(filters)

    def seconds_for_day(self, day, exam_id: str | None = None) -> int:
        return self.sessions.total_seconds(
            SessionFilter(date_from=day, date_to=day, exam_id=exam_id)
        )

    def seconds_for_week(self, day, exam_id: str | None = None) -> int:
        start, end = clock.week_range(day, self.settings.week_starts_on)
        return self.sessions.total_seconds(
            SessionFilter(date_from=start, date_to=end, exam_id=exam_id)
        )

    def initial_classification(self) -> dict[str, str | None]:
        """新規記録の初期値（設定に覚えた値、無ければ直近の記録）。"""
        remembered = self.settings.last_used()
        if remembered["exam_id"]:
            return remembered
        return self.sessions.last_used()
