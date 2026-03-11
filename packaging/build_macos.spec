# PyInstaller spec — macOS
# Usage: pyinstaller packaging/build_macos.spec
# Output: dist/KitsatGS.app  (then wrap with create-dmg)
#
# Note: macOS will show a Gatekeeper warning without code signing.
# Users right-click → Open → "Open Anyway" to bypass.
# For signed distribution, an Apple Developer Program membership ($99/yr)
# is required.

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
    strip=False,
    upx=False,      # upx can break macOS code signing
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="KitsatGS",
)

app = BUNDLE(
    coll,
    name="KitsatGS.app",
    icon=str(PKG / "assets" / "icon.icns") if (PKG / "assets" / "icon.icns").exists() else None,
    bundle_identifier="fi.kitsat.groundstation",
    info_plist={
        "CFBundleShortVersionString": "2.0.0",
        "CFBundleVersion": "2.0.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
    },
)
