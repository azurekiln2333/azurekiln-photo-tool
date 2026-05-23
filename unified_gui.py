from __future__ import annotations

import importlib
import sys

from qframelesswindow import FramelessMainWindow

from PyQt6.QtCore import QParallelAnimationGroup, QPoint, QEasingCurve, QPropertyAnimation, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget

from main_gui import MainWindow as FlymeFixWindow
from merge_live_photo_gui import MainWindow as MergeLivePhotoWindow
from split_huawei_live_photo_gui import MainWindow as SplitHuaweiWindow


APP_TITLE = "AzureKiln Photo Tool"


def _import_fluent():
    module_candidates = (
        ("qfluentwidgetspro", True),
        ("qfluentwidgets_pro", True),
        ("qfluentwidgets", False),
    )

    module = None
    is_pro = False
    last_exc = None
    for mod_name, pro_flag in module_candidates:
        try:
            module = importlib.import_module(mod_name)
            is_pro = pro_flag
            break
        except Exception as exc:
            last_exc = exc

    if module is None:
        raise ImportError(
            "未安装 qfluentwidgets。请安装 PyQt6-Fluent-Widgets；如果要使用 Pro，请按官方文档安装 Pro 包。"
        ) from last_exc

    return {
        "FluentIcon": module.FluentIcon,
        "FluentWindow": module.FluentWindow,
        "NavigationItemPosition": module.NavigationItemPosition,
        "Theme": module.Theme,
        "setTheme": module.setTheme,
        "setThemeColor": module.setThemeColor,
        "is_pro": is_pro,
    }


FW = _import_fluent()
FluentIcon = FW["FluentIcon"]
FluentWindow = FW["FluentWindow"]
NavigationItemPosition = FW["NavigationItemPosition"]
Theme = FW["Theme"]
setTheme = FW["setTheme"]
setThemeColor = FW["setThemeColor"]
IS_PRO = FW["is_pro"]


def _pick_icon(*names: str):
    for name in names:
        icon = getattr(FluentIcon, name, None)
        if icon is not None:
            return icon
    return FluentIcon.APPLICATION


class EmbeddedPage(QWidget):
    """Display only the content widget from an existing feature window."""

    def __init__(self, object_name: str, feature_window: FramelessMainWindow, parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.feature_window = feature_window

        content = feature_window.takeCentralWidget()
        if content is None:
            raise RuntimeError(f"{type(feature_window).__name__} has no central widget")

        feature_window.hide()
        feature_window.setParent(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(content)


class UnifiedMainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1440, 900)
        self.setMinimumSize(980, 680)
        self._fade_label: QLabel | None = None
        self._transition_group: QParallelAnimationGroup | None = None
        self._incoming_effect: QGraphicsOpacityEffect | None = None
        self._incoming_page: QWidget | None = None
        self._incoming_origin = QPoint()

        self._feature_windows = [
            MergeLivePhotoWindow(self, embedded=True),
            SplitHuaweiWindow(self, embedded=True),
            FlymeFixWindow(self, embedded=True),
        ]
        self.pages = [
            EmbeddedPage("merge", self._feature_windows[0], self),
            EmbeddedPage("split", self._feature_windows[1], self),
            EmbeddedPage("flyme", self._feature_windows[2], self),
        ]

        self.merge_item = self.addSubInterface(
            self.pages[0],
            _pick_icon("ADD_TO", "SAVE_COPY", "LINK"),
            "LivePhoto 合并",
            NavigationItemPosition.TOP,
        )
        self.split_item = self.addSubInterface(
            self.pages[1],
            _pick_icon("CUT", "IMAGE_EXPORT", "FOLDER"),
            "华为 LivePhoto 分离",
            NavigationItemPosition.TOP,
        )
        self.flyme_item = self.addSubInterface(
            self.pages[2],
            _pick_icon("DEVELOPER_TOOLS", "SYNC", "UPDATE"),
            "Flyme LivePhoto 修复",
            NavigationItemPosition.TOP,
        )
        self._tune_animations()

    def switchTo(self, interface: QWidget):
        if interface is self.stackedWidget.currentWidget():
            return

        self._clear_transition()

        old_page_pixmap = self.stackedWidget.grab()
        self.stackedWidget.setCurrentWidget(interface, popOut=False)

        if old_page_pixmap.isNull():
            return

        offset = 22
        duration = 220
        curve = QEasingCurve.Type.OutCubic
        self._incoming_page = interface
        self._incoming_origin = interface.pos()

        self._fade_label = QLabel(self.stackedWidget)
        self._fade_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._fade_label.setGeometry(self.stackedWidget.rect())
        self._fade_label.setPixmap(old_page_pixmap)
        self._fade_label.setScaledContents(True)
        self._fade_label.show()
        self._fade_label.raise_()

        effect = QGraphicsOpacityEffect(self._fade_label)
        effect.setOpacity(1.0)
        self._fade_label.setGraphicsEffect(effect)

        self._incoming_effect = QGraphicsOpacityEffect(interface)
        self._incoming_effect.setOpacity(0.0)
        interface.setGraphicsEffect(self._incoming_effect)
        interface.move(self._incoming_origin + QPoint(offset, 0))

        old_fade = QPropertyAnimation(effect, b"opacity", self)
        old_fade.setDuration(duration)
        old_fade.setStartValue(1.0)
        old_fade.setEndValue(0.0)
        old_fade.setEasingCurve(curve)

        old_slide = QPropertyAnimation(self._fade_label, b"pos", self)
        old_slide.setDuration(duration)
        old_slide.setStartValue(self._fade_label.pos())
        old_slide.setEndValue(self._fade_label.pos() + QPoint(-10, 0))
        old_slide.setEasingCurve(curve)

        new_fade = QPropertyAnimation(self._incoming_effect, b"opacity", self)
        new_fade.setDuration(duration)
        new_fade.setStartValue(0.0)
        new_fade.setEndValue(1.0)
        new_fade.setEasingCurve(curve)

        new_slide = QPropertyAnimation(interface, b"pos", self)
        new_slide.setDuration(duration)
        new_slide.setStartValue(self._incoming_origin + QPoint(offset, 0))
        new_slide.setEndValue(self._incoming_origin)
        new_slide.setEasingCurve(curve)

        self._transition_group = QParallelAnimationGroup(self)
        for animation in (old_fade, old_slide, new_fade, new_slide):
            self._transition_group.addAnimation(animation)
        self._transition_group.finished.connect(self._clear_transition)
        self._transition_group.start()

    def _tune_animations(self):
        self.navigationInterface.panel.setIndicatorAnimationEnabled(False)
        self.stackedWidget.setAnimationEnabled(False)

    def _clear_transition(self):
        if self._transition_group is not None:
            self._transition_group.stop()
            self._transition_group.deleteLater()
            self._transition_group = None

        if self._fade_label is not None:
            self._fade_label.deleteLater()
            self._fade_label = None

        if self._incoming_page is not None:
            self._incoming_page.move(self._incoming_origin)
            self._incoming_page.setGraphicsEffect(None)
            self._incoming_page = None
            self._incoming_effect = None


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 10))
    setThemeColor("#1677FF")
    setTheme(Theme.LIGHT)

    win = UnifiedMainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
