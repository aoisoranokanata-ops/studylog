"""誤答。一覧と編集、母艦での復習、苦手分析の3つのタブ。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ....context import AppContext
from ....domain import enums
from ...widgets.charts import BarItem, BarList, Meter, Panel, StatTile, TEXT_MUTED
from ...widgets.common import NONE_VALUE, combo_id, confirm, fill_combo, heading, show_error
from .dialog import MistakeDialog

COLUMNS = ["問題", "メモ", "正解・ポイント", "資格", "分野", "理由", "習熟", "次回"]


class ListTab(QWidget):
    """誤答の一覧。絞り込みと、克服の切り替え。"""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._rows: list = []

        layout = QVBoxLayout(self)
        filters = QHBoxLayout()
        self.exam = QComboBox(self)
        self.mastery = QComboBox(self)
        self.mastery.addItem("すべて", NONE_VALUE)
        for key, label in enums.MASTERY.items():
            self.mastery.addItem(label, key)
        self.reason = QComboBox(self)
        self.reason.addItem("すべて", NONE_VALUE)
        for key, label in enums.MISTAKE_REASON.items():
            self.reason.addItem(label, key)
        self.keyword = QLineEdit(self)
        self.keyword.setPlaceholderText("問題・メモを検索")
        for widget in (self.exam, self.mastery, self.reason):
            widget.currentIndexChanged.connect(self.refresh)
        self.keyword.textChanged.connect(self.refresh)
        filters.addWidget(QLabel("資格"))
        filters.addWidget(self.exam)
        filters.addWidget(QLabel("習熟"))
        filters.addWidget(self.mastery)
        filters.addWidget(QLabel("理由"))
        filters.addWidget(self.reason)
        filters.addWidget(self.keyword, 1)
        layout.addLayout(filters)

        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._edit)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.summary = QLabel(self)
        buttons.addWidget(self.summary)
        buttons.addStretch(1)
        for text, slot in (
            ("追加", self._add),
            ("編集", self._edit),
            ("克服にする", lambda: self._set_mastery("mastered")),
            ("復習に戻す", lambda: self._set_mastery("reviewing")),
            ("削除", self._delete),
        ):
            button = QPushButton(text, self)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.refresh()

    def refresh(self) -> None:
        current = combo_id(self.exam)
        self.exam.blockSignals(True)
        fill_combo(
            self.exam,
            [(exam.id, exam.name) for exam in self.ctx.masters.list_exams(include_archived=True)],
            current=current,
            empty_label="すべて",
        )
        self.exam.blockSignals(False)

        mastery = self.mastery.currentData()
        reason = self.reason.currentData()
        self._rows = self.ctx.mistakes.search(
            exam_id=combo_id(self.exam),
            mastery=None if mastery == NONE_VALUE else mastery,
            reason=None if reason == NONE_VALUE else reason,
            keyword=self.keyword.text().strip(),
            limit=500,
        )

        self.table.setRowCount(len(self._rows))
        for row, mistake in enumerate(self._rows):
            labels = self.ctx.masters.labels_for(mistake.exam_id, mistake.material_id, mistake.subject_id)
            values = [
                mistake.question_ref,
                mistake.memo,
                mistake.answer_memo,
                labels["exam"] or "未分類",
                labels["subject"] or "",
                enums.label(enums.MISTAKE_REASON, mistake.reason),
                enums.label(enums.MASTERY, mistake.mastery),
                mistake.next_review_on.isoformat() if mistake.next_review_on else "—",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        for column in (1, 2):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)

        counts = self.ctx.mistakes.counts(combo_id(self.exam))
        self.summary.setText(
            f"{len(self._rows)}件を表示　（未克服 {counts['unmastered']}／克服 {counts['mastered']}）"
        )

    def _selected(self):
        row = self.table.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _add(self) -> None:
        dialog = MistakeDialog(self.ctx, parent=self)
        if not dialog.exec():
            return
        values = dialog.values()
        try:
            self.ctx.mistakes.create(**values)
        except ValueError as error:
            show_error(self, str(error))
            return
        self.refresh()

    def _edit(self) -> None:
        mistake = self._selected()
        if mistake is None:
            show_error(self, "誤答を選んでください")
            return
        dialog = MistakeDialog(self.ctx, mistake, parent=self)
        if not dialog.exec():
            return
        try:
            self.ctx.mistakes.update(mistake.id, dialog.values())
        except ValueError as error:
            show_error(self, str(error))
            return
        self.refresh()

    def _set_mastery(self, mastery: str) -> None:
        mistake = self._selected()
        if mistake is None:
            show_error(self, "誤答を選んでください")
            return
        self.ctx.mistakes.set_mastery(mistake.id, mastery)
        self.refresh()

    def _delete(self) -> None:
        mistake = self._selected()
        if mistake is None:
            show_error(self, "誤答を選んでください")
            return
        if confirm(self, f"「{mistake.question_ref}」を削除しますか？"):
            self.ctx.mistakes.delete(mistake.id)
            self.refresh()


class ReviewTab(QWidget):
    """母艦での「今日の復習」。1件ずつ出し、できた／できなかったを記録する。"""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.skipped: set[str] = set()

        layout = QVBoxLayout(self)
        self.progress = QLabel(self)
        layout.addWidget(self.progress)
        self.meter = Meter(self, height=8)
        layout.addWidget(self.meter)

        self.card = Panel("")
        self.where = QLabel(self.card)
        self.where.setStyleSheet(f"color: {TEXT_MUTED.name()};")
        self.question = QLabel(self.card)
        font = self.question.font()
        font.setPointSize(font.pointSize() + 8)
        font.setBold(True)
        self.question.setFont(font)
        self.question.setWordWrap(True)
        self.reveal = QPushButton("メモと正解を見る", self.card)
        self.reveal.clicked.connect(self._reveal)
        self.memo = QLabel(self.card)
        self.memo.setWordWrap(True)
        self.answer = QLabel(self.card)
        self.answer.setWordWrap(True)
        self.answer.setStyleSheet("background: #eef3fb; padding: 8px; border-radius: 6px;")
        for widget in (self.where, self.question, self.reveal, self.memo, self.answer):
            self.card.body.addWidget(widget)
        layout.addWidget(self.card)

        buttons = QHBoxLayout()
        self.ng_button = QPushButton("できなかった", self)
        self.ng_button.clicked.connect(lambda: self._answer("ng"))
        self.ok_button = QPushButton("できた", self)
        self.ok_button.clicked.connect(lambda: self._answer("ok"))
        self.skip_button = QPushButton("あとで", self)
        self.skip_button.clicked.connect(self._skip)
        for button in (self.ng_button, self.ok_button):
            button.setMinimumHeight(48)
        buttons.addWidget(self.ng_button)
        buttons.addWidget(self.ok_button)
        buttons.addWidget(self.skip_button)
        layout.addLayout(buttons)

        self.empty = QLabel("今日の復習対象はありません。", self)
        self.empty.setStyleSheet(f"color: {TEXT_MUTED.name()};")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty)
        layout.addStretch(1)

        self.current = None
        self.refresh()

    def refresh(self) -> None:
        due = self.ctx.mistakes.due()
        remaining = [mistake for mistake in due if mistake.id not in self.skipped]
        self.progress.setText(
            f"今日の復習：残り {len(remaining)}件"
            + (f"（あとで {len(due) - len(remaining)}件）" if len(due) != len(remaining) else "")
        )
        self.meter.set_ratio(0 if not due else 1 - len(remaining) / len(due))

        has_any = bool(remaining)
        self.card.setVisible(has_any)
        self.empty.setVisible(not has_any)
        for button in (self.ok_button, self.ng_button, self.skip_button):
            button.setVisible(has_any)
        if not has_any:
            self.current = None
            return

        mistake = remaining[0]
        self.current = mistake
        labels = self.ctx.masters.labels_for(mistake.exam_id, mistake.material_id, mistake.subject_id)
        where = "　".join(part for part in (labels["exam"], labels["material"], labels["subject"]) if part)
        late = (self.ctx.mistakes.today() - mistake.next_review_on).days if mistake.next_review_on else 0
        self.where.setText(where + (f"　{late}日遅れ" if late > 0 else ""))
        self.question.setText(mistake.question_ref)
        self.memo.setText(mistake.memo)
        self.answer.setText(mistake.answer_memo or "（正解・ポイントは未記入）")
        self.memo.setVisible(False)
        self.answer.setVisible(False)
        self.reveal.setVisible(True)

    def _reveal(self) -> None:
        self.memo.setVisible(True)
        self.answer.setVisible(True)
        self.reveal.setVisible(False)

    def _answer(self, result: str) -> None:
        if self.current is None:
            return
        self.ctx.mistakes.answer(self.current.id, result)
        self.refresh()

    def _skip(self) -> None:
        if self.current is not None:
            self.skipped.add(self.current.id)
        self.refresh()


class WeakTab(QWidget):
    """苦手分析。誤答の多い分野・参考書と、理由の内訳。"""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        layout = QVBoxLayout(self)
        filters = QHBoxLayout()
        self.exam = QComboBox(self)
        self.exam.currentIndexChanged.connect(self.refresh)
        filters.addWidget(QLabel("資格"))
        filters.addWidget(self.exam)
        filters.addStretch(1)
        layout.addLayout(filters)

        tiles = QHBoxLayout()
        self.tile_total = StatTile("誤答の数")
        self.tile_unmastered = StatTile("未克服")
        self.tile_due = StatTile("今日の復習")
        for tile in (self.tile_total, self.tile_unmastered, self.tile_due):
            tiles.addWidget(tile, 1)
        layout.addLayout(tiles)

        panels = QHBoxLayout()
        self.subject_panel = Panel("誤答が多い分野（棒は未克服の数）")
        self.subjects = BarList(limit=10, empty_text="誤答がまだありません")
        self.subject_panel.body.addWidget(self.subjects)
        self.subject_panel.body.addStretch(1)

        self.material_panel = Panel("誤答が多い参考書")
        self.materials = BarList(limit=10, empty_text="誤答がまだありません")
        self.material_panel.body.addWidget(self.materials)
        self.material_panel.body.addStretch(1)

        self.reason_panel = Panel("誤答の理由")
        self.reasons = BarList(limit=6, empty_text="理由の記録がありません")
        self.reason_panel.body.addWidget(self.reasons)
        self.reason_panel.body.addStretch(1)

        panels.addWidget(self.subject_panel, 1)
        panels.addWidget(self.material_panel, 1)
        panels.addWidget(self.reason_panel, 1)
        layout.addLayout(panels)
        layout.addStretch(1)

        self.refresh()

    def refresh(self) -> None:
        current = combo_id(self.exam)
        self.exam.blockSignals(True)
        fill_combo(
            self.exam,
            [(exam.id, exam.name) for exam in self.ctx.masters.list_exams(include_archived=True)],
            current=current,
            empty_label="すべて",
        )
        self.exam.blockSignals(False)
        exam_id = combo_id(self.exam)

        counts = self.ctx.mistakes.counts(exam_id)
        self.tile_total.set(f"{counts['total']}件", "")
        self.tile_unmastered.set(f"{counts['unmastered']}件", "克服できていないもの")
        self.tile_due.set(f"{counts['due']}件", "今日が復習日のもの")

        for bar_list, by in ((self.subjects, "subject"), (self.materials, "material")):
            rows = self.ctx.mistakes.weak_ranking(by, exam_id)
            peak = max((row.unmastered for row in rows), default=0) or 1
            bar_list.set_items(
                [
                    BarItem(
                        row.label, row.unmastered / peak, f"{row.unmastered}件",
                        f"全{row.total}件中", tooltip=f"{row.label}：未克服 {row.unmastered} / 全 {row.total}",
                    )
                    for row in rows
                ]
            )

        reasons = self.ctx.mistakes.reason_breakdown(exam_id)
        total = sum(count for _, count in reasons) or 1
        peak = max((count for _, count in reasons), default=0) or 1
        self.reasons.set_items(
            [
                BarItem(
                    enums.label(enums.MISTAKE_REASON, key) or "（未選択）",
                    count / peak,
                    f"{count}件",
                    f"{count / total:.0%}",
                )
                for key, count in reasons
            ]
        )


class MistakesView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(heading("誤答"))

        self.tabs = QTabWidget(self)
        self.list_tab = ListTab(ctx, self)
        self.review_tab = ReviewTab(ctx, self)
        self.weak_tab = WeakTab(ctx, self)
        self.tabs.addTab(self.list_tab, "一覧")
        self.tabs.addTab(self.review_tab, "今日の復習")
        self.tabs.addTab(self.weak_tab, "苦手分析")
        self.tabs.currentChanged.connect(lambda _: self.refresh())
        layout.addWidget(self.tabs, 1)

    def refresh(self) -> None:
        current = self.tabs.currentWidget()
        if hasattr(current, "refresh"):
            current.refresh()
