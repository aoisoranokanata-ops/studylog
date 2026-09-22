"""受験の結果（合否）と、合格したときに見せる振り返り。

合格を登録すると、その資格の総勉強時間・学習期間・いちばん時間をかけた分野などをまとめて返す。
合格した資格は実績として残す（アーカイブしても消えない）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..domain.models import Exam, SessionFilter
from ..repositories.masters import ExamSittingRepository
from ..repositories.mistakes import MistakeRepository
from ..repositories.sessions import SessionRepository
from .master_service import MasterService
from .stats_service import StatsService

STATUS_BY_RESULT = {True: "passed", False: "failed"}


@dataclass(slots=True)
class ExamSummary:
    """振り返りの数字。"""

    exam: Exam
    total_seconds: int
    sessions: int
    study_days: int
    first_day: date | None
    last_day: date | None
    top_subject: tuple[str, int] | None
    top_material: tuple[str, int] | None
    mistakes_total: int
    mistakes_mastered: int
    goal_seconds: int | None

    @property
    def span_days(self) -> int:
        if not self.first_day or not self.last_day:
            return 0
        return (self.last_day - self.first_day).days + 1

    @property
    def goal_ratio(self) -> float | None:
        return None if not self.goal_seconds else self.total_seconds / self.goal_seconds

    @property
    def average_per_study_day(self) -> int:
        return self.total_seconds // self.study_days if self.study_days else 0


@dataclass(slots=True)
class SittingResult:
    id: str
    exam_id: str
    label: str
    exam_date: date | None
    score: int | None
    passed: bool | None
    memo: str
    certificate_on: date | None


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


class ResultService:
    def __init__(
        self,
        sittings: ExamSittingRepository,
        masters: MasterService,
        sessions: SessionRepository,
        mistakes: MistakeRepository,
        stats: StatsService,
    ) -> None:
        self.sittings = sittings
        self.masters = masters
        self.sessions = sessions
        self.mistakes = mistakes
        self.stats = stats

    # --- 受験回 -------------------------------------------------------------

    def sittings_for(self, exam_id: str) -> list[SittingResult]:
        return [
            SittingResult(
                id=row["id"],
                exam_id=row["exam_id"],
                label=row["label"],
                exam_date=_date(row["exam_date"]),
                score=row["result_score"],
                passed=None if row["result_passed"] is None else bool(row["result_passed"]),
                memo=row["result_memo"],
                certificate_on=_date(row["certificate_received_on"]),
            )
            for row in self.sittings.list(exam_id)
        ]

    def add_sitting(self, exam_id: str, exam_date: date | None, label: str = "") -> str:
        return self.sittings.insert(
            {
                "exam_id": exam_id,
                "exam_date": exam_date.isoformat() if exam_date else None,
                "label": label,
                "is_primary": 0 if self.sittings.primary(exam_id) else 1,
            }
        )

    def update_sitting(self, sitting_id: str, *, exam_date: date | None, label: str = "") -> None:
        self.sittings.update(
            sitting_id,
            {"exam_date": exam_date.isoformat() if exam_date else None, "label": label.strip()},
        )

    def delete_sitting(self, sitting_id: str) -> None:
        self.sittings.soft_delete(sitting_id)

    def set_primary(self, sitting_id: str) -> None:
        """カウントダウンに使う回を入れ替える。"""
        row = self.sittings.row(sitting_id)
        if row is None:
            raise ValueError("受験回が見つかりません")
        for other in self.sittings.list(row["exam_id"]):
            want = 1 if other["id"] == sitting_id else 0
            if other["is_primary"] != want:
                self.sittings.update(other["id"], {"is_primary": want})

    def record_result(
        self,
        sitting_id: str,
        *,
        score: int | None,
        passed: bool | None,
        memo: str = "",
        certificate_on: date | None = None,
    ) -> ExamSummary | None:
        """結果を記録し、資格のステータスも合わせる。合格なら振り返りを返す。"""
        row = self.sittings.row(sitting_id)
        if row is None:
            raise ValueError("受験回が見つかりません")
        self.sittings.record_result(
            sitting_id,
            score=score,
            passed=passed,
            memo=memo.strip(),
            certificate_on=certificate_on.isoformat() if certificate_on else None,
        )
        exam_id = row["exam_id"]
        if passed is not None:
            self.masters.update_exam(exam_id, {"status": STATUS_BY_RESULT[passed]})
        return self.summary(exam_id) if passed else None

    # --- 振り返り -----------------------------------------------------------

    def summary(self, exam_id: str) -> ExamSummary | None:
        exam = self.masters.exams.get(exam_id)
        if exam is None:
            return None
        filters = SessionFilter(exam_id=exam_id)
        sessions = self.sessions.list(filters)
        days = sorted({session.study_date for session in sessions})

        def top(by: str) -> tuple[str, int] | None:
            rows = [row for row in self.stats.breakdown(by, date(1970, 1, 1), date(2999, 12, 31), exam_id)]
            return (rows[0].label, rows[0].seconds) if rows else None

        mistakes = self.mistakes.search(exam_id=exam_id)
        return ExamSummary(
            exam=exam,
            total_seconds=self.sessions.total_seconds(filters),
            sessions=len(sessions),
            study_days=len(days),
            first_day=days[0] if days else None,
            last_day=days[-1] if days else None,
            top_subject=top("subject"),
            top_material=top("material"),
            mistakes_total=len(mistakes),
            mistakes_mastered=sum(1 for mistake in mistakes if mistake.mastery == "mastered"),
            goal_seconds=exam.goal_total_seconds,
        )

    def achievements(self) -> list[tuple[Exam, SittingResult]]:
        """合格した資格の一覧（新しい試験日が先頭）。アーカイブしたものも残す。"""
        rows: list[tuple[Exam, SittingResult]] = []
        for exam in self.masters.list_exams(include_archived=True):
            for sitting in self.sittings_for(exam.id):
                if sitting.passed:
                    rows.append((exam, sitting))
        rows.sort(key=lambda item: item[1].exam_date or date.min, reverse=True)
        return rows
