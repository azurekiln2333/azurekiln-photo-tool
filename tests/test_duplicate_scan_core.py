"""``duplicate_scan_core`` 单元测试。

运行：``.venv\\Scripts\\python.exe -m unittest tests.test_duplicate_scan_core -v``

重点锁住 design.md「准确性不变量」：
1. duplicates 中的文件一定满足 size 相同 ∧ SHA-256 相同 ∧ files_identical 为 True；
2. keeper 永不出现在 duplicates；比对模式下 A 中路径永不出现在 duplicates；
3. revalidate_pair 不通过时 recycle_duplicate 绝不调用 send2trash；
4. 读错误只产生 issue / skipped，不抛给调用方（ScanCancelled 由 find_* 捕获）。
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import duplicate_scan_core as core
from duplicate_scan_core import (
    CHUNK_SIZE,
    DuplicateGroup,
    FileEntry,
    HashMismatch,
    ScanCancelled,
    ScanIssue,
    ScanResult,
    choose_keeper,
    collect_files,
    files_identical,
    find_cross_duplicates,
    find_internal_duplicates,
    recycle_duplicate,
    revalidate_pair,
    sha256_file,
    validate_compare_roots,
)


def write_file(path: Path, data: bytes, mtime_ns: int | None = None) -> Path:
    """写入文件（自动建父目录），可选固定 mtime。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mtime_ns is not None:
        os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


def entry_of(path: Path, root: Path) -> FileEntry:
    """按当前磁盘状态构造 FileEntry（测试辅助）。"""
    stat_result = path.stat()
    return FileEntry(
        path=path,
        root=root,
        size=int(stat_result.st_size),
        mtime_ns=int(stat_result.st_mtime_ns),
        file_id=(int(stat_result.st_dev), int(stat_result.st_ino)),
    )


class TempCase(unittest.TestCase):
    """每个用例独立的临时目录。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)
        self.a = self.tmp / "A"
        self.b = self.tmp / "B"
        self.a.mkdir()
        self.b.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# 基础文件工具
# ---------------------------------------------------------------------------


class HashAndCompareTests(TempCase):
    def test_sha256_matches_hashlib(self) -> None:
        data = os.urandom(CHUNK_SIZE + 123)
        path = write_file(self.tmp / "blob.bin", data)
        self.assertEqual(sha256_file(path), hashlib.sha256(data).hexdigest())

    def test_files_identical_true_across_chunks(self) -> None:
        data = b"0123456789" * 1000
        left = write_file(self.tmp / "l.bin", data)
        right = write_file(self.tmp / "r.bin", data)
        self.assertTrue(files_identical(left, right, chunk_size=97))

    def test_files_identical_false_on_last_byte(self) -> None:
        payload = bytearray(b"x" * 5000)
        left = write_file(self.tmp / "l.bin", bytes(payload))
        payload[-1] = 0x00
        right = write_file(self.tmp / "r.bin", bytes(payload))
        self.assertFalse(files_identical(left, right, chunk_size=128))

    def test_files_identical_false_on_size(self) -> None:
        left = write_file(self.tmp / "l.bin", b"abc")
        right = write_file(self.tmp / "r.bin", b"abcd")
        self.assertFalse(files_identical(left, right))

    def test_sha256_cancel_raises(self) -> None:
        path = write_file(self.tmp / "blob.bin", b"data")
        with self.assertRaises(ScanCancelled):
            sha256_file(path, should_cancel=lambda: True)

    def test_files_identical_cancel_raises(self) -> None:
        data = b"a" * (CHUNK_SIZE + 1)
        left = write_file(self.tmp / "l.bin", data)
        right = write_file(self.tmp / "r.bin", data)
        with self.assertRaises(ScanCancelled):
            files_identical(left, right, should_cancel=lambda: True)


class FileEntryTests(TempCase):
    def test_relative_path(self) -> None:
        root = self.tmp / "root"
        path = write_file(root / "sub" / "deep" / "x.jpg", b"1")
        entry = entry_of(path, root)
        self.assertEqual(entry.relative_path, Path("sub/deep/x.jpg"))

    def test_relative_path_falls_back_to_name(self) -> None:
        path = write_file(self.tmp / "x.jpg", b"1")
        entry = entry_of(path, self.tmp / "other-root")
        self.assertEqual(entry.relative_path, Path("x.jpg"))


# ---------------------------------------------------------------------------
# 根目录校验（AC6）
# ---------------------------------------------------------------------------


class ValidateRootsTests(TempCase):
    def test_same_root(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_compare_roots(self.a, self.a)
        self.assertEqual(str(ctx.exception), "same_root")

    def test_same_root_via_relative_traversal(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_compare_roots(self.a, self.a / ".." / "A")
        self.assertEqual(str(ctx.exception), "same_root")

    def test_b_inside_a(self) -> None:
        nested = self.a / "inner" / "B"
        nested.mkdir(parents=True)
        with self.assertRaises(ValueError) as ctx:
            validate_compare_roots(self.a, nested)
        self.assertEqual(str(ctx.exception), "b_inside_a")

    def test_a_inside_b(self) -> None:
        nested = self.b / "inner"
        nested.mkdir()
        with self.assertRaises(ValueError) as ctx:
            validate_compare_roots(nested, self.b)
        self.assertEqual(str(ctx.exception), "a_inside_b")

    def test_missing_roots(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_compare_roots(self.tmp / "nope", self.b)
        self.assertEqual(str(ctx.exception), "a_missing")
        with self.assertRaises(ValueError) as ctx:
            validate_compare_roots(self.a, self.tmp / "nope")
        self.assertEqual(str(ctx.exception), "b_missing")

    def test_file_is_not_root(self) -> None:
        file_path = write_file(self.tmp / "file.txt", b"1")
        with self.assertRaises(ValueError) as ctx:
            validate_compare_roots(file_path, self.b)
        self.assertEqual(str(ctx.exception), "a_missing")

    def test_sibling_roots_are_allowed(self) -> None:
        validate_compare_roots(self.a, self.b)


# ---------------------------------------------------------------------------
# 文件枚举
# ---------------------------------------------------------------------------


class CollectFilesTests(TempCase):
    def test_skip_zero_byte_and_sort_deterministically(self) -> None:
        write_file(self.a / "b.jpg", b"1")
        write_file(self.a / "a.jpg", b"2")
        write_file(self.a / "sub" / "c.jpg", b"3")
        write_file(self.a / "empty.jpg", b"")
        entries = collect_files(self.a)
        self.assertEqual([e.path.name for e in entries], ["a.jpg", "b.jpg", "c.jpg"])
        self.assertEqual([e.path.name for e in collect_files(self.a)], ["a.jpg", "b.jpg", "c.jpg"])
        self.assertTrue(all(e.root == self.a for e in entries))

    def test_media_scope_filters_by_extension(self) -> None:
        write_file(self.a / "photo.JPG", b"1")
        write_file(self.a / "clip.mp4", b"2")
        write_file(self.a / "note.txt", b"3")
        write_file(self.a / "raw.dng", b"4")
        media = collect_files(self.a, "media")
        self.assertEqual(sorted(e.path.name for e in media), ["clip.mp4", "photo.JPG", "raw.dng"])
        self.assertEqual(len(collect_files(self.a, "all")), 4)

    def test_missing_root_records_issue(self) -> None:
        issues: list[ScanIssue] = []
        entries = collect_files(self.tmp / "nope", issues=issues)
        self.assertEqual(entries, [])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].stage, "enumerate")

    def test_symlinked_directory_not_followed(self) -> None:
        outside = self.tmp / "outside"
        write_file(outside / "secret.jpg", b"payload")
        link = self.a / "link"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("当前环境无法创建目录符号链接")
        write_file(self.a / "real.jpg", b"real")
        entries = collect_files(self.a)
        self.assertEqual([e.path.name for e in entries], ["real.jpg"])

    def test_cancel_stops_enumeration(self) -> None:
        write_file(self.a / "x.jpg", b"1")
        entries = collect_files(self.a, should_cancel=lambda: True)
        self.assertEqual(entries, [])


# ---------------------------------------------------------------------------
# 目录比对（AC1 / AC2 / AC3）
# ---------------------------------------------------------------------------


class CrossDuplicateTests(TempCase):
    def test_three_copies_in_b_all_listed(self) -> None:
        """AC1：A 一个文件、B 三份副本（不同子目录、不同文件名）→ 1 组 3 个 duplicates。"""
        payload = b"livephoto-payload" * 500
        write_file(self.a / "keep" / "orig.jpg", payload)
        write_file(self.b / "copy1.jpg", payload)
        write_file(self.b / "sub" / "copy2.jpg", payload)
        write_file(self.b / "sub" / "deep" / "renamed.png", payload)

        result = find_cross_duplicates(self.a, self.b)

        self.assertFalse(result.cancelled)
        self.assertEqual(len(result.groups), 1)
        group = result.groups[0]
        self.assertEqual(group.keeper.path, self.a / "keep" / "orig.jpg")
        self.assertEqual(group.size, len(payload))
        self.assertEqual(group.sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(len(group.duplicates), 3)
        expected = sorted(
            ["copy1.jpg", str(Path("sub") / "copy2.jpg"), str(Path("sub") / "deep" / "renamed.png")]
        )
        self.assertEqual(sorted(str(d.relative_path) for d in group.duplicates), expected)
        # keeper 一定来自 A，duplicates 一定来自 B
        self.assertEqual(group.keeper.root, self.a)
        for duplicate in group.duplicates:
            self.assertEqual(duplicate.root, self.b)

    def test_same_size_one_byte_difference_not_grouped(self) -> None:
        """AC2：同大小、仅末尾 1 字节不同 → 不成组、不算校验不一致。"""
        payload = bytearray(b"Z" * 4096)
        write_file(self.a / "a.bin", bytes(payload))
        payload[-1] ^= 0xFF
        write_file(self.b / "b.bin", bytes(payload))

        result = find_cross_duplicates(self.a, self.b)

        self.assertEqual(result.groups, [])
        self.assertEqual(result.mismatches, [])
        self.assertGreater(result.hashed_files, 0)

    def test_large_files_multi_chunk_difference(self) -> None:
        """AC2：跨多个 1 MiB 分块的大文件同样不能误判。"""
        size = CHUNK_SIZE * 2 + 777
        payload = bytearray(os.urandom(size))
        write_file(self.a / "big.bin", bytes(payload))
        payload[-1] ^= 0x01
        write_file(self.b / "big-copy.bin", bytes(payload))

        result = find_cross_duplicates(self.a, self.b)

        self.assertEqual(result.groups, [])
        self.assertEqual(result.mismatches, [])

    def test_b_internal_duplicates_not_reported(self) -> None:
        """B 内部互相重复、A 中没有的文件：本页不处理。"""
        write_file(self.a / "a.bin", b"AAAA")
        write_file(self.b / "x.bin", b"BBBB")
        write_file(self.b / "y.bin", b"BBBB")

        result = find_cross_duplicates(self.a, self.b)

        self.assertEqual(result.groups, [])
        self.assertEqual(result.mismatches, [])

    def test_b_duplicate_of_a_never_takes_keeper_from_b(self) -> None:
        """A 内两份相同内容时只输出一组，keeper 取 A 内路径排序第一个。"""
        payload = b"same-content" * 20
        write_file(self.a / "z-first.jpg", payload)
        write_file(self.a / "sub" / "a-second.jpg", payload)
        write_file(self.b / "copy.jpg", payload)

        result = find_cross_duplicates(self.a, self.b)

        self.assertEqual(len(result.groups), 1)
        group = result.groups[0]
        self.assertEqual(group.keeper.path, self.a / "sub" / "a-second.jpg")
        self.assertEqual([d.path for d in group.duplicates], [self.b / "copy.jpg"])
        self.assertNotIn(group.keeper.path, [d.path for d in group.duplicates])

    def test_media_scope_filter(self) -> None:
        write_file(self.a / "photo.jpg", b"image-bytes")
        write_file(self.a / "note.txt", b"text-bytes")
        write_file(self.b / "photo.jpg", b"image-bytes")
        write_file(self.b / "note.txt", b"text-bytes")

        media = find_cross_duplicates(self.a, self.b, scope="media")
        self.assertEqual(len(media.groups), 1)
        self.assertEqual(media.groups[0].duplicates[0].path, self.b / "photo.jpg")

        everything = find_cross_duplicates(self.a, self.b, scope="all")
        self.assertEqual(len(everything.groups), 2)

    def test_zero_byte_files_ignored(self) -> None:
        write_file(self.a / "empty.jpg", b"")
        write_file(self.b / "empty.jpg", b"")
        result = find_cross_duplicates(self.a, self.b)
        self.assertEqual(result.scanned_files, 0)
        self.assertEqual(result.groups, [])

    def test_size_prefilter_avoids_useless_hashing(self) -> None:
        """A 中尺寸与 B 全不相同的文件不应参与哈希。"""
        write_file(self.a / "a10.bin", b"0123456789")                       # A 有 10 字节
        write_file(self.a / "a20.bin", b"01234567890123456789")             # A 有 20 字节（B 无）
        write_file(self.b / "b10.bin", b"0123456789")                       # B 有 10 字节

        result = find_cross_duplicates(self.a, self.b)

        self.assertEqual(result.scanned_files, 3)
        # 只哈希 A/a10 + B/b10
        self.assertEqual(result.hashed_files, 2)
        self.assertGreater(result.hashed_bytes, 0)
        self.assertEqual(len(result.groups), 1)

    def test_same_size_different_content_in_a_disambiguated_by_hash(self) -> None:
        """A 内有同大小但内容不同的文件，B 只匹配其中一个：不能按大小串组。"""
        write_file(self.a / "left.bin", b"LLLLLLLL")
        write_file(self.a / "right.bin", b"RRRRRRRR")
        write_file(self.b / "copy.bin", b"RRRRRRRR")

        result = find_cross_duplicates(self.a, self.b)

        self.assertEqual(len(result.groups), 1)
        self.assertEqual(result.groups[0].keeper.path, self.a / "right.bin")
        self.assertEqual([d.path for d in result.groups[0].duplicates], [self.b / "copy.bin"])
        self.assertEqual(result.mismatches, [])

    def test_duplicates_are_sorted_deterministically(self) -> None:
        payload = b"deterministic" * 100
        write_file(self.a / "keep.bin", payload)
        for name in ("zeta.bin", "Alpha.bin", "mid.bin"):
            write_file(self.b / "sub" / name, payload)
        first = find_cross_duplicates(self.a, self.b)
        second = find_cross_duplicates(self.a, self.b)
        names = [dup.path.name for dup in first.groups[0].duplicates]
        self.assertEqual(names, ["Alpha.bin", "mid.bin", "zeta.bin"])
        self.assertEqual(
            names, [dup.path.name for dup in second.groups[0].duplicates]
        )

    def test_scan_result_counters_are_consistent(self) -> None:
        payload = b"counter-check" * 50
        write_file(self.a / "a.bin", payload)
        write_file(self.a / "unique-size.bin", b"z" * 4095)
        write_file(self.b / "b1.bin", payload)
        write_file(self.b / "b2.bin", payload)

        result = find_cross_duplicates(self.a, self.b)

        self.assertEqual(result.scanned_files, 4)
        # 只哈希 A/a.bin + B/b1 + B/b2（unique-size 在 B 中无同尺寸候选）
        self.assertEqual(result.hashed_files, 3)
        self.assertEqual(result.hashed_bytes, len(payload) * 3)
        self.assertFalse(result.cancelled)

    def test_progress_callback_exception_does_not_break_scan(self) -> None:
        payload = b"payload" * 100
        write_file(self.a / "a.jpg", payload)
        write_file(self.b / "b.jpg", payload)

        def boom(stage: str, done: int, total: int) -> None:
            raise RuntimeError("gui signal failure")

        result = find_cross_duplicates(self.a, self.b, on_progress=boom)
        self.assertEqual(len(result.groups), 1)

    def test_large_scan_throttles_progress(self) -> None:
        """进度回调必须节流：500 个同尺寸文件不得触发 500 次回调。"""
        for index in range(500):
            write_file(self.b / "many" / f"f{index}.bin", b"z" * 32)
        write_file(self.a / "match.bin", b"z" * 32)
        calls: list[tuple[str, int, int]] = []
        find_cross_duplicates(self.a, self.b, on_progress=lambda s, d, t: calls.append((s, d, t)))
        hash_calls = [call for call in calls if call[0] == "hash"]
        self.assertGreater(len(hash_calls), 0)
        self.assertLess(len(hash_calls), 500)

    def test_progress_stages_and_final_calls(self) -> None:
        payload = b"payload" * 100
        write_file(self.a / "a.jpg", payload)
        write_file(self.b / "b.jpg", payload)
        calls: list[tuple[str, int, int]] = []
        find_cross_duplicates(self.a, self.b, on_progress=lambda s, d, t: calls.append((s, d, t)))
        stages = {stage for stage, _, _ in calls}
        self.assertTrue(stages.issubset({"enumerate", "hash", "verify"}))
        self.assertIn("hash", stages)
        self.assertIn("verify", stages)

    def test_cancel_returns_partial_result_without_raising(self) -> None:
        write_file(self.a / "a.jpg", b"payload" * 100)
        write_file(self.b / "b.jpg", b"payload" * 100)
        result = find_cross_duplicates(self.a, self.b, should_cancel=lambda: True)
        self.assertIsInstance(result, ScanResult)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.groups, [])

    def test_invariants_hold_on_disk(self) -> None:
        """不变量 1/2：duplicates 与 keeper 真实满足 size+HASH+逐字节一致。"""
        payloads = [os.urandom(300) + bytes([index]) for index in range(3)]
        for index, payload in enumerate(payloads):
            write_file(self.a / f"a{index}.bin", payload)
            write_file(self.b / f"copy{index}-1.bin", payload)
            write_file(self.b / "sub" / f"copy{index}-2.bin", payload)

        result = find_cross_duplicates(self.a, self.b)

        self.assertEqual(len(result.groups), 3)
        a_paths = {entry.path for entry in collect_files(self.a)}
        for group in result.groups:
            self.assertTrue(group.duplicates)
            keeper_hash = sha256_file(group.keeper.path)
            keeper_size = group.keeper.path.stat().st_size
            for duplicate in group.duplicates:
                self.assertNotEqual(duplicate.path, group.keeper.path)
                self.assertNotIn(duplicate.path, a_paths)
                self.assertEqual(duplicate.path.stat().st_size, keeper_size)
                self.assertEqual(sha256_file(duplicate.path), keeper_hash)
                self.assertTrue(files_identical(group.keeper.path, duplicate.path))


class HashMismatchTests(TempCase):
    def test_identical_hash_but_different_bytes_becomes_mismatch(self) -> None:
        """AC3：monkeypatch 哈希使 SHA-256「相同」但内容不同 → mismatches，不回收。"""
        write_file(self.a / "a.bin", b"AAAA")
        write_file(self.b / "b.bin", b"BBBB")

        with mock.patch.object(core, "sha256_file", return_value="0" * 64):
            result = find_cross_duplicates(self.a, self.b)

        self.assertEqual(result.groups, [])
        self.assertEqual(len(result.mismatches), 1)
        mismatch: HashMismatch = result.mismatches[0]
        self.assertEqual(mismatch.sha256, "0" * 64)
        self.assertEqual(mismatch.keeper.path, self.a / "a.bin")
        self.assertEqual(mismatch.other.path, self.b / "b.bin")

    def test_verify_read_error_becomes_issue_not_group(self) -> None:
        write_file(self.a / "a.bin", b"AAAA")
        write_file(self.b / "b.bin", b"AAAA")

        with mock.patch.object(
            core, "files_identical", side_effect=PermissionError(13, "denied")
        ):
            result = find_cross_duplicates(self.a, self.b)

        self.assertEqual(result.groups, [])
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].stage, "verify")

    def test_hash_read_error_becomes_issue_and_other_groups_survive(self) -> None:
        """AC8：单个文件读不了 → 进 issues，不崩溃，不回收，其他组照常输出。"""
        locked = write_file(self.b / "locked.bin", b"locked-content")
        write_file(self.a / "locked.bin", b"locked-content")
        good = b"good-content"
        write_file(self.a / "good.bin", good)
        write_file(self.b / "good-copy.bin", good)

        real_sha = core.sha256_file

        def flaky(path, **kwargs):
            if Path(path) == locked:
                raise PermissionError(13, "denied")
            return real_sha(path, **kwargs)

        with mock.patch.object(core, "sha256_file", side_effect=flaky):
            result = find_cross_duplicates(self.a, self.b)

        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].stage, "hash")
        self.assertEqual(result.issues[0].path, locked)
        self.assertEqual(len(result.groups), 1)
        self.assertEqual(result.groups[0].duplicates[0].path, self.b / "good-copy.bin")
        for group in result.groups:
            self.assertNotIn(locked, [dup.path for dup in group.duplicates])

    def test_enumerate_error_becomes_issue(self) -> None:
        """AC8：枚举条目失败 → issue，不抛到调用方。"""
        write_file(self.a / "a.bin", b"AAAA")
        write_file(self.b / "b.bin", b"AAAA")
        write_file(self.b / "broken.bin", b"AAAA")
        real_classify = core._classify_entry

        def flaky(entry):
            if entry.name == "broken.bin":
                raise PermissionError(13, "denied")
            return real_classify(entry)

        with mock.patch.object(core, "_classify_entry", side_effect=flaky):
            result = find_cross_duplicates(self.a, self.b)

        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].stage, "enumerate")
        self.assertEqual(result.issues[0].path, self.b / "broken.bin")
        for group in result.groups:
            self.assertNotIn(self.b / "broken.bin", [dup.path for dup in group.duplicates])

    def test_validate_error_propagates_as_value_error(self) -> None:
        """参数/环境错误不是扫描问题：必须原样抛出 ValueError（不是塞进 issues）。"""
        with self.assertRaises(ValueError) as ctx:
            find_cross_duplicates(self.a, self.a)
        self.assertEqual(str(ctx.exception), "same_root")


# ---------------------------------------------------------------------------
# 目录内去重（AC7）
# ---------------------------------------------------------------------------


class InternalDedupeTests(TempCase):
    def _build_layout(self, mtimes: tuple[int, int, int]) -> Path:
        payload = b"identical-bytes" * 400
        root = self.a
        write_file(root / "shallow.jpg", payload, mtimes[0])
        write_file(root / "sub1" / "one.jpg", payload, mtimes[1])
        write_file(root / "sub2" / "deeper" / "two.jpg", payload, mtimes[2])
        return root

    def test_shallowest_strategy(self) -> None:
        root = self._build_layout((3000, 2000, 1000))
        result = find_internal_duplicates(root, keep_strategy="shallowest")
        self.assertEqual(len(result.groups), 1)
        group = result.groups[0]
        self.assertEqual(group.keeper.path, root / "shallow.jpg")
        self.assertEqual(len(group.duplicates), 2)

    def test_oldest_strategy(self) -> None:
        root = self._build_layout((3000, 2000, 1000))
        result = find_internal_duplicates(root, keep_strategy="oldest")
        self.assertEqual(result.groups[0].keeper.path, root / "sub2" / "deeper" / "two.jpg")

    def test_newest_strategy(self) -> None:
        root = self._build_layout((3000, 2000, 1000))
        result = find_internal_duplicates(root, keep_strategy="newest")
        self.assertEqual(result.groups[0].keeper.path, root / "shallow.jpg")

    def test_deterministic_across_runs(self) -> None:
        root = self._build_layout((5000, 5000, 5000))
        first = find_internal_duplicates(root, keep_strategy="shallowest")
        second = find_internal_duplicates(root, keep_strategy="shallowest")
        third = find_internal_duplicates(root, keep_strategy="shallowest")
        signatures = [
            (
                str(result.groups[0].keeper.path),
                [str(dup.path) for dup in result.groups[0].duplicates],
            )
            for result in (first, second, third)
        ]
        self.assertEqual(signatures[0], signatures[1])
        self.assertEqual(signatures[1], signatures[2])

    def test_every_group_keeps_exactly_one_untouched_file(self) -> None:
        """AC7：每组恰好保留 1 个文件，keeper 不在 duplicates；只有 duplicates 非空的组输出。"""
        root = self._build_layout((3000, 2000, 1000))
        write_file(root / "unique.jpg", b"unique-only")
        write_file(root / "same-size-a.jpg", b"0123456789")
        write_file(root / "same-size-b.jpg", b"9876543210")

        result = find_internal_duplicates(root, keep_strategy="shallowest")

        self.assertEqual(len(result.groups), 1)
        group = result.groups[0]
        self.assertNotIn(group.keeper.path, [dup.path for dup in group.duplicates])
        self.assertEqual(len(group.duplicates), 2)
        for duplicate in group.duplicates:
            self.assertTrue(files_identical(group.keeper.path, duplicate.path))

    def test_zero_byte_and_singleton_files_skipped(self) -> None:
        write_file(self.a / "empty1.bin", b"")
        write_file(self.a / "empty2.bin", b"")
        write_file(self.a / "only.bin", b"solo")
        result = find_internal_duplicates(self.a)
        self.assertEqual(result.groups, [])
        self.assertEqual(result.scanned_files, 1)

    def test_media_scope_case_insensitive_suffix(self) -> None:
        write_file(self.a / "UP.JPG", b"img")
        write_file(self.a / "clip.MOV", b"vid")
        write_file(self.a / "doc.PDF", b"pdf")
        self.assertEqual(sorted(e.path.name for e in collect_files(self.a, "media")), ["UP.JPG", "clip.MOV"])

    def test_media_scope_in_internal_mode(self) -> None:
        write_file(self.a / "p1.jpg", b"img")
        write_file(self.a / "p2.jpg", b"img")
        write_file(self.a / "t1.txt", b"txt")
        write_file(self.a / "t2.txt", b"txt")
        media = find_internal_duplicates(self.a, scope="media")
        self.assertEqual(len(media.groups), 1)
        self.assertEqual(media.groups[0].keeper.path.suffix, ".jpg")

    def test_equal_depth_tie_broken_by_path(self) -> None:
        payload = b"tie" * 100
        write_file(self.a / "b-dir" / "x.bin", payload)
        write_file(self.a / "a-dir" / "x.bin", payload)
        result = find_internal_duplicates(self.a, keep_strategy="shallowest")
        self.assertEqual(result.groups[0].keeper.path, self.a / "a-dir" / "x.bin")

    def test_unknown_strategy_raises(self) -> None:
        with self.assertRaises(ValueError):
            find_internal_duplicates(self.a, keep_strategy="unknown")  # type: ignore[arg-type]

    def test_cancel_returns_partial_result_without_raising(self) -> None:
        write_file(self.a / "p1.jpg", b"img")
        write_file(self.a / "p2.jpg", b"img")
        result = find_internal_duplicates(self.a, should_cancel=lambda: True)
        self.assertTrue(result.cancelled)


class ChooseKeeperTests(TempCase):
    def test_shallowest_prefers_shortest_relative_path(self) -> None:
        deep = write_file(self.a / "x" / "y" / "deep.jpg", b"1")
        shallow = write_file(self.a / "short.jpg", b"1")
        entries = [entry_of(deep, self.a), entry_of(shallow, self.a)]
        self.assertEqual(choose_keeper(entries, "shallowest").path, shallow)

    def test_oldest_and_newest(self) -> None:
        older = write_file(self.a / "older.jpg", b"1", 1_000_000_000)
        newer = write_file(self.a / "newer.jpg", b"1", 2_000_000_000)
        entries = [entry_of(older, self.a), entry_of(newer, self.a)]
        self.assertEqual(choose_keeper(entries, "oldest").path, older)
        self.assertEqual(choose_keeper(entries, "newest").path, newer)

    def test_empty_and_unknown(self) -> None:
        with self.assertRaises(ValueError):
            choose_keeper([], "shallowest")
        path = write_file(self.a / "f.jpg", b"1")
        with self.assertRaises(ValueError):
            choose_keeper([entry_of(path, self.a)], "bogus")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 执行前复核与回收（AC4 / AC5）
# ---------------------------------------------------------------------------


class RevalidateTests(TempCase):
    def setUp(self) -> None:
        super().setUp()
        self.payload = b"duplicate-payload" * 300
        self.keeper_path = write_file(self.a / "keeper.jpg", self.payload, 1_600_000_000_000_000_000)
        self.target_path = write_file(self.b / "target.jpg", self.payload, 1_600_000_000_500_000_000)
        self.keeper = entry_of(self.keeper_path, self.a)
        self.target = entry_of(self.target_path, self.b)

    def test_clean_pair_passes(self) -> None:
        self.assertIsNone(revalidate_pair(self.target, self.keeper))

    def test_same_path(self) -> None:
        self.assertEqual(revalidate_pair(self.keeper, self.keeper), "same_path")

    def test_target_missing(self) -> None:
        self.target_path.unlink()
        self.assertEqual(revalidate_pair(self.target, self.keeper), "target_missing")

    def test_keeper_missing(self) -> None:
        """AC5：扫描后删除参照/保留文件 → keeper_missing。"""
        self.keeper_path.unlink()
        self.assertEqual(revalidate_pair(self.target, self.keeper), "keeper_missing")

    def test_target_mtime_changed(self) -> None:
        os.utime(self.target_path, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
        self.assertEqual(revalidate_pair(self.target, self.keeper), "target_changed")

    def test_target_size_changed(self) -> None:
        self.target_path.write_bytes(self.payload + b"x")
        self.assertEqual(revalidate_pair(self.target, self.keeper), "target_changed")

    def test_keeper_changed(self) -> None:
        os.utime(self.keeper_path, ns=(1_800_000_000_000_000_000, 1_800_000_000_000_000_000))
        self.assertEqual(revalidate_pair(self.target, self.keeper), "keeper_changed")

    def test_content_differs_same_size_same_mtime(self) -> None:
        """AC4 的强形态：大小与 mtime 都恢复原样，逐字节复核仍然拦住。"""
        original = entry_of(self.target_path, self.b)
        mutated = bytes((byte ^ 0xFF) for byte in self.payload[:1]) + self.payload[1:]
        self.target_path.write_bytes(mutated)
        os.utime(self.target_path, ns=(original.mtime_ns, original.mtime_ns))
        self.assertEqual(revalidate_pair(self.target, self.keeper), "content_differs")

    def test_byte_verify_can_be_disabled(self) -> None:
        self.target_path.write_bytes(b"x" * len(self.payload))
        os.utime(self.target_path, ns=(self.target.mtime_ns, self.target.mtime_ns))
        self.assertEqual(revalidate_pair(self.target, self.keeper, byte_verify=False), None)

    def test_read_error_mapped(self) -> None:
        with mock.patch.object(core, "files_identical", side_effect=OSError(5, "io error")):
            self.assertEqual(revalidate_pair(self.target, self.keeper), "read_error")

    def test_hardlink_to_keeper_is_same_path(self) -> None:
        link_path = self.b / "hardlink.jpg"
        try:
            os.link(self.keeper_path, link_path)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("当前文件系统不支持硬链接")
        self.assertEqual(revalidate_pair(entry_of(link_path, self.b), self.keeper), "same_path")

    def test_cancel_propagates(self) -> None:
        # 契约：取消不是「跳过原因」，而是 ScanCancelled（worker 据此置「已停止」）
        with self.assertRaises(ScanCancelled):
            revalidate_pair(self.target, self.keeper, should_cancel=lambda: True)
        # 即使关闭逐字节复核，取消也必须抛（不得继续走回收）
        with self.assertRaises(ScanCancelled):
            revalidate_pair(self.target, self.keeper, byte_verify=False, should_cancel=lambda: True)


class RecycleTests(TempCase):
    """不变量 3：复核不通过时绝不调用 send2trash。"""

    def setUp(self) -> None:
        super().setUp()
        self.payload = b"recycle-payload" * 200
        self.keeper_path = write_file(self.a / "keeper.jpg", self.payload, 1_600_000_000_000_000_000)
        self.target_path = write_file(self.b / "target.jpg", self.payload, 1_600_000_000_500_000_000)
        self.keeper = entry_of(self.keeper_path, self.a)
        self.target = entry_of(self.target_path, self.b)
        self.calls: list[str] = []

    def _patch_send2trash(self, side_effect=None):
        def fake(path: str) -> None:
            self.calls.append(path)
            if side_effect is not None:
                raise side_effect

        return mock.patch.object(core, "send2trash", fake)

    def test_recycles_target_only(self) -> None:
        with self._patch_send2trash():
            outcome = recycle_duplicate(self.target, self.keeper)
        self.assertEqual(outcome.status, "recycled")
        self.assertEqual(outcome.reason, "")
        self.assertEqual(self.calls, [str(self.target_path)])
        self.assertTrue(self.keeper_path.exists())
        self.assertTrue(self.target_path.exists())  # fake 不会真的删除

    def test_skip_reasons_never_call_send2trash(self) -> None:
        mutations = {
            "target_missing": lambda: self.target_path.unlink(),
            "keeper_missing": lambda: self.keeper_path.unlink(),
            "target_changed": lambda: os.utime(
                self.target_path, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000)
            ),
            "keeper_changed": lambda: os.utime(
                self.keeper_path, ns=(1_800_000_000_000_000_000, 1_800_000_000_000_000_000)
            ),
            "content_differs": lambda: (
                self.target_path.write_bytes(b"y" * len(self.payload)),
                os.utime(self.target_path, ns=(self.target.mtime_ns, self.target.mtime_ns)),
            ),
        }
        for expected_reason, mutate in mutations.items():
            with self.subTest(reason=expected_reason):
                # 每个子用例重建文件与快照
                write_file(self.keeper_path, self.payload, self.keeper.mtime_ns)
                write_file(self.target_path, self.payload, self.target.mtime_ns)
                self.calls.clear()
                mutate()
                with self._patch_send2trash():
                    outcome = recycle_duplicate(self.target, self.keeper)
                self.assertEqual(outcome.status, "skipped")
                self.assertEqual(outcome.reason, expected_reason)
                self.assertEqual(self.calls, [])

    def test_byte_verify_off_still_guards_mtime(self) -> None:
        os.utime(self.target_path, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
        with self._patch_send2trash():
            outcome = recycle_duplicate(self.target, self.keeper, byte_verify=False)
        self.assertEqual(outcome.status, "skipped")
        self.assertEqual(outcome.reason, "target_changed")
        self.assertEqual(self.calls, [])

    def test_send2trash_unavailable(self) -> None:
        with mock.patch.object(core, "send2trash", None):
            outcome = recycle_duplicate(self.target, self.keeper)
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason, "send2trash_unavailable")
        self.assertTrue(self.target_path.exists())

    def test_send2trash_exception_becomes_failed(self) -> None:
        with self._patch_send2trash(side_effect=OSError(0, "shell failure")):
            outcome = recycle_duplicate(self.target, self.keeper)
        self.assertEqual(outcome.status, "failed")
        self.assertIn("shell failure", outcome.reason)
        self.assertTrue(self.target_path.exists())

    def test_same_path_never_recycled(self) -> None:
        with self._patch_send2trash():
            outcome = recycle_duplicate(self.keeper, self.keeper)
        self.assertEqual(outcome.status, "skipped")
        self.assertEqual(outcome.reason, "same_path")
        self.assertEqual(self.calls, [])

    def test_cancel_during_recycle_raises_without_trashing(self) -> None:
        """取消必须抛 ScanCancelled，且绝不调用 send2trash。"""
        with self._patch_send2trash():
            with self.assertRaises(ScanCancelled):
                recycle_duplicate(self.target, self.keeper, should_cancel=lambda: True)
        self.assertEqual(self.calls, [])
        self.assertTrue(self.target_path.exists())

    def test_byte_verify_off_still_honours_cancel(self) -> None:
        with self._patch_send2trash():
            with self.assertRaises(ScanCancelled):
                recycle_duplicate(
                    self.target, self.keeper, byte_verify=False, should_cancel=lambda: True
                )
        self.assertEqual(self.calls, [])


# ---------------------------------------------------------------------------
# 端到端：扫描 → 复核 → 回收 不会动到参照文件
# ---------------------------------------------------------------------------


class EndToEndTests(TempCase):
    def test_cross_scan_then_recycle_all_three_copies(self) -> None:
        """AC1 全链路：3 份副本全部被判可回收，A 原文件不动。"""
        payload = b"end-to-end-payload" * 300
        keeper_path = write_file(self.a / "orig.jpg", payload)
        targets = [
            write_file(self.b / "c1.jpg", payload),
            write_file(self.b / "sub" / "c2.jpg", payload),
            write_file(self.b / "sub" / "deep" / "c3.jpg", payload),
        ]

        result = find_cross_duplicates(self.a, self.b)
        group: DuplicateGroup = result.groups[0]
        self.assertEqual(len(group.duplicates), 3)

        trashed: list[str] = []
        with mock.patch.object(core, "send2trash", lambda path: trashed.append(path)):
            outcomes = [recycle_duplicate(dup, group.keeper) for dup in group.duplicates]

        self.assertTrue(all(outcome.status == "recycled" for outcome in outcomes))
        self.assertEqual(sorted(trashed), sorted(str(path) for path in targets))
        self.assertTrue(keeper_path.exists())
        self.assertEqual(keeper_path.read_bytes(), payload)

    def test_internal_scan_keeps_one_per_group(self) -> None:
        payload = b"internal-payload" * 300
        keeper_path = write_file(self.a / "keep.jpg", payload)
        others = [
            write_file(self.a / "x" / "dup1.jpg", payload),
            write_file(self.a / "y" / "z" / "dup2.jpg", payload),
        ]

        result = find_internal_duplicates(self.a, keep_strategy="shallowest")
        group = result.groups[0]
        self.assertEqual(group.keeper.path, keeper_path)

        trashed: list[str] = []
        with mock.patch.object(core, "send2trash", lambda path: trashed.append(path)):
            for duplicate in group.duplicates:
                recycle_duplicate(duplicate, group.keeper)

        self.assertEqual(sorted(trashed), sorted(str(path) for path in others))
        self.assertTrue(keeper_path.exists())


# ---------------------------------------------------------------------------
# 契约形状（防止并行开发时签名漂移）
# ---------------------------------------------------------------------------


class CoreClassificationAndKeeperTests(TempCase):
    def _snapshot(self, name: str, *, root: Path | None = None, size: int = 7,
                  mtime_ns: int = 11, file_id: tuple[int, int] = (1, 2)) -> FileEntry:
        scan_root = root or self.a
        return FileEntry(scan_root / name, scan_root, size, mtime_ns, file_id)

    def test_every_media_extension_has_one_explicit_category(self) -> None:
        self.assertTrue(core.VIDEO_EXTENSIONS <= core.MEDIA_EXTENSIONS)
        self.assertEqual(
            {suffix for suffix in core.MEDIA_EXTENSIONS
             if core.classify_media_type(Path("not-created" + suffix)) == "video"},
            core.VIDEO_EXTENSIONS,
        )
        self.assertEqual(
            {suffix for suffix in core.MEDIA_EXTENSIONS
             if core.classify_media_type(Path("not-created" + suffix)) == "photo"},
            core.MEDIA_EXTENSIONS - core.VIDEO_EXTENSIONS,
        )
        self.assertEqual(len(core.MEDIA_EXTENSIONS), 55)
        self.assertEqual(len(core.VIDEO_EXTENSIONS), 22)

    def test_media_type_is_case_insensitive_and_unknown_is_other(self) -> None:
        cases = {
            "PHOTO.JpEg": "photo",
            "clip.MOV": "video",
            "archive.tar.gz": "other",
            "no-extension": "other",
            ".profile": "other",
            "camera.photo.JPG": "photo",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(core.classify_media_type(name), expected)

    def test_classification_only_uses_path_text(self) -> None:
        with mock.patch.object(Path, "stat", side_effect=AssertionError("stat called")), \
             mock.patch("builtins.open", side_effect=AssertionError("open called")):
            self.assertEqual(core.classify_media_type(self.tmp / "missing.mp4"), "video")
            self.assertEqual(core.classify_media_type(self.tmp / "missing.unknown"), "other")

    def test_duplicate_group_classification_uses_stable_priority(self) -> None:
        photo = self._snapshot("a.jpg")
        video = self._snapshot("b.mp4")
        other = self._snapshot("c.txt")
        photo_video = DuplicateGroup(photo, [video], "a" * 64, photo.size)
        video_other = DuplicateGroup(video, [other], "b" * 64, video.size)
        other_only = DuplicateGroup(other, [self._snapshot("d.pdf")], "c" * 64, other.size)
        self.assertEqual(core.classify_duplicate_group(photo_video), "photo")
        self.assertEqual(core.classify_duplicate_group(video_other), "video")
        self.assertEqual(core.classify_duplicate_group(other_only), "other")
        singleton_photo = DuplicateGroup(photo, [], "d" * 64, photo.size)
        singleton_video = DuplicateGroup(video, [], "e" * 64, video.size)
        singleton_other = DuplicateGroup(other, [], "f" * 64, other.size)
        self.assertEqual(core.classify_duplicate_group(singleton_photo), "photo")
        self.assertEqual(core.classify_duplicate_group(singleton_video), "video")
        self.assertEqual(core.classify_duplicate_group(singleton_other), "other")
        reselected = core.reselect_internal_keeper(photo_video, video)
        self.assertEqual(core.classify_duplicate_group(reselected), "photo")

    def test_reselect_keeper_returns_new_group_and_preserves_input(self) -> None:
        a = self._snapshot("a.jpg")
        b = self._snapshot("b.jpg", mtime_ns=12, file_id=(1, 3))
        c = self._snapshot("c.jpg", mtime_ns=13, file_id=(1, 4))
        original_duplicates = [c, b]
        group = DuplicateGroup(a, original_duplicates, "e" * 64, a.size)

        changed = core.reselect_internal_keeper(group, b)

        self.assertIsNot(changed, group)
        self.assertIs(changed.keeper, b)
        self.assertEqual(changed.duplicates, [a, c])
        self.assertEqual(changed.sha256, group.sha256)
        self.assertEqual(changed.size, group.size)
        self.assertIs(group.keeper, a)
        self.assertIs(group.duplicates, original_duplicates)
        self.assertEqual(group.duplicates, [c, b])
        self.assertIs(core.reselect_internal_keeper(group, a).keeper, a)

    def test_reselect_requires_full_member_snapshot(self) -> None:
        keeper = self._snapshot("a.jpg")
        member = self._snapshot("b.jpg", mtime_ns=12, file_id=(1, 3))
        group = DuplicateGroup(keeper, [member], "f" * 64, keeper.size)
        altered = (
            replace(member, path=self.a / "renamed.jpg"),
            replace(member, root=self.b),
            replace(member, size=member.size + 1),
            replace(member, mtime_ns=member.mtime_ns + 1),
            replace(member, file_id=(9, 9)),
        )
        for candidate in altered:
            with self.subTest(candidate=candidate), self.assertRaisesRegex(
                ValueError, "keeper_not_group_member"
            ):
                core.reselect_internal_keeper(group, candidate)

    def test_reselect_rejects_cross_root_bad_size_and_duplicate_paths(self) -> None:
        singleton = DuplicateGroup(self._snapshot("solo.jpg"), [], "0" * 64, 7)
        with self.assertRaisesRegex(ValueError, "group_empty"):
            core.reselect_internal_keeper(singleton, singleton.keeper)
        a = self._snapshot("a.jpg")
        foreign = self._snapshot("b.jpg", root=self.b)
        with self.assertRaisesRegex(ValueError, "group_cross_root"):
            core.reselect_internal_keeper(
                DuplicateGroup(a, [foreign], "1" * 64, a.size), foreign
            )
        wrong_size = replace(self._snapshot("c.jpg"), size=a.size + 1)
        with self.assertRaisesRegex(ValueError, "group_size_mismatch"):
            core.reselect_internal_keeper(
                DuplicateGroup(a, [wrong_size], "2" * 64, a.size), a
            )
        duplicate_path = replace(a, mtime_ns=a.mtime_ns + 1)
        with self.assertRaisesRegex(ValueError, "group_duplicate_path"):
            core.reselect_internal_keeper(
                DuplicateGroup(a, [duplicate_path], "3" * 64, a.size), a
            )
        compare_target = self._snapshot("from-b.jpg", root=self.b)
        compare_group = DuplicateGroup(a, [compare_target], "4" * 64, a.size)
        with self.assertRaisesRegex(ValueError, "group_cross_root"):
            core.reselect_internal_keeper(compare_group, compare_target)

    def test_keeper_reselection_does_not_touch_filesystem(self) -> None:
        a = self._snapshot("a.jpg")
        b = self._snapshot("b.jpg", mtime_ns=12, file_id=(1, 3))
        group = DuplicateGroup(a, [b], "5" * 64, a.size)
        with mock.patch.object(Path, "stat", side_effect=AssertionError("stat called")), \
             mock.patch("builtins.open", side_effect=AssertionError("open called")):
            changed = core.reselect_internal_keeper(group, b)
        self.assertIs(changed.keeper, b)


class ContractShapeTests(unittest.TestCase):
    def test_public_signatures(self) -> None:
        self.assertEqual(
            str(inspect.signature(core.validate_compare_roots)),
            "(root_a: 'Path', root_b: 'Path') -> 'None'",
        )
        self.assertEqual(
            str(inspect.signature(core.sha256_file)),
            "(path: 'Path', *, chunk_size: 'int' = 1048576, "
            "should_cancel: 'CancelCheck | None' = None) -> 'str'",
        )
        self.assertEqual(
            str(inspect.signature(core.revalidate_pair)),
            "(target: 'FileEntry', keeper: 'FileEntry', *, byte_verify: 'bool' = True, "
            "should_cancel: 'CancelCheck | None' = None) -> 'SkipReason | None'",
        )
        cross = inspect.signature(core.find_cross_duplicates)
        self.assertEqual(
            list(cross.parameters),
            ["root_a", "root_b", "scope", "threads", "should_cancel", "on_progress"],
        )
        self.assertEqual(cross.parameters["scope"].default, "all")
        self.assertEqual(cross.parameters["threads"].default, 4)
        inner = inspect.signature(core.find_internal_duplicates)
        self.assertEqual(
            list(inner.parameters),
            ["root", "scope", "keep_strategy", "threads", "should_cancel", "on_progress"],
        )
        self.assertEqual(inner.parameters["keep_strategy"].default, "shallowest")
        self.assertEqual(
            str(inspect.signature(core.classify_media_type)),
            "(path: 'Path | str') -> 'MediaType'",
        )
        self.assertEqual(
            str(inspect.signature(core.classify_duplicate_group)),
            "(group: 'DuplicateGroup') -> 'MediaType'",
        )
        self.assertEqual(
            str(inspect.signature(core.reselect_internal_keeper)),
            "(group: 'DuplicateGroup', new_keeper: 'FileEntry') -> 'DuplicateGroup'",
        )
        for name in ("threads", "should_cancel", "on_progress"):
            self.assertEqual(cross.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertEqual(inner.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_dataclass_fields_match_contract(self) -> None:
        self.assertEqual(list(core.FileEntry.__dataclass_fields__), ["path", "root", "size", "mtime_ns", "file_id"])
        self.assertTrue(core.FileEntry.__dataclass_params__.frozen)
        self.assertEqual(list(core.DuplicateGroup.__dataclass_fields__), ["keeper", "duplicates", "sha256", "size"])
        self.assertEqual(list(core.HashMismatch.__dataclass_fields__), ["keeper", "other", "sha256"])
        self.assertEqual(list(core.ScanIssue.__dataclass_fields__), ["path", "stage", "message"])
        self.assertEqual(
            list(core.ScanResult.__dataclass_fields__),
            ["groups", "mismatches", "issues", "scanned_files", "hashed_files", "hashed_bytes", "cancelled"],
        )
        self.assertEqual(list(core.RecycleOutcome.__dataclass_fields__), ["target", "status", "reason"])

    def test_media_extensions_cover_contract_samples(self) -> None:
        for suffix in (".heic", ".heif", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
                       ".tif", ".tiff", ".dng", ".raw", ".cr2", ".nef", ".arw",
                       ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".3gp", ".wmv", ".mts", ".m2ts"):
            self.assertIn(suffix, core.MEDIA_EXTENSIONS)
            self.assertEqual(suffix, suffix.lower())
        self.assertIsInstance(core.MEDIA_EXTENSIONS, frozenset)

    def test_module_has_no_gui_dependency(self) -> None:
        """核心层不得依赖 PyQt（docstring 里出现这个词是允许的，只检查导入）。"""
        tree = ast.parse(Path(core.__file__).read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertFalse([name for name in imported if "PyQt" in name or "qfluentwidgets" in name])
        self.assertIn("send2trash", [name.split(".")[0] for name in imported])


if __name__ == "__main__":
    unittest.main()