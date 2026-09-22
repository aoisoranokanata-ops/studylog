"""週目標と資格ごとの目標。

週目標は、設定しなかった週は前の週の値を引き継ぐ（指示書 4.8）。
資格ごとに総勉強時間の目標を持ち、試験日から逆算して「1日あたり必要な時間」を出す。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..core import clock
from ..domain.models import Exam, SessionFilter
from ..repositories.goals import WeeklyGoalRepository
from ..repositories.sessions import SessionRepository
from .master_service import MasterService
from .settings_service import SettingsService


@dataclass(slots=True)
class WeekGoal:
    week_start: date
    seconds: int
    inherited_from: date | None  # 前の週から引き継いだ場合、その週の開始日

    @property
    def is_set(self) -> bool:
        return self.seconds > 0


@dataclass(slots=True)
class WeekProgress:
    week_start: date
    week_end: date
    actual: int
    goal: WeekGoal

    @property
    def ratio(self) -> float:
        return 0.0 if not self.goal.seconds else self.actual / self.goal.seconds


@dataclass(slots=True)
class ExamPlan:
    exam: Exam
    exam_date: date | None
    days_left: int | None
    total_goal: int | None
    studied: int

    @property
    def remaining(self) -> int | None:
        return None if not self.total_goal else max(0, self.total_goal - self.studied)

    @property
    def per_day_needed(self) -> int | None:
        """試験日までに総目標へ届くために、1日あたり必要な秒数。"""
        if self.remaining is None or self.days_left is None or self.days_left <= 0:
            return None
        return -(-self.remaining // self.days_left)  # 切り上げ

    @property
    def ratio(self) -> float | None:
        return None if not self.total_goal else self.studied / self.total_goal


class GoalService:
    def __init__(
        self,
        goals: WeeklyGoalRepository,
        sessions: SessionRepository,
        masters: MasterService,
        settings: SettingsService,
    ) -> None:
        self.goals = goals
        self.sessions = sessions
        self.masters = masters
        self.settings = settings

    def today(self) -> date:
        return clock.study_date(clock.now_utc(), self.settings.day_change_hour)

    def week_start(self, day: date) -> date:
        return clock.week_start(day, self.settings.week_starts_on)

    # --- 週目標 -------------------------------------------------------------

    def week_goal(self, week_start: date, exam_id: str | None = None) -> WeekGoal:
        row = self.goals.effective(week_start, exam_id)
        if row is None:
            return WeekGoal(week_start, 0, None)
        source = date.fromisoformat(row["week_start"])
        return WeekGoal(week_start, int(row["goal_seconds"]), None if source == week_start else source)

    def set_week_goal(self, week_start: date, seconds: int, exam_id: str | None = None) -> None:
        self.goals.set(self.week_start(week_start), max(0, int(seconds)), exam_id)

    def week_progress(self, day: date | None = None, exam_id: str | None = None) -> WeekProgress:
        day = day or self.today()
        start, end = clock.week_range(day, self.settings.week_starts_on)
        actual = self.sessions.total_seconds(
            SessionFilter(date_from=start, date_to=end, exam_id=exam_id)
        )
        return WeekProgress(start, end, actual, self.week_goal(start, exam_id))

    def week_history(self, weeks: int = 8, today: date | None = None) -> list[WeekProgress]:
        """直近の週ごとの実績と目標（新しい週が先頭）。"""
        today = today or self.today()
        start = self.week_start(today)
        return [self.week_progress(start - timedelta(weeks=offset)) for offset in range(weeks)]

    # --- 資格ごと -----------------------------------------------------------

    def exam_plans(self, today: date | None = None) -> list[ExamPlan]:
        today = today or self.today()
        plans = []
        for exam in self.masters.list_exams():
            exam_date_text = self.masters.exam_date(exam.id)
            exam_date = date.fromisoformat(exam_date_text) if exam_date_text else None
            studied = self.sessions.total_seconds(SessionFilter(exam_id=exam.id))
            plans.append(
                ExamPlan(
                    exam=exam,
                    exam_date=exam_date,
                    days_left=(exam_date - today).days if exam_date else None,
                    total_goal=exam.goal_total_seconds,
                    studied=studied,
                )
            )
        # 試験日が近い順（日付の無いものは最後）
        plans.sort(key=lambda plan: (plan.days_left is None or plan.days_left < 0, plan.days_left or 0))
        return plans

    def set_exam_total_goal(self, exam_id: str, seconds: int | None) -> None:
        self.masters.update_exam(exam_id, {"goal_total_seconds": seconds or None})
