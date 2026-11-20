"""统一窗口在真实记录线程运行时必须延后关闭（隔离目录和配置）。"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import dir_compare_gui
import folder_dedupe_gui
from scan_record_core import load_record
from unified_gui import UnifiedMainWindow


class UnifiedRecordCloseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _wait_for(self, predicate, seconds=12):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), "后台任务未在期限内完成清理")

    def _check_close_during_save(self, mode):
        module = dir_compare_gui if mode == "compare" else folder_dedupe_gui
        entered = threading.Event()
        release = threading.Event()
        errors = []
        with tempfile.TemporaryDirectory(prefix="unified-record-close-") as temporary:
            base = Path(temporary)
            root = base / "A"
            other = base / "B" if mode == "compare" else root / "sub"
            root.mkdir()
            other.mkdir(parents=True)
            (root / "keeper.jpg").write_bytes(b"isolated record close test" * 20)
            (other / "copy.jpg").write_bytes((root / "keeper.jpg").read_bytes())
            destination = base / "record.json"
            with patch.dict(os.environ, {"APPDATA": str(base / "settings"),
                                         "LOCALAPPDATA": str(base / "local")}), \
                 patch.object(sys, "excepthook", lambda kind, value, tb: errors.append(
                     f"{kind.__name__}: {value}")):
                window = UnifiedMainWindow()
                page = (window.dir_compare_window.window if mode == "compare"
                        else window.folder_dedupe_window.window)
                self.assertIsNotNone(page)
                # 所有提示在测试中收集，避免模态交互；仍使用真实按钮和 QThread。
                page._notify = lambda *args, **kwargs: None
                window.show()
                save_original = module.save_record

                def delayed_save(path, record):
                    entered.set()
                    if not release.wait(8):
                        raise OSError("test release timeout")
                    save_original(path, record)

                try:
                    if mode == "compare":
                        page.root_a_edit.setText(str(root))
                        page.root_b_edit.setText(str(other))
                    else:
                        page.root_edit.setText(str(root))
                    page.btn_scan.click()
                    self._wait_for(lambda: not page._is_busy() and page._scan_thread is None)
                    self.assertTrue(page._has_scan)
                    result = page._scan_result if mode == "compare" else page._current_result
                    self.assertEqual(len(result.groups), 1)
                    with patch.object(module, "save_record", side_effect=delayed_save), \
                         patch.object(module.QFileDialog, "getSaveFileName",
                                      return_value=(str(destination), "JSON")):
                        page.btn_export_record.click()
                        self._wait_for(entered.is_set)
                        self.assertTrue(page._is_busy())
                        self.assertFalse(window.close())
                        self.assertTrue(window.isVisible())
                        self.assertTrue(window._optional_close_timer.isActive())
                        QTimer.singleShot(80, release.set)
                        self._wait_for(lambda: page._record_thread is None
                                      and not window.isVisible())
                        self.assertFalse(window._optional_close_timer.isActive())
                    self.assertEqual(load_record(destination, expected_mode=mode).mode, mode)
                finally:
                    release.set()
                    # 即使断言失败也先结束线程；不能把析构期异常漏到 PASS 之后。
                    self._wait_for(lambda: not page._is_busy() and page._record_thread is None)
                    for feature in window._optional_windows():
                        feature._release_thumbnail_loader()
                    window.close()
                    window.deleteLater()
                    self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                    self.app.processEvents()
                self.assertEqual(errors, [])

    def test_compare_record_save_finishes_before_embedded_page_destruction(self):
        self._check_close_during_save("compare")

    def test_internal_record_save_finishes_before_embedded_page_destruction(self):
        self._check_close_during_save("internal")


if __name__ == "__main__":
    unittest.main()
