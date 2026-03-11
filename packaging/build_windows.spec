# PyInstaller spec — Windows
# Usage: pyinstaller packaging/build_windows.spec
# Output: dist/KitsatGS/KitsatGS.exe

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
PKG  = ROOT / "kitsat_gs"

block_cipher = None

a = Analysis(
    [str(ROOT / "kitsat_gs" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(PKG / "assets"),  "kitsat_gs/assets"),
        (str(PKG / "cfg"),     "kitsat_gs/cfg"),
    ],
    hiddenimports=[
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "pyqtgraph",
        "folium",
        "sgp4",
        "kitsat",
        "loguru",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="KitsatGS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(PKG / "assets" / "icon.ico") if (PKG / "assets" / "icon.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="KitsatGS",
)
