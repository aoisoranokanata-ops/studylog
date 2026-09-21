"""リポジトリの共通部分。SQLはこの層より外に出さない。"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from ..core import clock, ids


class BaseRepository:
    table: str = ""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # 列名はコード内の定数であり、利用者の入力は必ずプレースホルダで渡す
    def insert(self, values: Mapping[str, Any], *, record_id: str | None = None) -> str:
        now = clock.db_now()
        data: dict[str, Any] = dict(values)
        data.setdefault("id", record_id or ids.new_id())
        data.setdefault("created_at", now)
        data.setdefault("updated_at", now)
        columns = ", ".join(data)
        marks = ", ".join("?" * len(data))
        self.conn.execute(
            f"INSERT INTO {self.table} ({columns}) VALUES ({marks})", list(data.values())
        )
        return str(data["id"])

    def update(self, record_id: str, values: Mapping[str, Any], *, touch: bool = True) -> None:
        data: dict[str, Any] = dict(values)
        if touch:
            data["updated_at"] = clock.db_now()
        if not data:
            return
        assignments = ", ".join(f"{key} = ?" for key in data)
        self.conn.execute(
            f"UPDATE {self.table} SET {assignments} WHERE id = ?",
            [*data.values(), record_id],
        )

    def soft_delete(self, record_id: str) -> None:
        now = clock.db_now()
        self.conn.execute(
            f"UPDATE {self.table} SET deleted_at = ?, updated_at = ? WHERE id = ?",
            (now, now, record_id),
        )

    def restore(self, record_id: str) -> None:
        self.conn.execute(
            f"UPDATE {self.table} SET deleted_at = NULL, updated_at = ? WHERE id = ?",
            (clock.db_now(), record_id),
        )

    def hard_delete(self, record_id: str) -> None:
        self.conn.execute(f"DELETE FROM {self.table} WHERE id = ?", (record_id,))

    def row(self, record_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            f"SELECT * FROM {self.table} WHERE id = ?", (record_id,)
        ).fetchone()

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return list(self.conn.execute(sql, params).fetchall())

    def exists(self, record_id: str) -> bool:
        found = self.conn.execute(
            f"SELECT 1 FROM {self.table} WHERE id = ? AND deleted_at IS NULL", (record_id,)
        ).fetchone()
        return found is not None
