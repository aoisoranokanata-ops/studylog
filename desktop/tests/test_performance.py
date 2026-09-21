"""非機能要件の確認：1万件の記録があっても集計が1秒以内に返ること。"""

from __future__ import annotations

import time
from datetime import date, timedelta

from studylog.core import clock, ids
from studylog.domain.models import SessionFilter

from .conftest import local

COUNT = 10_000


def _bulk_insert(ctx, exam_id: str, count: int = COUNT) -> None:
    start = local(2024, 1, 1, 9, 0)
    rows = []
    now = clock.db_now()
    for index in range(count):
        started = start + timedelta(hours=index * 3)
        ended = started + timedelta(minutes=45)
        rows.append(
            (
                ids.new_id(), exam_id, None, None, None, 0,
                clock.to_db(started), clock.to_db(ended), 2700,
                clock.study_date_str(started, 4),
                None, None, None, None, None, None, "", "timer", "hub", None, now, now, None,
            )
        )
    ctx.conn.execute("BEGIN")
    ctx.conn.executemany(
        "INSERT INTO sessions (id, exam_id, material_id, subject_id, quota_id, unclassified,"
        " started_at, ended_at, active_seconds, study_date, range_unit, range_from, range_to,"
        " correct, attempted, focus, memo, entry_mode, source, device_id,"
        " created_at, updated_at, deleted_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    ctx.conn.execute("COMMIT")


def test_aggregation_is_fast_with_10k_sessions(ctx, sample_masters):
    _bulk_insert(ctx, sample_masters["exam_id"])
    assert ctx.session_repo.count() == COUNT

    started = time.perf_counter()
    totals = ctx.session_repo.daily_totals(date(2024, 1, 1), date(2028, 1, 1))
    week = ctx.sessions.seconds_for_week(date(2024, 6, 1))
    recent = ctx.sessions.list(SessionFilter(limit=200))
    elapsed = time.perf_counter() - started

    assert totals and week >= 0 and len(recent) == 200
    assert elapsed < 1.0, f"集計に{elapsed:.2f}秒かかった"
