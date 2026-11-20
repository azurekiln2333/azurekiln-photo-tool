"""目录比对页（dir_compare_gui）批量勾选与扫描记录导入导出的回归测试。

覆盖：
- 三键（全选/全不选/反选）通过真实 ``QPushButton.click()`` 触发，只作用于合法待回收行；
  保留/异常/碰撞/已处理/取消/失效行禁勾。
- 真实“开始扫描”按钮生成结果 → 导出记录 → 导入记录往返保留分组/指纹/勾选/处理状态。
- 导出使用扫描时的根/选项快照（并规范为绝对路径），不读后来修改过的目录控件。
- 导入后回收强制 ``byte_verify=True``，改动文件被跳过且绝不调用 send2trash。
- 取消/失效记录往返后不可回收；坏记录不破坏当前显示。

隔离：``APPDATA`` 指向临时目录，样例文件全部建在临时目录，绝不触碰真实相册/回收站。
回收时 ``duplicate_scan_core.send2trash`` 被 mock 掉（这是核心里的真实引用点）。

运行：.venv/Scripts/python.exe -m unittest tests.test_compare_page_features -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_TMP_APPDATA = tempfile.mkdtemp(prefix="ls-compare-appdata-")
os.environ["APPDATA"] = _TMP_APPDATA

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import dir_compare_gui as page  # noqa: E402
import duplicate_scan_core  # noqa: E402
from duplicate_scan_core import DuplicateGroup, FileEntry, ScanResult  # noqa: E402
from scan_record_core import ScanRecord, load_record, save_record  # noqa: E402


_APP = QApplication.instance() or QApplication(sys.argv[:1])
_SLOT_ERRORS: list[str] = []


def _excepthook(exc_type, exc_value, exc_tb):
    _SLOT_ERRORS.append("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))


_previous_hook = sys.excepthook
sys.excepthook = _excepthook


def tearDownModule():
    sys.excepthook = _previous_hook


def _pump(timeout: float = 5.0, condition=None) -> bool:
    """跑事件循环直到条件成立或超时。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _APP.processEvents()
        if condition is not None and condition():
            return True
        time.sleep(0.005)
    return condition is None or bool(condition())


def _entry(path: Path, root: Path) -> FileEntry:
    stat = path.stat()
    return FileEntry(
        path=path,
        root=root,
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        file_id=(int(stat.st_dev), int(stat.st_ino)),
    )


class ComparePageTestBase(unittest.TestCase):
    def setUp(self):
        _SLOT_ERRORS.clear()
        self._tmp = tempfile.TemporaryDirectory(prefix="ls-compare-")
        self.tmp = Path(self._tmp.name)
        self.root_a = self.tmp / "A"
        self.root_b = self.tmp / "B"
        (self.root_a / "sub").mkdir(parents=True)
        (self.root_b / "sub").mkdir(parents=True)
        self.files = {}
        for name, payload in (("keep1", b"alpha-1"), ("keep2", b"beta-2")):
            a_file = self.root_a / "sub" / f"{name}.bin"
            a_file.write_bytes(payload)
            b_file = self.root_b / "sub" / f"{name}.bin"
            b_file.write_bytes(payload)
            self.files[name] = (a_file, b_file)
        (self.root_b / "only.bin").write_bytes(b"unique-b")
        self.window = page.MainWindow()
        self.notifications = []
        self.window._notify = lambda title, content, is_error=False: self.notifications.append(
            (title, content, is_error)
        )

    def tearDown(self):
        try:
            self.window._shutdown_workers()
            self.window._release_thumbnail_loader()
            _pump(5.0, lambda: not self.window._workers_running())
            # 删除表格前先撑掉右键菜单事件过滤器，避免对象已删而过滤器仍在响应
            self.window.table.removeEventFilter(self.window.table_context_menu)
            viewport = self.window.table.viewport()
            if viewport is not None:
                viewport.removeEventFilter(self.window.table_context_menu)
            self.window.table.setParent(None)
            self.window.deleteLater()
            # 让 DeferredDelete 真正执行，再断言没有 Qt 槽异常
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
            _APP.processEvents()
        finally:
            self._tmp.cleanup()
        self.assertEqual(_SLOT_ERRORS, [], "Qt 槽异常")

    # ---- 辅助 ----
    def run_real_scan(self):
        """通过真实开始扫描按钮生成结果（不是直接塞 _apply_scan_result）。"""
        self.window.root_a_edit.setText(str(self.root_a))
        self.window.root_b_edit.setText(str(self.root_b))
        self.window.btn_scan.click()
        self.assertTrue(_pump(15.0, lambda: self.window._has_scan), "扫描未完成")
        self.assertTrue(_pump(15.0, lambda: not self.window._is_busy()), "扫描后仍处于忙状态")
        dup = [row for row in self.window.table_model.rows if row.kind == page.KIND_DUPLICATE]
        self.assertEqual(len(dup), 2, [row.status for row in self.window.table_model.rows])
        return dup

    def export_to(self, target: Path) -> ScanRecord:
        with mock.patch.object(
            page.QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *a, **k: (str(target), "")),
        ):
            self.window.btn_export_record.click()
        self.assertTrue(_pump(15.0, lambda: not self.window._is_busy()), "导出未结束")
        self.assertTrue(target.exists(), self.notifications)
        self.assertFalse([n for n in self.notifications if n[2]], self.notifications)
        return load_record(target, expected_mode="compare")

    def import_from(self, source: Path) -> None:
        with mock.patch.object(
            page.QFileDialog,
            "getOpenFileName",
            staticmethod(lambda *a, **k: (str(source), "")),
        ):
            self.window.btn_import_record.click()
        self.assertTrue(_pump(15.0, lambda: not self.window._is_busy()), "导入未结束")


class SelectionTests(ComparePageTestBase):
    def test_select_buttons_only_touch_checkable_rows(self):
        rows = self.run_real_scan()
        model = self.window.table_model
        entries = [row.target for row in rows]
        keeper = rows[0].keeper
        model.rows.append(
            page.CompareRow(
                kind=page.KIND_MISMATCH,
                target=entries[0],
                keeper=keeper,
                sha256="0" * 64,
                status="status_mismatch",
            )
        )
        model.rows.append(
            page.CompareRow(
                kind=page.KIND_ISSUE,
                issue_path=self.root_b / "broken.bin",
                issue_column=page.COL_PATH_B,
                status="status_issue|hash|locked",
            )
        )
        model.rows.append(
            page.CompareRow(
                kind=page.KIND_DUPLICATE,
                target=entries[1],
                keeper=rows[1].keeper,
                sha256=rows[1].sha256,
                checked=False,
                status="status_recycled",
            )
        )

        for row in rows:
            row.checked = False
        rows[0].checked = True

        # 反选：只反转 2 个可回收行，受保护行保持未勾选
        self.window.btn_select_invert.click()
        self.assertFalse(rows[0].checked)
        self.assertTrue(rows[1].checked)
        for row in model.rows[2:]:
            self.assertFalse(row.checked, row.kind)

        # 全选
        self.window.btn_select_all.click()
        self.assertTrue(rows[0].checked and rows[1].checked)
        for row in model.rows[2:]:
            self.assertFalse(row.checked, row.kind)

        # 全不选
        self.window.btn_select_none.click()
        self.assertFalse(any(row.checked for row in rows))

    def test_blocked_when_cancelled_or_stale(self):
        rows = self.run_real_scan()
        for row in rows:
            row.checked = False
        self.window._scan_cancelled = True
        self.window.btn_select_all.click()
        self.assertFalse(any(row.checked for row in rows))
        self.assertTrue(any(is_error for _t, _c, is_error in self.notifications))

        self.window._scan_cancelled = False
        self.window._scan_stale = True
        self.window._update_action_states()
        self.assertFalse(self.window.btn_select_all.isEnabled())
        self.assertFalse(self.window.btn_recycle.isEnabled())
        self.window.btn_select_all.click()
        self.assertFalse(any(row.checked for row in rows))

    def test_model_apply_check_mode_returns_count(self):
        rows = self.run_real_scan()
        model = self.window.table_model
        for row in rows:
            row.checked = False
        self.assertEqual(model.apply_check_mode("all"), 2)
        self.assertEqual(model.apply_check_mode("all"), 0)
        self.assertEqual(model.apply_check_mode("none"), 2)

    def test_busy_until_thread_reference_cleared(self):
        """回到：线程已退出但 finished 未清理时仍必须算忙，不能重入。

        对应真实症状：_is_busy() 先返回 False，而按钮仍禁用，测试/程序误以为空闲。
        """
        self.run_real_scan()
        self.assertFalse(self.window._is_busy())
        self.assertTrue(self.window.btn_select_all.isEnabled())

        # 模拟“线程已停止，但 finished 回调还没跑”的窗口
        class _StoppedThread:
            def isRunning(self):
                return False

        self.window._scan_thread = _StoppedThread()
        try:
            self.assertTrue(self.window._is_busy())
            self.assertTrue(self.window._workers_running())
            before = [row.checked for row in self.window.table_model.rows]
            # 忙态下点按钮：不改勾选，并给出提示
            self.window.btn_select_none.click()
            self.assertEqual(
                [row.checked for row in self.window.table_model.rows], before
            )
            self.assertTrue(any(is_error for _t, _c, is_error in self.notifications))
        finally:
            self.window._scan_thread = None


class RecordRoundTripTests(ComparePageTestBase):
    def test_round_trip_keeps_groups_and_row_states(self):
        rows = self.run_real_scan()
        rows[0].checked = False
        rows[1].checked = True
        self.window._on_row_check_changed()
        target = self.tmp / "record-compare.json"
        record = self.export_to(target)
        self.assertEqual(record.mode, "compare")
        self.assertEqual(len(record.result.groups), 2)
        self.assertTrue(record.result.groups[0].sha256)
        self.assertEqual(record.scope, self.window._scope())
        self.assertEqual(record.root_a, Path(os.path.abspath(self.root_a)))

        self.window._reset_results()
        self.window.root_a_edit.setText("")
        self.window.root_b_edit.setText("")
        self.import_from(target)
        self.assertTrue(self.window._has_scan)
        self.assertTrue(self.window._record_imported)
        self.assertEqual(self.window.root_a_edit.text(), str(self.root_a))
        duplicates = [r for r in self.window.table_model.rows if r.kind == page.KIND_DUPLICATE]
        self.assertEqual(len(duplicates), 2)
        self.assertEqual(sum(1 for row in duplicates if row.checked), 1)
        self.assertEqual(self.window._recyclable_count(), 2)

    def test_relative_root_is_absolutized_in_snapshot(self):
        self.window.root_a_edit.setText(os.path.relpath(self.root_a, Path.cwd()))
        self.window.root_b_edit.setText(os.path.relpath(self.root_b, Path.cwd()))
        self.window.btn_scan.click()
        self.assertTrue(_pump(15.0, lambda: self.window._has_scan), "扫描未完成")
        self.assertTrue(_pump(15.0, lambda: not self.window._is_busy()))
        target = self.tmp / "relative.json"
        record = self.export_to(target)
        self.assertTrue(os.path.isabs(str(record.root_a)))
        self.assertTrue(os.path.isabs(str(record.root_b)))

    def test_export_uses_scan_time_snapshot(self):
        self.run_real_scan()
        other = self.tmp / "elsewhere"
        other.mkdir()
        # 扫描后改目录控件：导出仍必须记录扫描时的根
        self.window.root_a_edit.setText(str(other))
        self.window.root_b_edit.setText(str(other))
        target = self.tmp / "snapshot.json"
        record = self.export_to(target)
        self.assertEqual(record.root_a, Path(os.path.abspath(self.root_a)))
        self.assertEqual(record.root_b, Path(os.path.abspath(self.root_b)))

    def test_export_disabled_before_scan(self):
        self.assertFalse(self.window.btn_export_record.isEnabled())
        self.assertTrue(self.window.btn_import_record.isEnabled())

    def test_bad_record_does_not_destroy_current_results(self):
        rows = self.run_real_scan()
        before = [row.status for row in self.window.table_model.rows]
        before_checks = [row.checked for row in self.window.table_model.rows]
        bad = self.tmp / "bad.json"
        bad.write_text("{ not json", encoding="utf-8")
        self.import_from(bad)
        self.assertTrue(self.window._has_scan)
        self.assertFalse(self.window._record_imported)
        self.assertEqual([row.status for row in self.window.table_model.rows], before)
        self.assertEqual([row.checked for row in self.window.table_model.rows], before_checks)
        self.assertTrue(any(n[2] for n in self.notifications), self.notifications)

    def test_wrong_mode_record_rejected(self):
        self.run_real_scan()
        before = [row.status for row in self.window.table_model.rows]
        target = self.tmp / "mode.json"
        self.export_to(target)
        data = json.loads(target.read_text(encoding="utf-8"))
        data["mode"] = "internal"
        target.write_text(json.dumps(data), encoding="utf-8")
        self.import_from(target)
        # 拒绝且保留当前结果，不做任何替换
        self.assertTrue(self.window._has_scan)
        self.assertFalse(self.window._record_imported)
        self.assertEqual([row.status for row in self.window.table_model.rows], before)
        self.assertTrue(any(n[2] for n in self.notifications), self.notifications)


class ImportedRecycleGuardTests(ComparePageTestBase):
    def _import_current_record(self) -> Path:
        self.run_real_scan()
        target = self.tmp / f"rec-{time.monotonic_ns()}.json"
        self.export_to(target)
        self.window._reset_results()
        self.import_from(target)
        self.assertTrue(self.window._record_imported)
        return target

    def test_import_forces_byte_verify_and_recycles(self):
        self._import_current_record()
        self.window.byte_verify_check.setChecked(False)
        sent: list[bool] = []
        trash_calls: list[str] = []
        real_recycle = page.recycle_duplicate

        def tracking_recycle(target, keeper, *, byte_verify=True, should_cancel=None):
            sent.append(bool(byte_verify))
            return real_recycle(
                target, keeper, byte_verify=byte_verify, should_cancel=should_cancel
            )

        with mock.patch.object(
            duplicate_scan_core, "send2trash", side_effect=lambda p: trash_calls.append(str(p))
        ), mock.patch.object(page, "recycle_duplicate", tracking_recycle), mock.patch.object(
            page.QMessageBox,
            "question",
            staticmethod(lambda *a, **k: page.QMessageBox.StandardButton.Yes),
        ):
            self.window.btn_recycle.click()
            self.assertTrue(
                _pump(20.0, lambda: not self.window.is_recycling and not self.window._is_busy()),
                "回收未结束",
            )

        self.assertTrue(sent, self.notifications)
        self.assertTrue(all(sent), sent)
        self.assertEqual(len(trash_calls), len(sent))
        self.assertEqual(self.window._recycled_count, len(sent))
        self.assertFalse(self.window.byte_verify_check.isChecked())

    def test_changed_file_is_skipped(self):
        self._import_current_record()
        target_file = self.root_b / "sub" / "keep1.bin"
        stat = target_file.stat()
        payload = bytearray(target_file.read_bytes())
        payload[0] = payload[0] ^ 0xFF
        target_file.write_bytes(bytes(payload))
        os.utime(target_file, ns=(stat.st_atime_ns, stat.st_mtime_ns))

        sent: list[bool] = []
        trash_calls: list[str] = []
        real_recycle = page.recycle_duplicate

        def tracking_recycle(target, keeper, *, byte_verify=True, should_cancel=None):
            sent.append(bool(byte_verify))
            return real_recycle(
                target, keeper, byte_verify=byte_verify, should_cancel=should_cancel
            )

        with mock.patch.object(
            duplicate_scan_core, "send2trash", side_effect=lambda p: trash_calls.append(str(p))
        ), mock.patch.object(page, "recycle_duplicate", tracking_recycle), mock.patch.object(
            page.QMessageBox,
            "question",
            staticmethod(lambda *a, **k: page.QMessageBox.StandardButton.Yes),
        ):
            self.window.btn_recycle.click()
            self.assertTrue(
                _pump(20.0, lambda: not self.window.is_recycling and not self.window._is_busy()),
                "回收未结束",
            )

        self.assertTrue(sent)
        self.assertTrue(all(sent), sent)
        statuses = {
            row.target.path.name: row.status
            for row in self.window.table_model.rows
            if row.target is not None
        }
        self.assertTrue(statuses["keep1.bin"].startswith("status_skipped"), statuses)
        self.assertTrue(target_file.exists(), "被跳过的文件必须留在原处")
        normalized = {os.path.normcase(p) for p in trash_calls}
        self.assertNotIn(os.path.normcase(str(target_file)), normalized)
        self.assertEqual(self.window._skipped_count, 1)

    def test_import_restores_done_counts(self):
        self._import_current_record()
        record = self.window._build_scan_record()
        rows = [r for r in self.window.table_model.rows if r.kind == page.KIND_DUPLICATE]
        self.assertEqual(len(rows), 2)
        rows[0].checked = False
        rows[0].status = "status_recycled"
        rows[1].checked = False
        rows[1].status = "status_skipped|target_changed"
        for row in rows:
            record.row_states[str(row.target.path)] = {
                "checked": row.checked,
                "status": row.status,
            }
        target = self.tmp / "done.json"
        save_record(target, record)
        self.window._reset_results()
        self.import_from(target)
        self.assertEqual(self.window._recycled_count, 1)
        self.assertEqual(self.window._skipped_count, 1)
        self.assertEqual(self.window._failed_count, 0)
        # 已回收/已跳过行不可勾选
        self.assertFalse(any(r.checked for r in self.window.table_model.rows))
        self.assertFalse(self.window.btn_recycle.isEnabled())
        self.assertTrue(self.window.summary.text())
        self.assertTrue(any("summary_done" not in t for t, _c, _e in self.notifications))

    def test_cancelled_record_not_recyclable(self):
        """取消记录导出再导入仍然不可回收（ScanResult.cancelled 随记录往返）。"""
        self.run_real_scan()
        # 用真实结果构造“取消”的 ScanResult，而不是只改 UI 标志
        cancelled_result = replace(self.window._scan_result, cancelled=True)
        record = self.window._build_scan_record()
        record.result = cancelled_result
        target = self.tmp / "cancelled.json"
        save_record(target, record)
        loaded = load_record(target, expected_mode="compare")
        self.assertTrue(loaded.result.cancelled)

        self.window._reset_results()
        self.import_from(target)
        self.assertTrue(self.window._has_scan)
        self.assertTrue(self.window._scan_cancelled)
        self.assertFalse(any(row.checked for row in self.window.table_model.rows))
        self.assertFalse(self.window.btn_recycle.isEnabled())
        self.assertFalse(self.window.btn_select_all.isEnabled())

    def test_stale_record_round_trip_and_rejected(self):
        """失效（stale）记录往返后仍为失效，且不能回收。"""
        self.run_real_scan()
        self.window._scan_stale = True
        self.window._update_action_states()
        self.assertFalse(self.window.btn_recycle.isEnabled())
        target = self.tmp / "stale.json"
        record = self.export_to(target)
        self.assertTrue(record.stale)

        self.window._reset_results()
        self.import_from(target)
        self.assertTrue(self.window._has_scan)
        self.assertTrue(self.window._scan_stale)
        self.assertFalse(any(row.checked for row in self.window.table_model.rows))
        self.assertFalse(self.window.btn_recycle.isEnabled())
        self.assertFalse(self.window.btn_select_all.isEnabled())

    def test_issue_columns_use_record_root(self):
        """历史记录里的异常行分栏用记录自己的根，不受导入前界面上残留根影响。"""
        self.run_real_scan()
        record = self.window._build_scan_record()
        record.result.issues.append(
            duplicate_scan_core.ScanIssue(
                path=self.root_a / "sub" / "broken.bin", stage="hash", message="locked"
            )
        )
        target = self.tmp / "with-issue.json"
        save_record(target, record)
        self.window._reset_results()
        other = self.tmp / "other-root"
        other.mkdir()
        self.window.root_a_edit.setText(str(other))
        self.import_from(target)
        issue_rows = [r for r in self.window.table_model.rows if r.kind == page.KIND_ISSUE]
        self.assertEqual(len(issue_rows), 1)
        self.assertEqual(issue_rows[0].issue_column, page.COL_PATH_A)


class RecordCoreGuardTests(unittest.TestCase):
    """记录层的越界/角色冲突由核心拒绝（页面不应把坏记录应用到界面）。"""

    def test_out_of_root_rejected(self):
        tmp = tempfile.TemporaryDirectory(prefix="ls-record-")
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        a = base / "A"
        b = base / "B"
        a.mkdir()
        b.mkdir()
        (a / "x.bin").write_bytes(b"same")
        (b / "x.bin").write_bytes(b"same")
        result = ScanResult(
            groups=[
                DuplicateGroup(
                    keeper=_entry(a / "x.bin", a),
                    duplicates=[_entry(b / "x.bin", b)],
                    sha256="a" * 64,
                    size=4,
                )
            ],
            scanned_files=2,
        )
        record = ScanRecord(
            mode="compare",
            root_a=a,
            root_b=b,
            scope="all",
            keep_strategy="shallowest",
            result=result,
            row_states={str(b / "x.bin"): {"checked": True, "status": "status_pending"}},
        )
        target = base / "ok.json"
        save_record(target, record)
        self.assertEqual(len(load_record(target, expected_mode="compare").result.groups), 1)

        data = json.loads(target.read_text(encoding="utf-8"))
        data["row_states"] = {
            str(a / "other.bin"): {"checked": True, "status": "status_pending"}
        }
        target.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_record(target, expected_mode="compare")


if __name__ == "__main__":
    unittest.main()
