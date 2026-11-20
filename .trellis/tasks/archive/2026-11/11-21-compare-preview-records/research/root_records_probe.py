"""验证真实扫描→保存→导入→回收前重验；只使用临时文件和 mock 回收站。"""

import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

REPO = next(parent for parent in Path(__file__).resolve().parents
            if (parent / 'duplicate_scan_core.py').is_file())
sys.path.insert(0, str(REPO))
import duplicate_scan_core as core
import scan_record_core as records

with tempfile.TemporaryDirectory(prefix="compare-records-") as temporary:
    base = Path(temporary)
    for mode in ("compare", "internal"):
        root = base / mode / "A"
        other = base / mode / "B" if mode == "compare" else root / "sub"
        root.mkdir(parents=True)
        other.mkdir(parents=True)
        payload = b"temporary duplicate bytes" * 10
        (root / "keeper.jpg").write_bytes(payload)
        (other / "duplicate.jpg").write_bytes(payload)
        (other / "second.jpg").write_bytes(payload)
        result = core.find_cross_duplicates(root, other, threads=1) if mode == "compare" else core.find_internal_duplicates(root, threads=1)
        assert len(result.groups) == 1
        assert len(result.groups[0].duplicates) == 2
        states = {str(entry.path): {"checked": True, "status": "status_pending"} for group in result.groups for entry in group.duplicates}
        record = records.ScanRecord(mode, root, other if mode == "compare" else None, "all", "shallowest", result, states)
        destination = base / f"{mode}.json"
        records.save_record(destination, record)
        loaded = records.load_record(destination, expected_mode=mode)
        assert loaded.result == result
        assert loaded.row_states == states
        records.save_record(destination, replace(record, stale=True))
        assert records.load_record(destination).stale is True
        records.save_record(destination, record)
        existing = destination.read_bytes()
        with patch.object(records.os, "replace", side_effect=OSError("simulated save failure")):
            try:
                records.save_record(destination, record)
            except OSError:
                pass
            else:
                raise AssertionError("atomic replacement failure was ignored")
        assert destination.read_bytes() == existing
        assert not list(destination.parent.glob(f".{destination.name}.*.tmp"))
        target = loaded.result.groups[0].duplicates[0]
        keeper = loaded.result.groups[0].keeper
        target.path.write_bytes(b"X" + payload[1:])
        os.utime(target.path, ns=(target.mtime_ns, target.mtime_ns))
        with patch.object(core, "send2trash") as recycle:
            outcome = core.recycle_duplicate(target, keeper, byte_verify=True)
            assert (outcome.status, outcome.reason) == ("skipped", "content_differs")
            recycle.assert_not_called()
            target.path.unlink()
            assert core.recycle_duplicate(target, keeper, byte_verify=True).reason == "target_missing"
            recycle.assert_not_called()
        historical = records.load_record(destination)
        assert historical.result == result
        print(f"PASS: {mode}: real scan, roundtrip, stale state, atomic save failure, changed/deleted historical target protected")
