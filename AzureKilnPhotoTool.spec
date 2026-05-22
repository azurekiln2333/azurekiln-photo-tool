# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


datas = []
binaries = []
hiddenimports = [
    "pillow_heif",
    "send2trash",
    "win32com",
    "win32com.shell",
    "win32timezone",
]

for package_name in ("qfluentwidgets", "qframelesswindow"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

exiftool_dir = Path(os.environ.get("EXIFTOOL_DIR", r"D:\ProgramFiles\exiftool"))
if exiftool_dir.exists():
    exiftool_exe = exiftool_dir / "exiftool.exe"
    exiftool_files = exiftool_dir / "exiftool_files"
    if exiftool_exe.exists():
        datas.append((str(exiftool_exe), "."))
    if exiftool_files.exists():
        for path in exiftool_files.rglob("*"):
            if path.is_file():
                target_dir = Path("exiftool_files") / path.relative_to(exiftool_files).parent
                datas.append((str(path), str(target_dir)))


a = Analysis(
    ["unified_gui.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt6.QtNetwork",
        "PyQt6.QtOpenGL",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtSql",
        "PyQt6.QtTest",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AzureKilnPhotoTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name="AzureKilnPhotoTool",
)
