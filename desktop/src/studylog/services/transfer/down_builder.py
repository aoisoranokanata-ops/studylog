"""下りパッケージ（母艦→子機）の組み立て（転送仕様書 第3章）。"""

from __future__ import annotations

from datetime import date

from ... import config
from ...core import clock, ids
from ...domain.models import Quota
from ...repositories.mistakes import MistakeRepository
from ...repositories.sessions import SessionRepository
from ...repositories.transfer import ImportedPackageRepository
from ..master_service import MasterService
from ..quota_service import QuotaService
from ..settings_service import SettingsService


def _range(unit: str | None, start: int | None, end: int | None) -> dict | None:
    if unit is None or start is None or end is None:
        return None
    return {"unit": unit, "from": int(start), "to": int(end)}


class DownBuilder:
    def __init__(
        self,
        *,
        settings: SettingsService,
        masters: MasterService,
        quotas: QuotaService,
        mistakes: MistakeRepository,
        sessions: SessionRepository,
        imported: ImportedPackageRepository,
    ) -> None:
        self.settings = settings
        self.masters = masters
        self.quotas = quotas
        self.mistakes = mistakes
        self.sessions = sessions
        self.imported = imported

    # --- 部品 ---------------------------------------------------------------

    def build_masters(self) -> dict:
        exams = []
        for exam in self.masters.list_exams(include_archived=True):
            exams.append(
                {
                    "id": exam.id,
                    "name": exam.name,
                    "color": exam.color,
                    "examDate": self.masters.exam_date(exam.id),
                    "archived": bool(exam.archived),
                }
            )
        materials = [
            {
                "id": material.id,
                "examId": material.exam_id,
                "name": material.name,
                "type": material.type,
                "unitLabel": material.unit_label,
                "total": material.total,
                "current": material.current,
                "archived": bool(material.archived),
            }
            for material in self.masters.list_materials(include_archived=True)
            if material.exam_id
        ]
        subjects = [
            {
                "id": subject.id,
                "examId": subject.exam_id,
                "parentId": subject.parent_id,
                "name": subject.name,
                "order": subject.sort_order,
                "archived": bool(subject.archived),
            }
            for subject in self.masters.list_subjects(include_archived=True)
            if subject.exam_id
        ]
        return {"exams": exams, "materials": materials, "subjects": subjects}

    def build_quota(self, quota: Quota) -> dict:
        labels = self.quotas.labels_for(quota)
        payload = {
            "id": quota.id,
            "date": quota.date.isoformat(),
            "order": quota.sort_order,
            "examId": quota.exam_id,
            "materialId": quota.material_id,
            "subjectId": quota.subject_id,
            "labels": {
                "exam": labels["exam"] or "未分類",
                "material": labels["material"],
                "subject": labels["subject"],
            },
            "title": quota.title or "ノルマ",
            "targetSeconds": quota.target_seconds,
        }
        range_value = _range(quota.range_unit, quota.range_from, quota.range_to)
        if range_value:
            payload["range"] = range_value
        if quota.note:
            payload["note"] = quota.note
        return payload

    def build_reviews(self, target_date: date) -> list[dict]:
        reviews = []
        for mistake in self.mistakes.list(due_on=target_date):
            labels = self.masters.labels_for(
                mistake.exam_id, mistake.material_id, mistake.subject_id
            )
            reviews.append(
                {
                    "mistakeId": mistake.id,
                    "examId": mistake.exam_id,
                    "materialId": mistake.material_id,
                    "subjectId": mistake.subject_id,
                    "labels": {
                        "exam": labels["exam"] or "未分類",
                        "material": labels["material"],
                        "subject": labels["subject"],
                    },
                    "questionRef": mistake.question_ref or "（問題の指定なし）",
                    "memo": mistake.memo,
                    "dueDate": (mistake.next_review_on or target_date).isoformat(),
                }
            )
        return reviews

    def build_summary(self, target_date: date) -> dict:
        week_start, week_end = clock.week_range(target_date, self.settings.week_starts_on)
        from ...domain.models import SessionFilter

        total = self.sessions.total_seconds(
            SessionFilter(date_from=week_start, date_to=week_end)
        )
        goal_row = self.sessions.conn.execute(
            "SELECT goal_seconds FROM weekly_goals "
            "WHERE week_start = ? AND exam_id IS NULL AND deleted_at IS NULL",
            (week_start.isoformat(),),
        ).fetchone()

        countdowns = []
        for exam in self.masters.list_exams():
            exam_date = self.masters.exam_date(exam.id)
            if not exam_date:
                continue
            countdowns.append(
                {
                    "examId": exam.id,
                    "name": exam.name,
                    "examDate": exam_date,
                    "daysLeft": (date.fromisoformat(exam_date) - target_date).days,
                }
            )
        return {
            "weekStart": week_start.isoformat(),
            "weekTotalSeconds": total,
            "weekGoalSeconds": int(goal_row["goal_seconds"]) if goal_row else 0,
            "countdowns": countdowns,
        }

    # --- 組み立て -----------------------------------------------------------

    def build(
        self,
        target_date: date,
        *,
        variant: str = "full",
        include_reviews: bool = True,
        date_to: date | None = None,
    ) -> dict:
        if variant not in ("full", "lite"):
            raise ValueError(f"variant が不正: {variant}")

        quotas = self.quotas.list(target_date, date_to)
        package = {
            "format": "studylog-transfer",
            "kind": "down",
            "schemaVersion": config.SCHEMA_VERSION,
            "packageId": ids.new_id(),
            "createdAt": clock.to_transfer(clock.now_utc()),
            "hubId": self.settings.hub_id,
            "targetDate": target_date.isoformat(),
            "variant": variant,
            "settings": {
                "dayChangeHour": self.settings.day_change_hour,
                "weekStartsOn": self.settings.week_starts_on,
            },
            "quotas": [self.build_quota(quota) for quota in quotas],
            "acks": self.imported.recent_ids(),
        }
        if variant == "full":
            package["masters"] = self.build_masters()
            package["summary"] = self.build_summary(target_date)
        if include_reviews:
            package["reviews"] = self.build_reviews(target_date)
        return package
