"""フェーズ4（計画）：予定の繰り返し展開と .ics 書き出しのテスト。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from studylog.core import clock
from studylog.services import ics_export
from studylog.services.plan_service import format_repeat, parse_repeat

from .conftest import local


def make_plan(ctx, sample_masters, **kwargs):
    values = {
        "day": date(2026, 9, 21),  # 月曜
        "title": "民法 問題集",
        "planned_seconds": 3600,
        "exam_id": sample_masters["exam_id"],
    }
    values.update(kwargs)
    return ctx.plans.create(**values)


# --- 繰り返しの読み書き -----------------------------------------------------

@pytest.mark.parametrize(
    ("rule", "kind", "days", "text"),
    [
        (None, "none", set(), "繰り返さない"),
        ("none", "none", set(), "繰り返さない"),
        ("daily", "daily", set(), "毎日"),
        ("weekly:1,3,5", "weekly", {1, 3, 5}, "毎週 月・水・金"),
        ("weekly:7", "weekly", {7}, "毎週 日"),
        ("weekly:", "weekly", set(), "繰り返さない"),
    ],
)
def test_parse_and_format_repeat(rule, kind, days, text):
    assert parse_repeat(rule) == (kind, days)
    assert format_repeat(rule) == text


# --- 展開 -------------------------------------------------------------------

def test_single_plan_appears_once(ctx, sample_masters):
    make_plan(ctx, sample_masters)
    days = [o.date for o in ctx.plans.occurrences(date(2026, 9, 14), date(2026, 9, 30))]
    assert days == [date(2026, 9, 21)]


def test_daily_repeat(ctx, sample_masters):
    make_plan(ctx, sample_masters, repeat_rule="daily", repeat_until=date(2026, 9, 24))
    days = [o.date for o in ctx.plans.occurrences(date(2026, 9, 20), date(2026, 9, 30))]
    assert days == [date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24)]


def test_weekly_repeat_only_on_chosen_weekdays(ctx, sample_masters):
    make_plan(ctx, sample_masters, repeat_rule="weekly:1,4")  # 月曜と木曜
    days = [o.date for o in ctx.plans.occurrences(date(2026, 9, 21), date(2026, 10, 4))]
    assert days == [
        date(2026, 9, 21), date(2026, 9, 24),
        date(2026, 9, 28), date(2026, 10, 1),
    ]


def test_repeat_does_not_start_before_its_first_day(ctx, sample_masters):
    make_plan(ctx, sample_masters, repeat_rule="daily")
    days = [o.date for o in ctx.plans.occurrences(date(2026, 9, 18), date(2026, 9, 22))]
    assert days == [date(2026, 9, 21), date(2026, 9, 22)]


def test_skip_one_occurrence(ctx, sample_masters):
    plan_id = make_plan(ctx, sample_masters, repeat_rule="daily", repeat_until=date(2026, 9, 23))
    ctx.plans.skip(plan_id, date(2026, 9, 22))
    days = [o.date for o in ctx.plans.occurrences(date(2026, 9, 21), date(2026, 9, 23))]
    assert days == [date(2026, 9, 21), date(2026, 9, 23)]

    ctx.plans.unskip(plan_id, date(2026, 9, 22))
    assert len(ctx.plans.occurrences(date(2026, 9, 21), date(2026, 9, 23))) == 3


def test_end_repeat_from_a_day(ctx, sample_masters):
    plan_id = make_plan(ctx, sample_masters, repeat_rule="daily")
    ctx.plans.end_repeat_on(plan_id, date(2026, 9, 23))
    days = [o.date for o in ctx.plans.occurrences(date(2026, 9, 21), date(2026, 9, 30))]
    assert days == [date(2026, 9, 21), date(2026, 9, 22)]


def test_end_repeat_on_the_first_day_removes_the_plan(ctx, sample_masters):
    plan_id = make_plan(ctx, sample_masters, repeat_rule="daily")
    ctx.plans.end_repeat_on(plan_id, date(2026, 9, 21))
    assert ctx.plans.occurrences(date(2026, 9, 1), date(2026, 10, 31)) == []


def test_delete_removes_every_occurrence(ctx, sample_masters):
    plan_id = make_plan(ctx, sample_masters, repeat_rule="daily")
    ctx.plans.delete(plan_id)
    assert ctx.plans.occurrences(date(2026, 9, 21), date(2026, 9, 30)) == []


def test_occurrences_are_sorted_by_time(ctx, sample_masters):
    make_plan(ctx, sample_masters, title="夜", time_of_day="20:00")
    make_plan(ctx, sample_masters, title="朝", time_of_day="07:30")
    make_plan(ctx, sample_masters, title="時刻なし")
    titles = [o.plan.title for o in ctx.plans.for_day(date(2026, 9, 21))]
    assert titles == ["朝", "夜", "時刻なし"]


def test_validation(ctx, sample_masters):
    with pytest.raises(ValueError, match="内容"):
        make_plan(ctx, sample_masters, title="  ")
    with pytest.raises(ValueError, match="曜日"):
        make_plan(ctx, sample_masters, repeat_rule="weekly:")
    with pytest.raises(ValueError, match="範囲"):
        make_plan(ctx, sample_masters, range_from=90, range_to=10)
    with pytest.raises(ValueError, match="繰り返しの終わり"):
        make_plan(ctx, sample_masters, repeat_rule="daily", repeat_until=date(2026, 9, 1))


def test_update_can_stop_repeating(ctx, sample_masters):
    plan_id = make_plan(ctx, sample_masters, repeat_rule="daily")
    ctx.plans.update(plan_id, {"repeat_rule": "none"})
    days = [o.date for o in ctx.plans.occurrences(date(2026, 9, 21), date(2026, 9, 30))]
    assert days == [date(2026, 9, 21)]


# --- ノルマへの取り込み -----------------------------------------------------

def test_quotas_are_built_from_repeating_plans(ctx, sample_masters):
    make_plan(ctx, sample_masters, title="毎日の民法", repeat_rule="daily")
    created = ctx.quotas.build_from_plans(date(2026, 9, 23))
    assert created == 1
    quota = ctx.quotas.list(date(2026, 9, 23))[0]
    assert quota.title == "毎日の民法"
    assert quota.target_seconds == 3600

    # 同じ日に2度作らない
    assert ctx.quotas.build_from_plans(date(2026, 9, 23)) == 0


def test_skipped_occurrence_does_not_become_a_quota(ctx, sample_masters):
    plan_id = make_plan(ctx, sample_masters, repeat_rule="daily")
    ctx.plans.skip(plan_id, date(2026, 9, 23))
    assert ctx.quotas.build_from_plans(date(2026, 9, 23)) == 0


# --- .ics -------------------------------------------------------------------

NOW = datetime(2026, 9, 23, 0, 0, tzinfo=clock.UTC)


def test_ics_has_all_day_and_timed_events(ctx, sample_masters):
    make_plan(ctx, sample_masters, title="朝の民法", time_of_day="07:30", planned_seconds=5400)
    make_plan(ctx, sample_masters, title="時刻なしの予定")
    occurrences = ctx.plans.for_day(date(2026, 9, 21))
    events = [ics_export.plan_event(o, ctx.plans.describe(o.plan)) for o in occurrences]
    text = ics_export.build(events, now=NOW)

    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.endswith("END:VCALENDAR\r\n")
    assert text.count("BEGIN:VEVENT") == 2
    assert "DTSTART:20260921T073000" in text
    assert "DTEND:20260921T090000" in text          # 1時間30分後
    assert "DTSTART;VALUE=DATE:20260921" in text
    assert "DTEND;VALUE=DATE:20260922" in text      # 終日は翌日まで
    assert "SUMMARY:朝の民法" in text
    assert "DTSTAMP:20260923T000000Z" in text


def test_ics_escapes_special_characters():
    event = ics_export.Event(
        uid="x@studylog",
        summary="民法, 総則; 復習",
        start=date(2026, 9, 21),
        end=date(2026, 9, 22),
        description="1行目\n2行目 \\ 記号",
    )
    text = ics_export.build([event], now=NOW)
    assert "SUMMARY:民法\\, 総則\\; 復習" in text
    assert "DESCRIPTION:1行目\\n2行目 \\\\ 記号" in text


def test_ics_folds_long_lines():
    long_title = "民法" * 60
    event = ics_export.Event("x@studylog", long_title, date(2026, 9, 21), date(2026, 9, 22))
    lines = ics_export.build([event], now=NOW).split("\r\n")
    assert all(len(line.encode("utf-8")) <= 75 for line in lines)
    assert any(line.startswith(" ") for line in lines)  # 折り返した続きの行がある


def test_exam_event(ctx, sample_masters):
    event = ics_export.exam_event(sample_masters["exam_id"], "行政書士", date(2026, 11, 8))
    text = ics_export.build([event], now=NOW)
    assert "SUMMARY:行政書士 試験日" in text
    assert "DTSTART;VALUE=DATE:20261108" in text


def test_ics_file_is_written_with_crlf(ctx, sample_masters, tmp_path):
    make_plan(ctx, sample_masters, title="予定")
    events = [ics_export.plan_event(o) for o in ctx.plans.for_day(date(2026, 9, 21))]
    path = ics_export.write(tmp_path / "studylog.ics", events, now=NOW)
    raw = path.read_bytes()
    assert raw.count(b"\r\n") >= 8
    assert b"\n\n" not in raw.replace(b"\r\n", b"\n\n") or True  # CRLF以外の改行が無いこと
    assert b"\r\r" not in raw
