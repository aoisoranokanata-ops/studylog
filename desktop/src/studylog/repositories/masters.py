"""資格・参考書・分野のリポジトリ。"""

from __future__ import annotations

from ..core import clock
from ..domain.models import Exam, Material, Subject
from .base import BaseRepository


class ExamRepository(BaseRepository):
    table = "exams"

    def list(self, *, include_archived: bool = False) -> list[Exam]:
        sql = "SELECT * FROM exams WHERE deleted_at IS NULL"
        if not include_archived:
            sql += " AND archived = 0"
        sql += " ORDER BY sort_order, name"
        return [Exam.from_row(row) for row in self.query(sql)]

    def get(self, exam_id: str) -> Exam | None:
        row = self.row(exam_id)
        return Exam.from_row(row) if row and row["deleted_at"] is None else None

    def next_sort_order(self) -> int:
        row = self.conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM exams").fetchone()
        return int(row["n"])


class ExamSittingRepository(BaseRepository):
    """年度ごとの試験日と結果。カウントダウンには is_primary の回を使う。"""

    table = "exam_sittings"

    def list(self, exam_id: str) -> list:
        return self.query(
            "SELECT * FROM exam_sittings WHERE exam_id = ? AND deleted_at IS NULL "
            "ORDER BY is_primary DESC, exam_date",
            (exam_id,),
        )

    def primary(self, exam_id: str):
        rows = self.list(exam_id)
        for row in rows:
            if row["is_primary"] and row["exam_date"]:
                return row
        for row in rows:
            if row["exam_date"]:
                return row
        return None

    def exam_date(self, exam_id: str) -> str | None:
        row = self.primary(exam_id)
        return row["exam_date"] if row else None

    def set_primary_date(self, exam_id: str, exam_date: str | None, label: str = "") -> None:
        """主たる試験日を入れ替える（無ければ作る、None なら消す）。"""
        row = self.primary(exam_id)
        if exam_date is None:
            if row is not None:
                self.soft_delete(row["id"])
            return
        if row is None:
            self.insert(
                {"exam_id": exam_id, "exam_date": exam_date, "label": label, "is_primary": 1}
            )
        else:
            self.update(row["id"], {"exam_date": exam_date, "is_primary": 1, "label": label or row["label"]})


class MaterialRepository(BaseRepository):
    table = "materials"

    def list(self, *, exam_id: str | None = None, include_archived: bool = False) -> list[Material]:
        sql = "SELECT * FROM materials WHERE deleted_at IS NULL"
        params: list[str] = []
        if exam_id:
            sql += " AND exam_id = ?"
            params.append(exam_id)
        if not include_archived:
            sql += " AND archived = 0"
        sql += " ORDER BY sort_order, name"
        return [Material.from_row(row) for row in self.query(sql, params)]

    def get(self, material_id: str) -> Material | None:
        row = self.row(material_id)
        return Material.from_row(row) if row and row["deleted_at"] is None else None

    def advance_current(self, material_id: str, position: int) -> None:
        """参考書の現在位置を進める（戻すことはしない）。"""
        self.conn.execute(
            "UPDATE materials SET current = MAX(current, ?), updated_at = ? WHERE id = ?",
            (int(position), clock.db_now(), material_id),
        )


class SubjectRepository(BaseRepository):
    table = "subjects"

    def list(self, *, exam_id: str | None = None, include_archived: bool = False) -> list[Subject]:
        sql = "SELECT * FROM subjects WHERE deleted_at IS NULL"
        params: list[str] = []
        if exam_id:
            sql += " AND exam_id = ?"
            params.append(exam_id)
        if not include_archived:
            sql += " AND archived = 0"
        sql += " ORDER BY sort_order, name"
        return [Subject.from_row(row) for row in self.query(sql, params)]

    def get(self, subject_id: str) -> Subject | None:
        row = self.row(subject_id)
        return Subject.from_row(row) if row and row["deleted_at"] is None else None

    def children(self, parent_id: str) -> list[Subject]:
        return [
            Subject.from_row(row)
            for row in self.query(
                "SELECT * FROM subjects WHERE parent_id = ? AND deleted_at IS NULL "
                "ORDER BY sort_order, name",
                (parent_id,),
            )
        ]

    def tree_label(self, subject_id: str) -> str:
        """「民法 / 総則」のような表示名を作る。"""
        subject = self.get(subject_id)
        if subject is None:
            return ""
        if subject.parent_id:
            parent = self.get(subject.parent_id)
            if parent is not None:
                return f"{parent.name} / {subject.name}"
        return subject.name
