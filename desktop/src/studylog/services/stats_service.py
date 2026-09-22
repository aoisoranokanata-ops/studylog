"""集計。数えるのはSQL（repositories）に任せ、ここでは期間の区切りや並べ替えだけを行う。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..core import clock
from ..domain.models import SessionFilter
from ..repositories.quotas import QuotaRepository
from ..repositories.sessions import SessionRepository
from .master_service import MasterService
from .settings_service import SettingsService

UNITS = ("day", "week", "month")
BREAKDOWNS = {"exam": "exam_id", "material": "material_id", "subject": "subject_id"}


@dataclass(slots=True)
class PeriodTotal:
    start: date
    end: date
    label: str
    seconds: int


@dataclass(slots=True)
class BreakdownRow:
    key: str | None
    label: str
    seconds: int
    share: float


@dataclass(slots=True)
class AccuracyRow:
    key: str | None
    label: str
    correct: int
    attempted: int

    @property
    def rate(self) -> float:
        return self.correct / self.attempted if self.attempted else 0.0


@dataclass(slots=True)
class MaterialProgress:
    id: str
    name: str
    exam: str
    current: int
    total: int
    unit: str

    @property
    def rate(self) -> float:
        return 0.0 if self.total <= 0 else min(1.0, self.current / self.total)


@dataclass(slots=True)
class Streak:
    current: int
    longest: int


@dataclass(slots=True)
class QuotaAchievement:
    total: int = 0
    done: int = 0
    partial: int = 0
    skipped: int = 0
    none: int = 0

    @property
    def rate(self) -> float:
        """完了の割合（一部は半分として数える）。"""
        return 0.0 if not self.total else (self.done + self.partial * 0.5) / self.total


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _next_month(day: date) -> date:
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


class StatsService:
    def __init__(
        self,
        sessions: SessionRepository,
        masters: MasterService,
        quotas: QuotaRepository,
        settings: SettingsService,
    ) -> None:
        self.sessions = sessions
        self.masters = masters
        self.quotas = quotas
        self.settings = settings

    def today(self) -> date:
        return clock.study_date(clock.now_utc(), self.settings.day_change_hour)

    # --- 期間 ---------------------------------------------------------------

    def default_range(self, unit: str, today: date | None = None) -> tuple[date, date]:
        """単位ごとの標準の表示期間（日=30日、週=12週、月=12か月）。"""
        today = today or self.today()
        if unit == "day":
            return today - timedelta(days=29), today
        if unit == "week":
            start = clock.week_start(today, self.settings.week_starts_on) - timedelta(weeks=11)
            return start, today
        if unit == "month":
            start = _month_start(today)
            for _ in range(11):
                start = _month_start(start - timedelta(days=1))
            return start, today
        raise ValueError(f"単位が不正: {unit}")

    def period_totals(
        self, unit: str, date_from: date, date_to: date, exam_id: str | None = None
    ) -> list[PeriodTotal]:
        """日・週・月ごとの合計。勉強しなかった期間も0として並べる（グラフが歯抜けにならない）。"""
        if unit not in UNITS:
            raise ValueError(f"単位が不正: {unit}")
        daily = {row.day: row.seconds for row in self.sessions.daily_totals(date_from, date_to, exam_id)}

        buckets: list[PeriodTotal] = []
        if unit == "day":
            day = date_from
            while day <= date_to:
                buckets.append(PeriodTotal(day, day, f"{day.month}/{day.day}", daily.get(day, 0)))
                day += timedelta(days=1)
            return buckets

        if unit == "week":
            start = clock.week_start(date_from, self.settings.week_starts_on)
            step = lambda d: d + timedelta(days=7)  # noqa: E731
            label = lambda d: f"{d.month}/{d.day}〜"  # noqa: E731
        else:
            start = _month_start(date_from)
            step = _next_month
            label = lambda d: f"{d.year}/{d.month:02d}"  # noqa: E731

        while start <= date_to:
            end = step(start) - timedelta(days=1)
            seconds = sum(value for day, value in daily.items() if start <= day <= end)
            buckets.append(PeriodTotal(start, end, label(start), seconds))
            start = step(start)
        return buckets

    # --- 内訳 ---------------------------------------------------------------

    def _label(self, by: str, key: str | None) -> str:
        if key is None:
            return "未分類" if by == "exam" else "（指定なし）"
        if by == "exam":
            exam = self.masters.exams.row(key)
            return exam["name"] if exam else "（削除済み）"
        if by == "material":
            material = self.masters.materials.row(key)
            return material["name"] if material else "（削除済み）"
        return self.masters.subjects.tree_label(key) or "（削除済み）"

    def breakdown(
        self, by: str, date_from: date, date_to: date, exam_id: str | None = None
    ) -> list[BreakdownRow]:
        column = BREAKDOWNS[by]
        rows = self.sessions.totals_by(
            column, SessionFilter(date_from=date_from, date_to=date_to, exam_id=exam_id)
        )
        total = sum(seconds for _, seconds in rows) or 1
        return [
            BreakdownRow(key, self._label(by, key), seconds, seconds / total)
            for key, seconds in rows
            if seconds > 0
        ]

    def accuracy_by_subject(
        self, date_from: date, date_to: date, exam_id: str | None = None
    ) -> list[AccuracyRow]:
        rows = self.sessions.accuracy_by_subject(
            SessionFilter(date_from=date_from, date_to=date_to, exam_id=exam_id)
        )
        return [AccuracyRow(key, self._label("subject", key), c, a) for key, c, a in rows]

    def material_progress(self, exam_id: str | None = None) -> list[MaterialProgress]:
        result = []
        for material in self.masters.list_materials(exam_id):
            if material.total <= 0:
                continue
            exam = self.masters.exams.get(material.exam_id) if material.exam_id else None
            result.append(
                MaterialProgress(
                    material.id, material.name, exam.name if exam else "",
                    material.current, material.total, material.unit_label,
                )
            )
        result.sort(key=lambda item: item.rate, reverse=True)
        return result

    # --- 日数 ---------------------------------------------------------------

    def study_day_count(self, date_from: date, date_to: date) -> int:
        return len(self.sessions.study_days(date_from, date_to))

    def streak(self, today: date | None = None) -> Streak:
        """連続学習日数。今日まだ勉強していなくても、昨日まで続いていれば途切れていない扱い。"""
        today = today or self.today()
        days = self.sessions.all_study_dates(today)
        if not days:
            return Streak(0, 0)

        longest = run = 1
        for previous, current in zip(days, days[1:]):
            run = run + 1 if (current - previous).days == 1 else 1
            longest = max(longest, run)

        current = 0
        latest = days[-1]
        if (today - latest).days <= 1:
            current = 1
            for previous, day in zip(reversed(days[:-1]), reversed(days[1:])):
                if (day - previous).days != 1:
                    break
                current += 1
        return Streak(current, longest)

    # --- ノルマ -------------------------------------------------------------

    def quota_achievement(self, date_from: date, date_to: date) -> QuotaAchievement:
        result = QuotaAchievement()
        for quota in self.quotas.list(date_from, date_to):
            result.total += 1
            status = quota.status if quota.status in ("done", "partial", "skipped") else "none"
            setattr(result, status, getattr(result, status) + 1)
        return result

    def total_seconds(self, date_from: date, date_to: date, exam_id: str | None = None) -> int:
        return self.sessions.total_seconds(
            SessionFilter(date_from=date_from, date_to=date_to, exam_id=exam_id)
        )
