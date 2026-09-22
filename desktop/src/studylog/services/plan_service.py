"""予定（カレンダー）。繰り返しは1行で持ち、表示のたびに展開する。

繰り返しの書き方：
    None / "none"      繰り返さない
    "daily"            毎日
    "weekly:1,3,5"     指定の曜日（ISO-8601：1=月曜 … 7=日曜）

「この回だけ休む」は plan_exceptions に日付で残す（元の予定は消さない）。
"""

from __future__ import annotations

from datetime import date, timedelta

from ..db.connection import transaction
from ..domain.models import Plan, PlanOccurrence
from ..repositories.plans import PlanExceptionRepository, PlanRepository
from .master_service import MasterService
from .settings_service import SettingsService

WEEKDAY_NAMES = {1: "月", 2: "火", 3: "水", 4: "木", 5: "金", 6: "土", 7: "日"}


def parse_repeat(rule: str | None) -> tuple[str, set[int]]:
    """（種類, 曜日の集合）に分ける。曜日は ISO-8601（1=月曜）。"""
    if not rule or rule == "none":
        return "none", set()
    if rule == "daily":
        return "daily", set()
    if rule.startswith("weekly:"):
        days = {int(part) for part in rule.split(":", 1)[1].split(",") if part.strip().isdigit()}
        return "weekly", {day for day in days if 1 <= day <= 7}
    return "none", set()


def format_repeat(rule: str | None) -> str:
    kind, days = parse_repeat(rule)
    if kind == "daily":
        return "毎日"
    if kind == "weekly" and days:
        return "毎週 " + "・".join(WEEKDAY_NAMES[day] for day in sorted(days))
    return "繰り返さない"


class PlanService:
    def __init__(
        self,
        plans: PlanRepository,
        exceptions: PlanExceptionRepository,
        masters: MasterService,
        settings: SettingsService,
    ) -> None:
        self.plans = plans
        self.exceptions = exceptions
        self.masters = masters
        self.settings = settings
        self.conn = plans.conn

    # --- 作成・編集 ---------------------------------------------------------

    def create(
        self,
        *,
        day: date,
        title: str,
        planned_seconds: int,
        exam_id: str | None = None,
        material_id: str | None = None,
        subject_id: str | None = None,
        time_of_day: str | None = None,
        range_unit: str | None = None,
        range_from: int | None = None,
        range_to: int | None = None,
        note: str = "",
        repeat_rule: str | None = None,
        repeat_until: date | None = None,
    ) -> str:
        title = title.strip()
        if not title:
            raise ValueError("予定の内容を入力してください")
        if range_from is not None and range_to is not None and range_from > range_to:
            raise ValueError("範囲の開始が終了より後になっています")
        kind, days = parse_repeat(repeat_rule)
        if kind == "weekly" and not days:
            raise ValueError("繰り返す曜日を選んでください")
        if repeat_until and repeat_until < day:
            raise ValueError("繰り返しの終わりが開始日より前になっています")
        return self.plans.insert(
            {
                "date": day.isoformat(),
                "time_of_day": time_of_day,
                "exam_id": exam_id,
                "material_id": material_id,
                "subject_id": subject_id,
                "title": title,
                "planned_seconds": max(0, int(planned_seconds)),
                "range_unit": range_unit,
                "range_from": range_from,
                "range_to": range_to,
                "note": note,
                "repeat_rule": None if kind == "none" else repeat_rule,
                "repeat_from": day.isoformat() if kind != "none" else None,
                "repeat_until": repeat_until.isoformat() if repeat_until else None,
            }
        )

    def update(self, plan_id: str, values: dict) -> None:
        data = dict(values)
        for key in ("date", "repeat_from", "repeat_until"):
            if isinstance(data.get(key), date):
                data[key] = data[key].isoformat()
        if "title" in data and not str(data["title"]).strip():
            raise ValueError("予定の内容を入力してください")
        if "repeat_rule" in data:
            kind, days = parse_repeat(data["repeat_rule"])
            if kind == "weekly" and not days:
                raise ValueError("繰り返す曜日を選んでください")
            if kind == "none":
                data["repeat_rule"] = None
                data["repeat_from"] = None
                data["repeat_until"] = None
            else:
                data.setdefault("repeat_from", data.get("date"))
        self.plans.update(plan_id, data)

    def delete(self, plan_id: str) -> None:
        """予定を丸ごと消す（繰り返しなら全部）。"""
        self.plans.soft_delete(plan_id)

    def skip(self, plan_id: str, day: date) -> None:
        """繰り返しの「この回だけ休む」。"""
        self.exceptions.add(plan_id, day)

    def unskip(self, plan_id: str, day: date) -> None:
        self.exceptions.remove(plan_id, day)

    def end_repeat_on(self, plan_id: str, day: date) -> None:
        """「今後の繰り返しをやめる」。指定日の前日で終わりにする。"""
        plan = self.plans.get(plan_id)
        if plan is None or not plan.repeats:
            return
        if day <= plan.date:
            self.delete(plan_id)
            return
        self.plans.update(plan_id, {"repeat_until": (day - timedelta(days=1)).isoformat()})

    # --- 展開 ---------------------------------------------------------------

    def _matches(self, plan: Plan, day: date) -> bool:
        kind, days = parse_repeat(plan.repeat_rule)
        start = plan.repeat_from or plan.date
        if kind == "none":
            return plan.date == day
        if day < start:
            return False
        if plan.repeat_until and day > plan.repeat_until:
            return False
        if kind == "daily":
            return True
        return day.isoweekday() in days

    def occurrences(self, date_from: date, date_to: date) -> list[PlanOccurrence]:
        """期間内の予定を、繰り返しを展開して返す（日付→時刻の順）。"""
        if date_to < date_from:
            date_from, date_to = date_to, date_from
        candidates = self.plans.list_candidates(date_from, date_to)
        skipped = self.exceptions.dates_for([plan.id for plan in candidates])

        result: list[PlanOccurrence] = []
        day = date_from
        while day <= date_to:
            for plan in candidates:
                if self._matches(plan, day) and (plan.id, day.isoformat()) not in skipped:
                    result.append(PlanOccurrence(plan, day))
            day += timedelta(days=1)
        result.sort(key=lambda occurrence: (occurrence.date, occurrence.sort_key))
        return result

    def for_day(self, day: date) -> list[PlanOccurrence]:
        return self.occurrences(day, day)

    def by_day(self, date_from: date, date_to: date) -> dict[date, list[PlanOccurrence]]:
        grouped: dict[date, list[PlanOccurrence]] = {}
        for occurrence in self.occurrences(date_from, date_to):
            grouped.setdefault(occurrence.date, []).append(occurrence)
        return grouped

    # --- 表示用 -------------------------------------------------------------

    def labels_for(self, plan: Plan) -> dict[str, str | None]:
        return self.masters.labels_for(plan.exam_id, plan.material_id, plan.subject_id)

    def describe(self, plan: Plan) -> str:
        labels = self.labels_for(plan)
        parts = [labels["exam"], labels["material"], labels["subject"]]
        return "　".join(part for part in parts if part)
