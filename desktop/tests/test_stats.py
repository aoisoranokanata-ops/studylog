"""フェーズ3（可視化）：集計・週目標・資格目標のテスト。"""

from __future__ import annotations

import time
from datetime import date, timedelta

import pytest

from .conftest import local
from .test_performance import _bulk_insert


def add(ctx, day: date, seconds: int, *, hour: int = 9, **kwargs) -> str:
    started = local(day.year, day.month, day.day, hour)
    return ctx.sessions.create(
        started_at=started,
        ended_at=started + timedelta(seconds=max(seconds, 60)),
        active_seconds=seconds,
        **kwargs,
    )


# --- 期間ごとの合計 ---------------------------------------------------------

def test_daily_totals_fill_empty_days(ctx, sample_masters):
    add(ctx, date(2026, 9, 18), 1800, exam_id=sample_masters["exam_id"])
    add(ctx, date(2026, 9, 20), 3600, exam_id=sample_masters["exam_id"])
    totals = ctx.stats.period_totals("day", date(2026, 9, 17), date(2026, 9, 20))
    assert [t.seconds for t in totals] == [0, 1800, 0, 3600]
    assert totals[0].label == "9/17"


def test_weekly_totals_follow_week_start(ctx, sample_masters):
    add(ctx, date(2026, 9, 14), 3600, exam_id=sample_masters["exam_id"])  # 月曜
    add(ctx, date(2026, 9, 20), 1800, exam_id=sample_masters["exam_id"])  # 日曜
    add(ctx, date(2026, 9, 21), 600, exam_id=sample_masters["exam_id"])   # 翌週の月曜
    totals = ctx.stats.period_totals("week", date(2026, 9, 14), date(2026, 9, 21))
    assert [(t.start, t.seconds) for t in totals] == [
        (date(2026, 9, 14), 5400),
        (date(2026, 9, 21), 600),
    ]

    ctx.settings.set("week_starts_on", "7")  # 日曜始まり
    totals = ctx.stats.period_totals("week", date(2026, 9, 14), date(2026, 9, 21))
    assert [(t.start, t.seconds) for t in totals] == [
        (date(2026, 9, 13), 3600),
        (date(2026, 9, 20), 2400),
    ]


def test_monthly_totals(ctx, sample_masters):
    add(ctx, date(2026, 8, 31), 1200, exam_id=sample_masters["exam_id"])
    add(ctx, date(2026, 9, 1), 600, exam_id=sample_masters["exam_id"])
    add(ctx, date(2026, 9, 30), 600, exam_id=sample_masters["exam_id"])
    totals = ctx.stats.period_totals("month", date(2026, 8, 1), date(2026, 10, 5))
    assert [(t.label, t.seconds) for t in totals] == [
        ("2026/08", 1200),
        ("2026/09", 1200),
        ("2026/10", 0),
    ]


def test_default_ranges(ctx):
    today = date(2026, 9, 22)
    assert ctx.stats.default_range("day", today) == (date(2026, 8, 24), today)
    week_from, _ = ctx.stats.default_range("week", today)
    assert week_from == date(2026, 7, 6) and week_from.isoweekday() == 1
    assert ctx.stats.default_range("month", today)[0] == date(2025, 10, 1)


def test_late_night_goes_to_previous_day_in_totals(ctx, sample_masters):
    add(ctx, date(2026, 9, 21), 1800, hour=2, exam_id=sample_masters["exam_id"])
    totals = ctx.stats.period_totals("day", date(2026, 9, 20), date(2026, 9, 21))
    assert [t.seconds for t in totals] == [1800, 0]


# --- 内訳 -------------------------------------------------------------------

def test_breakdown_by_exam_material_subject(ctx, sample_masters):
    exam2 = ctx.masters.create_exam("FP2級")
    add(ctx, date(2026, 9, 20), 3000, exam_id=sample_masters["exam_id"],
        material_id=sample_masters["material_id"], subject_id=sample_masters["subject_id"])
    add(ctx, date(2026, 9, 20), 1000, exam_id=exam2)
    add(ctx, date(2026, 9, 20), 1000)  # 未分類

    by_exam = ctx.stats.breakdown("exam", date(2026, 9, 1), date(2026, 9, 30))
    assert [(row.label, row.seconds) for row in by_exam] == [
        ("行政書士", 3000), ("FP2級", 1000), ("未分類", 1000),
    ]
    assert by_exam[0].share == pytest.approx(0.6)

    by_material = ctx.stats.breakdown("material", date(2026, 9, 1), date(2026, 9, 30))
    assert by_material[0].label == "民法 問題集"
    assert by_material[1].label == "（指定なし）"

    by_subject = ctx.stats.breakdown(
        "subject", date(2026, 9, 1), date(2026, 9, 30), exam_id=sample_masters["exam_id"]
    )
    assert [(row.label, row.seconds) for row in by_subject] == [("民法", 3000)]


def test_accuracy_by_subject(ctx, sample_masters):
    exam = sample_masters["exam_id"]
    sosoku = ctx.masters.create_subject(exam, "総則", parent_id=sample_masters["subject_id"])
    add(ctx, date(2026, 9, 20), 1800, exam_id=exam, subject_id=sosoku, correct=18, attempted=20)
    add(ctx, date(2026, 9, 21), 1800, exam_id=exam, subject_id=sosoku, correct=6, attempted=10)
    add(ctx, date(2026, 9, 21), 1800, exam_id=exam, subject_id=sosoku)  # 正答未入力は数えない

    rows = ctx.stats.accuracy_by_subject(date(2026, 9, 1), date(2026, 9, 30))
    assert len(rows) == 1
    assert rows[0].label == "民法 / 総則"
    assert (rows[0].correct, rows[0].attempted) == (24, 30)
    assert rows[0].rate == pytest.approx(0.8)


def test_material_progress(ctx, sample_masters):
    add(ctx, date(2026, 9, 20), 1800, exam_id=sample_masters["exam_id"],
        material_id=sample_masters["material_id"], range_unit="question", range_from=1, range_to=120)
    rows = ctx.stats.material_progress()
    assert rows[0].name == "民法 問題集"
    assert rows[0].rate == pytest.approx(120 / 480)


# --- 学習日数・連続 ---------------------------------------------------------

def test_streak_counts_until_today(ctx, sample_masters):
    for day in (15, 16, 17, 19, 20, 21, 22):
        add(ctx, date(2026, 9, day), 600, exam_id=sample_masters["exam_id"])
    streak = ctx.stats.streak(date(2026, 9, 22))
    assert streak.current == 4  # 19〜22
    assert streak.longest == 4


def test_streak_survives_until_end_of_today(ctx, sample_masters):
    """今日まだ勉強していなくても、昨日まで続いていれば途切れていない。"""
    for day in (20, 21):
        add(ctx, date(2026, 9, day), 600, exam_id=sample_masters["exam_id"])
    assert ctx.stats.streak(date(2026, 9, 22)).current == 2
    assert ctx.stats.streak(date(2026, 9, 23)).current == 0


def test_streak_longest_in_the_past(ctx, sample_masters):
    for day in (1, 2, 3, 4, 5, 20):
        add(ctx, date(2026, 9, day), 600, exam_id=sample_masters["exam_id"])
    streak = ctx.stats.streak(date(2026, 9, 20))
    assert (streak.current, streak.longest) == (1, 5)


def test_streak_empty(ctx):
    streak = ctx.stats.streak(date(2026, 9, 22))
    assert (streak.current, streak.longest) == (0, 0)


def test_study_day_count(ctx, sample_masters):
    add(ctx, date(2026, 9, 20), 600, exam_id=sample_masters["exam_id"])
    add(ctx, date(2026, 9, 20), 600, hour=15, exam_id=sample_masters["exam_id"])
    add(ctx, date(2026, 9, 22), 600, exam_id=sample_masters["exam_id"])
    assert ctx.stats.study_day_count(date(2026, 9, 1), date(2026, 9, 30)) == 2


# --- ノルマの達成率 ---------------------------------------------------------

def test_quota_achievement(ctx, sample_masters):
    day = date(2026, 9, 22)
    ids = [
        ctx.quotas.create(day=day, title=f"q{i}", target_seconds=600, exam_id=sample_masters["exam_id"])
        for i in range(4)
    ]
    ctx.quota_repo.update(ids[0], {"status": "done"})
    ctx.quota_repo.update(ids[1], {"status": "partial"})
    ctx.quota_repo.update(ids[2], {"status": "skipped"})
    result = ctx.stats.quota_achievement(day, day)
    assert (result.total, result.done, result.partial, result.skipped, result.none) == (4, 1, 1, 1, 1)
    assert result.rate == pytest.approx(1.5 / 4)


# --- 週目標 -----------------------------------------------------------------

def test_week_goal_is_inherited_from_previous_week(ctx):
    ctx.goals.set_week_goal(date(2026, 9, 7), 20 * 3600)
    goal = ctx.goals.week_goal(date(2026, 9, 21))
    assert goal.seconds == 20 * 3600
    assert goal.inherited_from == date(2026, 9, 7)

    ctx.goals.set_week_goal(date(2026, 9, 21), 25 * 3600)
    goal = ctx.goals.week_goal(date(2026, 9, 21))
    assert goal.seconds == 25 * 3600 and goal.inherited_from is None
    # 過去の週は過去の値のまま
    assert ctx.goals.week_goal(date(2026, 9, 14)).seconds == 20 * 3600


def test_week_goal_is_normalized_to_week_start(ctx):
    ctx.goals.set_week_goal(date(2026, 9, 24), 10 * 3600)  # 木曜を渡しても週の頭に揃える
    assert ctx.goals.week_goal(date(2026, 9, 21)).seconds == 10 * 3600


def test_no_goal_means_zero(ctx):
    goal = ctx.goals.week_goal(date(2026, 9, 21))
    assert goal.seconds == 0 and not goal.is_set


def test_per_exam_week_goal_is_separate(ctx, sample_masters):
    ctx.goals.set_week_goal(date(2026, 9, 21), 20 * 3600)
    ctx.goals.set_week_goal(date(2026, 9, 21), 8 * 3600, exam_id=sample_masters["exam_id"])
    assert ctx.goals.week_goal(date(2026, 9, 21)).seconds == 20 * 3600
    assert ctx.goals.week_goal(date(2026, 9, 21), sample_masters["exam_id"]).seconds == 8 * 3600


def test_week_progress(ctx, sample_masters):
    ctx.goals.set_week_goal(date(2026, 9, 21), 10 * 3600)
    add(ctx, date(2026, 9, 21), 3 * 3600, exam_id=sample_masters["exam_id"])
    add(ctx, date(2026, 9, 23), 2 * 3600, exam_id=sample_masters["exam_id"])
    progress = ctx.goals.week_progress(date(2026, 9, 23))
    assert progress.week_start == date(2026, 9, 21)
    assert progress.actual == 5 * 3600
    assert progress.ratio == pytest.approx(0.5)


def test_week_history_is_newest_first(ctx, sample_masters):
    add(ctx, date(2026, 9, 15), 3600, exam_id=sample_masters["exam_id"])
    history = ctx.goals.week_history(3, date(2026, 9, 22))
    assert [h.week_start for h in history] == [date(2026, 9, 21), date(2026, 9, 14), date(2026, 9, 7)]
    assert history[1].actual == 3600


def test_down_package_uses_inherited_week_goal(ctx):
    ctx.goals.set_week_goal(date(2026, 9, 7), 15 * 3600)
    package = ctx.transfer.build_down(date(2026, 9, 22), variant="full")
    assert package["summary"]["weekGoalSeconds"] == 15 * 3600


# --- 資格ごとの目標 ---------------------------------------------------------

def test_exam_plan_per_day_needed(ctx, sample_masters):
    exam = sample_masters["exam_id"]
    ctx.masters.set_exam_date(exam, "2026-10-02")
    ctx.goals.set_exam_total_goal(exam, 100 * 3600)
    add(ctx, date(2026, 9, 20), 40 * 3600 // 10, exam_id=exam)  # 4時間

    plan = next(p for p in ctx.goals.exam_plans(date(2026, 9, 22)) if p.exam.id == exam)
    assert plan.days_left == 10
    assert plan.studied == 4 * 3600
    assert plan.remaining == 96 * 3600
    assert plan.per_day_needed == pytest.approx(96 * 3600 / 10)


def test_exam_plan_without_goal_or_date(ctx, sample_masters):
    plan = ctx.goals.exam_plans(date(2026, 9, 22))[0]
    assert plan.days_left is None
    assert plan.per_day_needed is None
    assert plan.ratio is None


def test_exam_plans_sorted_by_nearest_exam(ctx, sample_masters):
    far = ctx.masters.create_exam("宅建")
    ctx.masters.set_exam_date(far, "2027-10-01")
    ctx.masters.set_exam_date(sample_masters["exam_id"], "2026-11-08")
    ctx.masters.create_exam("日付なし")
    names = [p.exam.name for p in ctx.goals.exam_plans(date(2026, 9, 22))]
    assert names == ["行政書士", "宅建", "日付なし"]


# --- 速さ -------------------------------------------------------------------

def test_stats_are_fast_with_10k_sessions(ctx, sample_masters):
    _bulk_insert(ctx, sample_masters["exam_id"])
    today = date(2027, 6, 1)
    started = time.perf_counter()
    for unit in ("day", "week", "month"):
        date_from, date_to = ctx.stats.default_range(unit, today)
        ctx.stats.period_totals(unit, date_from, date_to)
    for by in ("exam", "material", "subject"):
        ctx.stats.breakdown(by, date(2024, 1, 1), today)
    ctx.stats.accuracy_by_subject(date(2024, 1, 1), today)
    ctx.stats.streak(today)
    ctx.goals.week_history(8, today)
    ctx.goals.exam_plans(today)
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0, f"集計に{elapsed:.2f}秒かかった"
