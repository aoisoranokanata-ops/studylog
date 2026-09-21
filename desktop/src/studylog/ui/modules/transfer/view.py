"""転送画面（送る／受け取る／履歴）。"""

from __future__ import annotations

import json
from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDateEdit,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ....context import AppContext
from ....core import clock
from ....domain import enums
from ....services.transfer import codec, validator
from ...widgets.common import confirm, heading, show_error, show_info
from ..app_settings.view import open_in_explorer
from .qr_dialog import QrDialog
from .quota_dialog import QuotaDialog

QUOTA_COLUMNS = ["内容", "目標", "実績", "状況", "資格", "参考書", "分野", "範囲"]
HISTORY_COLUMNS = ["日時", "方向", "結果", "件数", "packageId", "備考"]


class SendTab(QWidget):
    """ノルマを作って子機へ渡す。"""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._quotas: list = []

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        today = ctx.quotas.today()
        self.date = QDateEdit(QDate(today.year, today.month, today.day), self)
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.dateChanged.connect(self.refresh)
        top.addWidget(QLabel("日付"))
        top.addWidget(self.date)
        for text, slot in (("予定から作る", self._from_plans), ("前日からコピー", self._copy_previous)):
            button = QPushButton(text, self)
            button.clicked.connect(slot)
            top.addWidget(button)
        top.addStretch(1)
        layout.addLayout(top)

        self.table = QTableWidget(0, len(QUOTA_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(QUOTA_COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._edit)
        layout.addWidget(self.table, 1)

        edit_row = QHBoxLayout()
        edit_row.addStretch(1)
        for text, slot in (
            ("追加", self._add),
            ("編集", self._edit),
            ("削除", self._delete),
            ("↑", lambda: self._move(-1)),
            ("↓", lambda: self._move(1)),
        ):
            button = QPushButton(text, self)
            button.clicked.connect(slot)
            if text in ("↑", "↓"):
                button.setFixedWidth(40)
            edit_row.addWidget(button)
        layout.addLayout(edit_row)

        send_box = QGroupBox("子機へ渡す", self)
        send_layout = QVBoxLayout(send_box)
        self.include_reviews = QCheckBox("今日の復習対象を含める", send_box)
        self.include_reviews.setChecked(True)
        self.include_reviews.stateChanged.connect(self._update_info)
        send_layout.addWidget(self.include_reviews)

        self.info = QLabel(send_box)
        self.info.setWordWrap(True)
        send_layout.addWidget(self.info)

        buttons = QHBoxLayout()
        for text, slot in (
            ("QRコードを表示", self._show_qr),
            ("ファイルに保存", self._save_file),
            ("文字列をコピー", self._copy_text),
        ):
            button = QPushButton(text, send_box)
            button.setMinimumHeight(36)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        send_layout.addLayout(buttons)
        layout.addWidget(send_box)

        self.refresh()

    # --- 表示 ---------------------------------------------------------------

    def selected_date(self) -> date:
        return self.date.date().toPython()

    def refresh(self) -> None:
        self._quotas = self.ctx.quotas.list(self.selected_date())
        self.table.setRowCount(len(self._quotas))
        for row, quota in enumerate(self._quotas):
            labels = self.ctx.quotas.labels_for(quota)
            actual = self.ctx.quotas.actual_seconds(quota.id)
            range_text = ""
            if quota.range_from is not None and quota.range_to is not None:
                unit = enums.label(enums.RANGE_UNIT, quota.range_unit)
                range_text = f"{quota.range_from}〜{quota.range_to} {unit}"
            values = [
                quota.title,
                clock.format_hm(quota.target_seconds),
                clock.format_hm(actual) if actual else "",
                enums.label(enums.QUOTA_STATUS, quota.status),
                labels["exam"] or "",
                labels["material"] or "",
                labels["subject"] or "",
                range_text,
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column in (1, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._update_info()

    def _build(self, variant: str) -> dict:
        return self.ctx.transfer.build_down(
            self.selected_date(),
            variant=variant,
            include_reviews=self.include_reviews.isChecked(),
        )

    def _update_info(self) -> None:
        try:
            lite = self._build("lite")
            text = codec.encode(lite)
        except Exception as error:  # 設定途中などで作れないことがある
            self.info.setText(f"パッケージを作れません: {error}")
            return
        size = codec.byte_length(text)
        fits = codec.fits_in_qr(text)
        reviews = len(lite.get("reviews") or [])
        acks = len(lite.get("acks") or [])
        status = (
            f"QR用 {size} バイト（上限 {codec.QR_BYTE_LIMIT}）"
            if fits
            else f"QR用 {size} バイトで上限 {codec.QR_BYTE_LIMIT} を超えています → ファイルで渡してください"
        )
        self.info.setText(
            f"ノルマ {len(lite['quotas'])}件／復習 {reviews}件／取り込み済み通知 {acks}件　—　{status}"
        )
        self.info.setStyleSheet("" if fits else "color: #b34;")

    # --- ノルマの編集 -------------------------------------------------------

    def _selected(self):
        row = self.table.currentRow()
        return self._quotas[row] if 0 <= row < len(self._quotas) else None

    def _add(self) -> None:
        dialog = QuotaDialog(self.ctx, self.selected_date(), parent=self)
        if not dialog.exec():
            return
        try:
            self.ctx.quotas.create(**dialog.values())
        except ValueError as error:
            show_error(self, str(error))
            return
        self.refresh()

    def _edit(self) -> None:
        quota = self._selected()
        if quota is None:
            show_error(self, "ノルマを選んでください")
            return
        dialog = QuotaDialog(self.ctx, self.selected_date(), quota, parent=self)
        if not dialog.exec():
            return
        try:
            self.ctx.quotas.update(quota.id, dialog.update_values())
        except ValueError as error:
            show_error(self, str(error))
            return
        self.refresh()

    def _delete(self) -> None:
        quota = self._selected()
        if quota is None:
            show_error(self, "ノルマを選んでください")
            return
        if confirm(self, f"「{quota.title}」を削除しますか？"):
            self.ctx.quotas.delete(quota.id)
            self.refresh()

    def _move(self, offset: int) -> None:
        quota = self._selected()
        if quota is None:
            return
        row = self.table.currentRow()
        self.ctx.quotas.move(quota.id, offset)
        self.refresh()
        self.table.setCurrentCell(min(max(0, row + offset), self.table.rowCount() - 1), 0)

    def _from_plans(self) -> None:
        created = self.ctx.quotas.build_from_plans(self.selected_date())
        self.refresh()
        show_info(self, f"予定から{created}件のノルマを作りました。" if created else "その日の予定はありません。")

    def _copy_previous(self) -> None:
        source = self.selected_date() - timedelta(days=1)
        created = self.ctx.quotas.copy_from(source, self.selected_date())
        self.refresh()
        show_info(self, f"{source} から{created}件コピーしました。" if created else f"{source} にノルマはありません。")

    # --- 送る ---------------------------------------------------------------

    def _show_qr(self) -> None:
        package = self._build("lite")
        try:
            text = self.ctx.transfer.down_string(package)
        except validator.TransferError as error:
            show_error(self, str(error))
            return
        if not codec.fits_in_qr(text):
            show_error(
                self,
                f"QRコードには大きすぎます（{codec.byte_length(text)} バイト／上限 "
                f"{codec.QR_BYTE_LIMIT}）。\nノルマを減らすか、「ファイルに保存」で渡してください。",
            )
            return
        self.ctx.transfer.record_down_sent(package, "QR表示")
        QrDialog(text, caption=f"{self.selected_date()} のノルマ", parent=self).exec()
        self.refresh()

    def _save_file(self) -> None:
        package = self._build("full")
        suggested = self.ctx.transfer.down_filename(package)
        chosen, _ = QFileDialog.getSaveFileName(self, "下りパッケージを保存", suggested, "JSON (*.json)")
        try:
            written = self.ctx.transfer.save_down(package, chosen or None)
        except validator.TransferError as error:
            show_error(self, str(error))
            return
        self.refresh()
        show_info(self, "保存しました：\n" + "\n".join(str(path) for path in written))

    def _copy_text(self) -> None:
        package = self._build("lite")
        try:
            text = self.ctx.transfer.down_string(package)
        except validator.TransferError as error:
            show_error(self, str(error))
            return
        QGuiApplication.clipboard().setText(text)
        self.ctx.transfer.record_down_sent(package, "文字列コピー")
        self.refresh()
        show_info(self, f"クリップボードにコピーしました（{codec.byte_length(text)} バイト）。")


class ReceiveTab(QWidget):
    """子機から届いたファイルを取り込む。"""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)

        self.folder_label = QLabel(self)
        self.folder_label.setWordWrap(True)
        layout.addWidget(self.folder_label)

        buttons = QHBoxLayout()
        for text, slot in (
            ("いま取り込む", self.scan_now),
            ("ファイルを選ぶ…", self._choose_file),
            ("inbox を開く", self._open_inbox),
        ):
            button = QPushButton(text, self)
            button.setMinimumHeight(36)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.drop_hint = QLabel("ここにファイルをドラッグ＆ドロップしても取り込めます", self)
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.setMinimumHeight(70)
        self.drop_hint.setStyleSheet("border: 2px dashed #aaa; border-radius: 8px; color: #666;")
        layout.addWidget(self.drop_hint)

        self.log = QPlainTextEdit(self)
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)

        self.devices = QLabel(self)
        layout.addWidget(self.devices)

        self.refresh()

    def refresh(self) -> None:
        folders = self.ctx.transfer.ensure_sync_dirs()
        waiting = len(list(folders["inbox"].glob("*.json")))
        self.folder_label.setText(
            f"監視フォルダ: {folders['inbox']}\n"
            f"未処理のファイル: {waiting}件（自動取り込みは常に動いています）"
        )
        devices = self.ctx.transfer.device_list()
        if devices:
            parts = [
                f"{row['name'] or '(名前なし)'}: "
                f"{clock.format_local(clock.from_db(row['last_received_at'])) if row['last_received_at'] else '―'}"
                for row in devices
            ]
            self.devices.setText("子機の最終受信　" + "　/　".join(parts))
        else:
            self.devices.setText("まだ子機から受け取っていません")

    def append(self, message: str) -> None:
        stamp = clock.format_local(clock.now_utc(), "%H:%M:%S")
        self.log.appendPlainText(f"[{stamp}] {message}")

    # --- 操作 ---------------------------------------------------------------

    def scan_now(self) -> None:
        results = self.ctx.transfer.scan_inbox()
        if not results:
            self.append("取り込むファイルはありませんでした")
        for result in results:
            self.append(result.summary())
        self.refresh()

    def _choose_file(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "上りパッケージを選ぶ", str(self.ctx.transfer.sync_dir), "JSON (*.json)"
        )
        if chosen:
            self.import_path(chosen)

    def _open_inbox(self) -> None:
        open_in_explorer(self.ctx.transfer.ensure_sync_dirs()["inbox"])

    def import_path(self, path_text: str) -> None:
        from pathlib import Path

        path = Path(path_text)
        try:
            # 選んだファイルは元の場所に残す（同期フォルダの中のものだけ移動する）
            inside = self.ctx.transfer.sync_dir in path.parents
            result = self.ctx.transfer.import_file(path, move=inside)
        except validator.NeedsUpdateError as error:
            self.append(f"{path.name}: {error}")
            show_error(self, str(error), title="アプリの更新が必要です")
            return
        except validator.TransferError as error:
            self.append(f"{path.name}: 取り込めませんでした — {error}")
            show_error(self, f"{path.name} を取り込めませんでした。\n\n{error}")
            return
        self.append(f"{path.name}: {result.summary()}")
        self.refresh()
        if result.unclassified:
            show_info(
                self,
                f"{result.summary()}\n\n未分類の記録が{result.unclassified}件あります。"
                "「未分類」の画面で分類できます。",
            )

    # --- ドラッグ＆ドロップ -------------------------------------------------

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_hint.setStyleSheet(
                "border: 2px dashed #4a6fa5; border-radius: 8px; color: #4a6fa5;"
            )

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.drop_hint.setStyleSheet("border: 2px dashed #aaa; border-radius: 8px; color: #666;")

    def dropEvent(self, event) -> None:  # noqa: N802
        self.dragLeaveEvent(event)
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".json"):
                self.import_path(path)
            else:
                self.append(f"{path}: JSONファイルではありません")
        event.acceptProposedAction()


class HistoryTab(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, len(HISTORY_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(HISTORY_COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        refresh = QPushButton("更新", self)
        refresh.clicked.connect(self.refresh)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(refresh)
        layout.addLayout(row)

        self.refresh()

    def refresh(self) -> None:
        rows = self.ctx.transfer.history(200)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            counts = json.loads(row["counts"] or "{}")
            counts_text = "／".join(f"{key} {value}" for key, value in counts.items())
            values = [
                clock.format_local(clock.from_db(row["occurred_at"])),
                "送信" if row["direction"] == "down" else "受信",
                {"ok": "成功", "rejected": "拒否", "error": "失敗"}.get(row["result"], row["result"]),
                counts_text,
                (row["package_id"] or "")[:8],
                row["message"],
            ]
            for column, text in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            len(HISTORY_COLUMNS) - 1, QHeaderView.ResizeMode.Stretch
        )


class TransferView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        layout = QVBoxLayout(self)
        layout.addWidget(heading("転送"))

        self.tabs = QTabWidget(self)
        self.send = SendTab(ctx, self)
        self.receive = ReceiveTab(ctx, self)
        self.history = HistoryTab(ctx, self)
        self.tabs.addTab(self.send, "送る")
        self.tabs.addTab(self.receive, "受け取る")
        self.tabs.addTab(self.history, "履歴")
        self.tabs.currentChanged.connect(lambda _: self.refresh())
        layout.addWidget(self.tabs, 1)

    def refresh(self) -> None:
        current = self.tabs.currentWidget()
        if hasattr(current, "refresh"):
            current.refresh()

    def on_imported(self, results: list) -> None:
        """自動取り込みが動いたときに、メインウィンドウから呼ばれる。"""
        for result in results:
            self.receive.append(f"自動取り込み: {result.summary()}")
        self.refresh()
