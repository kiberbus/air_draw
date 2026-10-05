# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Air Draw.

- Windows / Linux: a single self-contained executable (dist/AirDraw[.exe]).
- macOS: an app bundle (dist/AirDraw.app) with camera permission text.

Build with:  pyinstaller air_draw.spec --clean --noconfirm
"""
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

IS_MACOS = sys.platform == "darwin"

# MediaPipe loads its .tflite models and graphs from package data at runtime
mediapipe_datas = collect_data_files('mediapipe')
mediapipe_modules = collect_submodules('mediapipe')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=mediapipe_datas,
    hiddenimports=[
        'cv2',
        'mediapipe',
        'mediapipe.python.solutions',
        'mediapipe.python.solutions.hands',
        'mediapipe.python.solutions.drawing_utils',
        'mediapipe.python.solutions.drawing_styles',
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'psutil',
        'numpy',
    ] + mediapipe_modules,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

if IS_MACOS:
    # macOS: one-folder build wrapped into AirDraw.app
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='AirDraw',
        debug=False,
        strip=False,
        upx=False,
        console=False,
        argv_emulation=False,
    )
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='AirDraw')
    app = BUNDLE(
        coll,
        name='AirDraw.app',
        bundle_identifier='com.kiberbus.airdraw',
        info_plist={
            'CFBundleDisplayName': 'Air Draw',
            'CFBundleShortVersionString': '1.0.0',
            # Without this key macOS denies camera access to the app
            'NSCameraUsageDescription': 'Air Draw uses the camera to track your hand for drawing.',
            'NSHighResolutionCapable': True,
        },
    )
else:
    # Windows / Linux: everything packed into a single executable
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='AirDraw',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
    )
