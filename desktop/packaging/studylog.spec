# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller の設定（onedir方式）。

onedir にする理由：起動が速く、ウイルス対策ソフトの誤検知も少ない。
データは exe の隣の data/ に作られるので、フォルダごと持ち運べる。

動作確認をするときは console=True にすると、起動時の例外が見える。
"""

import os
import sys

from PyInstaller.utils.hooks import collect_submodules

PROJECT_DIR = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC_DIR = os.path.join(PROJECT_DIR, "src")

# collect_submodules は解析中にパッケージをimportできる必要がある
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# ui/modules/ は実行時に動的に読み込むので、明示的に含める
hidden = collect_submodules("studylog.ui.modules")
if not hidden:
    raise SystemExit("ui/modules を収集できませんでした（src がパスに入っているか確認）")

a = Analysis(
    [os.path.join(SRC_DIR, "studylog", "__main__.py")],
    pathex=[SRC_DIR],
    binaries=[],
    datas=[
        (os.path.join(SRC_DIR, "studylog", "db", "migrations"), "studylog/db/migrations"),
        # 転送パッケージの検証に使う JSON Schema（spec/schemas と同じもの）
        (os.path.join(SRC_DIR, "studylog", "schemas"), "studylog/schemas"),
    ],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DRender",
        "PySide6.QtBluetooth",
        "PySide6.QtDesigner",
        "PySide6.QtHelp",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtNfc",
        "PySide6.QtPositioning",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtQuickWidgets",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtSpatialAudio",
        "PySide6.QtTest",
        "PySide6.QtTextToSpeech",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebSockets",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StudyLog",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="StudyLog",
)
