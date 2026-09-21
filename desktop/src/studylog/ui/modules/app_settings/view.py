"""設定画面。バックアップの作成・復元もここから行う。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .... import config
from ....context import AppContext
from ...widgets.common import confirm, heading, show_error, show_info

WEEKDAYS = {1: "月曜", 2: "火曜", 3: "水曜", 4: "木曜", 5: "金曜", 6: "土曜", 7: "日曜"}


def open_in_explorer(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # noqa: S606
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except OSError:
        pass


class SettingsView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        layout = QVBoxLayout(self)
        layout.addWidget(heading("設定"))

        # --- 基本 -----------------------------------------------------------
        basic = QGroupBox("基本", self)
        form = QFormLayout(basic)

        self.day_change_hour = QSpinBox(self)
        self.day_change_hour.setRange(0, 23)
        self.day_change_hour.setSuffix(" 時")
        self.day_change_hour.setValue(ctx.settings.day_change_hour)
        form.addRow("日付変更時刻", self.day_change_hour)

        self.week_starts_on = QComboBox(self)
        for value, label in WEEKDAYS.items():
            self.week_starts_on.addItem(label, value)
        self.week_starts_on.setCurrentIndex(
            max(0, self.week_starts_on.findData(ctx.settings.week_starts_on))
        )
        form.addRow("週の開始", self.week_starts_on)

        self.long_session_hours = QSpinBox(self)
        self.long_session_hours.setRange(1, 24)
        self.long_session_hours.setSuffix(" 時間")
        self.long_session_hours.setValue(ctx.settings.get_int("long_session_hours"))
        form.addRow("つけっぱなし判定", self.long_session_hours)

        self.backup_generations = QSpinBox(self)
        self.backup_generations.setRange(1, 100)
        self.backup_generations.setValue(ctx.settings.backup_generations)
        form.addRow("バックアップ世代数", self.backup_generations)

        sync_row = QWidget(self)
        sync_layout = QHBoxLayout(sync_row)
        sync_layout.setContentsMargins(0, 0, 0, 0)
        self.sync_dir = QLineEdit(str(ctx.settings.sync_dir), sync_row)
        browse = QPushButton("選ぶ…", sync_row)
        browse.clicked.connect(self._pick_sync_dir)
        sync_layout.addWidget(self.sync_dir, 1)
        sync_layout.addWidget(browse)
        form.addRow("同期フォルダ", sync_row)

        save_button = QPushButton("保存", self)
        save_button.clicked.connect(self._save)
        form.addRow("", save_button)
        layout.addWidget(basic)

        # --- バックアップ ---------------------------------------------------
        backup_box = QGroupBox("バックアップ", self)
        backup_layout = QVBoxLayout(backup_box)
        self.backup_list = QListWidget(backup_box)
        backup_layout.addWidget(self.backup_list)
        backup_buttons = QHBoxLayout()
        for text, slot in (
            ("いま作る", self._create_backup),
            ("選んだものから復元", self._restore_backup),
            ("フォルダを開く", lambda: open_in_explorer(config.backup_dir())),
        ):
            button = QPushButton(text, backup_box)
            button.clicked.connect(slot)
            backup_buttons.addWidget(button)
        backup_layout.addLayout(backup_buttons)
        layout.addWidget(backup_box, 1)

        # --- 情報 -----------------------------------------------------------
        info = QGroupBox("このアプリについて", self)
        info_layout = QFormLayout(info)
        info_layout.addRow("バージョン", QLabel(config.APP_VERSION))
        info_layout.addRow("転送 schemaVersion", QLabel(str(config.SCHEMA_VERSION)))
        info_layout.addRow("データの場所", QLabel(str(config.data_dir())))
        info_layout.addRow("母艦ID", QLabel(ctx.settings.hub_id))
        open_data = QPushButton("データフォルダを開く", info)
        open_data.clicked.connect(lambda: open_in_explorer(config.data_dir()))
        info_layout.addRow("", open_data)
        layout.addWidget(info)

        self.refresh()

    # --- 操作 ---------------------------------------------------------------

    def refresh(self) -> None:
        self.backup_list.clear()
        for path in self.ctx.backups.listing():
            size_mb = path.stat().st_size / (1024 * 1024)
            self.backup_list.addItem(f"{path.name}　({size_mb:.1f} MB)")

    def _pick_sync_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "同期フォルダを選ぶ", self.sync_dir.text())
        if chosen:
            self.sync_dir.setText(chosen)

    def _save(self) -> None:
        previous_hour = self.ctx.settings.day_change_hour
        self.ctx.settings.set("day_change_hour", str(self.day_change_hour.value()))
        self.ctx.settings.set("week_starts_on", str(self.week_starts_on.currentData()))
        self.ctx.settings.set("long_session_hours", str(self.long_session_hours.value()))
        self.ctx.settings.set("backup_generations", str(self.backup_generations.value()))
        self.ctx.settings.set_sync_dir(self.sync_dir.text().strip() or None)

        message = "保存しました。"
        if previous_hour != self.day_change_hour.value():
            changed = self.ctx.session_repo.recompute_study_dates(self.ctx.settings.day_change_hour)
            message += f"\n日付変更時刻が変わったので、{changed}件の記録の学習日を計算し直しました。"
        show_info(self, message)

    def _create_backup(self) -> None:
        path = self.ctx.backups.create("manual")
        self.refresh()
        show_info(self, f"バックアップを作りました：\n{path.name}" if path else "バックアップに失敗しました")

    def _restore_backup(self) -> None:
        row = self.backup_list.currentRow()
        backups = self.ctx.backups.listing()
        if not 0 <= row < len(backups):
            show_error(self, "復元するバックアップを選んでください")
            return
        target = backups[row]
        if not confirm(
            self,
            f"「{target.name}」の内容で、いまのデータを置き換えますか？\n"
            "（置き換える直前のデータも自動でバックアップします）",
        ):
            return
        self.ctx.backups.restore(target)
        self.ctx.settings.reload()
        self.refresh()
        show_info(self, "復元しました。アプリを再起動してください。")
