# -*- mode: python ; coding: utf-8 -*-
import os
import mediapipe

# Bundle the entire mediapipe package (includes .pyd/.so and data files)
mediapipe_path = os.path.dirname(mediapipe.__file__)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        (mediapipe_path, 'mediapipe'),
        ('icon.png', '.'),
        ('hand_landmarker.task', '.'),
    ],
    hiddenimports=[
        'mediapipe',
        'mediapipe.tasks',
        'mediapipe.tasks.python',
        'mediapipe.tasks.python.vision',
        'mediapipe.tasks.python.core',
        'mediapipe.python',
        'mediapipe.python.solutions',
        'mediapipe.python.solutions.hands',
        'mediapipe.python.solutions.drawing_utils',
        'customtkinter',
        'pynput',
        'pynput.keyboard',
        'pynput.mouse',
        'pynput._util',
        'pynput._util.win32',
        'cv2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Handy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.png',
)
