"""転送（フェーズ2）のテスト。仕様書のサンプルをそのまま受け入れ条件として使う。"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from studylog.core import clock
from studylog.services.transfer import codec, validator
from studylog.services.transfer.service import sanitize_device_name

SPEC_DIR = Path(__file__).resolve().parents[2] / "spec"
EXAMPLES = SPEC_DIR / "examples"

# サンプルが使っているマスタのID（母艦側にも同じIDで用意して「既知のマスタ」を作る）
EXAM_GYOSEI = "e0000001-0000-4000-8000-000000000001"
EXAM_FP = "e0000002-0000-4000-8000-000000000002"
MATERIAL_DRILL = "3a000001-0000-4000-8000-000000000001"
MATERIAL_TEXT = "3a000002-0000-4000-8000-000000000002"
SUBJECT_MINPO = "5b000001-0000-4000-8000-000000000001"
SUBJECT_SOSOKU = "5b000002-0000-4000-8000-000000000002"
SUBJECT_GYOSEI = "5b000003-0000-4000-8000-000000000003"
QUOTA_1 = "9c000001-0000-4000-8000-000000000001"
QUOTA_3 = "9c000003-0000-4000-8000-000000000003"
MISTAKE_1 = "7d000001-0000-4000-8000-000000000001"
SESSION_1 = "4e000001-0000-4000-8000-000000000001"
SESSION_2 = "4e000002-0000-4000-8000-000000000002"
SESSION_UNCLASSIFIED = "4e000005-0000-4000-8000-000000000005"
SESSION_UNKNOWN_EXAM = "4e000006-0000-4000-8000-000000000006"


def load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture
def spec_masters(ctx):
    """サンプルと同じIDでマスタとノルマ・誤答を用意する。"""
    ctx.masters.exams.insert({"name": "行政書士", "color": "#2f6f4f"}, record_id=EXAM_GYOSEI)
    ctx.masters.exams.insert({"name": "FP2級", "color": "#8a5a2b"}, record_id=EXAM_FP)
    ctx.masters.set_exam_date(EXAM_GYOSEI, "2026-11-08")
    ctx.masters.materials.insert(
        {"exam_id": EXAM_GYOSEI, "name": "民法 問題集", "type": "drill", "unit_label": "問", "total": 480},
        record_id=MATERIAL_DRILL,
    )
    ctx.masters.materials.insert(
        {"exam_id": EXAM_GYOSEI, "name": "合格テキスト", "type": "text", "unit_label": "ページ", "total": 640},
        record_id=MATERIAL_TEXT,
    )
    ctx.masters.subjects.insert({"exam_id": EXAM_GYOSEI, "name": "民法"}, record_id=SUBJECT_MINPO)
    ctx.masters.subjects.insert(
        {"exam_id": EXAM_GYOSEI, "name": "総則", "parent_id": SUBJECT_MINPO}, record_id=SUBJECT_SOSOKU
    )
    ctx.masters.subjects.insert({"exam_id": EXAM_GYOSEI, "name": "行政法"}, record_id=SUBJECT_GYOSEI)

    ctx.quota_repo.insert(
        {
            "date": "2026-09-20",
            "sort_order": 1,
            "exam_id": EXAM_GYOSEI,
            "material_id": MATERIAL_DRILL,
            "subject_id": SUBJECT_SOSOKU,
            "title": "民法総則 問題集 p.40-65",
            "target_seconds": 5400,
        },
        record_id=QUOTA_1,
    )
    ctx.quota_repo.insert(
        {
            "date": "2026-09-20",
            "sort_order": 3,
            "exam_id": EXAM_FP,
            "title": "FP 過去問 1年分",
            "target_seconds": 1800,
        },
        record_id=QUOTA_3,
    )
    ctx.mistake_repo.insert(
        {
            "exam_id": EXAM_GYOSEI,
            "material_id": MATERIAL_DRILL,
            "subject_id": SUBJECT_SOSOKU,
            "question_ref": "p.52 問3",
            "memo": "制限行為能力者の取消権の期間",
            "next_review_on": "2026-09-20",
        },
        record_id=MISTAKE_1,
    )
    return {"exam": EXAM_GYOSEI, "material": MATERIAL_DRILL, "subject": SUBJECT_SOSOKU}


# --- スキーマの同期 ---------------------------------------------------------

def test_packaged_schemas_match_spec():
    """EXEに同梱するスキーマが spec/ とずれていないこと。"""
    from studylog.services.transfer.validator import SCHEMA_DIR

    for name in ("down.schema.json", "up.schema.json"):
        packaged = (SCHEMA_DIR / name).read_text(encoding="utf-8")
        original = (SPEC_DIR / "schemas" / name).read_text(encoding="utf-8")
        assert packaged == original, f"{name} が spec/schemas と違います"


# --- codec ------------------------------------------------------------------

def test_codec_roundtrip():
    package = load("down-02-lite-valid.json")
    text = codec.encode(package)
    assert text.startswith("SL1:")
    assert codec.decode(text) == package


def test_codec_compresses_well_enough_for_qr():
    text = codec.encode(load("down-02-lite-valid.json"))
    assert codec.fits_in_qr(text)
    assert codec.byte_length(text) == len(text.encode("utf-8"))


def test_codec_rejects_newer_version():
    text = codec.encode(load("down-02-lite-valid.json"), version=2)
    assert text.startswith("SL2:")
    with pytest.raises(codec.CodecError, match="更新が必要"):
        codec.decode(text)


@pytest.mark.parametrize("text", ["ただの文字列", "SL1:", "SL1:!!!!", "SLx:abc"])
def test_codec_rejects_broken_text(text):
    with pytest.raises(codec.CodecError):
        codec.decode(text)


def test_full_package_is_too_big_for_qr(ctx, spec_masters):
    """full はQRに載らない想定。載らないことを検知できること。"""
    for index in range(40):
        ctx.quotas.create(
            day=date(2026, 9, 20),
            title=f"ノルマ{index} " + "あ" * 30,
            target_seconds=3600,
            exam_id=EXAM_GYOSEI,
            material_id=MATERIAL_DRILL,
            note="とても長い補足" * 10,
        )
    package = ctx.transfer.build_down(date(2026, 9, 20), variant="full")
    assert not codec.fits_in_qr(codec.encode(package))


# --- 仕様書サンプルの検証 ---------------------------------------------------

@pytest.mark.parametrize(
    "name",
    [path.name for path in sorted(EXAMPLES.glob("*-valid.json"))],
)
def test_spec_valid_examples_pass(name):
    package = load(name)
    result = validator.validate(package, package["kind"])
    assert result.ok, result.errors


def test_future_version_example_asks_for_update():
    with pytest.raises(validator.NeedsUpdateError, match="更新が必要"):
        validator.validate(load("invalid-down-01-future-version.json"), "down")


@pytest.mark.parametrize(
    "name",
    [
        "invalid-down-02-missing-required.json",
        "invalid-down-03-bad-formats.json",
        "invalid-up-01-type-violation.json",
        "invalid-up-02-unclassified-conflict.json",
        "invalid-up-03-app-level-checks.json",
    ],
)
def test_spec_invalid_examples_are_rejected(name):
    package = load(name)
    result = validator.validate(package, package["kind"])
    assert not result.ok
    assert result.errors


def test_app_level_check_catches_included_ids_mismatch():
    result = validator.validate(load("invalid-up-03-app-level-checks.json"), "up")
    joined = "\n".join(result.errors)
    assert "includedIds" in joined
    assert "範囲" in joined
    assert "勉強時間" in joined
    assert "正答数" in joined


# --- 取り込み ---------------------------------------------------------------

def test_import_up_example(ctx, spec_masters):
    result = ctx.transfer.import_package(load("up-01-normal-valid.json"))
    assert result.added == 4  # セッション2・誤答1・復習結果1
    assert result.unclassified == 0

    session = ctx.sessions.get(SESSION_1)
    assert session is not None
    assert session.active_seconds == 6300
    assert session.source == "satellite"
    assert session.exam_id == EXAM_GYOSEI
    assert session.study_date == date(2026, 9, 20)
    assert ctx.mistake_repo.get("6f000001-0000-4000-8000-000000000001") is not None


def test_import_is_idempotent(ctx, spec_masters):
    package = load("up-01-normal-valid.json")
    first = ctx.transfer.import_package(package)
    before = ctx.session_repo.count()

    second = ctx.transfer.import_package(package)
    assert ctx.session_repo.count() == before
    assert second.added == 0
    assert second.updated == 0
    assert second.skipped == first.total
    assert second.already_imported is True


def test_resend_updates_only_newer_records(ctx, spec_masters):
    ctx.transfer.import_package(load("up-01-normal-valid.json"))
    result = ctx.transfer.import_package(load("up-02-resend-valid.json"))

    # 4e000002 だけ updatedAt が新しい。ほかは変化なし
    assert result.updated >= 1
    session = ctx.sessions.get(SESSION_2)
    assert session.range_to == 226
    assert session.focus == 3


def test_hub_edit_is_not_overwritten_by_older_data(ctx, spec_masters):
    ctx.transfer.import_package(load("up-01-normal-valid.json"))
    ctx.sessions.update(SESSION_1, {"memo": "母艦で直したメモ"})

    result = ctx.transfer.import_package(load("up-02-resend-valid.json"))

    assert ctx.sessions.get(SESSION_1).memo == "母艦で直したメモ"
    assert result.skipped >= 1


def test_unknown_masters_become_unclassified(ctx, spec_masters):
    ctx.transfer.import_package(load("up-01-normal-valid.json"))
    ctx.transfer.import_package(load("up-02-resend-valid.json"))
    result = ctx.transfer.import_package(load("up-03-unclassified-valid.json"))

    assert result.unclassified >= 2
    unclassified = ctx.sessions.get(SESSION_UNCLASSIFIED)
    assert unclassified.unclassified is True
    assert unclassified.exam_id is None

    unknown = ctx.sessions.get(SESSION_UNKNOWN_EXAM)
    assert unknown.unclassified is True
    assert unknown.exam_id is None


def test_deleted_record_is_marked_deleted(ctx, spec_masters):
    ctx.transfer.import_package(load("up-02-resend-valid.json"))
    assert ctx.sessions.get("4e000004-0000-4000-8000-000000000004") is not None

    ctx.transfer.import_package(load("up-03-unclassified-valid.json"))
    assert ctx.sessions.get("4e000004-0000-4000-8000-000000000004") is None


def test_quota_status_is_applied_and_newer_wins(ctx, spec_masters):
    ctx.transfer.import_package(load("up-01-normal-valid.json"))
    assert ctx.quotas.get(QUOTA_1).status == "done"
    assert ctx.quotas.get(QUOTA_3).status == "skipped"

    # 同じ内容を再送しても変わらない
    ctx.transfer.import_package(load("up-02-resend-valid.json"))
    assert ctx.quotas.get(QUOTA_1).status == "done"


def test_review_result_moves_the_schedule(ctx, spec_masters):
    before = ctx.mistake_repo.get(MISTAKE_1)
    ctx.transfer.import_package(load("up-01-normal-valid.json"))
    after = ctx.mistake_repo.get(MISTAKE_1)

    assert after.consecutive_ok == before.consecutive_ok + 1
    assert after.review_stage == 1
    assert after.next_review_on == date(2026, 9, 20) + timedelta(days=3)


def test_unknown_mistake_id_in_review_result_is_accepted(ctx, spec_masters):
    package = load("up-01-normal-valid.json")
    package["records"]["reviewResults"][0]["mistakeId"] = "7d00000f-0000-4000-8000-00000000000f"
    result = ctx.transfer.import_package(package)
    assert result.added >= 3  # 拒否されない


def test_import_rejects_invalid_package(ctx, spec_masters):
    with pytest.raises(validator.TransferError):
        ctx.transfer.import_package(load("invalid-up-01-type-violation.json"))


def test_acks_include_imported_packages(ctx, spec_masters):
    ctx.transfer.import_package(load("up-01-normal-valid.json"))
    package = ctx.transfer.build_down(date(2026, 9, 21), variant="lite")
    assert "c0000001-0000-4000-8000-000000000001" in package["acks"]


# --- 下り -------------------------------------------------------------------

def test_built_down_package_is_valid(ctx, spec_masters):
    package = ctx.transfer.build_down(date(2026, 9, 20), variant="full")
    validator.validate(package, "down").raise_if_bad()

    assert package["variant"] == "full"
    assert len(package["quotas"]) == 2
    exams = {exam["id"]: exam for exam in package["masters"]["exams"]}
    assert exams[EXAM_GYOSEI]["examDate"] == "2026-11-08"
    assert exams[EXAM_FP]["examDate"] is None
    assert package["summary"]["countdowns"][0]["daysLeft"] == (
        date(2026, 11, 8) - date(2026, 9, 20)
    ).days
    assert package["reviews"][0]["mistakeId"] == MISTAKE_1
    assert package["quotas"][0]["labels"]["subject"] == "民法 / 総則"


def test_lite_package_has_no_masters(ctx, spec_masters):
    package = ctx.transfer.build_down(date(2026, 9, 20), variant="lite")
    validator.validate(package, "down").raise_if_bad()
    assert "masters" not in package
    assert codec.fits_in_qr(codec.encode(package))


def test_reviews_can_be_left_out(ctx, spec_masters):
    package = ctx.transfer.build_down(date(2026, 9, 20), variant="lite", include_reviews=False)
    assert "reviews" not in package


def test_save_down_writes_outbox_and_marks_sent(ctx, spec_masters, tmp_path):
    package = ctx.transfer.build_down(date(2026, 9, 20), variant="full")
    written = ctx.transfer.save_down(package, tmp_path / "手元.json")

    assert len(written) == 2
    assert written[0].parent.name == "outbox"
    assert written[0].name.startswith("studylog-down-")
    assert written[0].name.endswith(f"{package['packageId'][:8]}.json")
    assert json.loads(written[1].read_text(encoding="utf-8"))["packageId"] == package["packageId"]
    assert ctx.quotas.get(QUOTA_1).sent_at is not None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("iPhone", "iPhone"),
        ("iPhone 12/Pro", "iPhone_12_Pro"),
        ("かなカナ漢字", "かなカナ漢字"),
        ("", "device"),
        ("////", "____"),
        ("あ" * 40, "あ" * 20),
    ],
)
def test_sanitize_device_name(raw, expected):
    assert sanitize_device_name(raw) == expected


# --- 同期フォルダ -----------------------------------------------------------

def test_scan_inbox_imports_and_moves_files(ctx, spec_masters):
    folders = ctx.transfer.ensure_sync_dirs()
    (folders["inbox"] / "studylog-up-iPhone-20260920-1830-c0000001.json").write_text(
        json.dumps(load("up-01-normal-valid.json"), ensure_ascii=False), encoding="utf-8"
    )
    (folders["inbox"] / "壊れている.json").write_text("{これはJSONではない", encoding="utf-8")

    results = ctx.transfer.scan_inbox()

    assert len(results) == 1
    assert results[0].added == 4
    assert list(folders["inbox"].glob("*.json")) == []
    assert len(list(folders["processed"].glob("*.json"))) == 1
    assert len(list(folders["rejected"].glob("*.json"))) == 1


def test_rejected_file_is_logged_with_reason(ctx, spec_masters):
    folders = ctx.transfer.ensure_sync_dirs()
    path = folders["inbox"] / "だめなやつ.json"
    path.write_text(
        json.dumps(load("invalid-up-02-unclassified-conflict.json"), ensure_ascii=False),
        encoding="utf-8",
    )
    ctx.transfer.scan_inbox()

    history = ctx.transfer.history()
    rejected = [row for row in history if row["result"] == "rejected"]
    assert rejected and "だめなやつ.json" in rejected[0]["message"]
    assert (folders["rejected"] / "だめなやつ.json").exists()


def test_history_records_both_directions(ctx, spec_masters, tmp_path):
    ctx.transfer.save_down(ctx.transfer.build_down(date(2026, 9, 20)))
    ctx.transfer.import_package(load("up-01-normal-valid.json"))

    directions = {row["direction"] for row in ctx.transfer.history()}
    assert directions == {"down", "up"}


def test_device_is_remembered(ctx, spec_masters):
    ctx.transfer.import_package(load("up-01-normal-valid.json"))
    devices = ctx.transfer.device_list()
    assert len(devices) == 1
    assert devices[0]["name"] == "iPhone"
    assert devices[0]["last_package_id"] == "c0000001-0000-4000-8000-000000000001"


def test_backup_is_taken_before_import(ctx, spec_masters):
    before = len(ctx.backups.listing())
    ctx.transfer.import_package(load("up-01-normal-valid.json"))
    assert len(ctx.backups.listing()) == before + 1


def test_import_advances_material_progress(ctx, spec_masters):
    """子機で進めた範囲を、母艦の参考書の現在位置にも反映する。"""
    assert ctx.masters.materials.get(MATERIAL_DRILL).current == 0
    ctx.transfer.import_package(load("up-01-normal-valid.json"))
    assert ctx.masters.materials.get(MATERIAL_DRILL).current == 65
