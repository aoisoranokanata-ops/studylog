"""QRコードの表示。

`qrcode` ライブラリで行列だけ作り、描画はQtで行う（画像ライブラリに依存させないため）。
誤り訂正レベルは仕様書どおり M 固定。
"""

from __future__ import annotations

import qrcode
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ....services.transfer import codec


def make_pixmap(text: str, *, target_px: int = 660) -> QPixmap:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=4,
    )
    qr.add_data(text)
    qr.make(fit=True)
    matrix = qr.get_matrix()

    modules = len(matrix)
    scale = max(1, target_px // modules)
    size = modules * scale

    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("white"))
    painter = QPainter(pixmap)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("black"))
    for row, line in enumerate(matrix):
        for column, filled in enumerate(line):
            if filled:
                painter.drawRect(column * scale, row * scale, scale, scale)
    painter.end()
    return pixmap


class QrDialog(QDialog):
    def __init__(self, text: str, *, caption: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("QRコードで渡す")

        layout = QVBoxLayout(self)
        image = QLabel(self)
        image.setPixmap(make_pixmap(text))
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(image)

        info = QLabel(
            f"{caption}\n"
            f"{codec.byte_length(text)} バイト（上限 {codec.QR_BYTE_LIMIT}）／誤り訂正レベル M",
            self,
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("閉じる")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
