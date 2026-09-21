"""バックアップの窓口。起動時・終了時・取り込み前に呼ぶ。"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from ..db import backup
from .settings_service import SettingsService

log = logging.getLogger(__name__)


class BackupService:
    def __init__(
        self, conn: sqlite3.Connection, backup_dir: Path, settings: SettingsService
    ) -> None:
        self.conn = conn
        self.backup_dir = backup_dir
        self.settings = settings

    def create(self, tag: str = "manual") -> Path | None:
        try:
            path = backup.create(self.conn, self.backup_dir, tag)
        except sqlite3.Error:
            log.exception("バックアップに失敗した（処理は続行する）")
            return None
        backup.prune(self.backup_dir, self.settings.backup_generations)
        return path

    def on_startup(self) -> Path | None:
        return self.create("startup")

    def on_shutdown(self) -> Path | None:
        return self.create("shutdown")

    def before_import(self) -> Path | None:
        return self.create("import")

    def listing(self) -> list[Path]:
        return backup.listing(self.backup_dir)

    def restore(self, path: Path) -> None:
        self.create("before-restore")
        backup.restore(self.conn, path)
