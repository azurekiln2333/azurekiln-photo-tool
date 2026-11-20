"""目录内去重页功能回归：批量勾选、扫描记录导入导出、导入后回收保护。

真实按钮点击 + 真实 QThread 扫描；回收相关一律 monkeypatch，绝不碰真实回收站。
运行：
    $env:QT_QPA_PLATFORM = "offscreen"
    .venv/Scripts/python.exe -m unittest tests.test_folder_dedupe_features -v
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

_TMP_APPDATA = tempfile.mkdtemp(prefix="test-folder-dedupe-appdata-")
_TMP_LOCALAPPDATA = tempfile.mkdtemp(prefix="test-folder-dedupe-localappdata-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = _TMP_APPDATA
os.environ["LOCALAPPDATA"] = _TMP_LOCALAPPDATA

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtGui import QImage  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import folder_dedupe_gui as g  # noqa: E402
import duplicate_scan_core  # noqa: E402
import media_thumbnail  # noqa: E402
from duplicate_scan_core import (  # noqa: E402
    DuplicateGroup,
    FileEntry,
    RecycleOutcome,
    ScanResult,
    classify_duplicate_group,
    classify_media_type,
    reselect_internal_keeper,
)
from scan_record_core import ScanRecord, load_record, save_record  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


def _pump(app: QApplication, predicate, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return predicate()


class FolderDedupeFixtureMixin:
    """旧回归与新验收共享的 fixture，不包含 unittest 测试方法。"""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="folder-dedupe-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.errors: list[str] = []
        self._orig_hook = sys.excepthook

        def hook(exc_type, exc, tb):
            self.errors.append(f"{exc_type.__name__}: {exc}")
            self._orig_hook(exc_type, exc, tb)

        sys.excepthook = hook
        self.addCleanup(setattr, sys, "excepthook", self._orig_hook)
        self.notifications: list[tuple[str, str]] = []
        for level in ("error", "success"):
            patcher = mock.patch.object(
                g.InfoBar,
                level,
                staticmethod(
                    lambda _level=level, **kw: self.notifications.append(
                        (_level, str(kw.get("content")))
                    )
                ),
            )
            patcher.start()
            self.addCleanup(patcher.stop)
        self.window = g.MainWindow()
        self.addCleanup(self._teardown_window)

    def _teardown_window(self):
        window = self.window
        try:
            window._shutdown_workers()
            window._release_thumbnail_loader()
        except Exception:
            pass
        # 使用产品真实析构路径，保留右键菜单/事件过滤器生命周期。
        window.close()
        window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.assertFalse(self.errors, self.errors)

    def _make_duplicates(self) -> Path:
        root = self.tmp / "album"
        payload = b"\\xff\\xd8\\xff\\xe0" + b"duplicate-payload" * 64
        for sub in ("a", "b", "c"):
            (root / sub).mkdir(parents=True, exist_ok=True)
            (root / sub / "photo.jpg").write_bytes(payload)
        return root

    def _run_scan(self, root: Path) -> None:
        self.window.root_edit.setText(str(root))
        self.window.btn_scan.click()
        ok = _pump(
            self.app,
            lambda: not self.window.is_scanning and self.window._scan_thread is None,
        )
        self.assertTrue(ok, "扫描未在超时内完成")
        self.assertTrue(_pump(self.app, lambda: not self.window._is_busy()), "扫描收尾未排空")

    def _duplicate_rows(self):
        return [row for row in self.window.table_model.rows if row.kind == g.KIND_DUPLICATE]

    def _keeper_rows(self):
        return [row for row in self.window.table_model.rows if row.kind == g.KIND_KEEPER]

    def _import(self, record_path: Path) -> bool:
        with mock.patch.object(
            g.QFileDialog, "getOpenFileName", return_value=(str(record_path), "")
        ):
            self.window.btn_import_record.click()
            return _pump(self.app, lambda: self.window._record_thread is None)


class FolderDedupePageTests(FolderDedupeFixtureMixin, unittest.TestCase):
    # ---- 批量勾选 -----------------------------------------------------
    def test_real_scan_and_batch_selection_protects_illegal_rows(self):
        root = self._make_duplicates()
        self._run_scan(root)

        duplicates = self._duplicate_rows()
        keepers = self._keeper_rows()
        self.assertTrue(duplicates, "扫描应产出重复行")
        self.assertTrue(keepers, "扫描应产出保留行")

        # 构造一批不可勾选的行，验证批量操作不会碰它们
        keeper = keepers[0].entry
        keeper_row = keepers[0]
        self.window.table_model.rows.append(
            g.DedupeRow(kind=g.KIND_MISMATCH, keeper=keeper, entry=keeper, status="status_mismatch")
        )
        self.window.table_model.rows.append(
            g.DedupeRow(kind=g.KIND_ISSUE, issue_path=self.tmp / "broken.jpg", status="status_issue|hash|boom")
        )
        self.window.table_model.rows.append(
            g.DedupeRow(
                kind=g.KIND_DUPLICATE,
                entry=keeper,
                keeper=keeper,
                status="status_recycled",
            )
        )
        self.window.table_model.reset_rows(list(self.window.table_model.rows))
        self.window._update_action_states()

        # 真实点击「全选」
        self.window.btn_select_all.click()
        self.app.processEvents()
        self.assertTrue(all(row.checked for row in duplicates))
        self.assertFalse(any(row.checked for row in keepers))
        for row in self.window.table_model.rows:
            if row.kind in (g.KIND_MISMATCH, g.KIND_ISSUE):
                self.assertFalse(row.checked, "异常/碰撞行不可被批量勾选")
            if row.kind == g.KIND_DUPLICATE and row.status != "status_pending":
                self.assertFalse(row.checked, "已处理行不可被批量勾选")

        # 真实点击「全不选」
        self.window.btn_select_none.click()
        self.app.processEvents()
        self.assertFalse(any(row.checked for row in self.window.table_model.rows))

        # 真实点击「反选」
        self.window.btn_invert.click()
        self.app.processEvents()
        self.assertTrue(all(row.checked for row in duplicates))
        self.assertFalse(any(row.checked for row in keepers))

        # Ctrl+A 快捷键同样只作用于合法行
        self.window.select_none_checkable()
        self.window._select_all_shortcut.activated.emit()
        self.app.processEvents()
        self.assertTrue(all(row.checked for row in duplicates))
        self.assertFalse(any(row.checked for row in keepers))
        self.assertFalse(self.errors, self.errors)

    def test_batch_buttons_disabled_when_stale(self):
        root = self._make_duplicates()
        self._run_scan(root)
        self.window.keep_strategy_combo.setCurrentIndex(1)  # 触发 stale
        self.app.processEvents()
        self.assertTrue(self.window._scan_stale)
        self.window._update_action_states()
        self.assertFalse(self.window.btn_select_all.isEnabled())
        self.assertEqual(self.window.select_all_checkable(), 0)

    # ---- 导出 ---------------------------------------------------------
    def test_export_uses_scan_time_snapshot_not_live_widgets(self):
        root = self._make_duplicates()
        self._run_scan(root)
        scanned_root = os.path.abspath(str(root))
        scanned_scope = self.window._scope()

        # 扫描后修改控件：导出记录必须仍用扫描时的根/选项
        other = self.tmp / "other-root"
        other.mkdir()
        self.window.root_edit.setText(str(other))
        for index in range(self.window.scope_combo.count()):
            if self.window.scope_combo.itemData(index) != scanned_scope:
                self.window.scope_combo.setCurrentIndex(index)
                break

        target = self.tmp / "record.json"
        with mock.patch.object(
            g.QFileDialog, "getSaveFileName", return_value=(str(target), "")
        ):
            self.window.btn_export_record.click()
            ok = _pump(self.app, lambda: self.window._record_thread is None)
        self.assertTrue(ok, "导出线程未结束")
        self.assertTrue(target.exists(), "导出文件不存在")

        record = load_record(target, expected_mode="internal")
        self.assertEqual(os.path.abspath(str(record.root_a)), scanned_root)
        self.assertEqual(record.scope, scanned_scope)
        self.assertEqual(len(record.result.groups), len(self.window._current_result.groups))
        self.assertTrue(record.row_states, "记录应包含行状态")
        statuses = {state["status"] for state in record.row_states.values()}
        self.assertIn("status_pending", statuses)
        self.assertIn("status_keep", statuses)
        self.assertFalse(self.errors, self.errors)

    def test_export_without_result_is_rejected(self):
        self.window._update_action_states()
        self.assertFalse(self.window.btn_export_record.isEnabled(), "无结果时导出按钮应禁用")
        with mock.patch.object(g.QFileDialog, "getSaveFileName") as dialog:
            self.assertFalse(self.window.export_scan_record())
            self.app.processEvents()
            dialog.assert_not_called()
        self.assertTrue(any("没有可导出" in content for _level, content in self.notifications))

    # ---- 导入 ---------------------------------------------------------
    def _make_record(self, root: Path, *, cancelled: bool = False, stale: bool = False,
                     statuses: dict[str, str] | None = None, checked: bool = True) -> Path:
        files = sorted(root.rglob("*.jpg"))
        self.assertGreaterEqual(len(files), 3, "样例题材不足")
        entries = [
            FileEntry(path=path, root=root, size=path.stat().st_size,
                      mtime_ns=path.stat().st_mtime_ns, file_id=(0, 0))
            for path in files
        ]
        group = DuplicateGroup(keeper=entries[0], duplicates=entries[1:], sha256="a" * 64,
                               size=entries[0].size)
        result = ScanResult(groups=[group], scanned_files=len(entries), hashed_files=len(entries),
                            hashed_bytes=sum(entry.size for entry in entries), cancelled=cancelled)
        rows: dict[str, dict] = {}
        for entry in entries:
            status = (statuses or {}).get(str(entry.path), "status_pending")
            if entry is entries[0]:
                status = "status_keep"
            rows[os.path.normcase(os.path.abspath(str(entry.path)))] = {
                "checked": bool(checked) and status == "status_pending",
                "status": status,
            }
        record = ScanRecord(mode="internal", root_a=root, root_b=None, scope="all",
                            keep_strategy="shallowest", result=result, row_states=rows,
                            created_at="2026-11-21T00:00:00", stale=stale)
        target = self.tmp / ("record-cancelled.json" if cancelled else "record.json")
        save_record(target, record)
        return target

    def _import(self, record_path: Path) -> bool:
        with mock.patch.object(g.QFileDialog, "getOpenFileName",
                               return_value=(str(record_path), "")):
            self.window.btn_import_record.click()
            return _pump(self.app, lambda: self.window._record_thread is None)

    def test_import_restores_rows_status_and_counts(self):
        root = self._make_duplicates()
        done_status = "status_skipped|target_missing"
        record_path = self._make_record(root, statuses={
            str(path): done_status for path in sorted(root.rglob("*.jpg"))[1:2]
        })
        self.assertTrue(self._import(record_path))
        self.assertTrue(self.window._record_imported)
        self.assertTrue(self.window._has_scan)
        self.assertEqual(self.window._group_count, 1)
        self.assertGreaterEqual(self.window._skipped_count, 1, "导入的已跳过行必须计入汇总")
        duplicates = self._duplicate_rows()
        self.assertTrue(any(row.status == done_status for row in duplicates))
        # 已处理行即使记录里 checked=True 也不可勾选
        for row in duplicates:
            if row.status != "status_pending":
                self.assertFalse(row.checked)
        self.assertTrue(self.window.btn_recycle.isEnabled())
        self.assertFalse(self.errors, self.errors)

    def test_import_forces_byte_verify_for_recycle_worker(self):
        root = self._make_duplicates()
        record_path = self._make_record(root)
        self.assertTrue(self._import(record_path))
        self.assertTrue(self.window._record_imported)

        captured: dict[str, bool] = {}

        class CapturingWorker(g.DedupeRecycleWorker):
            def __init__(self, items, byte_verify):
                captured["byte_verify"] = bool(byte_verify)
                super().__init__([], bool(byte_verify))

        self.window.byte_verify_check.setChecked(False)
        with mock.patch.object(g, "DedupeRecycleWorker", CapturingWorker), \
                mock.patch.object(g.QMessageBox, "question",
                                  return_value=QMessageBox.StandardButton.Yes):
            self.window.btn_recycle.click()
            ok = _pump(self.app, lambda: self.window._recycle_thread is None)
        self.assertTrue(ok, "回收线程未结束")
        self.assertIs(captured.get("byte_verify"), True, "导入后必须强制逐字节复核")

    def test_imported_cancelled_record_blocks_recycle(self):
        root = self._make_duplicates()
        record_path = self._make_record(root, cancelled=True)
        self.assertTrue(self._import(record_path))
        self.assertTrue(self.window._scan_cancelled)
        self.window._update_action_states()
        self.assertFalse(self.window.btn_recycle.isEnabled())
        self.assertEqual(self.window.select_all_checkable(), 0)

    def test_imported_stale_record_blocks_recycle(self):
        root = self._make_duplicates()
        record_path = self._make_record(root, stale=True)
        self.assertTrue(self._import(record_path))
        self.assertTrue(self.window._scan_stale)
        self.window._update_action_states()
        self.assertFalse(self.window.btn_recycle.isEnabled())

    def test_bad_record_keeps_current_display(self):
        root = self._make_duplicates()
        self._run_scan(root)
        before_rows = len(self.window.table_model.rows)
        before_imported = self.window._record_imported
        bad = self.tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")

        self.assertTrue(self._import(bad))
        self.assertEqual(len(self.window.table_model.rows), before_rows, "坏记录不得清空当前结果")
        self.assertFalse(self.window._record_imported)
        self.assertEqual(self.window._record_imported, before_imported)
        self.assertTrue(any("导入失败" in content for _level, content in self.notifications))

    def test_wrong_mode_record_is_rejected(self):
        root = self._make_duplicates()
        record_path = self._make_record(root)
        data = json.loads(record_path.read_text(encoding="utf-8"))
        data["mode"] = "compare"
        record_path.write_text(json.dumps(data), encoding="utf-8")
        before = len(self.window.table_model.rows)

        self.assertTrue(self._import(record_path))
        self.assertEqual(len(self.window.table_model.rows), before)
        self.assertFalse(self.window._record_imported)

    def test_new_scan_clears_imported_flag(self):
        root = self._make_duplicates()
        record_path = self._make_record(root)
        self.assertTrue(self._import(record_path))
        self.assertTrue(self.window._record_imported)

        self.window.root_edit.setText(str(root))
        self.window.btn_scan.click()
        _pump(self.app, lambda: not self.window.is_scanning and self.window._scan_thread is None)
        self.assertFalse(self.window._record_imported, "重扫成功必须清除导入标记")
        self.assertIsNotNone(self.window._current_result)

    def test_record_thread_is_busy_until_cleanup(self):
        root = self._make_duplicates()
        record_path = self._make_record(root)
        real_loader = g.load_record

        def slow_loader(path, expected_mode=None):
            time.sleep(0.25)
            return real_loader(path, expected_mode=expected_mode)

        with mock.patch.object(g, "load_record", slow_loader), \
                mock.patch.object(g.QFileDialog, "getOpenFileName",
                                  return_value=(str(record_path), "")):
            self.window.btn_import_record.click()
            self.app.processEvents()
            self.assertIsNotNone(self.window._record_thread, "导入应启动记录线程")
            self.assertTrue(self.window._is_busy(), "记录线程存在时必须算忙")
            self.assertFalse(self.window.btn_scan.isEnabled())
            ok = _pump(self.app, lambda: self.window._record_thread is None)
        self.assertTrue(ok, "记录线程未清理")
        self.assertFalse(self.window._is_busy())

    def test_imported_record_then_changed_files_skipped_without_send2trash(self):
        """合并回归：真实扫描→导出→导入→篡改/删除目标→真实回收按钮。

        断言：mock 的 ``duplicate_scan_core.send2trash`` 从未被调用；
        行状态为 skipped/content_differs 或 target_missing；无任何已回收行。
        同时验证导入后即使取消勾选 byte_verify 也强制逐字节复核（同大小同 mtime 的改写才能被识别）。
        """
        root = self._make_duplicates()
        self._run_scan(root)
        duplicates = self._duplicate_rows()
        self.assertEqual(len(duplicates), 2, "样例应有 2 个待回收副本")

        record_path = self.tmp / "roundtrip.json"
        with mock.patch.object(g.QFileDialog, "getSaveFileName",
                              return_value=(str(record_path), "")):
            self.window.btn_export_record.click()
            self.assertTrue(_pump(self.app, lambda: self.window._record_thread is None))
        self.assertTrue(record_path.exists())

        # 导入前篡改目标：一个同大小同 mtime 改写，一个删除
        targets = sorted((row.entry.path for row in duplicates), key=lambda p: str(p))
        modified_target, deleted_target = targets[0], targets[1]
        before = modified_target.stat()
        payload = modified_target.read_bytes()
        modified_target.write_bytes(b"X" * len(payload))  # 大小不变、内容不同
        os.utime(modified_target, ns=(before.st_atime_ns, before.st_mtime_ns))  # mtime 也不变
        deleted_target.unlink()

        with mock.patch.object(g.QFileDialog, "getOpenFileName",
                              return_value=(str(record_path), "")):
            self.window.btn_import_record.click()
            self.assertTrue(_pump(self.app, lambda: self.window._record_thread is None))
        self.assertTrue(self.window._record_imported)
        self.window._update_action_states()
        self.assertTrue(self.window.btn_recycle.isEnabled(), "导入后应可发起回收（逐项复核）")

        # 取消勾选 byte_verify：导入记录仍必须强制逐字节复核
        self.window.byte_verify_check.setChecked(False)
        send2trash_mock = mock.Mock()
        with mock.patch.object(duplicate_scan_core, "send2trash", send2trash_mock), \
                mock.patch.object(g.QMessageBox, "question",
                                  return_value=QMessageBox.StandardButton.Yes):
            self.window.btn_recycle.click()
            self.assertTrue(_pump(self.app, lambda: self.window._recycle_thread is None),
                            "回收线程未在超时内结束")
        self.app.processEvents()

        send2trash_mock.assert_not_called()
        statuses = {row.primary_path(): row.status for row in self.window.table_model.rows}
        self.assertTrue(statuses[modified_target].startswith("status_skipped|"), statuses[modified_target])
        self.assertIn(
            statuses[modified_target].split("|", 1)[1],
            {"content_differs", "target_changed"},
            statuses[modified_target],
        )
        self.assertEqual(statuses[deleted_target], "status_skipped|target_missing")
        self.assertFalse(any(row.status.startswith("status_recycled")
                             for row in self.window.table_model.rows))
        self.assertEqual(self.window._recycled_count, 0)
        self.assertEqual(self.window._skipped_count, 2)
        self.assertFalse(self.errors, self.errors)

    def test_stopped_thread_reference_still_counts_as_busy(self):
        """停止但尚未 finished 清理的 scan/recycle 线程仍算忙（不靠 sleep）。"""

        root = self._make_duplicates()
        self._run_scan(root)
        self.assertFalse(self.window._is_busy())

        def make_stopped_thread() -> object:
            """真实 QThread：run 空任务后自行 quit，事件循环抽干直到停下。"""
            from PyQt6.QtCore import QThread as _QThread

            class NoopThread(_QThread):
                def run(self):
                    return

            thread = NoopThread()
            thread.start()
            self.assertTrue(thread.wait(5000), "辅助线程未停下")
            self.assertFalse(thread.isRunning())
            return thread

        scan_thread = make_stopped_thread()
        # 主线程尚未处理该线程的 finished 信号：这正是要覆盖的窗口期
        self.window._scan_thread = scan_thread
        self.assertFalse(scan_thread.isRunning(), "此回归要求线程已停止")
        self.assertTrue(self.window._is_busy(), "_scan_thread 非 None 时必须算忙")
        self.window._update_action_states()
        self.assertFalse(self.window.btn_scan.isEnabled())
        self.assertFalse(self.window.btn_select_all.isEnabled())
        self.assertFalse(self.window.btn_import_record.isEnabled())
        # 真实点击被忽略：不会覆盖唯一引用，也不会重新开始扫描
        self.window.btn_scan.click()
        self.app.processEvents()
        self.assertIs(self.window._scan_thread, scan_thread)
        self.assertFalse(self.window.is_scanning)

        self.window._scan_thread = None
        self.assertFalse(self.window._is_busy())

        recycle_thread = make_stopped_thread()
        self.window._recycle_thread = recycle_thread
        self.assertFalse(recycle_thread.isRunning())
        self.assertTrue(self.window._is_busy(), "_recycle_thread 非 None 时必须算忙")
        self.window._update_action_states()
        self.assertFalse(self.window.btn_recycle.isEnabled())
        self.assertFalse(self.window.select_all_checkable(), "忙时批量勾选必须拒绝")
        self.window._recycle_thread = None
        self.window._update_action_states()
        self.assertFalse(self.window._is_busy())
        self.assertFalse(self.errors, self.errors)

    def test_language_switch_updates_new_buttons(self):
        self.window.lang = "en"
        self.window._apply_language()
        self.assertEqual(self.window.btn_select_all.text(), "Select all")
        self.assertEqual(self.window.btn_export_record.text(), "Export record")
        self.assertEqual(self.window.btn_import_record.text(), "Import record")
        self.window.lang = "zh"
        self.window._apply_language()
        self.assertEqual(self.window.btn_invert.text(), "反选")
        self.assertFalse(self.errors, self.errors)


class DedupeGroupsKeeperTests(FolderDedupeFixtureMixin, unittest.TestCase):
    """R1-R5 GUI acceptance for the frozen category/keeper button contract."""

    def setUp(self):
        super().setUp()
        self.window.byte_verify_check.setChecked(True)

        def fast_fixture_decode(_path, size, *, stop_event=None):
            # 类型/keeper UI 测试不验证真实编码；保留 ThumbnailLoader.request、
            # PreviewPanel 和其正向 spy，避免伪 MP4 启动 Shell/Qt 视频解码线程。
            if stop_event is not None and stop_event.is_set():
                return None, "cancelled"
            return QImage(max(1, min(2, int(size))), max(1, min(2, int(size))), QImage.Format.Format_RGB32), ""

        self._thumbnail_decode_patch = mock.patch.object(
            media_thumbnail, "load_thumbnail_image_detail", side_effect=fast_fixture_decode
        )
        self._thumbnail_decode_patch.start()
        self.addCleanup(self._thumbnail_decode_patch.stop)
        self.addCleanup(self._shutdown_fixture_loaders)

    def _shutdown_fixture_loaders(self):
        """关闭 table/preview 两套真实 loader，并有界等待 worker 退出。"""
        loaders = [self.window.thumbnail_loader, self.window.preview_panel.loader()]
        workers = [worker for loader in loaders for worker in list(loader._workers)]
        for loader in loaders:
            loader.shutdown()
        self.assertTrue(
            _pump(self.app, lambda: not any(worker.is_alive() for worker in workers), timeout=5.0),
            "fixture 的 thumbnail worker 未退出",
        )
        self.assertTrue(all(loader._stopped for loader in loaders))

    def _make_typed_duplicates(self) -> Path:
        root = self.tmp / "typed-album"
        fixtures = {
            "photo": ("photo.jpg", b"photo-payload-" * 80),
            "video": ("video.mp4", b"video-payload-" * 90),
            "other": ("data.bin", b"other-payload-" * 100),
        }
        for category, (filename, payload) in fixtures.items():
            for name in ("a", "b", "c"):
                folder = root / category / name
                folder.mkdir(parents=True, exist_ok=True)
                (folder / filename).write_bytes(payload)
        return root

    def _group_rows(self, group_id: int):
        return [
            (index, row)
            for index, row in enumerate(self.window.table_model.rows)
            if row.group_id == group_id
        ]

    def _category_for_group(self, group_id: int) -> str:
        result = self.window._current_result
        self.assertIsNotNone(result)
        return classify_duplicate_group(result.groups[group_id - 1])

    def _category_labels(self, category: str) -> tuple[str, str]:
        return {
            "photo": ("照片", "Photo"),
            "video": ("视频", "Video"),
            "other": ("其他", "Other"),
        }[category]

    def _typed_scan(self) -> Path:
        root = self._make_typed_duplicates()
        self._run_scan(root)
        self.assertEqual(set(self.window.category_buttons), {"photo", "video", "other"})
        return root

    def test_three_category_buttons_show_correct_counts_and_preserve_source_rows(self):
        self._typed_scan()
        result = self.window._current_result
        self.assertIsNotNone(result)
        source_before = [row.primary_path() for row in self.window.table_model.rows]
        expected_groups = {category: 0 for category in ("photo", "video", "other")}
        expected_files = {category: 0 for category in ("photo", "video", "other")}
        group_categories = {}
        for group_id, group in enumerate(result.groups, start=1):
            category = classify_duplicate_group(group)
            group_categories[group_id] = category
            expected_groups[category] += 1
            expected_files[category] += 1 + len(group.duplicates)

        for category, button in self.window.category_buttons.items():
            zh_label, en_label = self._category_labels(category)
            text = button.text()
            self.assertTrue(zh_label in text or en_label in text, (category, text))
            self.assertIn(str(expected_groups[category]), text, (category, text))
            self.assertIn(str(expected_files[category]), text, (category, text))
            button.click()
            self.app.processEvents()
            for index, row in enumerate(self.window.table_model.rows):
                if row.group_id:
                    self.assertEqual(
                        self.window.table.isRowHidden(index),
                        group_categories[row.group_id] != category,
                        (category, index, row.group_id),
                    )

        self.assertEqual(
            [row.primary_path() for row in self.window.table_model.rows], source_before,
            "筛选必须只隐藏 source row，不得重建或重排路径行",
        )
        self.assertEqual(
            len(self.window.table_model.rows), len(source_before),
            "筛选后 worker 使用的 source row 数量必须稳定",
        )

    def test_other_rows_never_request_thumbnail_and_clear_old_preview(self):
        self._typed_scan()
        result = self.window._current_result
        self.assertIsNotNone(result)
        other_group_id = next(
            group_id
            for group_id in range(1, len(result.groups) + 1)
            if self._category_for_group(group_id) == "other"
        )
        photo_group_id = next(
            group_id
            for group_id in range(1, len(result.groups) + 1)
            if self._category_for_group(group_id) == "photo"
        )
        photo_index = self._group_rows(photo_group_id)[0][0]
        other_index = self._group_rows(other_group_id)[0][0]

        self.window.category_buttons["photo"].click()
        self.window.table.selectRow(photo_index)
        self.app.processEvents()
        request = mock.Mock(wraps=self.window.thumbnail_loader.request)
        with mock.patch.object(self.window.thumbnail_loader, "request", request):
            # DecorationRole 是实际表格渲染路径；photo 可请求，other 不可请求。
            self.window.table_model.data(
                self.window.table_model.index(photo_index, g.COL_THUMB),
                Qt.ItemDataRole.DecorationRole,
            )
            self.assertGreater(request.call_count, 0, "photo 行应允许缩略图请求")
            photo_requests = request.call_count
            self.window.category_buttons["other"].click()
            self.window.table.selectRow(other_index)
            self.window.table_model.data(
                self.window.table_model.index(other_index, g.COL_THUMB),
                Qt.ItemDataRole.DecorationRole,
            )
            self.app.processEvents()
            self.assertEqual(request.call_count, photo_requests, "other 行不得请求缩略图")
            self.assertTrue(
                all(slot.path is None for slot in self.window.preview_panel._slot_widgets),
                "选中 other 后两个预览槽都应清空路径，不得残留旧图片",
            )

    def test_video_preview_loader_threads_stop_on_shutdown(self):
        """选中伪视频触发真实 loader request/preview 后，两套 loader 都应退出。"""
        self._typed_scan()
        result = self.window._current_result
        video_group_id = next(
            group_id
            for group_id in range(1, len(result.groups) + 1)
            if self._category_for_group(group_id) == "video"
        )
        row_index = self._group_rows(video_group_id)[0][0]
        self.window.category_buttons["video"].click()
        self.window.table.selectRow(row_index)
        self.window.table_model.data(
            self.window.table_model.index(row_index, g.COL_THUMB),
            Qt.ItemDataRole.DecorationRole,
        )
        self.app.processEvents()
        table_loader = self.window.thumbnail_loader
        preview_loader = self.window.preview_panel.loader()
        workers = list(table_loader._workers) + list(preview_loader._workers)
        self.assertTrue(workers, "视频缩略图请求应启动真实 loader worker")
        self.assertFalse(table_loader._stopped)
        self.assertFalse(preview_loader._stopped)
        self.window._release_thumbnail_loader()
        self.assertTrue(table_loader._stopped)
        self.assertTrue(preview_loader._stopped)
        self.assertTrue(
            _pump(self.app, lambda: not any(worker.is_alive() for worker in workers), timeout=5.0),
            "页面 cleanup 后遗留缩略图线程",
        )

    def test_set_keeper_button_changes_core_group_and_real_worker_uses_new_keeper(self):
        self._typed_scan()
        result = self.window._current_result
        self.assertIsNotNone(result)
        group_id = next(
            group_id
            for group_id in range(1, len(result.groups) + 1)
            if self._category_for_group(group_id) == "photo"
        )
        group_rows = self._group_rows(group_id)
        self.assertGreaterEqual(len(group_rows), 3)
        ordered = sorted(group_rows, key=lambda item: str(item[1].entry.path).casefold())
        old_keeper = next(row for _index, row in ordered if row.kind == g.KIND_KEEPER)
        candidates = [item for item in ordered if item[1].kind == g.KIND_DUPLICATE]
        new_index, new_keeper_row = candidates[0]
        _other_index, other_row = candidates[1]
        # 本用例只回收照片组：其它分类默认全选项必须明确取消，不能把隐藏行算作产品缺陷。
        for row in self._duplicate_rows():
            if row.group_id != group_id:
                row.checked = False
        other_row.checked = False
        source_before = [row.primary_path() for row in self.window.table_model.rows]

        self.window.table.selectRow(new_index)
        self.assertTrue(self.window.btn_set_keeper.isEnabled())
        self.window.btn_set_keeper.click()
        self.app.processEvents()

        updated_group = self.window._current_result.groups[group_id - 1]
        self.assertEqual(updated_group.keeper.path, new_keeper_row.entry.path)
        self.assertEqual(
            {entry.path for entry in updated_group.duplicates},
            {old_keeper.entry.path, other_row.entry.path},
        )
        self.assertEqual(
            [row.primary_path() for row in self.window.table_model.rows], source_before,
            "切 keeper 不得重建 source rows",
        )
        self.assertEqual(new_keeper_row.kind, g.KIND_KEEPER)
        self.assertEqual(new_keeper_row.status, "status_keep")
        self.assertFalse(new_keeper_row.checked)
        self.assertEqual(old_keeper.kind, g.KIND_DUPLICATE)
        self.assertEqual(old_keeper.status, "status_pending")
        self.assertTrue(old_keeper.checked)
        self.assertFalse(other_row.checked, "其它副本的合法 checked 状态必须保留")
        for _index, row in group_rows:
            self.assertEqual(row.keeper.path, new_keeper_row.entry.path)

        calls = []

        def fake_recycle(target, keeper, *, byte_verify, should_cancel=None):
            calls.append((target.path, keeper.path, byte_verify))
            return RecycleOutcome(target=target, status="recycled")

        with mock.patch.object(g, "recycle_duplicate", fake_recycle), \
                mock.patch.object(g.QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window.btn_recycle.click()
            self.assertTrue(
                _pump(self.app, lambda: self.window._recycle_thread is None and not self.window._is_busy()),
                "真实回收 worker 未结束",
            )
        self.assertTrue(calls)
        self.assertEqual({target for target, _keeper, _verify in calls}, {old_keeper.entry.path})
        self.assertTrue(all(keeper == new_keeper_row.entry.path for _target, keeper, _verify in calls))
        self.assertTrue(all(verify for _target, _keeper, verify in calls))

    def test_keeper_change_record_round_trip_preserves_roles_and_states(self):
        self._typed_scan()
        result = self.window._current_result
        group_id = next(
            group_id
            for group_id in range(1, len(result.groups) + 1)
            if self._category_for_group(group_id) == "photo"
        )
        rows = self._group_rows(group_id)
        old_keeper = next(row for _index, row in rows if row.kind == g.KIND_KEEPER)
        candidate_index, candidate = next(
            (index, row) for index, row in rows if row.kind == g.KIND_DUPLICATE
        )
        self.window.table.selectRow(candidate_index)
        self.window.btn_set_keeper.click()
        target = self.tmp / "keeper-roundtrip.json"
        with mock.patch.object(g.QFileDialog, "getSaveFileName", return_value=(str(target), "")):
            self.window.btn_export_record.click()
            self.assertTrue(_pump(self.app, lambda: self.window._record_thread is None))
        self.assertTrue(target.exists())
        saved = load_record(target, expected_mode="internal")
        self.assertEqual(saved.result.groups[group_id - 1].keeper.path, candidate.entry.path)

        self.window._reset_results()
        self.assertTrue(self._import(target))
        imported = self.window._current_result.groups[group_id - 1]
        self.assertEqual(imported.keeper.path, candidate.entry.path)
        imported_rows = self._group_rows(group_id)
        self.assertEqual(
            {row.entry.path for _index, row in imported_rows if row.kind == g.KIND_DUPLICATE},
            {entry.path for entry in imported.duplicates},
        )
        self.assertTrue(self.window._record_imported)
        self.window.byte_verify_check.setChecked(False)
        # 仅让当前照片组参与后续真实回收按钮链路；隐藏分类 checked 明确取消。
        for row in self.window.table_model.rows:
            if row.group_id != group_id and row.kind == g.KIND_DUPLICATE:
                row.checked = False
        self.window.category_buttons["photo"].click()
        self.window.btn_select_all.click()

        calls = []

        def fake_recycle(target, keeper, *, byte_verify, should_cancel=None):
            calls.append({"target": target.path, "keeper": keeper.path,
                          "byte_verify": byte_verify})
            return RecycleOutcome(target=target, status="recycled")

        with mock.patch.object(g, "recycle_duplicate", fake_recycle), mock.patch.object(
            g.QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ):
            self.window.btn_recycle.click()
            self.assertTrue(
                _pump(
                    self.app,
                    lambda: self.window._recycle_thread is None and not self.window._is_busy(),
                ),
                "导入记录后的回收 worker 未结束",
            )
        self.assertEqual(
            {call["target"] for call in calls},
            {entry.path for entry in imported.duplicates},
        )
        self.assertTrue(all(call["keeper"] == candidate.entry.path for call in calls))
        self.assertTrue(all(call["byte_verify"] for call in calls))

    def test_visible_batch_buttons_only_change_active_category(self):
        self._typed_scan()
        result = self.window._current_result
        category_group = {
            self._category_for_group(group_id): group_id
            for group_id in range(1, len(result.groups) + 1)
        }
        self.assertEqual(set(category_group), {"photo", "video", "other"})
        self.window.category_buttons["photo"].click()
        before = [row.checked for row in self.window.table_model.rows]
        self.window.category_buttons["video"].click()
        visible_before = [
            row.checked
            for index, row in enumerate(self.window.table_model.rows)
            if not self.window.table.isRowHidden(index) and row.is_checkable()
        ]
        self.window.btn_invert.click()
        self.app.processEvents()
        visible_after = [
            row.checked
            for index, row in enumerate(self.window.table_model.rows)
            if not self.window.table.isRowHidden(index) and row.is_checkable()
        ]
        self.assertEqual(visible_after, [not checked for checked in visible_before])
        for index, row in enumerate(self.window.table_model.rows):
            if self.window.table.isRowHidden(index):
                self.assertEqual(row.checked, before[index], (index, row.primary_path()))

    def test_embedded_mode_and_english_refresh_all_new_controls(self):
        from unified_gui import EmbeddedPage

        embedded = g.MainWindow(embedded=True)
        host = EmbeddedPage("dedupeTest", embedded)
        host.resize(1360, 880)
        try:
            self.assertEqual(set(embedded.category_buttons), {"photo", "video", "other"})
            host.show()
            self.app.processEvents()
            self.assertFalse(
                embedded.language_combo.isVisible(), "内嵌页不应显示独立语言选择器"
            )
            self.assertTrue(all(button.isVisible() for button in embedded.category_buttons.values()))
            self.assertTrue(embedded.btn_set_keeper.isVisible())
            self.assertFalse(embedded.btn_set_keeper.isEnabled(), "未选中合法副本前设为保留应禁用")

            embedded.lang = "en"
            embedded._apply_language()
            for category, button in embedded.category_buttons.items():
                expected = {"photo": "Photos", "video": "Videos", "other": "Other"}[category]
                self.assertIn(expected, button.text())
                self.assertIn("groups", button.text())
                self.assertIn("files", button.text())
            self.assertEqual(embedded.btn_set_keeper.text(), "Set as keeper")
            self.assertEqual(embedded.btn_select_all.text(), "Select all")
            self.assertEqual(embedded.btn_select_none.text(), "Select none")
            self.assertEqual(embedded.btn_invert.text(), "Invert")
            self.assertEqual(embedded.btn_export_record.text(), "Export record")
            self.assertEqual(embedded.btn_import_record.text(), "Import record")

            embedded.lang = "zh"
            embedded._apply_language()
            expected_zh = {"photo": "照片", "video": "视频", "other": "其他"}
            for category, button in embedded.category_buttons.items():
                self.assertIn(expected_zh[category], button.text())
            self.assertEqual(embedded.btn_set_keeper.text(), "设为保留")
            self.assertEqual(embedded.btn_select_all.text(), "全选")
            self.assertEqual(embedded.btn_select_none.text(), "全不选")
            self.assertEqual(embedded.btn_invert.text(), "反选")
            self.assertEqual(embedded.btn_export_record.text(), "导出记录")
            self.assertEqual(embedded.btn_import_record.text(), "导入记录")
        finally:
            # host 拥有 embedded，只显式停 loader 后销毁 host，不双重删除窗口。
            embedded._shutdown_workers()
            embedded._release_thumbnail_loader()
            loaders = (embedded.thumbnail_loader, embedded.preview_panel.loader())
            workers = [worker for loader in loaders for worker in list(loader._workers)]
            host.close()
            host.deleteLater()
            self.assertTrue(
                _pump(self.app, lambda: not any(worker.is_alive() for worker in workers), timeout=5.0),
                "内嵌关闭后遗留缩略图线程",
            )
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()

    def test_core_media_and_keeper_contracts_are_pure_and_stable(self):
        root = self._make_typed_duplicates()
        photo = root / "photo" / "a" / "photo.jpg"
        video = root / "video" / "a" / "video.mp4"
        other = root / "other" / "a" / "data.bin"
        self.assertEqual(classify_media_type(photo), "photo")
        self.assertEqual(classify_media_type(video), "video")
        self.assertEqual(classify_media_type(other), "other")
        self.assertEqual(classify_media_type(Path("MIXED.MP4")), "video")
        self.assertEqual(classify_media_type(Path("no-extension")), "other")

        self._run_scan(root)
        result = self.window._current_result
        photo_group = next(
            group for group in result.groups if classify_duplicate_group(group) == "photo"
        )
        original_keeper_path = photo_group.keeper.path
        candidate = photo_group.duplicates[0]
        changed = reselect_internal_keeper(photo_group, candidate)
        self.assertEqual(changed.keeper.path, candidate.path)
        self.assertEqual(changed.sha256, photo_group.sha256)
        self.assertEqual(changed.size, photo_group.size)
        self.assertEqual(photo_group.keeper.path, original_keeper_path)
        self.assertNotEqual(changed.keeper.path, original_keeper_path)

    def test_legacy_v1_single_keeper_group_imports_via_real_button(self):
        """兼容 schema v1 的单成员组：duplicates=[] 仍能真实导入和展示。"""
        root = self.tmp / "legacy-single"
        root.mkdir()
        photo_path = root / "only.jpg"
        photo_path.write_bytes(b"single-member-photo")
        stat = photo_path.stat()
        entry = FileEntry(
            path=photo_path,
            root=root,
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            file_id=(int(stat.st_dev), int(stat.st_ino)),
        )
        record = ScanRecord(
            mode="internal",
            root_a=root,
            root_b=None,
            scope="all",
            keep_strategy="shallowest",
            result=ScanResult(
                groups=[DuplicateGroup(keeper=entry, duplicates=[], sha256="a" * 64,
                                       size=entry.size)],
                scanned_files=1,
                hashed_files=1,
                hashed_bytes=entry.size,
            ),
            row_states={
                os.path.normcase(os.path.abspath(str(photo_path))): {
                    "checked": False,
                    "status": "status_keep",
                }
            },
            created_at="2026-11-20T00:00:00",
        )
        record_path = self.tmp / "legacy-v1-single-keeper.json"
        save_record(record_path, record)

        self.assertTrue(self._import(record_path), "旧 v1 单 keeper 记录应由真实导入按钮载入")
        loaded_group = self.window._current_result.groups[0]
        self.assertEqual(loaded_group.keeper.path, photo_path)
        self.assertEqual(loaded_group.duplicates, [])
        self.assertEqual(len(self.window.table_model.rows), 1)
        keeper_row = self.window.table_model.rows[0]
        self.assertEqual(keeper_row.kind, g.KIND_KEEPER)
        self.assertFalse(keeper_row.checked)
        self.assertEqual(classify_duplicate_group(loaded_group), "photo")
        self.assertTrue(self.window._record_imported)


class RecycleWorkerVerifyTests(unittest.TestCase):
    """回收 worker 必须把 byte_verify 传给核心复核（不真实回收）。"""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_worker_passes_byte_verify_flag(self):
        tmp = Path(tempfile.mkdtemp(prefix="worker-verify-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        target = tmp / "dup.jpg"
        keeper = tmp / "keep.jpg"
        target.write_bytes(b"same")
        keeper.write_bytes(b"same")
        entry_target = FileEntry(target, tmp, 4, target.stat().st_mtime_ns, (0, 0))
        entry_keeper = FileEntry(keeper, tmp, 4, keeper.stat().st_mtime_ns, (0, 0))

        calls: list[dict] = []

        def fake_recycle(item, keeper_entry, *, byte_verify, should_cancel=None):
            calls.append({"byte_verify": byte_verify})
            return RecycleOutcome(target=item, status="recycled")

        with mock.patch.object(g, "recycle_duplicate", fake_recycle):
            worker = g.DedupeRecycleWorker([(0, entry_target, entry_keeper)], True)
            results: list[dict] = []
            worker.finished.connect(results.append)
            worker.run()
        self.assertEqual(calls, [{"byte_verify": True}])
        self.assertEqual(results[0]["success"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
