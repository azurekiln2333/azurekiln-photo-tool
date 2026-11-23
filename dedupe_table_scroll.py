"""两个大缩略图结果表共用的滚轮配置。"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QAbstractItemView, QApplication


class _PixelWheelFilter(QObject):
    """Fluent 按 angleDelta 分派；垂直 pixelDelta 应直接按像素应用。"""

    def __init__(self, table: QAbstractItemView):
        super().__init__(table.viewport())
        self._bar = table.verticalScrollBar()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(event, QWheelEvent) and (pixels := event.pixelDelta().y()):
            self._bar.setValue(self._bar.value() - pixels)
            event.accept()
            return True
        return False


def configure_result_table_scrolling(table: QAbstractItemView) -> None:
    """保留 Fluent 平滑滚动，让标准一格约 48px，不随缩略图行高变化。"""
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    lines = max(1, QApplication.styleHints().wheelScrollLines())
    table.verticalScrollBar().setSingleStep(max(1, round(48 / lines)))

    # Fluent 1.11.2 通过 Qt 滚动条派送动画帧。只设像素模式或滚动条步长，
    # 仍会被两套引擎的默认 stepRatio=1.5 与滚轮连发加速再放大。
    delegate = getattr(table, "scrollDelagate", None)
    smooth = getattr(delegate, "verticalSmoothScroll", None)
    for name in ("fixedStepScrollEngine", "adaptiveScrollEngine"):
        engine = getattr(smooth, name, None)
        if engine is not None:
            engine.stepRatio = 1.0
            engine.acceleration = 0

    # 最后安装，先于 Fluent 的过滤器处理像素事件；不重发 Wheel 事件。
    viewport = table.viewport()
    if viewport.findChild(_PixelWheelFilter) is None:
        viewport.installEventFilter(_PixelWheelFilter(table))
