"""ストップウォッチ方式の計測。

経過時間は必ず開始・再開の時刻から計算する（アプリが落ちていても、PCがスリープしても正しい）。
状態は操作のたびにDBへ書くので、再起動しても続きから再開できる。
"""

from __future__ import annotations

from datetime import datetime

from ..core import clock
from ..domain.models import TimerState
from ..repositories.timer import TimerRepository
from .session_service import SessionService
from .settings_service import SettingsService


class TimerService:
    def __init__(
        self,
        repo: TimerRepository,
        sessions: SessionService,
        settings: SettingsService,
    ) -> None:
        self.repo = repo
        self.sessions = sessions
        self.settings = settings

    def current(self) -> TimerState | None:
        return self.repo.get()

    def elapsed_seconds(self, now: datetime | None = None) -> int:
        state = self.current()
        return state.elapsed_seconds(now) if state else 0

    def is_running(self) -> bool:
        state = self.current()
        return bool(state and state.is_running)

    def is_long(self, now: datetime | None = None) -> bool:
        """つけっぱなしの疑いがあるか（既定は5時間）。"""
        return self.elapsed_seconds(now) >= self.settings.long_session_seconds

    # --- 操作 ---------------------------------------------------------------

    def start(
        self,
        *,
        exam_id: str | None = None,
        material_id: str | None = None,
        subject_id: str | None = None,
        quota_id: str | None = None,
        memo: str = "",
        now: datetime | None = None,
    ) -> TimerState:
        if self.current() is not None:
            raise RuntimeError("すでに計測中です")
        now = now or clock.now_utc()
        state = TimerState(
            exam_id=exam_id,
            material_id=material_id,
            subject_id=subject_id,
            quota_id=quota_id,
            started_at=now,
            accumulated_seconds=0,
            resumed_at=now,
            is_running=True,
            memo=memo,
        )
        self.repo.save(state)
        return state

    def pause(self, now: datetime | None = None) -> TimerState:
        state = self._require_state()
        if not state.is_running:
            return state
        now = now or clock.now_utc()
        state.accumulated_seconds = state.elapsed_seconds(now)
        state.resumed_at = None
        state.is_running = False
        self.repo.save(state)
        return state

    def resume(self, now: datetime | None = None) -> TimerState:
        state = self._require_state()
        if state.is_running:
            return state
        state.resumed_at = now or clock.now_utc()
        state.is_running = True
        self.repo.save(state)
        return state

    def update_classification(
        self,
        *,
        exam_id: str | None,
        material_id: str | None,
        subject_id: str | None,
        quota_id: str | None = None,
        memo: str | None = None,
    ) -> TimerState:
        """計測中に選び直した分類を反映する。"""
        state = self._require_state()
        state.exam_id = exam_id
        state.material_id = material_id
        state.subject_id = subject_id
        state.quota_id = quota_id
        if memo is not None:
            state.memo = memo
        self.repo.save(state)
        return state

    def finish(
        self,
        *,
        ended_at: datetime | None = None,
        active_seconds: int | None = None,
        exam_id: str | None = None,
        material_id: str | None = None,
        subject_id: str | None = None,
        quota_id: str | None = None,
        range_unit: str | None = None,
        range_from: int | None = None,
        range_to: int | None = None,
        correct: int | None = None,
        attempted: int | None = None,
        focus: int | None = None,
        memo: str | None = None,
        now: datetime | None = None,
    ) -> str:
        """計測を終えて記録にする。終了時刻を手で直した場合は、その長さに丸める。"""
        state = self._require_state()
        now = now or clock.now_utc()
        ended_at = ended_at or now
        seconds = state.elapsed_seconds(now) if active_seconds is None else int(active_seconds)
        span = int((ended_at - state.started_at).total_seconds())
        seconds = max(0, min(seconds, span))

        session_id = self.sessions.create(
            started_at=state.started_at,
            ended_at=ended_at,
            active_seconds=seconds,
            exam_id=exam_id if exam_id is not None else state.exam_id,
            material_id=material_id if material_id is not None else state.material_id,
            subject_id=subject_id if subject_id is not None else state.subject_id,
            quota_id=quota_id if quota_id is not None else state.quota_id,
            range_unit=range_unit,
            range_from=range_from,
            range_to=range_to,
            correct=correct,
            attempted=attempted,
            focus=focus,
            memo=state.memo if memo is None else memo,
            entry_mode="timer",
        )
        self.repo.clear()
        return session_id

    def discard(self) -> None:
        self.repo.clear()

    def _require_state(self) -> TimerState:
        state = self.current()
        if state is None:
            raise RuntimeError("計測していません")
        return state
