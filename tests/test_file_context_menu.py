"""file_context_menu 局部回归：真实 ContextMenu 到 viewport 必须触发 show，
以及 TableView C++ 对象已删除时不得抛 RuntimeError。

运行：``.venv/Scripts/python.exe -m unittest tests.test_file_context_menu -v``
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("APPDATA", tempfile.mkdtemp(prefix="test-file-menu-appdata-"))

from PyQt6.QtCore import QCoreApplication, QEvent, QPoint
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtWidgets import QApplication, QTableView, QWidget

from file_context_menu import FileContextMenu


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


class FileContextMenuEventFilterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_context_menu_on_viewport_reaches_show(self):
        table = QTableView()
        self.addCleanup(table.deleteLater)
        helper = FileContextMenu(table, table, lambda row, selected: [])
        shown: list[QPoint] = []
        helper.show = lambda pos: shown.append(QPoint(pos))  # type: ignore[method-assign]

        viewport = table.viewport()
        event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(7, 9))
        handled = QCoreApplication.sendEvent(viewport, event)
        self.assertTrue(handled, "viewport 的 ContextMenu 必须被事件过滤器接收")
        self.assertEqual(len(shown), 1, "真实 ContextMenu 未进入 show")
        self.assertEqual((shown[0].x(), shown[0].y()), (7, 9))

    def test_non_context_menu_event_is_not_swallowed(self):
        table = QTableView()
        self.addCleanup(table.deleteLater)
        helper = FileContextMenu(table, table, lambda row, selected: [])
        shown: list[QPoint] = []
        helper.show = lambda pos: shown.append(QPoint(pos))  # type: ignore[method-assign]
        event = QEvent(QEvent.Type.User)
        QCoreApplication.sendEvent(table.viewport(), event)
        self.assertEqual(shown, [])

    def test_deleted_table_does_not_raise(self):
        table = QTableView()
        owner = QWidget()  # 独立保活：helper 的 QObject parent 是 owner，不随 table 删除
        self.addCleanup(owner.deleteLater)
        helper = FileContextMenu(table, owner, lambda row, selected: [])
        viewport = table.viewport()
        table.deleteLater()
        # 强制处理 DeferredDelete，使 TableView 的 C++ 对象真正销毁
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

        event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(1, 2))
        # 不能抛 RuntimeError；返回 False 表示未处理即可
        self.assertFalse(helper.eventFilter(viewport, event))


if __name__ == "__main__":
    unittest.main()
