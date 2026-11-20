"""独立验证长路径下的等宽预览与分隔条；只使用隔离配置。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = next(parent for parent in Path(__file__).resolve().parents
            if (parent / 'duplicate_scan_core.py').is_file())
sys.path.insert(0, str(REPO))
ISOLATED = tempfile.TemporaryDirectory(prefix="compare-layout-")
os.environ["APPDATA"] = ISOLATED.name
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import dir_compare_gui
import folder_dedupe_gui
from unified_gui import UnifiedMainWindow


def main() -> None:
    app = QApplication([])
    # Windows offscreen 插件未必发现系统字体；仅给截图探针显式加载。
    if "--capture" in sys.argv:
        for name in ("msyh.ttc", "segoeui.ttf"):
            font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if font_path.is_file():
                QFontDatabase.addApplicationFont(str(font_path))
        app.setFont(QFont("Microsoft YaHei", 9))
    errors = []
    def report_error(kind, value, tb):
        errors.append(f"{kind.__name__}: {value}")
        sys.__excepthook__(kind, value, tb)
    sys.excepthook = report_error
    measurements = []
    windows = []
    embedded = '--embedded' in sys.argv
    language = 'en' if '--en' in sys.argv else 'zh'
    capture_dir = Path(tempfile.mkdtemp(prefix="compare-layout-images-")) if "--capture" in sys.argv else None
    try:
        for module in (dir_compare_gui, folder_dedupe_gui):
            if embedded:
                window = UnifiedMainWindow()
                wrapper = (window.dir_compare_window if module is dir_compare_gui
                           else window.folder_dedupe_window)
                page = wrapper.window
                assert page is not None
                window.stackedWidget.setCurrentWidget(wrapper.page)
                window.apply_language(language, save=False)
            else:
                window = module.MainWindow()
                page = window
                page.lang = language
                page._apply_language()
            windows.append(window)
            window.resize(1360, 880)
            window.show()
            app.processEvents()
            panel = page.preview_panel
            # 不存在的临时路径，不读取任何相册；单个连续文件名刻意足够长。
            long_path = Path(ISOLATED.name) / ("long_filename_" * 25 + ".jpg")
            panel.set_slot(0, "B", long_path, 1024, 1700000000000000000)
            panel.set_slot(1, "A", Path(ISOLATED.name) / "a.jpg", 1024, 1700000000000000000)
            app.processEvents()
            page.splitter.setSizes([800, 450])
            app.processEvents()
            before = page.splitter.sizes()
            slots = [slot.width() for slot in panel._slot_widgets]
            assert abs(slots[0] - slots[1]) <= 1, slots
            assert panel.minimumSizeHint().width() < 600, panel.minimumSizeHint().width()
            handle = page.splitter.handle(1)
            point = handle.rect().center()
            QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=point)
            destination = point + QPoint(-100, 0)
            QTest.mouseMove(handle, destination, delay=25)
            QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=destination)
            app.processEvents()
            after = page.splitter.sizes()
            # 真实鼠标事件由 Qt 测试驱动；不声明覆盖 Windows 物理输入链。
            assert abs(before[0] - after[0]) > 10, (before, after)
            geometry = []
            for slot in panel._slot_widgets:
                path_label = slot.path_label
                needed = path_label.needed_height()
                assert path_label.height() >= needed, (
                    module.__name__, path_label.height(), needed)
                assert path_label.y() > slot.image_label.geometry().bottom(), (
                    module.__name__, '路径与图像重叠',
                    path_label.geometry().getRect(), slot.image_label.geometry().getRect())
                assert slot.meta_label.y() > path_label.geometry().bottom(), (
                    module.__name__, '路径与元信息重叠')
                geometry.append({'path_height': path_label.height(), 'needed': needed,
                                 'image': slot.image_label.geometry().getRect(),
                                 'path': path_label.geometry().getRect()})
            assert window.width() == 1360, ('页面撑宽窗口', module.__name__, window.width())
            for name in ('btn_select_all', 'btn_select_none', 'btn_export_record', 'btn_import_record'):
                button = getattr(page, name)
                assert button.text() == page.tr(name), (module.__name__, language, name, button.text())
                assert button.isVisible(), (module.__name__, name, '按钮不可见')
                assert button.parentWidget().rect().contains(button.geometry()), (
                    module.__name__, language, name, '按钮超出卡片')
            if capture_dir is not None:
                suffix = f"{'embedded' if embedded else 'standalone'}-{language}"
                assert window.grab().save(str(capture_dir / f"{module.__name__}-{suffix}.png"))
            measurements.append({"page": module.__name__, "embedded": embedded, "language": language, "slots": slots, "panel_minimum": panel.minimumSizeHint().width(), "splitter_before": before, "splitter_after": after, "geometry": geometry})
            window.close()
            app.processEvents()
    finally:
        for window in windows:
            features = window._optional_windows() if embedded else [window]
            for feature in features:
                feature._release_thumbnail_loader()
            window.close()
            window.deleteLater()
        # Qt 对象与线程先收尾，再结束隔离目录的生命期。
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    assert not errors, errors
    print(json.dumps(measurements, ensure_ascii=False, indent=2))
    if capture_dir is not None:
        print(f"captures: {capture_dir}")


if __name__ == "__main__":
    main()
