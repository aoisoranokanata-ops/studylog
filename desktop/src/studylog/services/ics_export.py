"""予定と試験日を .ics（iCalendar）に書き出す。

カレンダーアプリに読み込ませるためのもので、取り込みはしない。
時刻ありの予定は「フローティング時刻」（タイムゾーンを書かない）にする。
手元のカレンダーに入れる用途なので、端末の時刻そのままで読まれるほうが分かりやすい。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from ..core import clock
from ..domain.models import PlanOccurrence

PRODID = "-//StudyLog//JP"
DEFAULT_SECONDS = 30 * 60  # 予定時間が0のときの長さ


def escape(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold(line: str) -> list[str]:
    """1行75オクテットを超えたら折り返す（続きの行は空白で始める）。"""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return [line]
    parts: list[str] = []
    current = bytearray()
    for char in line:
        encoded = char.encode("utf-8")
        limit = 75 if not parts else 74  # 続きの行は先頭の空白の分だけ狭くする
        if len(current) + len(encoded) > limit:
            parts.append(current.decode("utf-8"))
            current = bytearray()
        current += encoded
    if current:
        parts.append(current.decode("utf-8"))
    return [parts[0]] + [" " + part for part in parts[1:]]


def _stamp(value: datetime) -> str:
    return value.astimezone(clock.UTC).strftime("%Y%m%dT%H%M%SZ")


def _local(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def _date(value: date) -> str:
    return value.strftime("%Y%m%d")


@dataclass(slots=True)
class Event:
    uid: str
    summary: str
    start: date | datetime
    end: date | datetime
    description: str = ""

    def lines(self, now: datetime) -> list[str]:
        lines = ["BEGIN:VEVENT", f"UID:{self.uid}", f"DTSTAMP:{_stamp(now)}"]
        if isinstance(self.start, datetime):
            lines.append(f"DTSTART:{_local(self.start)}")
            lines.append(f"DTEND:{_local(self.end)}")
        else:
            lines.append(f"DTSTART;VALUE=DATE:{_date(self.start)}")
            lines.append(f"DTEND;VALUE=DATE:{_date(self.end)}")
        lines.append(f"SUMMARY:{escape(self.summary)}")
        if self.description:
            lines.append(f"DESCRIPTION:{escape(self.description)}")
        lines.append("END:VEVENT")
        return lines


def plan_event(occurrence: PlanOccurrence, description: str = "") -> Event:
    plan = occurrence.plan
    uid = f"plan-{plan.id}-{occurrence.date.isoformat()}@studylog"
    if plan.time_of_day:
        hour, _, minute = plan.time_of_day.partition(":")
        start = datetime.combine(occurrence.date, time(int(hour), int(minute or 0)))
        end = start + timedelta(seconds=plan.planned_seconds or DEFAULT_SECONDS)
    else:
        start = occurrence.date
        end = occurrence.date + timedelta(days=1)
    return Event(uid=uid, summary=plan.title, start=start, end=end, description=description)


def exam_event(exam_id: str, name: str, exam_date: date) -> Event:
    return Event(
        uid=f"exam-{exam_id}@studylog",
        summary=f"{name} 試験日",
        start=exam_date,
        end=exam_date + timedelta(days=1),
    )


def build(events: list[Event], *, now: datetime | None = None) -> str:
    now = now or clock.now_utc()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:StudyLog",
    ]
    for event in events:
        lines.extend(event.lines(now))
    lines.append("END:VCALENDAR")

    folded: list[str] = []
    for line in lines:
        folded.extend(fold(line))
    return "\r\n".join(folded) + "\r\n"


def write(path: Path, events: list[Event], *, now: datetime | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # .ics は CRLF 固定なので、改行を変換させない
    path.write_text(build(events, now=now), encoding="utf-8", newline="")
    return path
