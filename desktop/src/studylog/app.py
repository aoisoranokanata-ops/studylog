"""アプリの起動。"""

from __future__ import annotations

import logging
import os
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from . import config, logging_setup
from .context import AppContext

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    logging_setup.setup()
    log.info("%s %s を起動する（データ: %s）", config.APP_NAME, config.APP_VERSION, config.data_dir())

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationDisplayName(config.APP_NAME)

    try:
        ctx = AppContext.open()
    except Exception as error:  # 起動できないときは理由を見せる
        log.exception("起動に失敗した")
        QMessageBox.critical(
            None,
            f"{config.APP_NAME} を起動できません",
            f"{error}\n\nログ: {config.log_dir()}",
        )
        return 1

    from .ui.main_window import MainWindow

    window = MainWindow(ctx)
    window.show()

    # 起動確認用の逃げ道（環境変数で指定したミリ秒後に自分で終了する）
    autoquit = os.environ.get("STUDYLOG_AUTOQUIT_MS")
    if autoquit and autoquit.isdigit():
        from PySide6.QtCore import QTimer

        QTimer.singleShot(int(autoquit), app.quit)
        log.info("%sミリ秒後に自動終了する", autoquit)

    try:
        code = app.exec()
    finally:
        ctx.close()
        log.info("終了する")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
