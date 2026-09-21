from __future__ import annotations

from datetime import timedelta

import pytest

from studylog import config
from studylog.context import AppContext

from .conftest import local


def test_elapsed_is_computed_from_timestamps(ctx, sample_masters):
    start = local(2026, 9, 20, 9, 0)
    ctx.timer.start(exam_id=sample_masters["exam_id"], now=start)
    assert ctx.timer.elapsed_seconds(start + timedelta(minutes=30)) == 1800


def test_pause_and_resume(ctx, sample_masters):
    start = local(2026, 9, 20, 9, 0)
    ctx.timer.start(exam_id=sample_masters["exam_id"], now=start)
    ctx.timer.pause(now=start + timedelta(minutes=30))

    # 停止中は時間が進まない
    assert ctx.timer.elapsed_seconds(start + timedelta(hours=2)) == 1800

    ctx.timer.resume(now=start + timedelta(hours=2))
    assert ctx.timer.elapsed_seconds(start + timedelta(hours=2, minutes=10)) == 1800 + 600


def test_state_survives_restart(ctx, sample_masters, tmp_path, monkeypatch):
    start = local(2026, 9, 20, 9, 0)
    ctx.timer.start(exam_id=sample_masters["exam_id"], now=start)
    ctx.close(backup_on_exit=False)

    monkeypatch.setenv(config.ENV_DATA_DIR, str(tmp_path))
    reopened = AppContext.open(backup_on_start=False)
    try:
        state = reopened.timer.current()
        assert state is not None and state.is_running
        # アプリが止まっていた間も経過時間は進んでいる
        assert reopened.timer.elapsed_seconds(start + timedelta(hours=1)) == 3600
    finally:
        reopened.close(backup_on_exit=False)


def test_finish_creates_session_and_clears_state(ctx, sample_masters):
    start = local(2026, 9, 20, 9, 0)
    ctx.timer.start(
        exam_id=sample_masters["exam_id"],
        material_id=sample_masters["material_id"],
        now=start,
    )
    ctx.timer.pause(now=start + timedelta(minutes=50))
    ctx.timer.resume(now=start + timedelta(minutes=60))
    end = start + timedelta(minutes=90)

    session_id = ctx.timer.finish(ended_at=end, now=end, range_unit="question", range_from=40, range_to=65)

    session = ctx.sessions.get(session_id)
    assert session.active_seconds == 80 * 60  # 一時停止の10分を除いた分
    assert session.entry_mode == "timer"
    assert session.range_to == 65
    assert ctx.timer.current() is None


def test_finish_with_corrected_end_time_clips_duration(ctx, sample_masters):
    """つけっぱなしを終了時に直した場合、勉強時間もその長さに収まる。"""
    start = local(2026, 9, 20, 9, 0)
    ctx.timer.start(exam_id=sample_masters["exam_id"], now=start)
    now = start + timedelta(hours=8)
    assert ctx.timer.is_long(now) is True

    corrected_end = start + timedelta(hours=2)
    session_id = ctx.timer.finish(ended_at=corrected_end, now=now)
    assert ctx.sessions.get(session_id).active_seconds == 7200


def test_cannot_start_twice(ctx, sample_masters):
    ctx.timer.start(exam_id=sample_masters["exam_id"])
    with pytest.raises(RuntimeError):
        ctx.timer.start(exam_id=sample_masters["exam_id"])


def test_discard_leaves_no_session(ctx, sample_masters):
    ctx.timer.start(exam_id=sample_masters["exam_id"])
    ctx.timer.discard()
    assert ctx.timer.current() is None
    assert ctx.sessions.list() == []


def test_classification_can_be_changed_while_running(ctx, sample_masters):
    start = local(2026, 9, 20, 9, 0)
    ctx.timer.start(now=start)
    ctx.timer.update_classification(
        exam_id=sample_masters["exam_id"],
        material_id=sample_masters["material_id"],
        subject_id=None,
    )
    end = start + timedelta(minutes=30)
    session_id = ctx.timer.finish(ended_at=end, now=end)
    assert ctx.sessions.get(session_id).exam_id == sample_masters["exam_id"]
