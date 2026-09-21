"""計測中の状態の保存先（1行だけ）。"""

from __future__ import annotations

from ..core import clock
from ..domain.models import TimerState
from .base import BaseRepository

CURRENT = "current"


class TimerRepository(BaseRepository):
    table = "timer_state"

    def get(self) -> TimerState | None:
        row = self.row(CURRENT)
        return TimerState.from_row(row) if row else None

    def save(self, state: TimerState) -> None:
        now = clock.db_now()
        values = {
            "exam_id": state.exam_id,
            "material_id": state.material_id,
            "subject_id": state.subject_id,
            "quota_id": state.quota_id,
            "started_at": clock.to_db(state.started_at),
            "accumulated_seconds": int(state.accumulated_seconds),
            "resumed_at": clock.to_db(state.resumed_at) if state.resumed_at else None,
            "is_running": 1 if state.is_running else 0,
            "memo": state.memo,
            "updated_at": now,
        }
        if self.row(CURRENT) is None:
            self.insert({**values, "id": CURRENT, "created_at": now})
        else:
            self.update(CURRENT, values)

    def clear(self) -> None:
        self.hard_delete(CURRENT)
