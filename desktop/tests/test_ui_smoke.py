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
    assert {"dashboard", "timer", "records", "stats", "goals", "masters", "transfer", "unclassified", "settings"} <= modules


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


# --- フェーズ3（可視化） ----------------------------------------------------

def _seed_week(ctx, sample_masters):
    from datetime import timedelta

    today = ctx.stats.today()
    for offset, minutes in ((0, 90), (1, 60), (3, 45)):
        day = today - timedelta(days=offset)
        started = local(day.year, day.month, day.day, 9)
        ctx.sessions.create(
            started_at=started,
            ended_at=started + timedelta(minutes=minutes),
            active_seconds=minutes * 60,
            exam_id=sample_masters["exam_id"],
            material_id=sample_masters["material_id"],
            subject_id=sample_masters["subject_id"],
            correct=8,
            attempted=10,
        )
    return today


def test_dashboard_shows_today_and_week(qapp, ctx, sample_masters):
    from studylog.ui.modules.dashboard.view import DashboardView

    today = _seed_week(ctx, sample_masters)
    ctx.goals.set_week_goal(today, 10 * 3600)
    ctx.masters.set_exam_date(sample_masters["exam_id"], "2026-11-08")
    view = DashboardView(ctx)
    try:
        assert view.tile_today.value.text() == "1:30"
        assert "目標" in view.tile_week.note.text()
        assert view.tile_streak.value.text() == "2日"
        assert view.exams_body.count() == 1
    finally:
        view.deleteLater()
        qapp.processEvents()


def test_dashboard_button_opens_unclassified(qapp, ctx):
    from studylog.ui.main_window import MainWindow

    window = MainWindow(ctx)
    try:
        assert window.modules[window.nav.currentRow()].id == "dashboard"
        ctx.open_module("unclassified")
        assert window.modules[window.nav.currentRow()].id == "unclassified"
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()


def test_main_window_opens_timer_first_when_measuring(qapp, ctx, sample_masters):
    from studylog.ui.main_window import MainWindow

    ctx.timer.start(exam_id=sample_masters["exam_id"])
    window = MainWindow(ctx)
    try:
        assert window.modules[window.nav.currentRow()].id == "timer"
    finally:
        ctx.timer.discard()
        window.close()
        window.deleteLater()
        qapp.processEvents()


def test_stats_view_all_units(qapp, ctx, sample_masters):
    from studylog.ui.modules.stats.view import StatsView

    _seed_week(ctx, sample_masters)
    view = StatsView(ctx)
    try:
        assert view.tile_total.value.text() == "3:15"
        assert view.series_table.rowCount() == 30
        for index in range(view.unit.count()):
            view.unit.setCurrentIndex(index)
            qapp.processEvents()
            assert view.series_table.rowCount() > 0
        assert view.breakdowns["exam"].grid.count() > 0
        assert view.accuracy.grid.count() >= 4  # 1行＝名前・棒・値・補足
    finally:
        view.deleteLater()
        qapp.processEvents()


def test_goals_view_saves_week_goal(qapp, ctx, sample_masters, monkeypatch):
    from studylog.ui.modules.goals import view as goals_view

    monkeypatch.setattr(goals_view, "show_info", lambda *a, **k: None)
    view = goals_view.GoalsView(ctx)
    try:
        view.total_goal.setValue(12)
        view._exam_week_spins[sample_masters["exam_id"]].setValue(5)
        view._save_week()
        week_start = ctx.goals.week_start(ctx.goals.today())
        assert ctx.goals.week_goal(week_start).seconds == 12 * 3600
        assert ctx.goals.week_goal(week_start, sample_masters["exam_id"]).seconds == 5 * 3600

        view._exam_spins[sample_masters["exam_id"]].setValue(300)
        view._save_exam_goals()
        assert ctx.masters.exams.get(sample_masters["exam_id"]).goal_total_seconds == 300 * 3600

        # 0 にして保存すると、その週の設定は消えて前の週を引き継ぐ
        view.total_goal.setValue(0)
        view._save_week()
        assert ctx.goals.goals.exact(week_start) is None
    finally:
        view.deleteLater()
        qapp.processEvents()


# --- フェーズ4（計画） ------------------------------------------------------

def test_calendar_shows_month_and_week(qapp, ctx, sample_masters):
    from datetime import date, timedelta

    from studylog.ui.modules.calendar.view import CalendarView

    today = ctx.stats.today()
    ctx.plans.create(day=today, title="民法 問題集", planned_seconds=3600,
                     exam_id=sample_masters["exam_id"], time_of_day="09:00")
    ctx.plans.create(day=today, title="毎日の復習", planned_seconds=1800,
                     exam_id=sample_masters["exam_id"], repeat_rule="daily")
    ctx.masters.set_exam_date(sample_masters["exam_id"], (today + timedelta(days=3)).isoformat())

    view = CalendarView(ctx)
    try:
        assert f"{today.year}年{today.month}月" == view.range_label.text()
        shown = [cell.info.date for cell in view.grid.cells if cell.info and not cell.isHidden()]
        assert len(shown) in (35, 42)          # 月表示は5〜6週
        assert today in shown
        # 選んだ日の予定が右に2件出る
        view._on_day_selected(today)
        assert view.day_body.count() >= 2

        view._set_mode("week")
        shown = [cell.info.date for cell in view.grid.cells if cell.info and not cell.isHidden()]
        assert len(shown) == 7 and today in shown

        # 前の月へ移動しても落ちない
        view._set_mode("month")
        view._move(-1)
        view._go_today()
        assert view.anchor == today
    finally:
        view.deleteLater()
        qapp.processEvents()


def test_calendar_starts_timer_from_a_plan(qapp, ctx, sample_masters):
    from studylog.ui.modules.calendar.view import CalendarView

    today = ctx.stats.today()
    ctx.plans.create(day=today, title="民法 問題集", planned_seconds=3600, exam_id=sample_masters["exam_id"])
    view = CalendarView(ctx)
    try:
        occurrence = ctx.plans.for_day(today)[0]
        view._start_timer(occurrence)
        state = ctx.timer.current()
        assert state is not None
        assert state.exam_id == sample_masters["exam_id"]
        assert state.memo == "民法 問題集"
    finally:
        ctx.timer.discard()
        view.deleteLater()
        qapp.processEvents()


def test_calendar_builds_quotas_from_plans(qapp, ctx, sample_masters, monkeypatch):
    from studylog.ui.modules.calendar import view as calendar_view

    monkeypatch.setattr(calendar_view, "show_info", lambda *a, **k: None)
    today = ctx.stats.today()
    ctx.plans.create(day=today, title="民法 問題集", planned_seconds=3600, exam_id=sample_masters["exam_id"])
    view = calendar_view.CalendarView(ctx)
    try:
        view._build_quotas()
        quotas = ctx.quotas.list(today)
        assert len(quotas) == 1 and quotas[0].title == "民法 問題集"
    finally:
        view.deleteLater()
        qapp.processEvents()


def test_dashboard_lists_todays_plans(qapp, ctx, sample_masters):
    from studylog.ui.modules.dashboard.view import DashboardView

    today = ctx.stats.today()
    ctx.plans.create(day=today, title="朝の民法", planned_seconds=3600,
                     exam_id=sample_masters["exam_id"], time_of_day="07:30")
    view = DashboardView(ctx)
    try:
        texts = []
        for index in range(view.plans_body.count()):
            item = view.plans_body.itemAt(index)
            if item.layout():
                for sub in range(item.layout().count()):
                    widget = item.layout().itemAt(sub).widget()
                    if widget is not None and hasattr(widget, "text"):
                        texts.append(widget.text())
            elif item.widget() is not None and hasattr(item.widget(), "text"):
                texts.append(item.widget().text())
        assert any("朝の民法" in text for text in texts)
    finally:
        view.deleteLater()
        qapp.processEvents()
