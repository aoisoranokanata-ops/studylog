from __future__ import annotations

from datetime import date, timedelta

import pytest

from studylog.core import clock

from .conftest import jst, local


def test_parse_iso_accepts_z_and_offset():
    assert clock.parse_iso("2026-09-20T05:30:00Z") == clock.parse_iso("2026-09-20T14:30:00+09:00")


def test_parse_iso_rejects_naive():
    with pytest.raises(ValueError):
        clock.parse_iso("2026-09-20T14:30:00")


def test_to_db_normalizes_to_utc_with_z():
    assert clock.to_db(jst(2026, 9, 20, 14, 30)) == "2026-09-20T05:30:00Z"


def test_db_roundtrip():
    original = jst(2026, 9, 20, 14, 30)
    assert clock.from_db(clock.to_db(original)) == original


def test_to_transfer_uses_local_offset():
    text = clock.to_transfer(clock.parse_iso("2026-09-20T05:30:00Z"))
    assert clock.parse_iso(text) == clock.parse_iso("2026-09-20T05:30:00Z")
    assert text.endswith(("+00:00", "+09:00")) or "+" in text or "-" in text[10:]


@pytest.mark.parametrize(
    ("hour", "day_change_hour", "expected"),
    [
        (14, 4, date(2026, 9, 20)),   # 昼はその日
        (2, 4, date(2026, 9, 19)),    # 深夜2時は前日
        (4, 4, date(2026, 9, 20)),    # 境界ちょうどは当日
        (3, 0, date(2026, 9, 20)),    # 日付変更時刻0なら暦どおり
    ],
)
def test_study_date(hour, day_change_hour, expected):
    assert clock.study_date(local(2026, 9, 20, hour), day_change_hour) == expected


def test_day_bounds_covers_exactly_one_day():
    start, end = clock.day_bounds(date(2026, 9, 20), 4)
    assert end - start == timedelta(days=1)
    assert clock.study_date(start, 4) == date(2026, 9, 20)
    assert clock.study_date(end - timedelta(seconds=1), 4) == date(2026, 9, 20)
    assert clock.study_date(end, 4) == date(2026, 9, 21)


def test_week_start_monday():
    # 2026-09-20 は日曜
    assert date(2026, 9, 20).isoweekday() == 7
    assert clock.week_start(date(2026, 9, 20), 1) == date(2026, 9, 14)
    assert clock.week_start(date(2026, 9, 14), 1) == date(2026, 9, 14)


def test_week_start_sunday():
    assert clock.week_start(date(2026, 9, 20), 7) == date(2026, 9, 20)
    assert clock.week_start(date(2026, 9, 19), 7) == date(2026, 9, 13)


def test_week_range_is_seven_days():
    start, end = clock.week_range(date(2026, 9, 20), 1)
    assert (end - start).days == 6


def test_week_start_rejects_out_of_range():
    with pytest.raises(ValueError):
        clock.week_start(date(2026, 9, 20), 0)


def test_formats():
    assert clock.format_hm(5400) == "1:30"
    assert clock.format_hm(0) == "0:00"
    assert clock.format_hms(3661) == "01:01:01"
