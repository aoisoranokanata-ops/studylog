from __future__ import annotations

from datetime import date, timedelta

import pytest

from studylog.domain.models import SessionFilter

from .conftest import local


# --- マスタ -----------------------------------------------------------------

def test_subject_depth_is_limited_to_two(ctx, sample_masters):
    exam_id = sample_masters["exam_id"]
    parent = ctx.masters.create_subject(exam_id, "民法")
    child = ctx.masters.create_subject(exam_id, "総則", parent_id=parent)
    with pytest.raises(ValueError, match="2階層"):
        ctx.masters.create_subject(exam_id, "意思表示", parent_id=child)


def test_subject_tree_label(ctx, sample_masters):
    exam_id = sample_masters["exam_id"]
    parent = ctx.masters.create_subject(exam_id, "民法A")
    child = ctx.masters.create_subject(exam_id, "総則", parent_id=parent)
    assert ctx.masters.subjects.tree_label(child) == "民法A / 総則"


def test_deleting_exam_makes_sessions_unclassified(ctx, sample_masters):
    ctx.sessions.create(
        started_at=local(2026, 9, 20, 9),
        ended_at=local(2026, 9, 20, 10),
        active_seconds=3600,
        exam_id=sample_masters["exam_id"],
        material_id=sample_masters["material_id"],
        subject_id=sample_masters["subject_id"],
    )
    result = ctx.masters.delete_exam(sample_masters["exam_id"])
    assert result["sessions_unclassified"] == 1

    session = ctx.sessions.list()[0]
    assert session.unclassified is True
    assert session.exam_id is None
    assert ctx.masters.list_materials() == []
    assert ctx.masters.list_exams() == []


def test_material_requires_exam(ctx):
    with pytest.raises(ValueError):
        ctx.masters.create_material("", "参考書")


# --- 記録 -------------------------------------------------------------------

def test_create_and_list_session(ctx, sample_masters):
    session_id = ctx.sessions.create(
        started_at=local(2026, 9, 20, 9),
        ended_at=local(2026, 9, 20, 11),
        active_seconds=6300,
        exam_id=sample_masters["exam_id"],
        material_id=sample_masters["material_id"],
        range_unit="question",
        range_from=40,
        range_to=65,
        correct=19,
        attempted=26,
        focus=4,
        memo="時効",
    )
    session = ctx.sessions.get(session_id)
    assert session is not None
    assert session.active_seconds == 6300
    assert session.unclassified is False
    assert session.study_date == date(2026, 9, 20)
    # 範囲の終わりまで参考書の現在位置が進む
    assert ctx.masters.materials.get(sample_masters["material_id"]).current == 65


def test_late_night_session_counts_as_previous_day(ctx, sample_masters):
    ctx.sessions.create(
        started_at=local(2026, 9, 21, 2, 0),
        ended_at=local(2026, 9, 21, 3, 0),
        active_seconds=3600,
        exam_id=sample_masters["exam_id"],
    )
    assert ctx.sessions.seconds_for_day(date(2026, 9, 20)) == 3600
    assert ctx.sessions.seconds_for_day(date(2026, 9, 21)) == 0


def test_changing_day_change_hour_recomputes_study_dates(ctx, sample_masters):
    ctx.sessions.create(
        started_at=local(2026, 9, 21, 2, 0),
        ended_at=local(2026, 9, 21, 3, 0),
        active_seconds=3600,
        exam_id=sample_masters["exam_id"],
    )
    ctx.settings.set("day_change_hour", "0")
    changed = ctx.session_repo.recompute_study_dates(ctx.settings.day_change_hour)
    assert changed == 1
    assert ctx.sessions.seconds_for_day(date(2026, 9, 21)) == 3600


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"ended_at": local(2026, 9, 20, 8)}, "終了時刻"),
        ({"active_seconds": 99999}, "長さを超え"),
        ({"correct": 30, "attempted": 25}, "正答数"),
        ({"focus": 9}, "集中度"),
        ({"range_from": 90, "range_to": 66}, "範囲"),
    ],
)
def test_session_validation(ctx, sample_masters, kwargs, message):
    payload = {
        "started_at": local(2026, 9, 20, 9),
        "ended_at": local(2026, 9, 20, 10),
        "active_seconds": 3600,
        "exam_id": sample_masters["exam_id"],
    }
    payload.update(kwargs)
    with pytest.raises(ValueError, match=message):
        ctx.sessions.create(**payload)


def test_session_without_exam_is_unclassified(ctx):
    session_id = ctx.sessions.create(
        started_at=local(2026, 9, 20, 9),
        ended_at=local(2026, 9, 20, 10),
        active_seconds=3600,
    )
    assert ctx.sessions.get(session_id).unclassified is True


def test_update_moves_study_date(ctx, sample_masters):
    session_id = ctx.sessions.create(
        started_at=local(2026, 9, 20, 9),
        ended_at=local(2026, 9, 20, 10),
        active_seconds=3600,
        exam_id=sample_masters["exam_id"],
    )
    ctx.sessions.update(
        session_id,
        {"started_at": local(2026, 9, 25, 9), "ended_at": local(2026, 9, 25, 10)},
    )
    assert ctx.sessions.get(session_id).study_date == date(2026, 9, 25)


def test_deleted_session_disappears_from_list_and_totals(ctx, sample_masters):
    session_id = ctx.sessions.create(
        started_at=local(2026, 9, 20, 9),
        ended_at=local(2026, 9, 20, 10),
        active_seconds=3600,
        exam_id=sample_masters["exam_id"],
    )
    ctx.sessions.delete(session_id)
    assert ctx.sessions.list() == []
    assert ctx.sessions.seconds_for_day(date(2026, 9, 20)) == 0


def test_weekly_total_uses_week_start_setting(ctx, sample_masters):
    for day in (14, 20):  # 月曜と日曜（同じ週）
        ctx.sessions.create(
            started_at=local(2026, 9, day, 9),
            ended_at=local(2026, 9, day, 10),
            active_seconds=3600,
            exam_id=sample_masters["exam_id"],
        )
    assert ctx.sessions.seconds_for_week(date(2026, 9, 20)) == 7200
    ctx.settings.set("week_starts_on", "7")  # 日曜始まりなら20日は別の週
    assert ctx.sessions.seconds_for_week(date(2026, 9, 20)) == 3600


def test_daily_totals(ctx, sample_masters):
    for day in (18, 19, 20):
        ctx.sessions.create(
            started_at=local(2026, 9, day, 9),
            ended_at=local(2026, 9, day, 12),
            active_seconds=1800 * (day - 17),
            exam_id=sample_masters["exam_id"],
        )
    totals = ctx.session_repo.daily_totals(date(2026, 9, 18), date(2026, 9, 20))
    assert [t.seconds for t in totals] == [1800, 3600, 5400]


def test_filter_by_unclassified(ctx, sample_masters):
    ctx.sessions.create(
        started_at=local(2026, 9, 20, 9),
        ended_at=local(2026, 9, 20, 10),
        active_seconds=3600,
        exam_id=sample_masters["exam_id"],
    )
    ctx.sessions.create(
        started_at=local(2026, 9, 20, 11),
        ended_at=local(2026, 9, 20, 12),
        active_seconds=3600,
    )
    assert len(ctx.sessions.list(SessionFilter(unclassified_only=True))) == 1


# --- 設定 -------------------------------------------------------------------

def test_settings_defaults_and_persistence(ctx):
    assert ctx.settings.day_change_hour == 4
    assert ctx.settings.week_starts_on == 1
    assert ctx.settings.backup_generations == 14
    assert ctx.settings.review_intervals == [1, 3, 7, 14, 30]
    ctx.settings.set("day_change_hour", "3")
    ctx.settings.reload()
    assert ctx.settings.day_change_hour == 3


def test_hub_id_is_stable(ctx):
    first = ctx.settings.hub_id
    assert first and ctx.settings.hub_id == first


def test_last_used_is_remembered_after_create(ctx, sample_masters):
    ctx.sessions.create(
        started_at=local(2026, 9, 20, 9),
        ended_at=local(2026, 9, 20, 10),
        active_seconds=3600,
        exam_id=sample_masters["exam_id"],
        material_id=sample_masters["material_id"],
    )
    initial = ctx.sessions.initial_classification()
    assert initial["exam_id"] == sample_masters["exam_id"]
    assert initial["material_id"] == sample_masters["material_id"]


# --- バックアップ -----------------------------------------------------------

def test_backup_service_keeps_generations(ctx):
    ctx.settings.set("backup_generations", "2")
    created = [ctx.backups.create("test") for _ in range(3)]
    assert len({path.name for path in created}) == 3  # 同じ秒でも別ファイルになる
    assert len(ctx.backups.listing()) == 2
