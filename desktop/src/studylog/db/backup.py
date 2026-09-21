"""SQLiteのbackup APIによるバックアップと復元。"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

FILENAME_PATTERN = "studylog-*.db"


def _timestamp() -> str:
    # 同じ秒に2回作っても上書きしないよう、ミリ秒まで入れる
    return datetime.now().strftime("%Y%m%d-%H%M%S%f")[:-3]


def create(conn: sqlite3.Connection, backup_dir: Path, tag: str = "manual") -> Path:
    """現在のDBをバックアップし、作ったファイルのパスを返す。"""
    backup_dir.mkdir(parents=True, exist_ok=True)
    safe_tag = "".join(ch for ch in tag if ch.isalnum() or ch in "-_") or "manual"
    path = backup_dir / f"studylog-{_timestamp()}-{safe_tag}.db"
    dest = sqlite3.connect(str(path))
    try:
        conn.backup(dest)
    finally:
        dest.close()
    log.info("バックアップを作成した: %s", path.name)
    return path


def listing(backup_dir: Path) -> list[Path]:
    """新しい順のバックアップ一覧。"""
    if not backup_dir.exists():
        return []
    return sorted(backup_dir.glob(FILENAME_PATTERN), key=lambda p: p.name, reverse=True)


def prune(backup_dir: Path, keep: int) -> list[Path]:
    """古い世代を削除し、削除したものを返す。"""
    if keep < 1:
        return []
    removed: list[Path] = []
    for path in listing(backup_dir)[keep:]:
        try:
            path.unlink()
            removed.append(path)
        except OSError:
            log.exception("バックアップを削除できなかった: %s", path)
    if removed:
        log.info("古いバックアップを%d件削除した", len(removed))
    return removed


def restore(conn: sqlite3.Connection, backup_path: Path) -> None:
    """バックアップの内容を、いま開いているDBに書き戻す。

    backup APIで上書きするため、WALのファイルを直接触らずに済む。
    呼び出し側は、復元後にアプリを再起動して画面を作り直すこと。
    """
    if not backup_path.exists():
        raise FileNotFoundError(backup_path)
    source = sqlite3.connect(str(backup_path))
    try:
        source.backup(conn)
    finally:
        source.close()
    log.info("バックアップから復元した: %s", backup_path.name)
