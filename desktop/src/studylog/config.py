"""保存場所の解決とアプリ全体の定数。

データはインストール先ではなく、exe（開発時は desktop/）の隣の data/ に置く。
こうすると持ち運べるうえ、環境によって %APPDATA% が仮想化されて保存先が二重になる事故を避けられる。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "StudyLog"
APP_VERSION = "0.1.0"
SCHEMA_VERSION = 1  # 転送仕様書の schemaVersion

# 環境変数で保存先を差し替えられるようにしておく（テストと検証で使う）
ENV_DATA_DIR = "STUDYLOG_DATA_DIR"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def base_dir() -> Path:
    """exe（開発時は desktop/）が置かれているフォルダ。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    override = os.environ.get(ENV_DATA_DIR)
    if override:
        return Path(override).expanduser().resolve()
    return base_dir() / "data"


def db_path() -> Path:
    return data_dir() / "studylog.db"


def backup_dir() -> Path:
    return data_dir() / "backups"


def log_dir() -> Path:
    return data_dir() / "logs"


def default_sync_dir() -> Path:
    """子機とのやりとりに使う同期フォルダの既定値（設定で変更できる）。"""
    return data_dir() / "sync"


def ensure_dirs() -> None:
    for path in (data_dir(), backup_dir(), log_dir()):
        path.mkdir(parents=True, exist_ok=True)
