"""アプリ全体で持ち回る依存の束。

UIのモジュールはこの AppContext だけを受け取り、SQLには直接触らない。
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .db import migrator
from .db.connection import connect
from .repositories.goals import WeeklyGoalRepository
from .repositories.masters import (
    ExamRepository,
    ExamSittingRepository,
    MaterialRepository,
    SubjectRepository,
)
from .repositories.mistakes import MistakeRepository, ReviewResultRepository
from .repositories.quotas import QuotaRepository
from .repositories.sessions import SessionRepository
from .repositories.settings import SettingsRepository
from .repositories.tasks import TaskRepository
from .repositories.timer import TimerRepository
from .repositories.transfer import (
    DeviceRepository,
    ImportedPackageRepository,
    TransferLogRepository,
)
from .services.backup_service import BackupService
from .services.goal_service import GoalService
from .services.master_service import MasterService
from .services.quota_service import QuotaService
from .services.review_service import ReviewService
from .services.session_service import SessionService
from .services.settings_service import SettingsService
from .services.stats_service import StatsService
from .services.timer_service import TimerService
from .services.transfer.down_builder import DownBuilder
from .services.transfer.service import TransferService
from .services.transfer.up_importer import UpImporter

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    conn: sqlite3.Connection
    db_path: Path
    settings: SettingsService
    masters: MasterService
    sessions: SessionService
    timer: TimerService
    backups: BackupService
    quotas: QuotaService
    reviews: ReviewService
    transfer: TransferService
    stats: StatsService
    goals: GoalService
    session_repo: SessionRepository
    mistake_repo: MistakeRepository
    quota_repo: QuotaRepository
    task_repo: TaskRepository
    applied_migrations: list[int] = field(default_factory=list)
    # 画面から別の画面を開くための入口（メインウィンドウが差し込む）
    navigate: Callable[[str], None] | None = None

    def open_module(self, module_id: str) -> None:
        if self.navigate is not None:
            self.navigate(module_id)

    @classmethod
    def open(cls, db_path: Path | None = None, *, backup_on_start: bool = True) -> "AppContext":
        config.ensure_dirs()
        db_path = Path(db_path) if db_path else config.db_path()
        is_new = not db_path.exists()
        conn = connect(db_path)

        applied = migrator.migrate(conn)
        if applied:
            log.info("マイグレーションを適用した: %s", applied)

        settings = SettingsService(SettingsRepository(conn))
        settings.hub_id  # 初回に母艦IDを採番しておく

        exam_repo = ExamRepository(conn)
        sitting_repo = ExamSittingRepository(conn)
        material_repo = MaterialRepository(conn)
        subject_repo = SubjectRepository(conn)
        session_repo = SessionRepository(conn)
        timer_repo = TimerRepository(conn)
        quota_repo = QuotaRepository(conn)
        mistake_repo = MistakeRepository(conn)
        review_result_repo = ReviewResultRepository(conn)
        device_repo = DeviceRepository(conn)
        imported_repo = ImportedPackageRepository(conn)
        log_repo = TransferLogRepository(conn)

        masters = MasterService(exam_repo, material_repo, subject_repo, sitting_repo)
        sessions = SessionService(session_repo, material_repo, settings)
        timer = TimerService(timer_repo, sessions, settings)
        backups = BackupService(conn, config.backup_dir(), settings)
        quotas = QuotaService(quota_repo, masters, settings)
        reviews = ReviewService(mistake_repo, review_result_repo, settings)
        goals = GoalService(WeeklyGoalRepository(conn), session_repo, masters, settings)
        stats = StatsService(session_repo, masters, quota_repo, settings)

        builder = DownBuilder(
            settings=settings,
            masters=masters,
            quotas=quotas,
            mistakes=mistake_repo,
            sessions=session_repo,
            imported=imported_repo,
            goals=goals,
        )
        importer = UpImporter(
            conn=conn,
            settings=settings,
            masters=masters,
            sessions=session_repo,
            mistakes=mistake_repo,
            quotas=quota_repo,
            devices=device_repo,
            imported=imported_repo,
            reviews=reviews,
        )
        transfer = TransferService(
            settings=settings,
            builder=builder,
            importer=importer,
            quotas=quotas,
            logs=log_repo,
            devices=device_repo,
            backups=backups,
        )

        ctx = cls(
            conn=conn,
            db_path=db_path,
            settings=settings,
            masters=masters,
            sessions=sessions,
            timer=timer,
            backups=backups,
            quotas=quotas,
            reviews=reviews,
            transfer=transfer,
            stats=stats,
            goals=goals,
            session_repo=session_repo,
            mistake_repo=mistake_repo,
            quota_repo=quota_repo,
            task_repo=TaskRepository(conn),
            applied_migrations=applied,
        )
        if backup_on_start and not is_new:
            ctx.backups.on_startup()
        return ctx

    def close(self, *, backup_on_exit: bool = True) -> None:
        try:
            if backup_on_exit:
                self.backups.on_shutdown()
        finally:
            self.conn.close()
