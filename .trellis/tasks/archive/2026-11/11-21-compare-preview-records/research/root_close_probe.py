"""验证统一窗口延后关闭内嵌任务，配置/路径均使用临时目录。"""

import os
import sys
import tempfile
from pathlib import Path

REPO = next(parent for parent in Path(__file__).resolve().parents
            if (parent / 'duplicate_scan_core.py').is_file())
sys.path.insert(0, str(REPO))
isolated = tempfile.TemporaryDirectory(prefix="compare-close-")
os.environ["APPDATA"] = isolated.name
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication
from unified_gui import UnifiedMainWindow

app = QApplication([])
errors = []
def report_error(kind, value, tb):
    errors.append(f"{kind.__name__}: {value}")
    sys.__excepthook__(kind, value, tb)
sys.excepthook = report_error
window = UnifiedMainWindow()
window.show()
app.processEvents()
page = window.dir_compare_window.window
assert page is not None
busy = {"active": True, "stop_requests": 0}
original_busy = page._is_busy
original_shutdown = page._shutdown_workers
page._is_busy = lambda: busy["active"]
page._shutdown_workers = lambda: busy.update(stop_requests=busy["stop_requests"] + 1)

assert window.close() is False
assert window.isVisible()
assert busy["stop_requests"] > 0
assert window._optional_close_timer.isActive()
busy["active"] = False
loop = QEventLoop()
QTimer.singleShot(300, loop.quit)
loop.exec()
assert not window.isVisible()
assert not window._optional_close_timer.isActive()
page._is_busy = original_busy
page._shutdown_workers = original_shutdown
assert not errors, errors
for feature in window._optional_windows():
    feature._release_thumbnail_loader()
app.processEvents()
print("PASS: busy close deferred, shutdown requested, idle close completed; no Qt slot errors")
