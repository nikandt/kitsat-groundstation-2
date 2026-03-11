# PyInstaller spec — Linux
# Usage: pyinstaller packaging/build_linux.spec
# Output: dist/KitsatGS/KitsatGS  (then wrap with appimage-builder)

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
    runtime_hooks=[],
    excludes=[],
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
    strip=True,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name="KitsatGS",
)
