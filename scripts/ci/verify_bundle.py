"""Verify that the onefile exe bundles the runtime media stack.

Usage:
    python scripts/ci/verify_bundle.py [dist/AzureKilnPhotoTool.exe]

Checks pillow_heif (HEIC), send2trash (回收站), ExifTool, and the QtMultimedia
FFmpeg backend used for video first-frame fallbacks (media_thumbnail.py).
Reads the PyInstaller CArchive (and embedded PYZ) table of contents without running the exe.
Exit code 1 if any required entry is missing.
"""

from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader, NotAnArchiveError

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXE = REPO_ROOT / "dist" / "AzureKilnPhotoTool.exe"

# Exact data entries (relative to _MEIPASS) required by exiftool_resolver._candidate_dirs().
REQUIRED_FILES = (
    "exiftool.exe",
    "exiftool_files/perl.exe",
    "exiftool_files/exiftool.pl",
)
REQUIRED_PREFIXES = (
    "exiftool_files/lib/",
)

# Video first-frame fallback: PyQt6 wheel ships the Qt FFmpeg media backend plus its
# av*/sw* DLLs. Bundled paths come from PyInstaller's PyQt6 QtMultimedia hook
# (PyQt6/Qt6/bin, PyQt6/Qt6/plugins/multimedia). Missing entries would silently
# degrade every video preview to "video_unavailable".
REQUIRED_BINARIES = (
    # PyQt6 扩展是原生 .pyd（在 CArchive，不在 PYZ）；缺失时导入回落必然失败
    "QtMultimedia.pyd",
    "Qt6Multimedia.dll",
    # Qt 6.11 的 FFmpeg 后端插件文件名为 ffmpegmediaplugin.dll
    "ffmpegmediaplugin.dll",
    "avcodec-*.dll",
    "avformat-*.dll",
    "avutil-*.dll",
    "swresample-*.dll",
    "swscale-*.dll",
)

# Python 模块（纯 Python，在 PYZ）。页面/核心由 unified_gui 用 importlib 动态导入，
# 静态分析不可见，只能靠 spec 的 hiddenimports 收录，这里做回归断言。
REQUIRED_MODULES = (
    "pillow_heif",
    "send2trash",
    "media_thumbnail",
    "scan_record_core",
    "dir_compare_gui",
    "folder_dedupe_gui",
)

# QtMultimedia 的 FFmpeg 后端在运行时依赖 QtNetwork（PyInstaller hook 会带进来）；
# spec 的 excludes 里禁止出现它。
REQUIRED_QT_DLLS = ("Qt6Network.dll",)
FORBIDDEN_EXCLUDES = ("PyQt6.QtNetwork",)


def _dll_matches(basenames: set[str], pattern: str) -> bool:
    """大小写无关地匹配 DLL 文件名；支持 ``name-*.dll`` 这类版本前缀模式。"""
    return any(fnmatch.fnmatchcase(name, pattern.lower()) for name in basenames)


def list_contents(exe: Path) -> tuple[set[str], set[str]]:
    """Return (carchive entry names, pyz module names). Paths use forward slashes."""
    reader = CArchiveReader(str(exe))
    entries: set[str] = set()
    modules: set[str] = set()
    for name, toc_entry in reader.toc.items():
        entries.add(name.replace("\\", "/"))
        try:
            pyz = reader.open_embedded_archive(name)
        except NotAnArchiveError:
            continue
        modules.update(pyz.toc.keys())
    return entries, modules


def _spec_excludes() -> set[str]:
    """取 spec 中 ``excludes=[...]`` 列表里的 PyQt6 子模块名（文本级提取，不 exec spec）。

    仅看 excludes 块，避免把 excludes 以外的同名引用误判为排除。
    """
    spec_path = REPO_ROOT / "AzureKilnPhotoTool_onefile.spec"
    if not spec_path.is_file():
        return set()
    text = spec_path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"excludes\s*=\s*\[(.*?)\]", text, re.S)
    if not match:
        return set()
    return set(re.findall(r'"(PyQt6\.[A-Za-z0-9_]+)"', match.group(1)))


def main() -> int:
    exe = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EXE
    if not exe.is_file():
        print(f"error: {exe} not found", file=sys.stderr)
        return 1

    entries, modules = list_contents(exe)
    errors: list[str] = []

    basenames = {e.rsplit("/", 1)[-1].lower() for e in entries}
    for module in REQUIRED_MODULES:
        if module not in modules:
            errors.append(f"python module '{module}' missing from PYZ")
    # pillow_heif's native extension is the top-level module '_pillow_heif' (+ bundled libheif DLL).
    if not any(b.startswith("_pillow_heif.") and b.endswith(".pyd") for b in basenames):
        errors.append("native extension '_pillow_heif*.pyd' missing")
    if not any(b.startswith("libheif") and b.endswith(".dll") for b in basenames):
        errors.append("libheif*.dll missing")
    for pattern in REQUIRED_BINARIES:
        if not _dll_matches(basenames, pattern):
            errors.append(f"binary '{pattern}' missing (video preview fallback)")
    for dll in REQUIRED_QT_DLLS:
        if not _dll_matches(basenames, dll.lower()):
            errors.append(f"binary '{dll}' missing (required by QtMultimedia)")
    spec_excludes = _spec_excludes()
    for name in FORBIDDEN_EXCLUDES:
        if name in spec_excludes:
            errors.append(f"spec excludes '{name}' which QtMultimedia needs at runtime")

    for required in REQUIRED_FILES:
        if required not in entries:
            errors.append(f"data file '{required}' missing")
    for prefix in REQUIRED_PREFIXES:
        if not any(e.startswith(prefix) for e in entries):
            errors.append(f"no entries under '{prefix}'")

    exiftool_count = sum(1 for e in entries if e.startswith("exiftool_files/"))
    multimedia_count = sum(
        1
        for e in entries
        if "multimedia" in e.lower() or _dll_matches({e.rsplit("/", 1)[-1].lower()}, "av*")
    )
    print(f"{exe}: {len(entries)} archive entries, {len(modules)} PYZ modules, "
          f"{exiftool_count} exiftool_files entries, {multimedia_count} multimedia entries")

    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 1
    print("bundle check passed: pillow_heif, send2trash, ExifTool, QtMultimedia FFmpeg backend present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
