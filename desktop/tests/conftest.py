from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from studylog import config
from studylog.context import AppContext

JST = timezone(timedelta(hours=9))


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    """使い捨てのデータフォルダでアプリ一式を開く。"""
    monkeypatch.setenv(config.ENV_DATA_DIR, str(tmp_path))
    context = AppContext.open(backup_on_start=False)
    yield context
    context.close(backup_on_exit=False)


@pytest.fixture
def sample_masters(ctx):
    exam_id = ctx.masters.create_exam("行政書士", "#2f6f4f")
    material_id = ctx.masters.create_material(exam_id, "民法 問題集", type="drill", unit_label="問", total=480)
    subject_id = ctx.masters.create_subject(exam_id, "民法")
    return {"exam_id": exam_id, "material_id": material_id, "subject_id": subject_id}


def jst(year, month, day, hour=0, minute=0, second=0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=JST)


def local(year, month, day, hour=0, minute=0, second=0) -> datetime:
    """その時刻をシステムのローカル時刻として解釈する（テストをタイムゾーンに依存させない）。"""
    return datetime(year, month, day, hour, minute, second).astimezone()
