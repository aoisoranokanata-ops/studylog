"""バージョン番号付きのSQLファイルを順に適用する。

`migrations/0001_init.sql` のように、先頭4桁がバージョン。
適用済みのバージョンは `PRAGMA user_version` に持つ。
1ファイルを1トランザクションで適用するため、`executescript`（暗黙のCOMMITが入る）は使わず、
文単位に分割して実行する。
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

from .connection import set_user_version, user_version

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_NAME_RE = re.compile(r"^(\d{4})_.+\.sql$")


def discover(directory: Path | None = None) -> list[tuple[int, Path]]:
    directory = directory or MIGRATIONS_DIR
    found: list[tuple[int, Path]] = []
    for path in sorted(directory.glob("*.sql")):
        matched = _NAME_RE.match(path.name)
        if not matched:
            log.warning("マイグレーションの命名が不正なので無視する: %s", path.name)
            continue
        found.append((int(matched.group(1)), path))
    found.sort(key=lambda item: item[0])
    return found


def split_statements(sql: str) -> list[str]:
    """SQLを文に分ける。文字列リテラル内と `--` コメント内のセミコロンは区切りにしない。"""
    statements: list[str] = []
    buffer: list[str] = []
    in_string = False
    in_comment = False
    index = 0
    while index < len(sql):
        char = sql[index]
        nxt = sql[index + 1] if index + 1 < len(sql) else ""
        if in_comment:
            if char == "\n":
                in_comment = False
                buffer.append(char)
        elif in_string:
            buffer.append(char)
            if char == "'":
                if nxt == "'":  # エスケープされた '
                    buffer.append(nxt)
                    index += 1
                else:
                    in_string = False
        elif char == "-" and nxt == "-":
            in_comment = True
            index += 1
        elif char == "'":
            in_string = True
            buffer.append(char)
        elif char == ";":
            statements.append("".join(buffer).strip())
            buffer = []
        else:
            buffer.append(char)
        index += 1
    tail = "".join(buffer).strip()
    if tail:
        statements.append(tail)
    return [s for s in statements if s]


def pending(conn: sqlite3.Connection, directory: Path | None = None) -> list[tuple[int, Path]]:
    current = user_version(conn)
    return [item for item in discover(directory) if item[0] > current]


def migrate(conn: sqlite3.Connection, directory: Path | None = None) -> list[int]:
    """未適用のマイグレーションを適用し、適用したバージョンの一覧を返す。"""
    applied: list[int] = []
    for version, path in pending(conn, directory):
        log.info("マイグレーションを適用する: %s", path.name)
        statements = split_statements(path.read_text(encoding="utf-8"))
        conn.execute("BEGIN")
        try:
            for statement in statements:
                conn.execute(statement)
            set_user_version(conn, version)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            log.exception("マイグレーションに失敗した: %s", path.name)
            raise
        applied.append(version)
    return applied
