"""`scan_record_core` 的往返与坏输入安全回归（stdlib unittest）。

覆盖：两种模式往返、坏版本/模式/类型/路径归属/跨根/嵌套根/重复目标/保留项相交、
链接越界、重复键、大小上限、原子保存，以及「导入记录后文件被修改/删除仍不会回收」。
全程使用临时目录 + mock send2trash，不写真实相册、不动真实用户文件。

运行：``.venv/Scripts/python.exe -m unittest tests.test_scan_record_core -v``
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import duplicate_scan_core as core
import scan_record_core as records
from duplicate_scan_core import (
    DuplicateGroup,
    FileEntry,
    HashMismatch,
    ScanIssue,
    ScanResult,
)


def _make_file(path: Path, payload: bytes) -> FileEntry:
    """在临时目录写一个真实文件并返回其扫描快照。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    stat = path.stat()
    return FileEntry(
        path=path,
        root=path.parent,
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        file_id=(stat.st_dev, stat.st_ino),
    )


def _entry(path: Path, root: Path, size: int) -> FileEntry:
    """只构造快照（不要求文件存在），用于路径校验场景。"""
    return FileEntry(path=path, root=root, size=size, mtime_ns=1, file_id=(0, 0))


class _TempCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(os.path.abspath(self._tmp.name))

    def path(self, *parts: str) -> Path:
        return self.base.joinpath(*parts)


class CompareRecordTest(_TempCase):
    def _build(self) -> records.ScanRecord:
        root_a = self.path("A")
        root_b = self.path("B")
        a_file = _make_file(root_a / "keep.jpg", b"identical-bytes")
        b_dup = _make_file(root_b / "dup.jpg", b"identical-bytes")
        b_other = _make_file(root_b / "other.jpg", b"identical-bytes")
        # 快照的 root 必须是扫描根，而不是文件所在目录；保留真实 mtime/file_id
        a_file = FileEntry(a_file.path, root_a, a_file.size, a_file.mtime_ns, a_file.file_id)
        b_dup = FileEntry(b_dup.path, root_b, b_dup.size, b_dup.mtime_ns, b_dup.file_id)
        b_other = FileEntry(b_other.path, root_b, b_other.size, b_other.mtime_ns, b_other.file_id)
        mismatch_other = _entry(root_b / "mismatch.jpg", root_b, 8)
        digest = "a" * 64
        result = ScanResult(
            groups=[
                DuplicateGroup(keeper=a_file, duplicates=[b_dup, b_other], sha256=digest, size=15)
            ],
            mismatches=[HashMismatch(keeper=a_file, other=mismatch_other, sha256="b" * 64)],
            issues=[ScanIssue(path=root_b / "broken.jpg", stage="hash", message="读取失败：拒绝访问")],
            scanned_files=5,
            hashed_files=4,
            hashed_bytes=60,
            cancelled=False,
        )
        row_states = {
            os.fspath(b_dup.path): {"checked": True, "status": "status_pending"},
            os.fspath(b_other.path): {"checked": False, "status": "status_skipped|target_missing"},
            os.fspath(mismatch_other.path): {"checked": False, "status": "status_mismatch"},
            os.fspath(root_b / "broken.jpg"): {
                "checked": False,
                "status": "status_issue|hash|读取失败：拒绝访问",
            },
        }
        return records.ScanRecord(
            mode="compare",
            root_a=root_a,
            root_b=root_b,
            scope="media",
            keep_strategy="shallowest",
            result=result,
            row_states=row_states,
            created_at="2026-11-21T10:00:00Z",
        )

    def test_roundtrip_preserves_snapshot_and_states(self) -> None:
        record = self._build()
        target = self.path("record.json")
        records.save_record(target, record)
        self.assertTrue(target.is_file())

        loaded = records.load_record(target, expected_mode="compare")
        self.assertEqual(loaded.mode, "compare")
        self.assertEqual(loaded.root_a, record.root_a)
        self.assertEqual(loaded.root_b, record.root_b)
        self.assertEqual(loaded.scope, "media")
        self.assertEqual(loaded.keep_strategy, "shallowest")
        self.assertEqual(loaded.created_at, record.created_at)
        self.assertFalse(loaded.stale)

        self.assertEqual(len(loaded.result.groups), 1)
        group = loaded.result.groups[0]
        self.assertEqual(group.keeper.path, record.result.groups[0].keeper.path)
        self.assertEqual(group.keeper.file_id, record.result.groups[0].keeper.file_id)
        self.assertEqual(group.keeper.mtime_ns, record.result.groups[0].keeper.mtime_ns)
        self.assertEqual([d.path for d in group.duplicates], [d.path for d in record.result.groups[0].duplicates])
        self.assertEqual(group.sha256, "a" * 64)
        self.assertEqual(len(loaded.result.mismatches), 1)
        self.assertEqual(loaded.result.mismatches[0].sha256, "b" * 64)
        self.assertEqual(loaded.result.issues[0].stage, "hash")
        self.assertEqual(loaded.result.scanned_files, 5)
        self.assertEqual(loaded.result.hashed_bytes, 60)
        self.assertFalse(loaded.result.cancelled)
        self.assertEqual(loaded.row_states, record.row_states)

    def test_saved_payload_is_versioned_utf8_json(self) -> None:
        record = self._build()
        target = self.path("record.json")
        records.save_record(target, record)
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], records.SCHEMA_VERSION)
        self.assertEqual(payload["mode"], "compare")
        self.assertIn("读取失败：拒绝访问", target.read_text(encoding="utf-8"))
        leftovers = [p.name for p in self.base.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_checked_flag_normalized_for_non_pending_rows(self) -> None:
        record = self._build()
        target = self.path("record.json")
        records.save_record(target, record)
        payload = json.loads(target.read_text(encoding="utf-8"))
        skipped_key = next(k for k, v in payload["row_states"].items() if k.endswith("other.jpg"))
        self.assertFalse(payload["row_states"][skipped_key]["checked"])
        # 手改记录声称「已跳过行也被勾选」，导入时必须归一化为未勾选
        payload["row_states"][skipped_key]["checked"] = True
        target.write_text(json.dumps(payload), encoding="utf-8")

        loaded = records.load_record(target)
        self.assertFalse(loaded.row_states[skipped_key]["checked"])
        self.assertEqual(loaded.row_states[skipped_key]["status"], "status_skipped|target_missing")

    def test_stale_flag_saved_and_validated(self) -> None:
        record = self._build()
        record.stale = True
        target = self.path("stale.json")
        records.save_record(target, record)
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertIs(payload["stale"], True)
        self.assertTrue(records.load_record(target).stale)

        for bad in ("true", 1, None, "yes"):
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["stale"] = bad
            broken = self.path("stale-bad.json")
            broken.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError, msg=repr(bad)):
                records.load_record(broken)

        payload = json.loads(target.read_text(encoding="utf-8"))
        del payload["stale"]
        missing = self.path("stale-missing.json")
        missing.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ValueError):
            records.load_record(missing)

    def test_wrong_mode_is_rejected(self) -> None:
        target = self.path("record.json")
        records.save_record(target, self._build())
        with self.assertRaises(ValueError):
            records.load_record(target, expected_mode="internal")

    def test_stale_or_non_record_cannot_be_saved(self) -> None:
        record = self._build()
        record.stale = "yes"  # type: ignore[assignment]
        with self.assertRaises(ValueError):
            records.save_record(self.path("stale.json"), record)
        self.assertFalse(self.path("stale.json").exists())

    def test_invalid_snapshot_is_rejected_before_write(self) -> None:
        record = self._build()
        record.result.groups[0].duplicates[0] = _entry(
            self.path("A", "not-in-b.jpg"), self.path("A"), 15
        )
        target = self.path("bad.json")
        with self.assertRaises(ValueError):
            records.save_record(target, record)
        self.assertFalse(target.exists())

    def test_imported_record_cannot_recycle_modified_target(self) -> None:
        record = self._build()
        target = self.path("record.json")
        records.save_record(target, record)
        loaded = records.load_record(target)
        group = loaded.result.groups[0]
        dup_path = group.duplicates[0].path
        dup_path.write_bytes(b"identical-bytez")  # 同长度、内容已变

        with mock.patch.object(core, "send2trash") as send2trash, mock.patch(
            "send2trash.send2trash"
        ):
            outcome = core.recycle_duplicate(
                group.duplicates[0], group.keeper, byte_verify=True
            )
        self.assertEqual(outcome.status, "skipped")
        self.assertIn(outcome.reason, {"target_changed", "content_differs"})
        send2trash.assert_not_called()
        self.assertTrue(dup_path.is_file())

    def test_imported_record_cannot_recycle_deleted_target(self) -> None:
        record = self._build()
        target = self.path("record.json")
        records.save_record(target, record)
        loaded = records.load_record(target)
        group = loaded.result.groups[0]
        group.duplicates[0].path.unlink()

        with mock.patch.object(core, "send2trash") as send2trash:
            outcome = core.recycle_duplicate(group.duplicates[0], group.keeper)
        self.assertEqual(outcome.status, "skipped")
        self.assertEqual(outcome.reason, "target_missing")
        send2trash.assert_not_called()

    def test_unchanged_files_only_recycled_after_revalidation(self) -> None:
        record = self._build()
        target = self.path("record.json")
        records.save_record(target, record)
        loaded = records.load_record(target)
        group = loaded.result.groups[0]
        with mock.patch.object(core, "send2trash") as send2trash:
            outcome = core.recycle_duplicate(group.duplicates[0], group.keeper)
        if outcome.status != "recycled":  # 先定位失败原因再断言
            print("recycle outcome:", outcome.status, outcome.reason)
        self.assertEqual(outcome.status, "recycled")
        send2trash.assert_called_once()
        self.assertTrue(group.duplicates[1].path.is_file())


class InternalRecordTest(_TempCase):
    def _build(self) -> records.ScanRecord:
        root = self.path("root")
        keeper = _entry(root / "keep.jpg", root, 10)
        keep2 = _entry(root / "keep2.jpg", root, 20)
        dup = _entry(root / "sub" / "dup.jpg", root, 10)
        result = ScanResult(
            groups=[
                DuplicateGroup(keeper=keeper, duplicates=[dup], sha256="c" * 64, size=10),
                DuplicateGroup(keeper=keep2, duplicates=[], sha256="d" * 64, size=20),
            ],
            scanned_files=3,
        )
        return records.ScanRecord(
            mode="internal",
            root_a=root,
            root_b=None,
            scope="all",
            keep_strategy="newest",
            result=result,
            row_states={
                os.fspath(keeper.path): {"checked": False, "status": "status_keep"},
                os.fspath(dup.path): {"checked": True, "status": "status_pending"},
            },
        )

    def test_internal_roundtrip(self) -> None:
        record = self._build()
        target = self.path("internal.json")
        records.save_record(target, record)
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertIsNone(payload["roots"]["b"])
        loaded = records.load_record(target, expected_mode="internal")
        self.assertIsNone(loaded.root_b)
        self.assertEqual(loaded.keep_strategy, "newest")
        self.assertEqual(len(loaded.result.groups), 2)
        self.assertEqual(loaded.result.groups[0].duplicates[0].path, record.result.groups[0].duplicates[0].path)
        self.assertEqual(loaded.row_states, record.row_states)

    def test_internal_rejects_foreign_root_in_snapshot(self) -> None:
        record = self._build()
        record.result.groups[0].duplicates.append(
            _entry(self.path("elsewhere", "x.jpg"), self.path("elsewhere"), 10)
        )
        with self.assertRaises(ValueError):
            records.save_record(self.path("bad-internal.json"), record)


class BadInputTest(_TempCase):
    def setUp(self) -> None:
        super().setUp()
        self.root_a = self.path("A")
        self.root_b = self.path("B")
        self.root_a.mkdir()
        self.root_b.mkdir()
        self.record = records.ScanRecord(
            mode="compare",
            root_a=self.root_a,
            root_b=self.root_b,
            scope="all",
            keep_strategy="oldest",
            result=ScanResult(),
            row_states={},
        )
        self.valid = self.path("valid.json")
        records.save_record(self.valid, self.record)
        self.payload = json.loads(self.valid.read_text(encoding="utf-8"))

    def _write(self, payload: object) -> Path:
        target = self.path("mutated.json")
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return target

    def test_bad_version(self) -> None:
        for version in (0, 2, "1", True, -1):
            payload = json.loads(json.dumps(self.payload))
            payload["schema_version"] = version
            with self.assertRaises(ValueError, msg=repr(version)):
                records.load_record(self._write(payload))

    def test_unknown_mode_and_expected_mode(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["mode"] = "similar"
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))
        with self.assertRaises(ValueError):
            records.load_record(self.valid, expected_mode="other")

    def test_unknown_or_missing_fields_rejected(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["extra"] = 1
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

        payload = json.loads(json.dumps(self.payload))
        del payload["options"]
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

    def test_bad_options(self) -> None:
        for key, value in (("scope", "videos"), ("keep_strategy", "random")):
            payload = json.loads(json.dumps(self.payload))
            payload["options"][key] = value
            with self.assertRaises(ValueError, msg=key):
                records.load_record(self._write(payload))

    def test_nested_or_same_roots_rejected(self) -> None:
        nested = self.root_a / "inner"
        nested.mkdir()
        payload = json.loads(json.dumps(self.payload))
        payload["roots"]["b"] = os.fspath(nested)
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

        payload = json.loads(json.dumps(self.payload))
        payload["roots"]["b"] = os.fspath(self.root_a)
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

    def test_internal_with_root_b_rejected(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["mode"] = "internal"
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

    def test_relative_paths_rejected(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["roots"]["a"] = "A"
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

    def test_target_outside_root_rejected(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["result"]["groups"] = [
            {
                "keeper": self._entry_payload(self.root_a / "k.jpg", self.root_a, 3),
                "duplicates": [
                    self._entry_payload(self.path("outside", "x.jpg"), self.root_b, 3)
                ],
                "sha256": "a" * 64,
                "size": 3,
            }
        ]
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

    def test_traversal_and_symlink_escape_rejected(self) -> None:
        outside = self.path("outside")
        outside.mkdir()
        (outside / "secret.jpg").write_bytes(b"abc")
        # 词法遍历
        payload = json.loads(json.dumps(self.payload))
        payload["row_states"] = {
            os.fspath(self.root_b / ".." / "outside" / "secret.jpg"): {
                "checked": True,
                "status": "status_pending",
            }
        }
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

        # 符号链接/联接越界：能创建才验证
        link = self.root_b / "link"
        created = False
        try:
            if os.name == "nt":
                link.symlink_to(outside, target_is_directory=True)
            else:
                link.symlink_to(outside, target_is_directory=True)
            created = True
        except (OSError, NotImplementedError):
            created = False
        if created:
            payload = json.loads(json.dumps(self.payload))
            payload["row_states"] = {
                os.fspath(link / "secret.jpg"): {"checked": True, "status": "status_pending"}
            }
            with self.assertRaises(ValueError):
                records.load_record(self._write(payload))

    def test_wrong_role_rejected(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["result"]["groups"] = [
            {
                "keeper": self._entry_payload(self.root_b / "k.jpg", self.root_b, 3),
                "duplicates": [
                    self._entry_payload(self.root_a / "x.jpg", self.root_a, 3)
                ],
                "sha256": "a" * 64,
                "size": 3,
            }
        ]
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

    def test_duplicate_target_and_keeper_intersection_rejected(self) -> None:
        keeper = self.root_a / "k.jpg"
        dup = self.root_b / "d.jpg"
        payload = json.loads(json.dumps(self.payload))
        payload["result"]["groups"] = [
            {
                "keeper": self._entry_payload(keeper, self.root_a, 3),
                "duplicates": [
                    self._entry_payload(dup, self.root_b, 3),
                    self._entry_payload(dup, self.root_b, 3),
                ],
                "sha256": "a" * 64,
                "size": 3,
            }
        ]
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

        payload = json.loads(json.dumps(self.payload))
        payload["result"]["groups"] = [
            {
                "keeper": self._entry_payload(keeper, self.root_a, 3),
                "duplicates": [self._entry_payload(self.root_a / "k2.jpg", self.root_a, 3)],
                "sha256": "a" * 64,
                "size": 3,
            }
        ]
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

    def test_size_mismatch_rejected(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["result"]["groups"] = [
            {
                "keeper": self._entry_payload(self.root_a / "k.jpg", self.root_a, 3),
                "duplicates": [self._entry_payload(self.root_b / "d.jpg", self.root_b, 4)],
                "sha256": "a" * 64,
                "size": 3,
            }
        ]
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

    def test_unknown_status_and_bad_row_state_rejected(self) -> None:
        dup = self.root_b / "d.jpg"
        base = json.loads(json.dumps(self.payload))
        base["result"]["groups"] = [
            {
                "keeper": self._entry_payload(self.root_a / "k.jpg", self.root_a, 3),
                "duplicates": [self._entry_payload(dup, self.root_b, 3)],
                "sha256": "a" * 64,
                "size": 3,
            }
        ]
        key = os.fspath(dup)
        for state in (
            {"checked": True, "status": "status_recycled_now"},
            {"checked": "yes", "status": "status_pending"},
            {"checked": True},
            {"checked": True, "status": "status_pending", "extra": 1},
            {"checked": True, "status": "status_issue|bogus|msg"},
        ):
            payload = json.loads(json.dumps(base))
            payload["row_states"] = {key: state}
            with self.assertRaises(ValueError, msg=repr(state)):
                records.load_record(self._write(payload))

    def test_row_state_outside_root_rejected(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["row_states"] = {
            os.fspath(self.path("elsewhere", "x.jpg")): {
                "checked": True,
                "status": "status_pending",
            }
        }
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

    def test_issue_outside_root_rejected(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["result"]["issues"] = [
            {"path": os.fspath(self.path("elsewhere", "x.jpg")), "stage": "hash", "message": "x"}
        ]
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

        payload["result"]["issues"] = [
            {"path": os.fspath(self.root_b / "x.jpg"), "stage": "unknown", "message": "x"}
        ]
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

    def test_duplicate_json_keys_rejected(self) -> None:
        text = self.valid.read_text(encoding="utf-8")
        broken = text.replace('"schema_version":1', '"schema_version":1,"schema_version":1', 1)
        target = self.path("dupkeys.json")
        target.write_text(broken, encoding="utf-8")
        with self.assertRaises(ValueError):
            records.load_record(target)

    def test_nan_and_non_json_rejected(self) -> None:
        target = self.path("nan.json")
        target.write_text('{"schema_version": NaN}', encoding="utf-8")
        with self.assertRaises(ValueError):
            records.load_record(target)

        target.write_text("not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            records.load_record(target)

    def test_non_utf8_rejected(self) -> None:
        target = self.path("gbk.json")
        target.write_bytes(self.valid.read_bytes().replace(b'"all"', b'"\xff\xfe"'))
        with self.assertRaises(ValueError):
            records.load_record(target)

    def test_oversize_file_rejected(self) -> None:
        target = self.path("big.json")
        with open(target, "wb") as handle:
            handle.truncate(records.MAX_RECORD_BYTES + 1)
        with self.assertRaises(ValueError):
            records.load_record(target)

    def test_missing_file_raises_oserror(self) -> None:
        with self.assertRaises(OSError):
            records.load_record(self.path("missing.json"))

    def test_failed_replace_keeps_previous_record(self) -> None:
        target = self.path("existing.json")
        records.save_record(target, self.record)
        before = target.read_bytes()
        broken = records.ScanRecord(
            mode="compare",
            root_a=self.root_a,
            root_b=self.root_b,
            scope="all",
            keep_strategy="oldest",
            result=ScanResult(),
            row_states={os.fspath(self.path("elsewhere", "x.jpg")): {"checked": True, "status": "status_pending"}},
        )
        with self.assertRaises(ValueError):
            records.save_record(target, broken)
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual([p.name for p in self.base.iterdir() if p.name.endswith(".tmp")], [])

    def test_replace_failure_keeps_previous_record_and_cleans_temp(self) -> None:
        target = self.path("replace.json")
        records.save_record(target, self.record)
        before = target.read_bytes()
        with mock.patch.object(records.os, "replace", side_effect=OSError("simulated")):
            with self.assertRaises(OSError):
                records.save_record(target, self.record)
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual([p.name for p in self.base.iterdir() if p.name.endswith(".tmp")], [])

    def test_save_into_missing_directory_raises_oserror(self) -> None:
        with self.assertRaises(OSError):
            records.save_record(self.path("nope", "r.json"), self.record)

    def test_row_state_for_foreign_row_rejected(self) -> None:
        payload = json.loads(json.dumps(self.payload))
        payload["row_states"] = {
            os.fspath(self.root_b / "not-in-result.jpg"): {
                "checked": True,
                "status": "status_pending",
            }
        }
        with self.assertRaises(ValueError):
            records.load_record(self._write(payload))

    def test_keeper_or_issue_cannot_be_checked_pending(self) -> None:
        keeper = self.root_a / "k.jpg"
        dup = self.root_b / "d.jpg"
        issue = self.root_b / "broken.jpg"
        base_payload = json.loads(json.dumps(self.payload))
        base_payload["result"]["groups"] = [
            {
                "keeper": self._entry_payload(keeper, self.root_a, 3),
                "duplicates": [self._entry_payload(dup, self.root_b, 3)],
                "sha256": "a" * 64,
                "size": 3,
            }
        ]
        base_payload["result"]["issues"] = [
            {"path": os.fspath(issue), "stage": "hash", "message": "x"}
        ]

        # 保留项被伪造成待回收目标：拒绝
        bad_keeper = json.loads(json.dumps(base_payload))
        bad_keeper["row_states"] = {
            os.fspath(keeper): {"checked": True, "status": "status_pending"}
        }
        with self.assertRaises(ValueError):
            records.load_record(self._write(bad_keeper))

        # 异常项被伪造成待回收目标：拒绝
        bad_issue = json.loads(json.dumps(base_payload))
        bad_issue["row_states"] = {
            os.fspath(issue): {"checked": True, "status": "status_pending"}
        }
        with self.assertRaises(ValueError):
            records.load_record(self._write(bad_issue))

        # 保留项保持 status_keep；异常项保持 status_issue，但即使勾选也被归一化
        ok = json.loads(json.dumps(base_payload))
        ok["row_states"] = {
            os.fspath(keeper): {"checked": False, "status": "status_keep"},
            os.fspath(dup): {"checked": True, "status": "status_pending"},
            os.fspath(issue): {"checked": True, "status": "status_issue|hash|x"},
        }
        loaded = records.load_record(self._write(ok))
        self.assertFalse(loaded.row_states[os.fspath(keeper)]["checked"])
        self.assertTrue(loaded.row_states[os.fspath(dup)]["checked"])
        self.assertFalse(loaded.row_states[os.fspath(issue)]["checked"])

    def test_deleted_history_paths_still_importable(self) -> None:
        record = CompareRecordTest._build(self)
        target = self.path("history.json")
        records.save_record(target, record)
        # 历史文件全部删除后仍可导入（仅展示，不读取媒体）
        for group in record.result.groups:
            group.keeper.path.unlink()
            for duplicate in group.duplicates:
                duplicate.path.unlink()
        loaded = records.load_record(target)
        self.assertEqual(len(loaded.result.groups), 1)
        self.assertFalse(loaded.result.groups[0].keeper.path.exists())

    def _entry_payload(self, path: Path, root: Path, size: int) -> dict:
        return {
            "path": os.fspath(path),
            "root": os.fspath(root),
            "size": size,
            "mtime_ns": 1,
            "file_id": [0, 0],
        }


if __name__ == "__main__":
    unittest.main()
