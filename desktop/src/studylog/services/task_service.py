"""課題（やることリスト）。期限と優先度を持ち、ダッシュボードにも出す。"""

from __future__ import annotations

from datetime import date

from ..core import clock
from ..repositories.tasks import TaskRepository
from .settings_service import SettingsService

PRIORITIES = {1: "高", 2: "中", 3: "低"}


class TaskService:
    def __init__(self, tasks: TaskRepository, settings: SettingsService) -> None:
        self.tasks = tasks
        self.settings = settings

    def today(self) -> date:
        return clock.study_date(clock.now_utc(), self.settings.day_change_hour)

    def list(self, *, include_done: bool = True, exam_id: str | None = None) -> list:
        return self.tasks.list(include_done=include_done, exam_id=exam_id)

    def create(
        self,
        *,
        content: str,
        due_on: date | None = None,
        priority: int = 2,
        exam_id: str | None = None,
        subject_id: str | None = None,
    ) -> str:
        content = content.strip()
        if not content:
            raise ValueError("課題の内容を入力してください")
        if priority not in PRIORITIES:
            raise ValueError(f"優先度が不正: {priority}")
        return self.tasks.insert(
            {
                "content": content,
                "due_on": due_on.isoformat() if due_on else None,
                "priority": int(priority),
                "exam_id": exam_id,
                "subject_id": subject_id,
            }
        )

    def update(self, task_id: str, values: dict) -> None:
        data = dict(values)
        if "content" in data and not str(data["content"]).strip():
            raise ValueError("課題の内容を入力してください")
        if isinstance(data.get("due_on"), date):
            data["due_on"] = data["due_on"].isoformat()
        self.tasks.update(task_id, data)

    def set_done(self, task_id: str, done: bool) -> None:
        self.tasks.update(
            task_id, {"done": 1 if done else 0, "done_at": clock.db_now() if done else None}
        )

    def delete(self, task_id: str) -> None:
        self.tasks.soft_delete(task_id)

    def due_soon(self, days: int = 7) -> list:
        return self.tasks.due_soon(self.today(), days)

    def count_open(self) -> int:
        return self.tasks.count_open()
