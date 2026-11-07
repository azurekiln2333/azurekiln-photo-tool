"""Verify that the onefile exe bundles pillow_heif and ExifTool.

Usage:
    python scripts/ci/verify_bundle.py [dist/AzureKilnPhotoTool.exe]

Reads the PyInstaller CArchive (and embedded PYZ) table of contents without running the exe.
Exit code 1 if any required entry is missing.
"""

from __future__ import annotations

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


def main() -> int:
    exe = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EXE
    if not exe.is_file():
        print(f"error: {exe} not found", file=sys.stderr)
        return 1

    entries, modules = list_contents(exe)
    errors: list[str] = []

    basenames = {e.rsplit("/", 1)[-1].lower() for e in entries}
    if "pillow_heif" not in modules:
        errors.append("python module 'pillow_heif' missing from PYZ")
    # pillow_heif's native extension is the top-level module '_pillow_heif' (+ bundled libheif DLL).
    if not any(b.startswith("_pillow_heif.") and b.endswith(".pyd") for b in basenames):
        errors.append("native extension '_pillow_heif*.pyd' missing")
    if not any(b.startswith("libheif") and b.endswith(".dll") for b in basenames):
        errors.append("libheif*.dll missing")
    if "send2trash" not in modules:
        errors.append("python module 'send2trash' missing from PYZ")

    for required in REQUIRED_FILES:
        if required not in entries:
            errors.append(f"data file '{required}' missing")
    for prefix in REQUIRED_PREFIXES:
        if not any(e.startswith(prefix) for e in entries):
            errors.append(f"no entries under '{prefix}'")

    exiftool_count = sum(1 for e in entries if e.startswith("exiftool_files/"))
    print(f"{exe}: {len(entries)} archive entries, {len(modules)} PYZ modules, "
          f"{exiftool_count} exiftool_files entries")

    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 1
    print("bundle check passed: pillow_heif, send2trash, ExifTool present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
