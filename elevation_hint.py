#!/usr/bin/env python3
"""管理员权限提示条（Windows UIPI 拖拽限制）。

程序以管理员（High 完整性）运行时，普通权限的资源管理器（Medium 完整性）无法
通过 UIPI 向本进程投递 OLE 拖拽数据，表现为「拖不进文件」。这里提供统一的：

- ``is_elevated()``：Windows 平台权限检测（非 Windows / 异常一律视为普通权限）。
- ``ElevationHintBar``：内嵌在页面标题下方的微软 Fluent 风格提示条，
  仅在后端检测到 elevated 时显示，非 elevated 时完全隐藏且不占位。

模块只依赖 PyQt6，不引入新的第三方依赖，也不耦合各页面的 qfluentwidgets 加载方式。
"""

from __future__ import annotations

import ctypes
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

# 提示文案（中英双语，跟随各页面语言切换刷新）
ELEVATION_HINT_TEXTS = {
    "zh": "检测到程序以管理员权限运行。Windows 会阻止从资源管理器拖入文件，如需拖拽请以普通权限重新启动。",
    "en": "Running as administrator. Windows blocks drag-and-drop from File Explorer; "
    "restart without elevation to enable drag-and-drop.",
}
DEFAULT_HINT_LANGUAGE = "zh"

# Fluent 提示条配色（浅色主题下的 warning 语义，保证可读性）
_HINT_STYLE = (
    "QWidget#elevationHintBar {"
    " background-color: #FFF4CE;"
    " border: 1px solid #F2E0A0;"
    " border-radius: 6px;"
    " }"
    "QLabel#elevationHintIcon { color: #8A6D00; font-size: 15px; }"
    "QLabel#elevationHintText { color: #6C4A00; }"
)


def is_elevated() -> bool:
    """返回当前进程是否以管理员（elevated）权限运行。

    非 Windows 平台或检测过程出现任何异常时返回 False，绝不向上抛出异常。
    """
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class ElevationHintBar(QWidget):
    """内嵌于页面标题下方的管理员权限提示条。

    这是页面内的普通控件（不是弹窗，也不是浮层 InfoBar）。仅当
    :func:`is_elevated` 为真时可见；否则隐藏，且在布局中不占位。
    """

    def __init__(self, parent: QWidget | None = None, lang: str = DEFAULT_HINT_LANGUAGE):
        super().__init__(parent)
        self.setObjectName("elevationHintBar")
        self.setStyleSheet(_HINT_STYLE)
        # 背景与边框由样式表绘制，保证与本页其它控件一致
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.icon_label = QLabel("⚠", self)
        self.icon_label.setObjectName("elevationHintIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.text_label = QLabel(self)
        self.text_label.setObjectName("elevationHintText")
        self.text_label.setWordWrap(True)

        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.text_label, 1)

        self.set_language(lang)
        # 非 elevated 时完全隐藏（隐藏控件在布局中不占空间）
        self.refresh_visibility()

    def set_language(self, lang: str):
        """刷新提示文案（中英双语）。"""
        text = ELEVATION_HINT_TEXTS.get(lang) or ELEVATION_HINT_TEXTS[DEFAULT_HINT_LANGUAGE]
        self.text_label.setText(text)

    def refresh_visibility(self, elevated: bool | None = None) -> bool:
        """根据权限状态同步可见性，返回当前是否显示。

        传入 ``elevated`` 可覆盖自动检测（便于测试/内嵌场景）。
        """
        if elevated is None:
            elevated = is_elevated()
        self.setVisible(bool(elevated))
        return bool(elevated)


def create_elevation_hint(parent: QWidget | None = None, lang: str = DEFAULT_HINT_LANGUAGE) -> ElevationHintBar:
    """构建管理员权限提示条（各页面统一的创建入口）。"""
    return ElevationHintBar(parent=parent, lang=lang)


def attach_elevation_hint(layout: QVBoxLayout, parent: QWidget | None = None,
                          lang: str = DEFAULT_HINT_LANGUAGE) -> ElevationHintBar:
    """在给定垂直布局末尾追加提示条，返回该控件供语言切换时刷新。"""
    hint = create_elevation_hint(parent=parent, lang=lang)
    layout.addWidget(hint)
    return hint
