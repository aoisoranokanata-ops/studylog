from __future__ import annotations

from pathlib import Path

import pytest

from studylog.db import backup, migrator
from studylog.db.connection import connect, transaction, user_version


def test_split_statements_ignores_semicolons_in_strings_and_comments():
    sql = """
    -- コメント内の ; は区切りではない
    CREATE TABLE t (a TEXT DEFAULT 'a;b');
    INSERT INTO t (a) VALUES ('x;y');
    """
    statements = migrator.split_statements(sql)
    assert len(statements) == 2
    assert statements[0].startswith("CREATE TABLE")
    assert "'a;b'" in statements[0]


def test_split_statements_handles_escaped_quote():
    statements = migrator.split_statements("INSERT INTO t VALUES ('it''s');")
    assert statements == ["INSERT INTO t VALUES ('it''s')"]


def test_migrate_creates_all_tables(tmp_path):
    conn = connect(tmp_path / "t.db")
    applied = migrator.migrate(conn)
    assert applied == [1, 2]
    assert user_version(conn) == len(migrator.discover())
    names = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    for table in (
        "exams", "exam_sittings", "materials", "subjects", "sessions", "timer_state",
        "plans", "quotas", "mistakes", "review_results", "tasks", "weekly_goals",
        "devices", "imported_packages", "transfer_log", "settings", "plan_exceptions",
    ):
        assert table in names
    conn.close()


def test_later_migration_applies_to_an_existing_database(tmp_path):
    """0001 までしか当たっていないDBを開いたら、0002 だけが追加で当たる。"""
    path = tmp_path / "t.db"
    conn = connect(path)
    only_first = tmp_path / "first"
    only_first.mkdir()
    first = next(item for item in migrator.discover() if item[0] == 1)[1]
    (only_first / first.name).write_text(first.read_text(encoding="utf-8"), encoding="utf-8")
    assert migrator.migrate(conn, only_first) == [1]
    assert user_version(conn) == 1

    # 本来のフォルダで開き直すと、続きから当たる
    applied = migrator.migrate(conn)
    assert applied == [2]
    names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master")}
    assert "plan_exceptions" in names
    assert "sessions" in names  # 既存の表はそのまま
    conn.close()


def test_migrate_is_idempotent(tmp_path):
    conn = connect(tmp_path / "t.db")
    migrator.migrate(conn)
    assert migrator.migrate(conn) == []
    conn.close()


def test_migration_rolls_back_on_failure(tmp_path):
    bad = tmp_path / "migrations"
    bad.mkdir()
    (bad / "0001_broken.sql").write_text(
        "CREATE TABLE ok (id TEXT);\nCREATE TABLE ; -- 構文エラー\n", encoding="utf-8"
    )
    conn = connect(tmp_path / "t.db")
    with pytest.raises(Exception):
        migrator.migrate(conn, bad)
    assert user_version(conn) == 0
    names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master")}
    assert "ok" not in names
    conn.close()


def test_transaction_rolls_back(tmp_path):
    conn = connect(tmp_path / "t.db")
    migrator.migrate(conn)
    with pytest.raises(RuntimeError):
        with transaction(conn):
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES ('a', 'b', 'now')"
            )
            raise RuntimeError("やめる")
    assert conn.execute("SELECT COUNT(*) AS n FROM settings").fetchone()["n"] == 0
    conn.close()


def test_backup_create_prune_and_restore(tmp_path):
    db = tmp_path / "t.db"
    backups = tmp_path / "backups"
    conn = connect(db)
    migrator.migrate(conn)
    conn.execute("INSERT INTO settings (key, value, updated_at) VALUES ('k', 'before', 'now')")

    first = backup.create(conn, backups, "startup")
    assert first.exists()

    conn.execute("UPDATE settings SET value = 'after' WHERE key = 'k'")
    assert conn.execute("SELECT value FROM settings WHERE key = 'k'").fetchone()[0] == "after"

    backup.restore(conn, first)
    assert conn.execute("SELECT value FROM settings WHERE key = 'k'").fetchone()[0] == "before"

    for index in range(5):
        path = backups / f"studylog-2026010{index}-000000-manual.db"
        path.write_bytes(b"dummy")
    removed = backup.prune(backups, keep=3)
    assert len(backup.listing(backups)) == 3
    assert removed
    conn.close()
