"""復習スケジュール。

正解なら間隔を延ばし（既定 1→3→7→14→30日）、不正解なら最初の間隔に戻す。
設定した回数だけ連続で正解したら「克服」とし、復習対象から外す。
子機から届いた復習結果もここを通して反映する。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from ..core import clock
from ..domain.models import Mistake
from ..repositories.mistakes import MistakeRepository, ReviewResultRepository
from .settings_service import SettingsService


class ReviewService:
    def __init__(
        self,
        mistakes: MistakeRepository,
        results: ReviewResultRepository,
        settings: SettingsService,
    ) -> None:
        self.mistakes = mistakes
        self.results = results
        self.settings = settings

    # --- スケジュール -------------------------------------------------------

    def _intervals(self) -> list[int]:
        return self.settings.review_intervals

    def _mastery_streak(self) -> int:
        return max(1, self.settings.get_int("mastery_streak"))

    def initial_schedule(self, on_day: date | None = None) -> dict:
        on_day = on_day or clock.study_date(clock.now_utc(), self.settings.day_change_hour)
        return {
            "review_stage": 0,
            "consecutive_ok": 0,
            "mastery": "unmastered",
            "next_review_on": (on_day + timedelta(days=self._intervals()[0])).isoformat(),
        }

    def next_schedule(self, mistake: Mistake, result: str, reviewed_on: date) -> dict:
        """1回の復習結果から、次の状態を決める。"""
        intervals = self._intervals()
        if result == "ok":
            stage = min(mistake.review_stage + 1, len(intervals) - 1)
            streak = mistake.consecutive_ok + 1
        else:
            stage = 0
            streak = 0

        if streak >= self._mastery_streak():
            return {
                "review_stage": stage,
                "consecutive_ok": streak,
                "mastery": "mastered",
                "next_review_on": None,
            }
        return {
            "review_stage": stage,
            "consecutive_ok": streak,
            "mastery": "reviewing" if streak else "unmastered",
            "next_review_on": (reviewed_on + timedelta(days=intervals[stage])).isoformat(),
        }

    # --- 反映 ---------------------------------------------------------------

    def apply_result(
        self, mistake_id: str, result: str, reviewed_at: datetime, *, source: str = "hub"
    ) -> bool:
        """復習結果を記録し、スケジュールを引き直す。誤答が無ければ何もしない。"""
        mistake = self.mistakes.get(mistake_id)
        if mistake is None:
            return False
        reviewed_on = clock.study_date(reviewed_at, self.settings.day_change_hour)
        self.mistakes.update(mistake_id, self.next_schedule(mistake, result, reviewed_on))
        return True

    def record_result(
        self,
        *,
        result_id: str,
        mistake_id: str,
        result: str,
        reviewed_at: datetime,
        source: str = "hub",
    ) -> bool:
        """復習結果を1件追記する（同じIDなら何もしない＝冪等）。"""
        if self.results.exists_id(result_id):
            return False
        self.results.insert(
            {
                "mistake_id": mistake_id,
                "result": result,
                "reviewed_at": clock.to_db(reviewed_at),
                "source": source,
            },
            record_id=result_id,
        )
        self.apply_result(mistake_id, result, reviewed_at, source=source)
        return True

    # --- 取得 ---------------------------------------------------------------

    def due(self, on_day: date | None = None, limit: int | None = None) -> list[Mistake]:
        on_day = on_day or clock.study_date(clock.now_utc(), self.settings.day_change_hour)
        return self.mistakes.list(due_on=on_day, limit=limit)
