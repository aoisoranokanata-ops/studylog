"""フェーズ5（苦手克服と結果）：誤答・課題・合格結果のテスト。"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from .conftest import local


def add_session(ctx, day: date, minutes: int, **kwargs):
    started = local(day.year, day.month, day.day, 9)
    return ctx.sessions.create(
        started_at=started,
        ended_at=started + timedelta(minutes=minutes),
        active_seconds=minutes * 60,
        **kwargs,
    )


# --- 誤答 -------------------------------------------------------------------

def test_create_sets_the_first_review_date(ctx, sample_masters):
    today = ctx.mistakes.today()
    mistake_id = ctx.mistakes.create(
        question_ref=" p.52 問3 ", memo="取消権の期間", exam_id=sample_masters["exam_id"]
    )
    mistake = ctx.mistakes.get(mistake_id)
    assert mistake.question_ref == "p.52 問3"      # 前後の空白は落とす
    assert mistake.mastery == "unmastered"
    assert mistake.next_review_on == today + timedelta(days=1)
    assert mistake.source == "hub"


def test_create_requires_a_question(ctx):
    with pytest.raises(ValueError, match="問題の識別"):
        ctx.mistakes.create(question_ref="   ")


def test_answering_on_the_hub_moves_the_schedule_and_leaves_a_record(ctx, sample_masters):
    today = ctx.mistakes.today()
    mistake_id = ctx.mistakes.create(question_ref="p.52 問3", exam_id=sample_masters["exam_id"])

    after_ok = ctx.mistakes.answer(mistake_id, "ok")
    assert after_ok.consecutive_ok == 1
    assert after_ok.next_review_on == today + timedelta(days=3)

    history = ctx.mistakes.history(mistake_id)
    assert len(history) == 1
    assert history[0]["result"] == "ok" and history[0]["source"] == "hub"

    after_ng = ctx.mistakes.answer(mistake_id, "ng")
    assert after_ng.consecutive_ok == 0
    assert after_ng.next_review_on == today + timedelta(days=1)   # 1日に戻る


def test_three_correct_answers_in_a_row_means_mastered(ctx, sample_masters):
    mistake_id = ctx.mistakes.create(question_ref="p.52 問3", exam_id=sample_masters["exam_id"])
    for _ in range(3):
        mistake = ctx.mistakes.answer(mistake_id, "ok")
    assert mistake.mastery == "mastered"
    assert mistake.next_review_on is None
    assert ctx.mistakes.due() == []


def test_mastery_can_be_switched_by_hand(ctx, sample_masters):
    today = ctx.mistakes.today()
    mistake_id = ctx.mistakes.create(question_ref="p.52 問3", exam_id=sample_masters["exam_id"])
    ctx.mistakes.set_mastery(mistake_id, "mastered")
    assert ctx.mistakes.get(mistake_id).next_review_on is None

    ctx.mistakes.set_mastery(mistake_id, "reviewing")
    mistake = ctx.mistakes.get(mistake_id)
    assert mistake.mastery == "reviewing"
    assert mistake.next_review_on == today + timedelta(days=1)

    with pytest.raises(ValueError):
        ctx.mistakes.set_mastery(mistake_id, "とても苦手")


def test_answer_memo_can_be_added_later(ctx, sample_masters):
    """子機から届いた誤答に、母艦で正解・ポイントを書き足せる。"""
    ctx.transfer.import_package(
        {
            "format": "studylog-transfer", "kind": "up", "schemaVersion": 1,
            "packageId": "aaaaaaaa-0000-4000-8000-00000000000a",
            "createdAt": "2026-09-22T18:00:00+09:00",
            "deviceId": "de000001-0000-4000-8000-000000000001", "deviceName": "iPhone",
            "basedOnPackageId": None,
            "records": {
                "sessions": [], "reviewResults": [], "quotaStatus": [],
                "mistakes": [{
                    "id": "6f00000a-0000-4000-8000-00000000000a",
                    "createdAt": "2026-09-22T10:42:00+09:00",
                    "updatedAt": "2026-09-22T10:42:00+09:00",
                    "questionRef": "模試 問7", "memo": "代理権の消滅事由", "reason": None,
                    "deleted": False,
                }],
            },
            "includedIds": ["6f00000a-0000-4000-8000-00000000000a"],
        }
    )
    mistake_id = "6f00000a-0000-4000-8000-00000000000a"
    ctx.mistakes.update(mistake_id, {"answer_memo": "本人の死亡・破産・後見開始", "exam_id": sample_masters["exam_id"]})
    mistake = ctx.mistakes.get(mistake_id)
    assert mistake.answer_memo.startswith("本人の死亡")
    assert mistake.source == "satellite"   # どこから来たかは残る


def test_search_filters(ctx, sample_masters):
    exam = sample_masters["exam_id"]
    other = ctx.masters.create_exam("FP2級")
    first = ctx.mistakes.create(question_ref="p.52 問3", memo="取消権", exam_id=exam, reason="confusion")
    ctx.mistakes.create(question_ref="FP 問1", memo="係数", exam_id=other)
    ctx.mistakes.set_mastery(first, "mastered")

    assert len(ctx.mistakes.search(exam_id=exam)) == 1
    assert len(ctx.mistakes.search(mastery="mastered")) == 1
    assert len(ctx.mistakes.search(reason="confusion")) == 1
    assert len(ctx.mistakes.search(keyword="係数")) == 1
    assert len(ctx.mistakes.search(due_on=ctx.mistakes.today() + timedelta(days=1))) == 1  # 克服した分は出ない


def test_weak_ranking_and_reasons(ctx, sample_masters):
    exam = sample_masters["exam_id"]
    minpo = sample_masters["subject_id"]
    gyosei = ctx.masters.create_subject(exam, "行政法")
    for _ in range(3):
        ctx.mistakes.create(question_ref="民法", exam_id=exam, subject_id=minpo, reason="knowledge")
    weak = ctx.mistakes.create(question_ref="行政法", exam_id=exam, subject_id=gyosei, reason="careless")
    ctx.mistakes.set_mastery(weak, "mastered")

    ranking = ctx.mistakes.weak_ranking("subject", exam)
    assert [(row.label, row.total, row.unmastered) for row in ranking] == [
        ("民法", 3, 3), ("行政法", 1, 0),
    ]
    assert ranking[1].mastered == 1

    reasons = dict(ctx.mistakes.reason_breakdown(exam))
    assert reasons == {"knowledge": 3, "careless": 1}

    counts = ctx.mistakes.counts(exam)
    assert counts == {"total": 4, "unmastered": 3, "mastered": 1, "due": 0}


# --- 課題 -------------------------------------------------------------------

def test_task_crud_and_order(ctx, sample_masters):
    today = ctx.tasks.today()
    later = ctx.tasks.create(content="模試の申し込み", due_on=today + timedelta(days=5))
    soon = ctx.tasks.create(content="教材を買う", due_on=today + timedelta(days=1), priority=1)
    someday = ctx.tasks.create(content="いつか法改正を確認")

    rows = ctx.tasks.list()
    assert [row["id"] for row in rows] == [soon, later, someday]  # 期限の近い順、期限なしは最後

    ctx.tasks.set_done(soon, True)
    rows = ctx.tasks.list()
    assert rows[-1]["id"] == soon and rows[-1]["done"] == 1        # 完了は下に回る
    assert [row["id"] for row in ctx.tasks.list(include_done=False)] == [later, someday]
    assert ctx.tasks.count_open() == 2

    ctx.tasks.update(later, {"content": "模試の申し込み（会場）"})
    assert ctx.tasks.list()[0]["content"] == "模試の申し込み（会場）"

    ctx.tasks.delete(later)
    assert len(ctx.tasks.list()) == 2


def test_task_validation(ctx):
    with pytest.raises(ValueError, match="内容"):
        ctx.tasks.create(content="  ")
    with pytest.raises(ValueError, match="優先度"):
        ctx.tasks.create(content="x", priority=9)


def test_due_soon_includes_overdue(ctx):
    today = ctx.tasks.today()
    overdue = ctx.tasks.create(content="期限切れ", due_on=today - timedelta(days=2))
    ctx.tasks.create(content="ずっと先", due_on=today + timedelta(days=30))
    rows = ctx.tasks.due_soon()
    assert [row["id"] for row in rows] == [overdue]


# --- 合格結果 ---------------------------------------------------------------

def test_recording_a_pass_updates_the_exam_and_returns_a_summary(ctx, sample_masters):
    exam = sample_masters["exam_id"]
    ctx.goals.set_exam_total_goal(exam, 100 * 3600)
    add_session(ctx, date(2026, 6, 1), 120, exam_id=exam, subject_id=sample_masters["subject_id"],
                material_id=sample_masters["material_id"])
    add_session(ctx, date(2026, 9, 1), 60, exam_id=exam, subject_id=sample_masters["subject_id"])
    mistake = ctx.mistakes.create(question_ref="p.1", exam_id=exam)
    ctx.mistakes.set_mastery(mistake, "mastered")

    sitting = ctx.results.add_sitting(exam, date(2026, 11, 8), "2026年度")
    summary = ctx.results.record_result(sitting, score=186, passed=True, memo="記述で稼げた")

    assert ctx.masters.exams.get(exam).status == "passed"
    assert summary is not None
    assert summary.total_seconds == 180 * 60
    assert summary.sessions == 2
    assert summary.study_days == 2
    assert (summary.first_day, summary.last_day) == (date(2026, 6, 1), date(2026, 9, 1))
    assert summary.span_days == 93
    assert summary.top_subject == ("民法", 180 * 60)
    assert summary.top_material[0] == "民法 問題集"
    assert (summary.mistakes_total, summary.mistakes_mastered) == (1, 1)
    assert summary.goal_ratio == pytest.approx(3 / 100)
    assert summary.average_per_study_day == 90 * 60


def test_recording_a_failure_sets_the_status_without_a_summary(ctx, sample_masters):
    exam = sample_masters["exam_id"]
    sitting = ctx.results.add_sitting(exam, date(2026, 11, 8))
    assert ctx.results.record_result(sitting, score=150, passed=False, memo="行政法が弱い") is None
    assert ctx.masters.exams.get(exam).status == "failed"

    stored = ctx.results.sittings_for(exam)[0]
    assert (stored.score, stored.passed, stored.memo) == (150, False, "行政法が弱い")


def test_achievements_list_keeps_passed_exams_even_when_archived(ctx, sample_masters):
    exam = sample_masters["exam_id"]
    sitting = ctx.results.add_sitting(exam, date(2025, 11, 9), "2025年度")
    ctx.results.record_result(sitting, score=190, passed=True, certificate_on=date(2026, 1, 20))
    ctx.masters.update_exam(exam, {"archived": 1})

    achievements = ctx.results.achievements()
    assert len(achievements) == 1
    achieved_exam, result = achievements[0]
    assert achieved_exam.name == "行政書士"
    assert result.certificate_on == date(2026, 1, 20)
    assert result.label == "2025年度"


def test_multiple_sittings_are_kept(ctx, sample_masters):
    exam = sample_masters["exam_id"]
    first = ctx.results.add_sitting(exam, date(2025, 11, 9), "2025年度")
    second = ctx.results.add_sitting(exam, date(2026, 11, 8), "2026年度")
    ctx.results.record_result(first, score=150, passed=False)
    ctx.results.record_result(second, score=190, passed=True)

    results = {row.label: row.passed for row in ctx.results.sittings_for(exam)}
    assert results == {"2025年度": False, "2026年度": True}
    assert len(ctx.results.achievements()) == 1


def test_summary_without_sessions(ctx, sample_masters):
    summary = ctx.results.summary(sample_masters["exam_id"])
    assert summary.total_seconds == 0
    assert summary.first_day is None
    assert summary.span_days == 0
    assert summary.top_subject is None
    assert summary.average_per_study_day == 0
