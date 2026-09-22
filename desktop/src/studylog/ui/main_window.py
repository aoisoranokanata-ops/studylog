"""メインウィンドウ。左のナビはモジュールの登録内容から自動で作る。"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from .. import config
from ..context import AppContext
from ..core import clock
from ..domain.models import SessionFilter
from ..services.transfer.watcher import InboxWatcher
from .module_registry import FeatureModule, discover

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"{config.APP_NAME} {config.APP_VERSION}")
        self.resize(1180, 800)

        self.modules: list[FeatureModule] = discover()
        self._views: dict[str, QWidget] = {}

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.nav = QListWidget(central)
        self.nav.setFixedWidth(160)
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for module in self.modules:
            item = QListWidgetItem(module.title)
            item.setData(Qt.ItemDataRole.UserRole, module.id)
            item.setToolTip(module.description)
            item.setSizeHint(item.sizeHint().expandedTo(item.sizeHint().boundedTo(item.sizeHint())))
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        layout.addWidget(self.nav)

        self.stack = QStackedWidget(central)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.status = QLabel()
        self.statusBar().addPermanentWidget(self.status)

        # 同期フォルダの inbox/ を見張って、子機から届いたファイルを自動で取り込む
        self.watcher = InboxWatcher(ctx.transfer, self)
        self.watcher.imported.connect(self._on_imported)
        self.watcher.failed.connect(
            lambda message: self.statusBar().showMessage(f"自動取り込みに失敗: {message}", 8000)
        )
        self.watcher.start()

        self._build_menu()
        # 画面から別の画面を開けるようにする（ダッシュボードのボタンなど）
        ctx.navigate = self.open_module
        if self.modules:
            # 計測中なら計測画面から、そうでなければ先頭（ダッシュボード）から開く
            start = "timer" if ctx.timer.current() is not None else self.modules[0].id
            self.open_module(start)
        else:
            self.stack.addWidget(QLabel("表示できる画面がありません"))
        self._update_status()

    # --- ナビ ---------------------------------------------------------------

    def _on_nav_changed(self, row: int) -> None:
        if not 0 <= row < len(self.modules):
            return
        module = self.modules[row]
        view = self._views.get(module.id)
        if view is None:
            try:
                view = module.factory(self.ctx)
            except Exception:
                log.exception("画面を作れなかった: %s", module.id)
                view = QLabel(f"「{module.title}」を開けませんでした。ログを確認してください。")
            self._views[module.id] = view
            self.stack.addWidget(view)
        self.stack.setCurrentWidget(view)
        if hasattr(view, "refresh"):
            try:
                view.refresh()
            except Exception:
                log.exception("画面の更新に失敗した: %s", module.id)
        self._update_status()

    def open_module(self, module_id: str) -> None:
        for row, module in enumerate(self.modules):
            if module.id == module_id:
                self.nav.setCurrentRow(row)
                return
        log.warning("モジュールが見つからない: %s", module_id)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("ファイル")
        backup_action = file_menu.addAction("バックアップを作る")
        backup_action.triggered.connect(self._backup_now)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("終了")
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)

        help_menu = self.menuBar().addMenu("ヘルプ")
        about_action = help_menu.addAction(f"{config.APP_NAME} について")
        about_action.triggered.connect(self._about)

    # --- その他 -------------------------------------------------------------

    def _backup_now(self) -> None:
        path = self.ctx.backups.create("manual")
        self.statusBar().showMessage(
            f"バックアップを作りました: {path.name}" if path else "バックアップに失敗しました", 5000
        )

    def _about(self) -> None:
        QMessageBox.information(
            self,
            f"{config.APP_NAME} について",
            f"{config.APP_NAME} {config.APP_VERSION}\n"
            f"転送 schemaVersion: {config.SCHEMA_VERSION}\n"
            f"データ: {config.data_dir()}",
        )

    def _on_imported(self, results: list) -> None:
        """inbox/ から自動で取り込めたときの後始末。"""
        added = sum(result.added for result in results)
        updated = sum(result.updated for result in results)
        unclassified = sum(result.unclassified for result in results)
        self.statusBar().showMessage(
            f"子機から{len(results)}件のファイルを取り込みました"
            f"（追加 {added}／更新 {updated}／未分類 {unclassified}）",
            10000,
        )
        transfer_view = self._views.get("transfer")
        if transfer_view is not None and hasattr(transfer_view, "on_imported"):
            transfer_view.on_imported(results)
        current = self.stack.currentWidget()
        if current is not None and hasattr(current, "refresh"):
            current.refresh()
        self._update_status()

    def _update_status(self) -> None:
        today = clock.study_date(clock.now_utc(), self.ctx.settings.day_change_hour)
        seconds = self.ctx.sessions.seconds_for_day(today)
        week = self.ctx.sessions.seconds_for_week(today)
        unclassified = self.ctx.session_repo.count(SessionFilter(unclassified_only=True))
        text = f"今日 {clock.format_hm(seconds)}　今週 {clock.format_hm(week)}　（{today}）"
        if unclassified:
            text = f"未分類 {unclassified}件　|　" + text
        self.status.setText(text)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qtの命名に合わせる)
        if self.ctx.timer.current() is not None:
            answer = QMessageBox.question(
                self,
                "計測中です",
                "計測したままです。終了しますか？\n（計測の状態は保存され、次に開いたとき続きから再開できます）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.watcher.stop()
        event.accept()
