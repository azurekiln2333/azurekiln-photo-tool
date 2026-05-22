from __future__ import annotations

import sys

from qframelesswindow import FramelessMainWindow, StandardTitleBar

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import FluentIcon, Theme, ToolButton, setTheme, setThemeColor

from main_gui import MainWindow as FlymeFixPage
from merge_live_photo_gui import MainWindow as MergeLivePhotoPage
from split_huawei_live_photo_gui import MainWindow as SplitHuaweiPage


APP_TITLE = "AzureKiln Photo Tool"
SIDEBAR_EXPANDED_WIDTH = 232
SIDEBAR_COLLAPSED_WIDTH = 64


def _pick_icon(*names: str):
    for name in names:
        icon = getattr(FluentIcon, name, None)
        if icon is not None:
            return icon
    return FluentIcon.APPLICATION


class NavigationButton(QPushButton):
    def __init__(self, icon, text: str, parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setIcon(icon)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_collapsed(self, collapsed: bool):
        self.setText("" if collapsed else self._full_text)
        self.setToolTip(self._full_text if collapsed else "")


class UnifiedMainWindow(FramelessMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1440, 900)
        self._title_bar_height = 36
        self._sidebar_collapsed = False
        self._set_blue_title_bar()

        root = QWidget(self)
        root.setObjectName("root")
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, self._title_bar_height, 0, 0)
        layout.setSpacing(0)

        self.sidebar = QFrame(self)
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(SIDEBAR_EXPANDED_WIDTH)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 12)
        sidebar_layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        self.menu_button = ToolButton(_pick_icon("MENU", "HAMBURGER", "MORE"), self)
        self.menu_button.setFixedSize(42, 38)
        self.menu_button.setToolTip("展开/收起菜单")
        self.menu_button.clicked.connect(self.toggle_sidebar)
        self.brand_label = QLabel(APP_TITLE, self)
        brand_font = QFont("Microsoft YaHei", 11)
        brand_font.setBold(True)
        self.brand_label.setFont(brand_font)
        self.brand_label.setObjectName("brandLabel")
        top_row.addWidget(self.menu_button)
        top_row.addWidget(self.brand_label, 1)
        sidebar_layout.addLayout(top_row)

        self.nav_buttons: list[NavigationButton] = []
        self.btn_merge = self._add_nav_button(
            sidebar_layout,
            _pick_icon("PHOTO", "ALBUM", "IMAGE_EXPORT"),
            "LivePhoto 合并",
            0,
        )
        self.btn_split = self._add_nav_button(
            sidebar_layout,
            _pick_icon("CUT", "SCISSORS", "FOLDER"),
            "华为 LivePhoto 分离",
            1,
        )
        self.btn_flyme = self._add_nav_button(
            sidebar_layout,
            _pick_icon("REPAIR", "SYNC", "UPDATE"),
            "Flyme LivePhoto 修复",
            2,
        )
        sidebar_layout.addStretch(1)

        self.stack = QStackedWidget(self)
        self.stack.setObjectName("contentStack")
        self.merge_page = MergeLivePhotoPage(self.stack, embedded=True)
        self.split_page = SplitHuaweiPage(self.stack, embedded=True)
        self.flyme_page = FlymeFixPage(self.stack, embedded=True)

        for page in (self.merge_page, self.split_page, self.flyme_page):
            page.setWindowFlag(Qt.WindowType.Widget, True)
            self.stack.addWidget(page)

        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)

        self._apply_style()
        self._select_page(0)
        self._sync_title_bar()

    def _add_nav_button(self, layout: QVBoxLayout, icon, text: str, index: int) -> NavigationButton:
        button = NavigationButton(icon, text, self)
        button.clicked.connect(lambda _checked=False, page_index=index: self._select_page(page_index))
        self.nav_buttons.append(button)
        layout.addWidget(button)
        return button

    def _select_page(self, index: int):
        self.stack.setCurrentIndex(index)
        for idx, button in enumerate(self.nav_buttons):
            button.setChecked(idx == index)

    def toggle_sidebar(self):
        self._sidebar_collapsed = not self._sidebar_collapsed
        width = SIDEBAR_COLLAPSED_WIDTH if self._sidebar_collapsed else SIDEBAR_EXPANDED_WIDTH
        self.sidebar.setFixedWidth(width)
        self.brand_label.setVisible(not self._sidebar_collapsed)
        for button in self.nav_buttons:
            button.set_collapsed(self._sidebar_collapsed)

    def _set_blue_title_bar(self):
        self.setTitleBar(StandardTitleBar(self))
        self._title_bar_height = self.titleBar.height()
        self.titleBar.setObjectName("blueTitleBar")
        self.titleBar.setStyleSheet(
            """
            QWidget#blueTitleBar {
                background: #1677FF;
            }
            QWidget#blueTitleBar QLabel {
                color: #FFFFFF;
                background: transparent;
            }
            """
        )
        for btn in (self.titleBar.minBtn, self.titleBar.maxBtn):
            btn.setNormalColor("#1F2937")
            btn.setHoverColor("#1F2937")
            btn.setPressedColor("#1F2937")
            btn.setNormalBackgroundColor("#00000000")
            btn.setHoverBackgroundColor("#4DFFFFFF")
            btn.setPressedBackgroundColor("#80FFFFFF")

        self.titleBar.closeBtn.setNormalColor("#1F2937")
        self.titleBar.closeBtn.setHoverColor("#FFFFFF")
        self.titleBar.closeBtn.setPressedColor("#FFFFFF")
        self.titleBar.closeBtn.setNormalBackgroundColor("#00000000")
        self.titleBar.closeBtn.setHoverBackgroundColor("#E81123")
        self.titleBar.closeBtn.setPressedBackgroundColor("#F1707A")

    def _sync_title_bar(self):
        if not hasattr(self, "titleBar"):
            return
        self.titleBar.move(0, 0)
        self.titleBar.resize(self.width(), self._title_bar_height)
        self.titleBar.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_title_bar()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_title_bar()

    def _apply_style(self):
        self.setStyleSheet(
            """
            QWidget#root {
                background: #F5F7FB;
            }
            QFrame#sidebar {
                background: #FFFFFF;
                border-right: 1px solid #D9E2EC;
            }
            QLabel#brandLabel {
                color: #1F2937;
            }
            QPushButton {
                border: none;
                border-radius: 8px;
                padding: 0 12px;
                text-align: left;
                color: #344054;
                background: transparent;
            }
            QPushButton:hover {
                background: #EEF4FF;
            }
            QPushButton:checked {
                color: #0B5ED7;
                background: #DCEBFF;
                font-weight: 600;
            }
            QStackedWidget#contentStack {
                background: #F5F7FB;
            }
            """
        )


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
