"""転送の窓口。ファイルの読み書き、同期フォルダ、履歴の記録をまとめる。"""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import date, datetime
from pathlib import Path

from ...core import clock
from ...domain.models import ImportResult
from ...repositories.transfer import DeviceRepository, TransferLogRepository
from ..backup_service import BackupService
from ..quota_service import QuotaService
from ..settings_service import SettingsService
from . import codec, validator
from .down_builder import DownBuilder
from .up_importer import UpImporter

log = logging.getLogger(__name__)

SYNC_SUBDIRS = ("inbox", "outbox", "processed", "rejected")
_NAME_ALLOWED = re.compile(r"[^0-9A-Za-z぀-ゟ゠-ヿ㐀-鿿ｦ-ﾟ_-]")


def sanitize_device_name(name: str) -> str:
    """ファイル名に使える形にする（転送仕様書 第6章 B-10）。"""
    cleaned = _NAME_ALLOWED.sub("_", (name or "").strip())[:20]
    return cleaned or "device"


class TransferService:
    def __init__(
        self,
        *,
        settings: SettingsService,
        builder: DownBuilder,
        importer: UpImporter,
        quotas: QuotaService,
        logs: TransferLogRepository,
        devices: DeviceRepository,
        backups: BackupService,
    ) -> None:
        self.settings = settings
        self.builder = builder
        self.importer = importer
        self.quotas = quotas
        self.logs = logs
        self.devices = devices
        self.backups = backups

    # --- 同期フォルダ -------------------------------------------------------

    @property
    def sync_dir(self) -> Path:
        return self.settings.sync_dir

    def ensure_sync_dirs(self) -> dict[str, Path]:
        paths = {name: self.sync_dir / name for name in SYNC_SUBDIRS}
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return paths

    # --- 下り ---------------------------------------------------------------

    def build_down(
        self,
        target_date: date,
        *,
        variant: str = "full",
        include_reviews: bool = True,
        date_to: date | None = None,
    ) -> dict:
        return self.builder.build(
            target_date, variant=variant, include_reviews=include_reviews, date_to=date_to
        )

    @staticmethod
    def down_filename(package: dict) -> str:
        created = clock.parse_iso(package["createdAt"])
        stamp = clock.to_local(created).strftime("%Y%m%d-%H%M")
        return f"studylog-down-{stamp}-{package['packageId'][:8]}.json"

    def save_down(self, package: dict, extra_path: Path | None = None) -> list[Path]:
        """下りパッケージをファイルに書く（同期フォルダの outbox/ と、任意の場所）。"""
        validator.validate(package, "down").raise_if_bad()
        text = json.dumps(package, ensure_ascii=False, indent=2)
        written: list[Path] = []

        outbox = self.ensure_sync_dirs()["outbox"]
        for path in [outbox / self.down_filename(package)] + ([extra_path] if extra_path else []):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            written.append(path)

        self._mark_sent(package)
        self.logs.record(
            direction="down",
            package_id=package["packageId"],
            variant=package.get("variant"),
            counts=self._down_counts(package),
            message=", ".join(path.name for path in written),
        )
        return written

    def down_string(self, package: dict) -> str:
        """QR・貼り付け用の文字列（`SL1:...`）。"""
        validator.validate(package, "down").raise_if_bad()
        return codec.encode(package)

    def record_down_sent(self, package: dict, how: str) -> None:
        """QR表示・文字列コピーで渡したときの記録。"""
        self._mark_sent(package)
        self.logs.record(
            direction="down",
            package_id=package["packageId"],
            variant=package.get("variant"),
            counts=self._down_counts(package),
            message=how,
        )

    @staticmethod
    def _down_counts(package: dict) -> dict:
        return {
            "quotas": len(package.get("quotas") or []),
            "reviews": len(package.get("reviews") or []),
            "acks": len(package.get("acks") or []),
        }

    def _mark_sent(self, package: dict) -> None:
        quota_ids = [quota["id"] for quota in package.get("quotas") or []]
        self.quotas.quotas.mark_sent(quota_ids, clock.db_now())

    # --- 上り ---------------------------------------------------------------

    def import_package(self, package: dict) -> ImportResult:
        self.backups.before_import()
        result = self.importer.import_package(package)
        self.logs.record(
            direction="up",
            package_id=result.package_id,
            device_id=result.device_id,
            variant="file",
            counts={
                "added": result.added,
                "updated": result.updated,
                "skipped": result.skipped,
                "unclassified": result.unclassified,
            },
            message=result.device_name,
        )
        return result

    def import_file(self, path: Path, *, move: bool = True) -> ImportResult:
        """ファイルを1つ取り込む。失敗したら rejected/ に移し、理由を記録する。"""
        try:
            package = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            self._reject(path, f"JSONとして読めません: {error}", move=move)
            raise validator.TransferError(f"{path.name}: JSONとして読めません") from error

        try:
            result = self.import_package(package)
        except validator.TransferError as error:
            self._reject(path, str(error), move=move, package=package)
            raise

        if move:
            self._move_to(path, "processed")
        return result

    def scan_inbox(self) -> list[ImportResult]:
        """inbox/ にあるファイルをすべて取り込む。失敗しても次のファイルへ進む。"""
        paths = self.ensure_sync_dirs()
        results: list[ImportResult] = []
        for path in sorted(paths["inbox"].glob("*.json")):
            try:
                results.append(self.import_file(path))
            except validator.TransferError as error:
                log.warning("取り込めなかった: %s (%s)", path.name, error)
        return results

    def _reject(
        self, path: Path, reason: str, *, move: bool, package: dict | None = None
    ) -> None:
        self.logs.record(
            direction="up",
            package_id=(package or {}).get("packageId"),
            variant="file",
            result="rejected",
            message=f"{path.name}: {reason}"[:500],
        )
        if move:
            self._move_to(path, "rejected")

    def _move_to(self, path: Path, folder: str) -> Path | None:
        try:
            destination = self.ensure_sync_dirs()[folder] / path.name
            if destination.exists():
                stem, suffix = destination.stem, destination.suffix
                destination = destination.with_name(
                    f"{stem}-{datetime.now().strftime('%H%M%S%f')[:-3]}{suffix}"
                )
            shutil.move(str(path), str(destination))
            return destination
        except OSError:
            log.exception("ファイルを移動できなかった: %s", path)
            return None

    # --- 履歴 ---------------------------------------------------------------

    def history(self, limit: int = 100) -> list:
        return self.logs.recent(limit)

    def device_list(self) -> list:
        return self.devices.list()
