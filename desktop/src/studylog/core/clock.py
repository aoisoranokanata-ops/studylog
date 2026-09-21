"""日時の変換と、学習日・週の区切りの計算。

保存はすべてUTC（`2026-09-20T05:30:00Z` 形式の文字列）。
表示と転送パッケージへの書き出しはローカル時刻（`2026-09-20T14:30:00+09:00`）に変換する。
文字列がすべて同じ書式のUTCになるので、SQLiteの比較・並べ替え・`updatedAt` の新旧判定がそのまま使える。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

UTC = timezone.utc


# --- 生成と変換 -------------------------------------------------------------

def now_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def parse_iso(text: str) -> datetime:
    """ISO 8601（`Z` でもオフセット付きでも）を、タイムゾーン付きのdatetimeにする。"""
    value = text.strip()
    if value.endswith(("Z", "z")):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"タイムゾーンの無い日時は受け付けない: {text!r}")
    return parsed


def to_db(dt: datetime) -> str:
    """DBに保存する形（UTC・秒まで・末尾Z）。"""
    if dt.tzinfo is None:
        raise ValueError("タイムゾーンの無いdatetimeは保存できない")
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def from_db(text: str) -> datetime:
    return parse_iso(text)


def to_local(dt: datetime) -> datetime:
    """システムのローカル時刻に変換する（その日付時点の夏時間も正しく扱われる）。"""
    return dt.astimezone()


def to_transfer(dt: datetime) -> str:
    """転送パッケージに書き出す形（ローカル時刻＋オフセット）。"""
    return to_local(dt).replace(microsecond=0).isoformat()


def db_now() -> str:
    return to_db(now_utc())


# --- 学習日 -----------------------------------------------------------------

def study_date(dt: datetime, day_change_hour: int) -> date:
    """日付変更時刻を考慮した「学習日」。2:00 の記録は day_change_hour=4 なら前日になる。"""
    local = to_local(dt)
    return (local - timedelta(hours=day_change_hour)).date()


def study_date_str(dt: datetime, day_change_hour: int) -> str:
    return study_date(dt, day_change_hour).isoformat()


def day_bounds(day: date, day_change_hour: int) -> tuple[datetime, datetime]:
    """その学習日に属する時刻の範囲（UTC、開始以上・終了未満）。"""
    start_local = datetime.combine(day, time(hour=day_change_hour)).astimezone()
    end_local = datetime.combine(day + timedelta(days=1), time(hour=day_change_hour)).astimezone()
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


# --- 週 ---------------------------------------------------------------------

def week_start(day: date, week_starts_on: int = 1) -> date:
    """その日を含む週の開始日。week_starts_on は ISO-8601（1=月曜 … 7=日曜）。"""
    if not 1 <= week_starts_on <= 7:
        raise ValueError(f"week_starts_on は1〜7: {week_starts_on}")
    delta = (day.isoweekday() - week_starts_on) % 7
    return day - timedelta(days=delta)


def week_range(day: date, week_starts_on: int = 1) -> tuple[date, date]:
    """その日を含む週の [開始日, 終了日]（どちらも含む）。"""
    start = week_start(day, week_starts_on)
    return start, start + timedelta(days=6)


# --- 表示 -------------------------------------------------------------------

def format_hm(seconds: int) -> str:
    """5400 -> '1:30'。"""
    seconds = max(0, int(seconds))
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}"


def format_hms(seconds: int) -> str:
    """5400 -> '01:30:00'。計測中の表示用。"""
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def format_local(dt: datetime, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return to_local(dt).strftime(fmt)
