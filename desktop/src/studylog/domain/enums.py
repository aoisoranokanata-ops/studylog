"""区分値と、その日本語表示。UIはここを参照する。"""

from __future__ import annotations

EXAM_STATUS = {
    "studying": "学習中",
    "taken": "受験済",
    "passed": "合格",
    "failed": "不合格",
    "paused": "中断",
}

MATERIAL_TYPE = {
    "text": "テキスト",
    "drill": "問題集",
    "past": "過去問",
    "lecture": "講義",
    "other": "その他",
}

RANGE_UNIT = {
    "page": "ページ",
    "question": "問",
}

ENTRY_MODE = {
    "timer": "計測",
    "manual": "手動",
}

SOURCE = {
    "hub": "母艦",
    "satellite": "子機",
}

QUOTA_STATUS = {
    "none": "未着手",
    "partial": "一部",
    "done": "完了",
    "skipped": "スキップ",
}

MISTAKE_REASON = {
    "knowledge": "知識不足",
    "misread": "読み違い",
    "careless": "ケアレスミス",
    "confusion": "混同",
    "other": "その他",
}

MASTERY = {
    "unmastered": "未克服",
    "reviewing": "復習中",
    "mastered": "克服",
}

FOCUS_LEVELS = {
    1: "1 散漫",
    2: "2",
    3: "3 ふつう",
    4: "4",
    5: "5 集中",
}


def label(mapping: dict, key, default: str = "") -> str:
    if key is None:
        return default
    return mapping.get(key, str(key))
