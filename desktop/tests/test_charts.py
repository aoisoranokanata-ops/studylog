"""自前のグラフ部品のテスト（目盛り・ラベルの間引き・マウスでの値表示）。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from studylog.ui.widgets.charts import BarItem, BarList, ColumnChart, nice_step  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    ("peak", "step"),
    [(0.4, 0.1), (1.3, 0.5), (3.4, 1.0), (4.6, 2.0), (9, 2.5), (17.5, 5.0), (42, 20.0)],
)
def test_nice_step(peak, step):
    assert nice_step(peak) == pytest.approx(step)


def test_scale_covers_the_peak_with_round_ticks(qapp):
    chart = ColumnChart()
    chart.set_data(["a", "b"], [3 * 3600 + 1200, 1800])  # 3.33時間
    step, top = chart.scale()
    assert step == 1.0 and top == 4.0
    assert chart.format_tick(2.0) == "2"
    assert chart.format_tick(2.5) == "2.5"


def test_goal_line_is_included_in_scale(qapp):
    chart = ColumnChart()
    chart.set_data(["a", "b"], [3600, 3600], goal_seconds=[20 * 3600, 20 * 3600])
    _, top = chart.scale()
    assert top >= 20


def test_labels_are_thinned_without_overlap_and_keep_the_last(qapp):
    chart = ColumnChart()
    labels = [f"9/{day}" for day in range(1, 31)]
    chart.set_data(labels, [1800] * 30)
    shown = chart.visible_label_indexes(slot=20, widest=30)
    assert shown[-1] == 29                       # 最後の期間は必ず出す
    gaps = {b - a for a, b in zip(shown, shown[1:])}
    assert len(gaps) == 1 and gaps.pop() * 20 >= 30 + 12   # 等間隔で、ラベル幅より広い

    # 余裕があれば全部出す
    assert chart.visible_label_indexes(slot=80, widest=30) == list(range(30))


def test_hover_shows_period_value_and_goal(qapp):
    chart = ColumnChart()
    chart.resize(600, 300)
    chart.set_data(["9/14〜", "9/21〜"], [5 * 3600, 3600], goal_seconds=[18 * 3600, 18 * 3600])
    chart.grab()  # 一度描いて描画範囲を決める
    assert chart.index_at(chart._plot.left() + 5) == 0
    assert chart.index_at(chart._plot.right() - 5) == 1
    assert chart.index_at(0) == -1
    assert chart.tooltip_text(0) == "9/14〜　5:00（目標 18:00）"


def test_empty_chart_paints(qapp):
    chart = ColumnChart()
    chart.resize(300, 200)
    chart.set_data([], [])
    assert not chart.grab().isNull()


def test_bar_list_folds_the_rest_into_other(qapp):
    bar_list = BarList(limit=3)
    items = [BarItem(f"分野{i}", 1 - i / 10, f"{i}:00") for i in range(5)]
    bar_list.set_items(items, other=BarItem("その他（3件）", 0.2, "1:00"))
    names = [bar_list.grid.itemAtPosition(row, 0).widget().text() for row in range(bar_list.grid.rowCount())
             if bar_list.grid.itemAtPosition(row, 0)]
    assert names == ["分野0", "分野1", "その他（3件）"]


def test_bar_list_shows_empty_text(qapp):
    bar_list = BarList(empty_text="なし")
    bar_list.set_items([])
    assert bar_list.grid.itemAt(0).widget().text() == "なし"
