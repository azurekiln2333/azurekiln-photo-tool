"""用真实 viewport 滚轮事件验证大缩略图表格的像素步长。"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QStandardItemModel, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QTableView, QWidget

from dedupe_table_scroll import _PixelWheelFilter, configure_result_table_scrolling


class ResultTableScrollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(cls.enterClassContext(tempfile.TemporaryDirectory(prefix="dedupe-wheel-")))
        cls.enterClassContext(patch.dict(os.environ, {
            "QT_QPA_PLATFORM": "offscreen",
            "APPDATA": str(root / "appdata"),
            "LOCALAPPDATA": str(root / "localappdata"),
        }))
        from qfluentwidgets import TableView

        cls.table_type = TableView
        cls.app = QApplication.instance() or QApplication([])
        cls.addClassCleanup(QApplication.setWheelScrollLines, QApplication.wheelScrollLines())
        QApplication.setWheelScrollLines(3)

    def setUp(self):
        errors = []
        self.addCleanup(self.assertEqual, errors, [])
        self.enterContext(patch.object(sys, "excepthook", lambda kind, value, tb: errors.append(
            f"{kind.__name__}: {value}"
        )))

    def _dispose(self, widget: QWidget) -> None:
        widget.close()
        widget.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def _make_table(self) -> QTableView:
        table = self.table_type()
        self.addCleanup(self._dispose, table)
        table.setModel(QStandardItemModel(80, 2, table))
        table.verticalHeader().setDefaultSectionSize(104)
        configure_result_table_scrolling(table)
        table.resize(460, 350)
        table.show()
        self.app.processEvents()
        self.assertGreater(table.verticalScrollBar().maximum(), 560)
        table.verticalScrollBar().setValue(500)
        return table

    def _send_wheel(self, table: QTableView, *, angle: int = 0, pixels: int = 0) -> None:
        viewport = table.viewport()
        point = viewport.rect().center()
        event = QWheelEvent(
            QPointF(point), QPointF(viewport.mapToGlobal(point)),
            QPoint(0, pixels), QPoint(0, angle), Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate if pixels else Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        event.ignore()
        self.app.sendEvent(viewport, event)
        self.assertTrue(event.isAccepted())

    def _wait_for_scroll(self, *timers) -> None:
        deadline = time.monotonic() + 4.0
        while any(timer.isActive() for timer in timers) and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertFalse(any(timer.isActive() for timer in timers), "平滑滚轮动画未在限时内结束")

    def test_standard_notch_scrolls_40_to_60_pixels_in_both_fluent_engines(self):
        table = self._make_table()
        smooth = table.scrollDelagate.verticalSmoothScroll
        smooth.widthThreshold = 0  # 让普通 DPI 的离屏测试也可覆盖自适应引擎。
        bar = table.verticalScrollBar()
        for adaptive, engine, angle in (
            (False, smooth.fixedStepScrollEngine, -120),
            (True, smooth.adaptiveScrollEngine, 120),
        ):
            with self.subTest(adaptive=adaptive):
                smooth.setDynamicEngineEnabled(adaptive)
                before = bar.value()
                self._send_wheel(table, angle=angle)
                self.assertTrue(engine.smoothMoveTimer.isActive(), "没有走真实的 Fluent 平滑引擎")
                self._wait_for_scroll(engine.smoothMoveTimer)
                distance = (bar.value() - before) * (1 if angle < 0 else -1)
                self.assertTrue(40 <= distance <= 60, f"一格滚了 {distance}px")

    def test_touchpad_pixels_scroll_once_even_when_the_event_has_angle_delta(self):
        table = self._make_table()
        configure_result_table_scrolling(table)
        self.assertEqual(len(table.viewport().findChildren(_PixelWheelFilter)), 1)
        smooth = table.scrollDelagate.verticalSmoothScroll
        timers = (smooth.fixedStepScrollEngine.smoothMoveTimer,
                  smooth.adaptiveScrollEngine.smoothMoveTimer)
        bar = table.verticalScrollBar()
        for pixels, angle in ((-8, 0), (-7, -120), (4, 120)):
            with self.subTest(pixels=pixels, angle=angle):
                before = bar.value()
                self._send_wheel(table, pixels=pixels, angle=angle)
                self.assertEqual(bar.value() - before, -pixels)
                self._wait_for_scroll(*timers)
                self.assertEqual(bar.value() - before, -pixels, "角度增量不应再触发一次滚动")

    def test_directory_compare_configures_its_result_table(self):
        from dir_compare_gui import MainWindow

        window = MainWindow()
        self.addCleanup(self._dispose, window)
        table = window.table
        table.setModel(QStandardItemModel(80, 2, table))
        window.show()
        self.app.processEvents()
        bar = table.verticalScrollBar()
        self.assertGreater(bar.maximum(), 560)
        bar.setValue(500)
        self._send_wheel(table, angle=-120)
        smooth = table.scrollDelagate.verticalSmoothScroll
        self._wait_for_scroll(smooth.fixedStepScrollEngine.smoothMoveTimer,
                              smooth.adaptiveScrollEngine.smoothMoveTimer)
        distance = bar.value() - 500
        self.assertTrue(40 <= distance <= 60, f"比对页一格滚了 {distance}px")


if __name__ == "__main__":
    unittest.main()
