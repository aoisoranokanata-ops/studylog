"""機能モジュールの登録口。

`ui/modules/` の下にフォルダを1つ作り、`MODULE = FeatureModule(...)` を定義すれば、
それだけでナビゲーションに現れる。母艦は今後も機能が増えるので、追加の手間をここに集約する。
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 実行時にQtを読み込まないようにする（テストを軽くするため）
    from PySide6.QtWidgets import QWidget

    from ..context import AppContext

log = logging.getLogger(__name__)

MODULES_PACKAGE = "studylog.ui.modules"


@dataclass(frozen=True)
class FeatureModule:
    id: str
    title: str
    order: int
    factory: "Callable[[AppContext], QWidget]"
    description: str = ""
    shortcut: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


def discover(package_name: str = MODULES_PACKAGE) -> list[FeatureModule]:
    """モジュールを集めて、order順に並べて返す。"""
    package = importlib.import_module(package_name)
    found: list[FeatureModule] = []
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_"):
            continue
        full_name = f"{package_name}.{info.name}"
        try:
            module = importlib.import_module(full_name)
        except Exception:
            log.exception("モジュールを読み込めなかった: %s", full_name)
            continue
        feature = getattr(module, "MODULE", None)
        if isinstance(feature, FeatureModule):
            found.append(feature)
        else:
            log.warning("MODULE が定義されていない: %s", full_name)
    found.sort(key=lambda item: (item.order, item.title))
    return found
