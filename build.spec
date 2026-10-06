# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DupliPix (تشخیص عکس‌های تکراری).

Produces a self-contained ``dist/DupliPix`` directory that runs
on a clean Windows machine with no Python installed.

Optional dependencies (``torch`` / ``open_clip_torch`` / ``psutil``) are *not*
bundled: the application degrades gracefully without them and shipping torch
would multiply the archive size by ~2 GB. The settings page simply reports the
AI engines as unavailable.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

hiddenimports = []
# ``src`` is imported as a package tree; PyInstaller's static analysis follows
# the normal imports, but these are reached dynamically in places.
hiddenimports += collect_submodules("src")
hiddenimports += ["sqlite3", "hashlib", "ctypes", "json"]

datas = []
# Persian / English translation dictionaries and any shipped assets.
datas += collect_data_files("src.i18n", include_py_files=False)
datas += [("assets", "assets")]
# ``database.py`` reads the schema SQL from ``src/database/migrations`` at
# runtime via ``os.path.dirname(__file__)``, so the scripts must be bundled.
datas += [("src/database/migrations", "src/database/migrations")]
# ``i18n`` loads fa.json / en.json next to the package at runtime.
datas += [("src/i18n", "src/i18n")]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy optional stacks the app never needs at runtime.
        "torch",
        "open_clip_torch",
        "psutil",
        "matplotlib",
        "scipy",
        "pandas",
        "tkinter",
        "PySide6.Qt3D",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtNetwork",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebChannel",
        "PySide6.QtMultimedia",
        "PySide6.QtSensors",
        "PySide6.QtPositioning",
        "PySide6.QtLocation",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtSerialPort",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtStateMachine",
        "PySide6.QtSpatialAudio",
        "PySide6.QtTextToSpeech",
        "PySide6.QtUiTools",
        "PySide6.QtHelp",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtQuick3D",
        "PySide6.QtQuickControls2",
        "PySide6.QtQuickTemplates2",
        "PySide6.QtPrintSupport",
        "PySide6.QtSvgWidgets",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtDesigner",
        "PySide6.QtAxContainer",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DupliPix",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DupliPix",
)
