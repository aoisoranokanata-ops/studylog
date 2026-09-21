"""同期フォルダの inbox/ を見張って、届いたファイルを自動で取り込む。

QFileSystemWatcher は取りこぼすことがある（保存の途中、ネットワーク越しの同期など）ので、
定期的なポーリングも併用する。
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

from ...domain.models import ImportResult
from .service import TransferService

log = logging.getLogger(__name__)

POLL_INTERVAL_MS = 30_000
SETTLE_DELAY_MS = 1_500  # 書き込み途中のファイルを掴まないよう、少し待つ


class InboxWatcher(QObject):
    imported = Signal(object)  # list[ImportResult]
    failed = Signal(str)

    def __init__(self, transfer: TransferService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.transfer = transfer
        self.enabled = True

        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._on_directory_changed)

        self.settle = QTimer(self)
        self.settle.setSingleShot(True)
        self.settle.setInterval(SETTLE_DELAY_MS)
        self.settle.timeout.connect(self.scan_now)

        self.poll = QTimer(self)
        self.poll.setInterval(POLL_INTERVAL_MS)
        self.poll.timeout.connect(self.scan_now)

    # --- 開始・停止 ---------------------------------------------------------

    def start(self) -> None:
        self.retarget()
        self.poll.start()
        self.scan_now()

    def stop(self) -> None:
        self.poll.stop()
        self.settle.stop()
        if self.watcher.directories():
            self.watcher.removePaths(self.watcher.directories())

    def retarget(self) -> None:
        """設定で同期フォルダを変えたときに見張り先を張り替える。"""
        if self.watcher.directories():
            self.watcher.removePaths(self.watcher.directories())
        inbox = self.transfer.ensure_sync_dirs()["inbox"]
        self.watcher.addPath(str(inbox))

    # --- 取り込み -----------------------------------------------------------

    def _on_directory_changed(self, _path: str) -> None:
        if self.enabled:
            self.settle.start()

    def scan_now(self) -> list[ImportResult]:
        if not self.enabled:
            return []
        try:
            results = self.transfer.scan_inbox()
        except Exception as error:  # 監視は止めない
            log.exception("inbox の取り込みで失敗した")
            self.failed.emit(str(error))
            return []
        if results:
            self.imported.emit(results)
        return results
