"""ログの設定。"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import config

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup(level: int = logging.INFO) -> None:
    config.ensure_dirs()
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(level)

    file_handler = RotatingFileHandler(
        config.log_dir() / "studylog.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(file_handler)

    if not config.is_frozen():
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(stream)
