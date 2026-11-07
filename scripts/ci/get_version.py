"""Read APP_VERSION from unified_gui.py (without importing the GUI).

Usage:
    python scripts/ci/get_version.py               # print version
    python scripts/ci/get_version.py --tag v1.1.0  # also require tag == "v" + version

When the GITHUB_OUTPUT environment variable is set, ``version=<ver>`` is appended to it.
Exit code 1 on parse failure or tag mismatch.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILE = REPO_ROOT / "unified_gui.py"
VERSION_PATTERN = re.compile(r'^APP_VERSION\s*=\s*["\'](\d+\.\d+\.\d+)["\']\s*$', re.MULTILINE)


def read_version(source: Path = SOURCE_FILE) -> str:
    match = VERSION_PATTERN.search(source.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"APP_VERSION (X.Y.Z) not found in {source}")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", help="git tag name that must equal 'v' + APP_VERSION")
    args = parser.parse_args()

    try:
        version = read_version()
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.tag is not None and args.tag != f"v{version}":
        print(
            f"error: tag {args.tag!r} does not match APP_VERSION {version!r} "
            f"(expected 'v{version}'); update unified_gui.py or retag",
            file=sys.stderr,
        )
        return 1

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fp:
            fp.write(f"version={version}\n")

    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
