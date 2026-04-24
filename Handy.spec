# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

project_root = Path.cwd()
model_file = project_root / "hand_landmarker.task"
icon_file = os.environ.get("HANDY_ICON_ICO")
build_target = os.environ.get("HANDY_BUILD_TARGET", "portable")

datas = []
binaries = []
hiddenimports = []

for package_name in ("mediapipe", "cv2", "customtkinter"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package_name)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

if model_file.exists():
    datas.append((str(model_file), "."))

hiddenimports += [
    "mediapipe.python.solutions.hands",
    "mediapipe.python.solutions.drawing_utils",
    "mediapipe.tasks",
    "mediapipe.tasks.python",
    "mediapipe.tasks.python.vision",
    "mediapipe.tasks.c",
    "mediapipe.tasks.cc",
    "customtkinter",
    "pynput",
    "pynput.mouse",
    "pynput.keyboard",
    "handy",
    "handy.config",
    "handy.state",
    "handy.gesture",
    "handy.drawing",
    "handy.mouse",
    "handy.model",
    "handy.camera",
    "handy.ui",
    "handy.ui.loading",
    "handy.ui.settings",
]
hiddenimports = list(dict.fromkeys(hiddenimports))

a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if build_target == "installer":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="Handy",
        icon=icon_file if icon_file and Path(icon_file).exists() else None,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
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
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="Handy",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="Handy",
        icon=icon_file if icon_file and Path(icon_file).exists() else None,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
