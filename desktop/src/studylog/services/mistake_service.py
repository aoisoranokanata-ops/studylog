"""誤答の管理と、母艦での復習。

復習スケジュールそのものは services/review_service.py が持つ（子機から届いた結果と同じ道を通す）。
ここでは、登録・編集・克服の切り替えと、苦手の集計を扱う。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..core import clock
from ..domain.models import Mistake
from ..repositories.mistakes import MistakeRepository, ReviewResultRepository
from .master_service import MasterService
from .review_service import ReviewService
from .settings_service import SettingsService

MASTERY_VALUES = ("unmastered", "reviewing", "mastered")


@dataclass(slots=True)
class WeakRow:
    key: str | None
    label: str
    total: int
    unmastered: int

    @property
    def mastered(self) -> int:
        return self.total - self.unmastered


class MistakeService:
    def __init__(
        self,
        mistakes: MistakeRepository,
        results: ReviewResultRepository,
        reviews: ReviewService,
        masters: MasterService,
        settings: SettingsService,
    ) -> None:
        self.mistakes = mistakes
        self.results = results
        self.reviews = reviews
        self.masters = masters
        self.settings = settings

    def today(self) -> date:
        return clock.study_date(clock.now_utc(), self.settings.day_change_hour)

    # --- 一覧・登録 ---------------------------------------------------------

    def search(self, **filters) -> list[Mistake]:
        return self.mistakes.search(**filters)

    def get(self, mistake_id: str) -> Mistake | None:
        return self.mistakes.get(mistake_id)

    def create(
        self,
        *,
        question_ref: str,
        memo: str = "",
        answer_memo: str = "",
        reason: str | None = None,
        exam_id: str | None = None,
        material_id: str | None = None,
        subject_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        question_ref = question_ref.strip()
        if not question_ref:
            raise ValueError("問題の識別を入力してください")
        schedule = self.reviews.initial_schedule(self.today())
        return self.mistakes.insert(
            {
                "question_ref": question_ref,
                "memo": memo.strip(),
                "answer_memo": answer_memo.strip(),
                "reason": reason,
                "exam_id": exam_id,
                "material_id": material_id,
                "subject_id": subject_id,
                "session_id": session_id,
                "source": "hub",
                **schedule,
            }
        )

    def update(self, mistake_id: str, values: dict) -> None:
        data = dict(values)
        if "question_ref" in data and not str(data["question_ref"]).strip():
            raise ValueError("問題の識別を入力してください")
        if "next_review_on" in data and isinstance(data["next_review_on"], date):
            data["next_review_on"] = data["next_review_on"].isoformat()
        if "mastery" in data and data["mastery"] not in MASTERY_VALUES:
            raise ValueError(f"習熟の状態が不正: {data['mastery']}")
        self.mistakes.update(mistake_id, data)

    def delete(self, mistake_id: str) -> None:
        self.mistakes.soft_delete(mistake_id)

    # --- 復習 ---------------------------------------------------------------

    def due(self, on_day: date | None = None) -> list[Mistake]:
        return self.reviews.due(on_day or self.today())

    def answer(self, mistake_id: str, result: str) -> Mistake | None:
        """母艦で「できた／できなかった」を記録する（子機からの結果と同じ扱い）。"""
        if result not in ("ok", "ng"):
            raise ValueError(f"結果が不正: {result}")
        from ..core import ids

        self.reviews.record_result(
            result_id=ids.new_id(),
            mistake_id=mistake_id,
            result=result,
            reviewed_at=clock.now_utc(),
            source="hub",
        )
        return self.get(mistake_id)

    def set_mastery(self, mistake_id: str, mastery: str) -> None:
        """克服にする／復習に戻す。克服にしたら復習対象から外す。"""
        if mastery not in MASTERY_VALUES:
            raise ValueError(f"習熟の状態が不正: {mastery}")
        if mastery == "mastered":
            self.mistakes.update(mistake_id, {"mastery": "mastered", "next_review_on": None})
            return
        schedule = self.reviews.initial_schedule(self.today())
        schedule["mastery"] = mastery
        self.mistakes.update(mistake_id, schedule)

    def history(self, mistake_id: str) -> list:
        return self.results.for_mistake(mistake_id)

    # --- 苦手の集計 ---------------------------------------------------------

    def weak_ranking(self, by: str = "subject", exam_id: str | None = None) -> list[WeakRow]:
        column = "subject_id" if by == "subject" else "material_id"
        rows = self.mistakes.counts_by(column, exam_id=exam_id)
        result = []
        for key, total, unmastered in rows:
            if key is None:
                label = "（指定なし）"
            elif by == "subject":
                label = self.masters.subjects.tree_label(key) or "（削除済み）"
            else:
                material = self.masters.materials.get(key)
                label = material.name if material else "（削除済み）"
            result.append(WeakRow(key, label, total, unmastered))
        return result

    def reason_breakdown(self, exam_id: str | None = None) -> list[tuple[str | None, int]]:
        return self.mistakes.counts_by_reason(exam_id=exam_id)

    def counts(self, exam_id: str | None = None) -> dict[str, int]:
        rows = self.mistakes.search(exam_id=exam_id)
        return {
            "total": len(rows),
            "unmastered": sum(1 for row in rows if row.mastery != "mastered"),
            "mastered": sum(1 for row in rows if row.mastery == "mastered"),
            "due": len(self.due()),
        }
