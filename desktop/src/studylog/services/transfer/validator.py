"""転送パッケージの検証（転送仕様書 第2章・付録B）。

検証の順序：形式 → kind → schemaVersion → JSON Schema → アプリ側の制約。
schemaVersion をスキーマより先に見るのは、「アプリの更新が必要」と案内するため。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from ... import config
from ...core import clock

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


class TransferError(ValueError):
    """パッケージを受け付けられない。"""


class NeedsUpdateError(TransferError):
    """受信側より新しい schemaVersion だった。"""


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)

    def raise_if_bad(self) -> None:
        if not self.ok:
            raise TransferError("\n".join(self.errors))


@lru_cache(maxsize=4)
def _validator(kind: str) -> Draft202012Validator:
    path = SCHEMA_DIR / f"{kind}.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def check_header(package: object, expected_kind: str) -> None:
    if not isinstance(package, dict):
        raise TransferError("JSONの形が違います（オブジェクトではありません）")
    if package.get("format") != "studylog-transfer":
        raise TransferError("StudyLogの転送ファイルではありません")
    if package.get("kind") != expected_kind:
        raise TransferError(
            f"種類が違います（{expected_kind} を期待しましたが {package.get('kind')!r} でした）"
        )
    version = package.get("schemaVersion")
    if not isinstance(version, int):
        raise TransferError("schemaVersion がありません")
    if version > config.SCHEMA_VERSION:
        raise NeedsUpdateError(
            f"このファイルは新しい形式です（schemaVersion {version}）。アプリの更新が必要です。"
        )


def check_schema(package: dict, kind: str) -> list[str]:
    errors = []
    for error in sorted(_validator(kind).iter_errors(package), key=lambda e: list(e.path)):
        location = "/".join(str(part) for part in error.path) or "(全体)"
        errors.append(f"{location}: {error.message}")
    return errors


# --- アプリ側の制約（仕様書 付録B） ----------------------------------------

def _range_errors(label: str, value: object) -> list[str]:
    if not isinstance(value, dict):
        return []
    start, end = value.get("from"), value.get("to")
    if isinstance(start, int) and isinstance(end, int) and start > end:
        return [f"{label}: 範囲の開始({start})が終了({end})より後です"]
    return []


def check_up_rules(package: dict) -> list[str]:
    errors: list[str] = []
    records = package.get("records", {})

    ids: list[str] = []
    for name in ("sessions", "mistakes", "reviewResults", "quotaStatus"):
        for item in records.get(name, []):
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                ids.append(item["id"])

    included = package.get("includedIds", [])
    missing = sorted(set(ids) - set(included))
    extra = sorted(set(included) - set(ids))
    if missing:
        errors.append(f"includedIds に足りないID: {', '.join(missing[:5])}")
    if extra:
        errors.append(f"includedIds に余分なID: {', '.join(extra[:5])}")
    if len(ids) != len(set(ids)):
        errors.append("records の中に重複したIDがあります")

    for session in records.get("sessions", []):
        if not isinstance(session, dict):
            continue
        label = f"sessions/{session.get('id', '?')[:8]}"
        errors.extend(_range_errors(label, session.get("range")))
        try:
            started = clock.parse_iso(session["startedAt"])
            ended = clock.parse_iso(session["endedAt"])
        except (KeyError, ValueError):
            continue
        if ended < started:
            errors.append(f"{label}: 終了時刻が開始時刻より前です")
            continue
        span = int((ended - started).total_seconds())
        active = session.get("activeSeconds")
        if isinstance(active, int) and active > span:
            errors.append(f"{label}: 勉強時間({active}秒)が開始〜終了({span}秒)を超えています")
        correct, attempted = session.get("correct"), session.get("attempted")
        if isinstance(correct, int) and isinstance(attempted, int) and correct > attempted:
            errors.append(f"{label}: 正答数({correct})が解答数({attempted})を超えています")

    return errors


def check_down_rules(package: dict) -> list[str]:
    errors: list[str] = []
    for quota in package.get("quotas", []):
        if isinstance(quota, dict):
            errors.extend(_range_errors(f"quotas/{quota.get('id', '?')[:8]}", quota.get("range")))
    if package.get("variant") == "lite" and package.get("masters"):
        errors.append("lite なのに masters が入っています")
    return errors


def validate(package: object, kind: str) -> ValidationResult:
    """ヘッダ→スキーマ→アプリ制約の順に確かめる。ヘッダ違反は例外で返す。"""
    check_header(package, kind)
    assert isinstance(package, dict)  # check_header で確認済み

    errors = check_schema(package, kind)
    if not errors:
        errors = check_up_rules(package) if kind == "up" else check_down_rules(package)
    return ValidationResult(ok=not errors, errors=errors)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return clock.parse_iso(value)
    except ValueError:
        return None
