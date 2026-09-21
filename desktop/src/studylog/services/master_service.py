"""資格・参考書・分野の操作。

DBにCHECK制約を置かない代わりに、整合はここで保証する。
とくに「資格を削除したら、その資格を参照していた記録は未分類に落とす」を必ず同じ
トランザクションで行う（ON DELETE SET NULL と CHECK がぶつかる事故を避けた設計）。
"""

from __future__ import annotations

from ..core import clock
from ..db.connection import transaction
from ..domain.models import Exam, Material, Subject
from ..repositories.masters import (
    ExamRepository,
    ExamSittingRepository,
    MaterialRepository,
    SubjectRepository,
)


class MasterService:
    def __init__(
        self,
        exams: ExamRepository,
        materials: MaterialRepository,
        subjects: SubjectRepository,
        sittings: ExamSittingRepository | None = None,
    ) -> None:
        self.exams = exams
        self.materials = materials
        self.subjects = subjects
        self.sittings = sittings or ExamSittingRepository(exams.conn)
        self.conn = exams.conn

    # --- 試験日 -------------------------------------------------------------

    def exam_date(self, exam_id: str) -> str | None:
        return self.sittings.exam_date(exam_id)

    def set_exam_date(self, exam_id: str, exam_date: str | None) -> None:
        self.sittings.set_primary_date(exam_id, exam_date or None)

    # --- 資格 ---------------------------------------------------------------

    def list_exams(self, *, include_archived: bool = False) -> list[Exam]:
        return self.exams.list(include_archived=include_archived)

    def create_exam(self, name: str, color: str = "#4a6fa5", **extra) -> str:
        name = name.strip()
        if not name:
            raise ValueError("資格の名称を入力してください")
        return self.exams.insert(
            {"name": name, "color": color, "sort_order": self.exams.next_sort_order(), **extra}
        )

    def update_exam(self, exam_id: str, values: dict) -> None:
        if "name" in values and not str(values["name"]).strip():
            raise ValueError("資格の名称を入力してください")
        self.exams.update(exam_id, values)

    def delete_exam(self, exam_id: str) -> dict[str, int]:
        """資格を削除し、ぶら下がっていたものの後始末をする。"""
        now = clock.db_now()
        with transaction(self.conn):
            affected = self.conn.execute(
                "UPDATE sessions SET exam_id = NULL, material_id = NULL, subject_id = NULL, "
                "unclassified = 1, updated_at = ? WHERE exam_id = ? AND deleted_at IS NULL",
                (now, exam_id),
            ).rowcount
            self.conn.execute(
                "UPDATE mistakes SET exam_id = NULL, material_id = NULL, subject_id = NULL, "
                "updated_at = ? WHERE exam_id = ? AND deleted_at IS NULL",
                (now, exam_id),
            )
            for table in ("materials", "subjects"):
                self.conn.execute(
                    f"UPDATE {table} SET deleted_at = ?, updated_at = ? "
                    f"WHERE exam_id = ? AND deleted_at IS NULL",
                    (now, now, exam_id),
                )
            self.exams.soft_delete(exam_id)
        return {"sessions_unclassified": max(0, affected)}

    # --- 参考書 -------------------------------------------------------------

    def list_materials(self, exam_id: str | None = None, *, include_archived: bool = False) -> list[Material]:
        return self.materials.list(exam_id=exam_id, include_archived=include_archived)

    def create_material(self, exam_id: str, name: str, **extra) -> str:
        name = name.strip()
        if not name:
            raise ValueError("参考書の名称を入力してください")
        if not exam_id:
            raise ValueError("参考書には資格を選んでください")
        return self.materials.insert({"exam_id": exam_id, "name": name, **extra})

    def update_material(self, material_id: str, values: dict) -> None:
        self.materials.update(material_id, values)

    def delete_material(self, material_id: str) -> None:
        now = clock.db_now()
        with transaction(self.conn):
            for table in ("sessions", "mistakes"):
                self.conn.execute(
                    f"UPDATE {table} SET material_id = NULL, updated_at = ? WHERE material_id = ?",
                    (now, material_id),
                )
            self.materials.soft_delete(material_id)

    # --- 分野 ---------------------------------------------------------------

    def list_subjects(self, exam_id: str | None = None, *, include_archived: bool = False) -> list[Subject]:
        return self.subjects.list(exam_id=exam_id, include_archived=include_archived)

    def create_subject(self, exam_id: str, name: str, parent_id: str | None = None, **extra) -> str:
        name = name.strip()
        if not name:
            raise ValueError("分野の名称を入力してください")
        if not exam_id:
            raise ValueError("分野には資格を選んでください")
        if parent_id:
            parent = self.subjects.get(parent_id)
            if parent is None:
                raise ValueError("親の分野が見つかりません")
            if parent.parent_id:
                raise ValueError("分野は2階層までです")
        return self.subjects.insert(
            {"exam_id": exam_id, "name": name, "parent_id": parent_id, **extra}
        )

    def update_subject(self, subject_id: str, values: dict) -> None:
        if values.get("parent_id"):
            if values["parent_id"] == subject_id:
                raise ValueError("自分自身を親にはできません")
            parent = self.subjects.get(values["parent_id"])
            if parent is None:
                raise ValueError("親の分野が見つかりません")
            if parent.parent_id:
                raise ValueError("分野は2階層までです")
            if self.subjects.children(subject_id):
                raise ValueError("子の分野があるため、これ以上深くできません")
        self.subjects.update(subject_id, values)

    def delete_subject(self, subject_id: str) -> None:
        now = clock.db_now()
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE subjects SET parent_id = NULL, updated_at = ? WHERE parent_id = ?",
                (now, subject_id),
            )
            for table in ("sessions", "mistakes"):
                self.conn.execute(
                    f"UPDATE {table} SET subject_id = NULL, updated_at = ? WHERE subject_id = ?",
                    (now, subject_id),
                )
            self.subjects.soft_delete(subject_id)

    # --- 表示名 -------------------------------------------------------------

    def labels_for(
        self, exam_id: str | None, material_id: str | None, subject_id: str | None
    ) -> dict[str, str | None]:
        exam = self.exams.get(exam_id) if exam_id else None
        material = self.materials.get(material_id) if material_id else None
        return {
            "exam": exam.name if exam else None,
            "material": material.name if material else None,
            "subject": self.subjects.tree_label(subject_id) if subject_id else None,
        }
