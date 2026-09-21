"""QR・文字列用のエンコードとデコード（転送仕様書 第6章）。

JSON → deflate-raw圧縮 → base64url → 先頭に `SL1:`。
`SL1` の数字は schemaVersion と連動する。
"""

from __future__ import annotations

import base64
import json
import zlib

from ... import config

PREFIX_TEMPLATE = "SL{version}:"
QR_BYTE_LIMIT = 1800


class CodecError(ValueError):
    """文字列を読めなかった。"""


def prefix(version: int = config.SCHEMA_VERSION) -> str:
    return PREFIX_TEMPLATE.format(version=version)


def encode(package: dict, *, version: int = config.SCHEMA_VERSION) -> str:
    raw = json.dumps(package, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressor = zlib.compressobj(level=9, wbits=-15)  # -15 = deflate-raw（ヘッダなし）
    compressed = compressor.compress(raw) + compressor.flush()
    encoded = base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")
    return prefix(version) + encoded


def decode(text: str) -> dict:
    value = text.strip()
    if not value.startswith("SL"):
        raise CodecError("`SL1:` で始まる文字列ではありません")
    head, _, body = value.partition(":")
    if not body:
        raise CodecError("`SL1:` の後ろが空です")
    try:
        version = int(head[2:])
    except ValueError as error:
        raise CodecError(f"バージョンを読めません: {head}") from error
    if version > config.SCHEMA_VERSION:
        raise CodecError(
            f"このアプリが対応していない形式です（SL{version}）。アプリの更新が必要です。"
        )

    padded = body + "=" * (-len(body) % 4)
    try:
        compressed = base64.urlsafe_b64decode(padded)
        raw = zlib.decompress(compressed, wbits=-15)
        return json.loads(raw.decode("utf-8"))
    except (ValueError, zlib.error, UnicodeDecodeError) as error:
        raise CodecError(f"読み取れませんでした（壊れている可能性があります）: {error}") from error


def byte_length(text: str) -> int:
    """QRに載せるときの長さ（`SL1:` 込みのUTF-8バイト数）。"""
    return len(text.encode("utf-8"))


def fits_in_qr(text: str, limit: int = QR_BYTE_LIMIT) -> bool:
    return byte_length(text) <= limit
