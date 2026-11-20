"""使用真实可解码图片模拟哈希碰撞，验证逐字节兜底；不操作用户文件。"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

REPO = next(parent for parent in Path(__file__).resolve().parents
            if (parent / 'duplicate_scan_core.py').is_file())
sys.path.insert(0, str(REPO))

from PIL import Image

import duplicate_scan_core as core


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="compare-collision-") as temporary:
        base = Path(temporary)
        root_a = base / "A"
        root_b = base / "B"
        root_a.mkdir()
        root_b.mkdir()
        left = root_a / "red.bmp"
        right = root_b / "blue.bmp"
        Image.new("RGB", (64, 64), "red").save(left)
        Image.new("RGB", (64, 64), "blue").save(right)
        assert left.stat().st_size == right.stat().st_size
        actual_hashes_differ = core.sha256_file(left) != core.sha256_file(right)
        assert actual_hashes_differ
        with patch.object(core, "sha256_file", return_value="0" * 64):
            result = core.find_cross_duplicates(root_a, root_b, threads=1)
        assert not result.groups
        assert len(result.mismatches) == 1
        mismatch = result.mismatches[0]
        with patch.object(core, "send2trash") as recycle:
            outcome = core.recycle_duplicate(mismatch.other, mismatch.keeper, byte_verify=True)
            recycle.assert_not_called()
        assert outcome.status == "skipped"
        assert outcome.reason == "content_differs"
        print(json.dumps({
            "fixture": "two valid 64x64 BMP images: red and blue",
            "equal_file_size": left.stat().st_size,
            "actual_sha256_differ": actual_hashes_differ,
            "hash_collision_simulated": True,
            "duplicate_groups": len(result.groups),
            "mismatches": len(result.mismatches),
            "recycle_status": outcome.status,
            "recycle_reason": outcome.reason,
            "send2trash_calls": recycle.call_count,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
