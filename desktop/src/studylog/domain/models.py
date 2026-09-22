"""DBにもUIにも依存しない値オブジェクト。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime

from ..core import clock


def _dt(value: str | None) -> datetime | None:
    return clock.from_db(value) if value else None


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@dataclass(slots=True)
class Exam:
    id: str
    name: str
    color: str = "#4a6fa5"
    status: str = "studying"
    goal_note: str = ""
    goal_total_seconds: int | None = None
    sort_order: int = 0
    archived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Exam":
        return cls(
            id=row["id"],
            name=row["name"],
            color=row["color"],
            status=row["status"],
            goal_note=row["goal_note"],
            goal_total_seconds=row["goal_total_seconds"],
            sort_order=row["sort_order"],
            archived=bool(row["archived"]),
            created_at=_dt(row["created_at"]),
            updated_at=_dt(row["updated_at"]),
        )


@dataclass(slots=True)
class Material:
    id: str
    exam_id: str | None
    name: str
    type: str = "text"
    unit_label: str = "ページ"
    total: int = 0
    current: int = 0
    sort_order: int = 0
    archived: bool = False

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Material":
        return cls(
            id=row["id"],
            exam_id=row["exam_id"],
            name=row["name"],
            type=row["type"],
            unit_label=row["unit_label"],
            total=row["total"],
            current=row["current"],
            sort_order=row["sort_order"],
            archived=bool(row["archived"]),
        )

    @property
    def progress(self) -> float:
        return 0.0 if self.total <= 0 else min(1.0, self.current / self.total)


@dataclass(slots=True)
class Subject:
    id: str
    exam_id: str | None
    parent_id: str | None
    name: str
    sort_order: int = 0
    archived: bool = False

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Subject":
        return cls(
            id=row["id"],
            exam_id=row["exam_id"],
            parent_id=row["parent_id"],
            name=row["name"],
            sort_order=row["sort_order"],
            archived=bool(row["archived"]),
        )


@dataclass(slots=True)
class Session:
    id: str
    exam_id: str | None
    material_id: str | None
    subject_id: str | None
    quota_id: str | None
    unclassified: bool
    started_at: datetime
    ended_at: datetime
    active_seconds: int
    study_date: date
    range_unit: str | None = None
    range_from: int | None = None
    range_to: int | None = None
    correct: int | None = None
    attempted: int | None = None
    focus: int | None = None
    memo: str = ""
    entry_mode: str = "timer"
    source: str = "hub"
    device_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Session":
        return cls(
            id=row["id"],
            exam_id=row["exam_id"],
            material_id=row["material_id"],
            subject_id=row["subject_id"],
            quota_id=row["quota_id"],
            unclassified=bool(row["unclassified"]),
            started_at=clock.from_db(row["started_at"]),
            ended_at=clock.from_db(row["ended_at"]),
            active_seconds=row["active_seconds"],
            study_date=date.fromisoformat(row["study_date"]),
            range_unit=row["range_unit"],
            range_from=row["range_from"],
            range_to=row["range_to"],
            correct=row["correct"],
            attempted=row["attempted"],
            focus=row["focus"],
            memo=row["memo"],
            entry_mode=row["entry_mode"],
            source=row["source"],
            device_id=row["device_id"],
            created_at=_dt(row["created_at"]),
            updated_at=_dt(row["updated_at"]),
        )


@dataclass(slots=True)
class TimerState:
    """計測中の状態。経過時間は必ず時刻の差から計算する。"""

    exam_id: str | None
    material_id: str | None
    subject_id: str | None
    quota_id: str | None
    started_at: datetime
    accumulated_seconds: int
    resumed_at: datetime | None
    is_running: bool
    memo: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TimerState":
        return cls(
            exam_id=row["exam_id"],
            material_id=row["material_id"],
            subject_id=row["subject_id"],
            quota_id=row["quota_id"],
            started_at=clock.from_db(row["started_at"]),
            accumulated_seconds=row["accumulated_seconds"],
            resumed_at=_dt(row["resumed_at"]),
            is_running=bool(row["is_running"]),
            memo=row["memo"],
        )

    def elapsed_seconds(self, now: datetime | None = None) -> int:
        """開始・再開の時刻から計算した経過秒。アプリが止まっていた間も正しく数える。"""
        total = self.accumulated_seconds
        if self.is_running and self.resumed_at is not None:
            now = now or clock.now_utc()
            total += max(0, int((now - self.resumed_at).total_seconds()))
        return total


@dataclass(slots=True)
class Quota:
    """子機に渡すノルマ。"""

    id: str
    date: date
    sort_order: int
    exam_id: str | None
    material_id: str | None
    subject_id: str | None
    title: str
    target_seconds: int
    plan_id: str | None = None
    range_unit: str | None = None
    range_from: int | None = None
    range_to: int | None = None
    note: str = ""
    status: str = "none"
    status_id: str | None = None
    status_updated_at: datetime | None = None
    sent_at: datetime | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Quota":
        return cls(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            sort_order=row["sort_order"],
            exam_id=row["exam_id"],
            material_id=row["material_id"],
            subject_id=row["subject_id"],
            title=row["title"],
            target_seconds=row["target_seconds"],
            plan_id=row["plan_id"],
            range_unit=row["range_unit"],
            range_from=row["range_from"],
            range_to=row["range_to"],
            note=row["note"],
            status=row["status"],
            status_id=row["status_id"],
            status_updated_at=_dt(row["status_updated_at"]),
            sent_at=_dt(row["sent_at"]),
        )


@dataclass(slots=True)
class Plan:
    """勉強の予定。繰り返しは1行で持ち、表示のたびに展開する。"""

    id: str
    date: date
    exam_id: str | None
    material_id: str | None
    subject_id: str | None
    title: str
    planned_seconds: int
    time_of_day: str | None = None      # HH:MM（未設定なら時刻なしの予定）
    range_unit: str | None = None
    range_from: int | None = None
    range_to: int | None = None
    note: str = ""
    repeat_rule: str | None = None      # None/none、daily、weekly:1,3,5（1=月曜）
    repeat_from: date | None = None
    repeat_until: date | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Plan":
        return cls(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            exam_id=row["exam_id"],
            material_id=row["material_id"],
            subject_id=row["subject_id"],
            title=row["title"],
            planned_seconds=row["planned_seconds"],
            time_of_day=row["time_of_day"],
            range_unit=row["range_unit"],
            range_from=row["range_from"],
            range_to=row["range_to"],
            note=row["note"],
            repeat_rule=row["repeat_rule"],
            repeat_from=_date(row["repeat_from"]),
            repeat_until=_date(row["repeat_until"]),
        )

    @property
    def repeats(self) -> bool:
        return bool(self.repeat_rule) and self.repeat_rule != "none"


@dataclass(slots=True)
class PlanOccurrence:
    """繰り返しを展開した「その日の予定」。"""

    plan: Plan
    date: date

    @property
    def is_repeat(self) -> bool:
        return self.plan.repeats

    @property
    def sort_key(self) -> tuple:
        return (self.plan.time_of_day or "99:99", self.plan.title)


@dataclass(slots=True)
class Mistake:
    """誤答。"""

    id: str
    session_id: str | None
    exam_id: str | None
    material_id: str | None
    subject_id: str | None
    question_ref: str
    memo: str = ""
    answer_memo: str = ""
    reason: str | None = None
    review_stage: int = 0
    next_review_on: date | None = None
    consecutive_ok: int = 0
    mastery: str = "unmastered"
    source: str = "hub"
    device_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Mistake":
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            exam_id=row["exam_id"],
            material_id=row["material_id"],
            subject_id=row["subject_id"],
            question_ref=row["question_ref"],
            memo=row["memo"],
            answer_memo=row["answer_memo"],
            reason=row["reason"],
            review_stage=row["review_stage"],
            next_review_on=_date(row["next_review_on"]),
            consecutive_ok=row["consecutive_ok"],
            mastery=row["mastery"],
            source=row["source"],
            device_id=row["device_id"],
            created_at=_dt(row["created_at"]),
            updated_at=_dt(row["updated_at"]),
        )


@dataclass(slots=True)
class ImportResult:
    """上りパッケージを取り込んだ結果。"""

    package_id: str
    device_id: str | None = None
    device_name: str = ""
    added: int = 0
    updated: int = 0
    skipped: int = 0
    unclassified: int = 0
    already_imported: bool = False

    @property
    def total(self) -> int:
        return self.added + self.updated + self.skipped

    def summary(self) -> str:
        head = "取り込み済みのファイルでした" if self.already_imported else "取り込みました"
        return (
            f"{head}：追加 {self.added}件／更新 {self.updated}件／"
            f"変更なし {self.skipped}件／未分類 {self.unclassified}件"
        )


@dataclass(slots=True)
class DailyTotal:
    day: date
    seconds: int


@dataclass(slots=True)
class SessionFilter:
    date_from: date | None = None
    date_to: date | None = None
    exam_id: str | None = None
    material_id: str | None = None
    subject_id: str | None = None
    unclassified_only: bool = False
    keyword: str = ""
    limit: int | None = None
    extra: dict = field(default_factory=dict)
