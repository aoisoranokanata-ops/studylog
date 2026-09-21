"""画面が組み立てられることの確認（オフスクリーンで動かす）。

ダイアログは開かず、モジュールの生成と refresh() が例外なく通ることだけを見る。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from studylog.ui.main_window import MainWindow  # noqa: E402
from studylog.ui.module_registry import discover  # noqa: E402

from .conftest import local  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_modules_are_discovered():
    modules = {module.id for module in discover()}
    assert {"timer", "records", "masters", "transfer", "unclassified", "settings"} <= modules


def test_main_window_opens_every_module(qapp, ctx, sample_masters):
    ctx.sessions.create(
        started_at=local(2026, 9, 20, 9),
        ended_at=local(2026, 9, 20, 10),
        active_seconds=3600,
        exam_id=sample_masters["exam_id"],
        material_id=sample_masters["material_id"],
        memo="表示の確認",
    )
    window = MainWindow(ctx)
    try:
        assert window.nav.count() == len(window.modules)
        for row in range(window.nav.count()):
            window.nav.setCurrentRow(row)
            qapp.processEvents()
            view = window.stack.currentWidget()
            assert view is not None
            assert not isinstance(view, type(None))
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()


def test_timer_view_start_and_state(qapp, ctx, sample_masters):
    from studylog.ui.modules.timer.view import TimerView

    view = TimerView(ctx)
    try:
        view.ticker.stop()
        view._start()
        assert ctx.timer.current() is not None
        view._toggle_pause()
        assert ctx.timer.is_running() is False
        view._toggle_pause()
        assert ctx.timer.is_running() is True
        ctx.timer.discard()
        view._tick()
        assert view.start_button.isEnabled() is True
    finally:
        view.deleteLater()
        qapp.processEvents()


def test_records_view_lists_sessions(qapp, ctx, sample_masters):
    from studylog.ui.modules.records.view import RecordsView

    ctx.sessions.create(
        started_at=local(2026, 9, 20, 9),
        ended_at=local(2026, 9, 20, 10),
        active_seconds=3600,
        exam_id=sample_masters["exam_id"],
    )
    view = RecordsView(ctx)
    try:
        # 既定の期間は直近30日なので、2026-09-20 が入るように広げる
        view.date_from.setDate(view.date_from.date().addYears(-5))
        view.date_to.setDate(view.date_to.date().addYears(5))
        view.refresh()
        assert view.table.rowCount() == 1
        assert view.table.item(0, 0).text() == "2026-09-20"
    finally:
        view.deleteLater()
        qapp.processEvents()


def test_masters_view_shows_exam(qapp, ctx, sample_masters):
    from studylog.ui.modules.masters.view import MastersView

    view = MastersView(ctx)
    try:
        view.exams.refresh()
        assert view.exams.list.count() == 1
        view.materials.refresh()
        assert view.materials.list.count() == 1
        view.subjects.refresh()
        assert view.subjects.list.count() == 1
    finally:
        view.deleteLater()
        qapp.processEvents()


def test_settings_view_saves(qapp, ctx, monkeypatch):
    from studylog.ui.modules.app_settings import view as settings_view

    # モーダルダイアログでテストが止まらないようにする
    monkeypatch.setattr(settings_view, "show_info", lambda *args, **kwargs: None)
    SettingsView = settings_view.SettingsView

    view = SettingsView(ctx)
    try:
        view.day_change_hour.setValue(3)
        view.week_starts_on.setCurrentIndex(view.week_starts_on.findData(7))
        view._save()
        ctx.settings.reload()
        assert ctx.settings.day_change_hour == 3
        assert ctx.settings.week_starts_on == 7
    finally:
        view.deleteLater()
        qapp.processEvents()


# --- フェーズ2（転送） ------------------------------------------------------

def test_transfer_view_builds_and_shows_size(qapp, ctx, sample_masters):
    from studylog.ui.modules.transfer.view import TransferView

    ctx.quotas.create(
        day=ctx.quotas.today(),
        title="民法 問題集 p.40-65",
        target_seconds=5400,
        exam_id=sample_masters["exam_id"],
        material_id=sample_masters["material_id"],
        range_unit="question",
        range_from=40,
        range_to=65,
    )
    view = TransferView(ctx)
    try:
        view.send.refresh()
        assert view.send.table.rowCount() == 1
        assert "QR用" in view.send.info.text()
        view.receive.refresh()
        assert "監視フォルダ" in view.receive.folder_label.text()
        view.history.refresh()
    finally:
        view.deleteLater()
        qapp.processEvents()


def test_qr_pixmap_is_drawn(qapp, ctx, sample_masters):
    from studylog.services.transfer import codec
    from studylog.ui.modules.transfer.qr_dialog import make_pixmap

    text = codec.encode(ctx.transfer.build_down(ctx.quotas.today(), variant="lite"))
    pixmap = make_pixmap(text)
    assert not pixmap.isNull()
    assert pixmap.width() == pixmap.height() > 200


def test_unclassified_view_assigns_in_bulk(qapp, ctx, sample_masters, monkeypatch):
    from studylog.ui.modules.unclassified import view as unclassified_view

    monkeypatch.setattr(unclassified_view, "show_info", lambda *a, **k: None)

    for _ in range(3):
        ctx.sessions.create(
            started_at=local(2026, 9, 22, 9),
            ended_at=local(2026, 9, 22, 10),
            active_seconds=3600,
            memo="子機から届いた記録",
        )

    view = unclassified_view.UnclassifiedView(ctx)
    try:
        assert view.table.rowCount() == 3
        view.table.selectAll()
        view.picker.set_values({"exam_id": sample_masters["exam_id"], "material_id": None, "subject_id": None})
        view._apply()
        assert view.table.rowCount() == 0
    finally:
        view.deleteLater()
        qapp.processEvents()


def test_watcher_imports_dropped_file(qapp, ctx, tmp_path):
    import json
    from pathlib import Path

    from studylog.services.transfer.watcher import InboxWatcher

    spec_example = Path(__file__).resolve().parents[2] / "spec" / "examples" / "up-01-normal-valid.json"
    inbox = ctx.transfer.ensure_sync_dirs()["inbox"]
    (inbox / "studylog-up-iPhone-20260920-1830-c0000001.json").write_text(
        spec_example.read_text(encoding="utf-8"), encoding="utf-8"
    )

    watcher = InboxWatcher(ctx.transfer)
    received: list = []
    watcher.imported.connect(received.append)
    try:
        results = watcher.scan_now()
        qapp.processEvents()
        assert len(results) == 1
        assert received and received[0][0].added == 4
        assert ctx.session_repo.count() == 2
    finally:
        watcher.stop()
        watcher.deleteLater()
        qapp.processEvents()


def test_main_window_starts_watcher(qapp, ctx):
    from studylog.ui.main_window import MainWindow

    window = MainWindow(ctx)
    try:
        assert window.watcher.poll.isActive()
        assert window.watcher.watcher.directories()
        window.close()
        assert not window.watcher.poll.isActive()
    finally:
        window.deleteLater()
        qapp.processEvents()
