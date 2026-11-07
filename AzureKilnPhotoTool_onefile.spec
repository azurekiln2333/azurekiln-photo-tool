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
    "exiftool_resolver",
]

for package_name in ("qfluentwidgets", "qframelesswindow"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

# Bundle ExifTool so every page that reads/writes metadata works out of the box.
# Layout matches exiftool_resolver._candidate_dirs(), which probes sys._MEIPASS:
#   _MEIPASS/exiftool_files/{perl.exe,exiftool.pl,lib}  -> perl 直调模式（onefile 下唯一可靠）
#   _MEIPASS/exiftool.exe                               -> stub 直调模式（回退）
# 注意：perl.exe 依赖的 DLL 必须与 perl.exe 同目录，因此整个 exiftool_files 原样打包。
exiftool_dir = Path(os.environ.get("EXIFTOOL_DIR", r"D:\ProgramFiles\exiftool"))
if os.environ.get("CI"):
    # CI 构建：缺 ExifTool 必须失败，避免发布不含 ExifTool 的产物（本地行为不变）。
    _missing = [
        str(p)
        for p in (
            exiftool_dir / "exiftool.exe",
            exiftool_dir / "exiftool_files" / "perl.exe",
            exiftool_dir / "exiftool_files" / "exiftool.pl",
            exiftool_dir / "exiftool_files" / "lib",
        )
        if not p.exists()
    ]
    if _missing:
        raise SystemExit(
            "[spec] CI build requires ExifTool (set EXIFTOOL_DIR). Missing: " + ", ".join(_missing)
        )
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
else:
    print(f"[spec] 警告：未找到 ExifTool 目录 {exiftool_dir}，打包结果将不含 ExifTool")


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
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AzureKilnPhotoTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        "vcruntime140.dll",
        "python3*.dll",
        "Qt6Core.dll",
        "Qt6Gui.dll",
        "Qt6Widgets.dll",
        "exiftool.exe",
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
