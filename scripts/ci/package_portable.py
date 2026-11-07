"""Create the portable zip + sha256 file following .trellis/spec/python/packaging.md.

Output (in --output-dir, default release/):
    AzureKilnPhotoTool-<ver>-<YYYYMMDD>-windows-x64-portable.zip
        AzureKilnPhotoTool.exe
        AzureKilnPhotoTool-<ver>-<YYYYMMDD>-windows-x64-portable.sha256.txt
    AzureKilnPhotoTool-<ver>-<YYYYMMDD>-windows-x64-portable.sha256.txt

sha256 file content: "<64 hex>  AzureKilnPhotoTool.exe\\r\\n" (90 bytes, hash of the exe).

Usage:
    python scripts/ci/package_portable.py --version 1.1.0 [--date 20261108]
        [--exe dist/AzureKilnPhotoTool.exe] [--output-dir release]

Prints the base name; appends ``base_name=...`` / ``date=...`` to $GITHUB_OUTPUT when set.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXE_NAME = "AzureKilnPhotoTool.exe"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Package portable zip + sha256")
    parser.add_argument("--version", required=True)
    parser.add_argument("--date", help="YYYYMMDD, default: today (UTC)")
    parser.add_argument("--exe", type=Path, default=REPO_ROOT / "dist" / EXE_NAME)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "release")
    args = parser.parse_args()

    date = args.date or datetime.now(timezone.utc).strftime("%Y%m%d")
    if not re.fullmatch(r"\d{8}", date):
        print(f"error: invalid --date {date!r}, expected YYYYMMDD", file=sys.stderr)
        return 1
    if not args.exe.is_file():
        print(f"error: {args.exe} not found", file=sys.stderr)
        return 1

    base_name = f"AzureKilnPhotoTool-{args.version}-{date}-windows-x64-portable"
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    exe_hash = sha256_of(args.exe)
    # 64 hex + 2 spaces + name + CRLF = 90 bytes, identical to past releases.
    sha_content = f"{exe_hash}  {EXE_NAME}\r\n".encode("ascii")
    sha_name = f"{base_name}.sha256.txt"
    sha_path = output_dir / sha_name
    zip_path = output_dir / f"{base_name}.zip"

    sha_path.write_bytes(sha_content)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.write(args.exe, EXE_NAME)
        zf.writestr(sha_name, sha_content)

    # Self-check: zip integrity and three-way hash consistency.
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad is not None:
            print(f"error: corrupt zip member {bad}", file=sys.stderr)
            return 1
        zipped_hash = hashlib.sha256(zf.read(EXE_NAME)).hexdigest()
        zipped_sha = zf.read(sha_name)
    if not (zipped_hash == exe_hash and zipped_sha == sha_content == sha_path.read_bytes()):
        print("error: hash mismatch between exe, zip member and sha256 file", file=sys.stderr)
        return 1

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fp:
            fp.write(f"base_name={base_name}\ndate={date}\n")

    print(f"{zip_path}\n{sha_path}\nsha256 {exe_hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
