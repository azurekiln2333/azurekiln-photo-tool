"""共享缩略图加载器与侧边预览面板。

本模块负责「目录比对」「目录内去重」两个页面的缩略图与预览显示，接口契约见
`.trellis/tasks/11-20-dir-compare-dedupe/design.md` 的「契约 2」。

设计要点：

- 后台线程只产出 ``QImage``，``QPixmap`` 只在 GUI 线程创建（Qt 硬性约束）。
- 加载顺序：Windows Shell 缩略图（ctypes 调 ``IShellItemImageFactory``，照片/视频/HEIC
  都依赖系统能力）→ 视频用 QtMultimedia（自带 FFmpeg 后端）解首帧 → ``QImageReader`` →
  类型占位图。任一步失败都会安静降级，绝不抛给 UI。
- LRU 缓存，key 为 ``(str(path), mtime_ns)``；失败按 key 做**有限退避重试**（不是永久负缓存），
  mtime 缓存有寿命上限，云端文件下载完成、mtime 变化后会自然重新加载。
- 只加载可见行：表格模型在 ``DecorationRole`` 里调用 ``request()``，未命中先返回占位图。

``QPixmap``/``QImage`` 需要 QGuiApplication，本模块只能在 GUI 进程中导入使用
（不依赖 qfluentwidgets，缺少时回退到裸 QLabel）。
"""

from __future__ import annotations

import ctypes
import math
import os
import queue
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import (
    QAbstractTextDocumentLayout,
    QColor,
    QFont,
    QImage,
    QImageReader,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:  # 与项目其他页面保持一致：优先 Fluent 控件，缺失时退化为 QLabel
    from qfluentwidgets import BodyLabel as _BodyLabel
    from qfluentwidgets import SubtitleLabel as _SubtitleLabel
except Exception:  # pragma: no cover - 正常环境一定有 qfluentwidgets
    _BodyLabel = QLabel  # type: ignore[assignment]
    _SubtitleLabel = QLabel  # type: ignore[assignment]


# 媒体扩展名集合。语义与 timestamp_fix_gui.IMAGE_SUFFIXES / VIDEO_SUFFIXES 一致，
# 但这里刻意不 import 那个模块：缩略图模块需要能独立导入（它只判断「用哪种占位图」）。
IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".heic", ".heif", ".png", ".tif", ".tiff", ".webp", ".bmp", ".gif"}
)
VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".mov", ".m4v", ".3gp", ".avi", ".wmv", ".mkv", ".mts", ".m2ts", ".webm", ".flv"}
)

KIND_IMAGE = "image"
KIND_VIDEO = "video"
KIND_OTHER = "other"

_PLACEHOLDER_CACHE: dict[tuple[int, str], QPixmap] = {}
_PLACEHOLDER_CACHE_LIMIT = 32


def _kind_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return KIND_IMAGE
    if suffix in VIDEO_EXTENSIONS:
        return KIND_VIDEO
    return KIND_OTHER


def _stat_mtime_ns(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns)
    except Exception:
        return 0


def _now() -> float:
    """单调时钟包装（测试可 patch，避免真实等待退避）。"""
    return time.monotonic()


def _build_placeholder(size: int, kind: str) -> QPixmap:
    """画一个跟类型相关的占位图：照片=山+太阳，视频=胶片框+播放键，其他=文档。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = max(3.0, size * 0.12)
        painter.setPen(QPen(QColor("#E4E7EC"), 1))
        painter.setBrush(QColor("#F2F4F7"))
        painter.drawRoundedRect(QRectF(0.5, 0.5, size - 1.0, size - 1.0), radius, radius)

        glyph_pen = QPen(QColor("#98A2B3"), max(1.0, size * 0.035))
        glyph_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        glyph_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(glyph_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        margin = size * 0.24
        box = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)

        if kind == KIND_VIDEO:
            painter.drawRoundedRect(box, size * 0.06, size * 0.06)
            triangle = QPainterPath()
            center = box.center()
            half = box.height() * 0.22
            triangle.moveTo(center.x() - half * 0.7, center.y() - half)
            triangle.lineTo(center.x() - half * 0.7, center.y() + half)
            triangle.lineTo(center.x() + half, center.y())
            triangle.closeSubpath()
            painter.setBrush(QColor("#98A2B3"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(triangle)
        elif kind == KIND_IMAGE:
            painter.drawRoundedRect(box, size * 0.05, size * 0.05)
            painter.setBrush(QColor("#98A2B3"))
            painter.setPen(Qt.PenStyle.NoPen)
            sun = box.width() * 0.11
            painter.drawEllipse(
                QRectF(box.left() + box.width() * 0.22 - sun, box.top() + box.height() * 0.24 - sun, sun * 2, sun * 2)
            )
            mountain = QPainterPath()
            mountain.moveTo(box.left(), box.bottom())
            mountain.lineTo(box.left() + box.width() * 0.38, box.top() + box.height() * 0.42)
            mountain.lineTo(box.left() + box.width() * 0.62, box.bottom())
            mountain.closeSubpath()
            mountain.moveTo(box.left() + box.width() * 0.45, box.bottom())
            mountain.lineTo(box.left() + box.width() * 0.72, box.top() + box.height() * 0.58)
            mountain.lineTo(box.right(), box.bottom())
            mountain.closeSubpath()
            painter.drawPath(mountain)
        else:
            painter.drawRoundedRect(box, size * 0.05, size * 0.05)
            line_height = box.height() * 0.16
            start_y = box.top() + box.height() * 0.28
            for index in range(3):
                width_ratio = 0.72 if index < 2 else 0.45
                painter.drawLine(
                    int(box.left() + box.width() * 0.14),
                    int(start_y + index * line_height * 1.35),
                    int(box.left() + box.width() * (0.14 + width_ratio)),
                    int(start_y + index * line_height * 1.35),
                )
    finally:
        painter.end()
    return pixmap


def placeholder_pixmap(size: int, kind: str) -> QPixmap:
    """按类型返回占位图（带进程内缓存；size 为像素边长）。"""
    size = max(8, int(size))
    if kind not in (KIND_IMAGE, KIND_VIDEO, KIND_OTHER):
        kind = KIND_OTHER
    key = (size, kind)
    cached = _PLACEHOLDER_CACHE.get(key)
    if cached is not None:
        return cached
    pixmap = _build_placeholder(size, kind)
    if len(_PLACEHOLDER_CACHE) >= _PLACEHOLDER_CACHE_LIMIT:
        _PLACEHOLDER_CACHE.clear()
    _PLACEHOLDER_CACHE[key] = pixmap
    return pixmap


# ---------------------------------------------------------------------------
# Windows Shell 缩略图（ctypes，COM）
# ---------------------------------------------------------------------------


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class _BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", ctypes.c_long),
        ("bmWidth", ctypes.c_long),
        ("bmHeight", ctypes.c_long),
        ("bmWidthBytes", ctypes.c_long),
        ("bmPlanes", ctypes.c_ushort),
        ("bmBitsPixel", ctypes.c_ushort),
        ("bmBits", ctypes.c_void_p),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_ushort),
        ("biBitCount", ctypes.c_ushort),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


_IID_SHELL_ITEM_IMAGE_FACTORY = _GUID(0xBCC18B79, 0xBA16, 0x442F, (ctypes.c_ubyte * 8)(0x80, 0xC4, 0x8A, 0x59, 0xC3, 0x0C, 0x46, 0x3B))
_SIIGBF_BIGGERSIZEOK = 0x01
_SIIGBF_THUMBNAILONLY = 0x08
_COINIT_APARTMENTTHREADED = 0x2


class _ShellThumbnails:
    """最小化封装的 ``IShellItemImageFactory`` 调用（只依赖 ctypes）。"""

    def __init__(self):
        self._shell32 = ctypes.windll.shell32
        self._ole32 = ctypes.windll.ole32
        self._gdi32 = ctypes.windll.gdi32
        self._user32 = ctypes.windll.user32

        self._shell32.SHCreateItemFromParsingName.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_void_p,
            ctypes.POINTER(_GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._shell32.SHCreateItemFromParsingName.restype = ctypes.c_long

        self._gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
        self._gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
        self._gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
        self._gdi32.DeleteDC.restype = ctypes.c_int
        self._gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
        self._gdi32.DeleteObject.restype = ctypes.c_int
        self._gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        self._gdi32.GetObjectW.restype = ctypes.c_int
        self._gdi32.GetDIBits.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint,
        ]
        self._gdi32.GetDIBits.restype = ctypes.c_int

        self._user32.GetDC.argtypes = [ctypes.c_void_p]
        self._user32.GetDC.restype = ctypes.c_void_p
        self._user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._user32.ReleaseDC.restype = ctypes.c_int

        self._ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self._ole32.CoInitializeEx.restype = ctypes.c_long
        self._ole32.CoUninitialize.argtypes = []
        self._ole32.CoUninitialize.restype = None

        self._com_ready = False

    def open(self):
        """每个工作线程调用一次（平衡 CoUninitialize）。"""
        if self._com_ready:
            return
        try:
            self._ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        except Exception:
            pass
        self._com_ready = True

    def close(self):
        if not self._com_ready:
            return
        self._com_ready = False
        try:
            self._ole32.CoUninitialize()
        except Exception:
            pass

    # -- 内部 ------------------------------------------------------------
    def _create_item(self, path: str) -> ctypes.c_void_p:
        item = ctypes.c_void_p()
        hr = self._shell32.SHCreateItemFromParsingName(
            path, None, ctypes.byref(_IID_SHELL_ITEM_IMAGE_FACTORY), ctypes.byref(item)
        )
        if hr < 0 or not item:
            return ctypes.c_void_p()
        return item

    @staticmethod
    def _vtable(ptr: ctypes.c_void_p) -> Any:
        return ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents

    def _release(self, ptr: ctypes.c_void_p):
        try:
            release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(self._vtable(ptr)[2])
            release(ptr)
        except Exception:
            pass

    def _get_image(self, ptr: ctypes.c_void_p, size: int, flags: int) -> ctypes.c_void_p:
        get_image = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, _SIZE, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)
        )(self._vtable(ptr)[3])
        hbitmap = ctypes.c_void_p()
        hr = get_image(ptr, _SIZE(int(size), int(size)), int(flags), ctypes.byref(hbitmap))
        if hr < 0 or not hbitmap:
            return ctypes.c_void_p()
        return hbitmap

    def _hbitmap_to_image(self, hbitmap: ctypes.c_void_p) -> QImage | None:
        gdi32 = self._gdi32
        user32 = self._user32
        try:
            info = _BITMAP()
            if not gdi32.GetObjectW(hbitmap, ctypes.sizeof(_BITMAP), ctypes.byref(info)):
                return None
            width = int(info.bmWidth)
            height = int(info.bmHeight)
            if width <= 0 or height <= 0:
                return None

            hdc = user32.GetDC(None)
            if not hdc:
                return None
            mem_dc = gdi32.CreateCompatibleDC(hdc)
            if not mem_dc:
                user32.ReleaseDC(None, hdc)
                return None
            try:
                header = _BITMAPINFOHEADER()
                header.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
                header.biWidth = width
                header.biHeight = -height  # 负值 = 自上而下
                header.biPlanes = 1
                header.biBitCount = 32
                header.biCompression = 0  # BI_RGB
                header.biSizeImage = width * height * 4

                buffer = ctypes.create_string_buffer(width * height * 4)
                copied = gdi32.GetDIBits(mem_dc, hbitmap, 0, height, buffer, ctypes.byref(header), 0)
                if not copied:
                    return None
                image = QImage(
                    bytes(buffer), width, height, width * 4, QImage.Format.Format_RGB32
                ).copy()
                return None if image.isNull() else image
            finally:
                gdi32.DeleteDC(mem_dc)
                user32.ReleaseDC(None, hdc)
        except Exception:
            return None
        finally:
            try:
                self._gdi32.DeleteObject(hbitmap)
            except Exception:
                pass

    def thumbnail(self, path: Path, size: int) -> QImage | None:
        """取系统缩略图；没有缩略图（只有图标）时返回 None，交给 QImageReader 回退。"""
        # SHCreateItemFromParsingName 只接受绝对路径（相对路径直接返回 E_INVALIDARG）
        try:
            absolute = Path(os.path.abspath(os.fspath(path)))
        except Exception:
            return None
        item = self._create_item(str(absolute))
        if not item:
            return None
        try:
            hbitmap = self._get_image(
                item, size, _SIIGBF_BIGGERSIZEOK | _SIIGBF_THUMBNAILONLY
            )
            if not hbitmap:
                return None
            image = self._hbitmap_to_image(hbitmap)
            if image is None:
                return None
            # 系统缓存里可能命中更大的缩略图（BIGGERSIZEOK），统一缩到目标尺寸
            if image.width() > size or image.height() > size:
                image = image.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            return None if image.isNull() else image
        except Exception:
            return None
        finally:
            self._release(item)


_THREAD_STATE = threading.local()


def _shell_api() -> "_ShellThumbnails | None":
    """返回当前线程的 Shell 调用器（每线程一次 COM 初始化）。"""
    if sys.platform != "win32":
        return None
    api = getattr(_THREAD_STATE, "api", None)
    if api is not None:
        return api
    try:
        api = _ShellThumbnails()
        api.open()
    except Exception:
        api = None
    _THREAD_STATE.api = api
    return api


def _release_shell_api():
    api = getattr(_THREAD_STATE, "api", None)
    if api is None:
        return
    try:
        api.close()
    except Exception:
        pass
    _THREAD_STATE.api = None


# ---------------------------------------------------------------------------
# 加载管线
# ---------------------------------------------------------------------------


def _load_with_qimage_reader(path: Path, size: int) -> QImage | None:
    """Qt 自带解码器（JPG/PNG/TIFF/WebP/GIF…），按比例缩放读取。"""
    try:
        # QImageReader 同样不应依赖当前工作目录
        target = Path(os.path.abspath(os.fspath(path)))
        reader = QImageReader(str(target))
        reader.setAutoTransform(True)
        source = reader.size()
        if source.isValid() and source.width() > 0 and source.height() > 0:
            scaled = source.scaled(QSize(size, size), Qt.AspectRatioMode.KeepAspectRatio)
            if scaled.width() > 0 and scaled.height() > 0 and scaled != source:
                reader.setScaledSize(scaled)
        image = reader.read()
        if image.isNull():
            return None
        if image.width() > size or image.height() > size:
            image = image.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return None if image.isNull() else image
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 视频首帧回退（QtMultimedia 自带 FFmpeg 后端，不依赖 Windows Shell 缓存）
# ---------------------------------------------------------------------------

# 首帧超时：OneDrive 占位文件需要先水化，给足余量但绝不无限等待
_VIDEO_FRAME_TIMEOUT_MS = 6000
_VIDEO_POLL_INTERVAL_MS = 100
# 多个工作线程同时驱动解码器会互相干扰，串行化（一次只解一个视频）
_VIDEO_LOCK = threading.Lock()

# 失败原因码 → 中英文提示（页面用 failure_message() 展示，不写死文案）
FAILURE_MESSAGES: dict[str, dict[str, str]] = {
    "zh": {
        "decode_failed": "无法解码此文件的预览",
        "video_unavailable": "缺少视频解码组件",
        "video_timeout": "视频首帧超时（文件可能尚未下载完成）",
        "cancelled": "已取消",
        "invalid_size": "预览尺寸无效",
    },
    "en": {
        "decode_failed": "Could not decode a preview for this file",
        "video_unavailable": "Video decoding component is unavailable",
        "video_timeout": "Timed out reading the first video frame (file may not be downloaded yet)",
        "cancelled": "Cancelled",
        "invalid_size": "Invalid preview size",
    },
}


def failure_message(code: str, lang: str = "zh") -> str:
    """把失败原因码翻译成界面文案（未知码原样返回）。"""
    table = FAILURE_MESSAGES.get(lang, FAILURE_MESSAGES["zh"])
    return table.get(code, code or "")


def _extract_video_frame_qtmultimedia(
    path: Path,
    size: int,
    *,
    timeout_ms: int = _VIDEO_FRAME_TIMEOUT_MS,
    stop_event: threading.Event | None = None,
) -> tuple[QImage | None, str]:
    """在**当前线程**用 QMediaPlayer 解视频首帧，返回 ``(图像, 原因码)``。

    只能在工作线程调用：函数自建 QEventLoop，不占用主线程事件循环。
    ``QImage`` 可跨线程传递，``QPixmap`` 必须回到 GUI 线程再创建。
    """
    try:
        from PyQt6.QtCore import QEventLoop, QTimer, QUrl
        from PyQt6.QtMultimedia import QMediaPlayer, QVideoSink
    except Exception:
        return None, "video_unavailable"

    deadline = max(200, int(timeout_ms))
    if not _VIDEO_LOCK.acquire(timeout=deadline / 1000.0):
        return None, "video_timeout"
    try:
        loop = QEventLoop()
        player = QMediaPlayer()
        sink = QVideoSink()
        state: dict[str, Any] = {"done": False, "image": None, "code": "video_timeout"}

        def finish(code: str, image: QImage | None = None) -> None:
            if state["done"]:
                return
            state["done"] = True
            state["code"] = code
            state["image"] = image
            loop.quit()

        def on_frame(frame) -> None:
            try:
                image = frame.toImage() if frame.isValid() else QImage()
            except Exception:
                image = QImage()
            if image is None or image.isNull():
                return
            finish("", image)

        sink.videoFrameChanged.connect(on_frame)
        player.errorOccurred.connect(lambda _error, _message: finish("decode_failed"))

        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(lambda: finish("video_timeout"))
        timeout.start(deadline)

        # 取消/关闭：小步轮询停止标志，避免关窗时卡在解帧里
        poll = QTimer()
        poll.setInterval(_VIDEO_POLL_INTERVAL_MS)

        def on_poll() -> None:
            if stop_event is not None and stop_event.is_set():
                finish("cancelled")

        poll.timeout.connect(on_poll)
        poll.start()

        try:
            player.setVideoSink(sink)
            player.setSource(QUrl.fromLocalFile(str(path)))
            player.play()
            loop.exec()
        finally:
            poll.stop()
            timeout.stop()
            try:
                player.stop()
                player.setVideoSink(None)
                player.setSource(QUrl())
            except Exception:
                pass

        image = state.get("image")
        code = str(state.get("code") or "")
        if not isinstance(image, QImage) or image.isNull():
            return None, code or "decode_failed"
        if image.width() > size or image.height() > size:
            image = image.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return (None, code) if image.isNull() else (image, "")
    finally:
        _VIDEO_LOCK.release()


def load_thumbnail_image_detail(
    path: Path, size: int, *, stop_event: threading.Event | None = None
) -> tuple[QImage | None, str]:
    """后台线程入口：Shell → 视频解码回退 → QImageReader → ``(None, 原因码)``。"""
    if size <= 0:
        return None, "invalid_size"
    resolved = Path(os.path.abspath(os.fspath(path)))
    api = _shell_api()
    if api is not None:
        image = api.thumbnail(resolved, size)
        if image is not None:
            return image, ""
    if stop_event is not None and stop_event.is_set():
        return None, "cancelled"
    video_code = ""
    if _kind_for_path(resolved) == KIND_VIDEO:
        # Windows Shell 取不到视频帧（云缓存未就绪/编码不受支持）时走独立解码
        image, video_code = _extract_video_frame_qtmultimedia(
            resolved, size, stop_event=stop_event
        )
        if image is not None:
            return image, ""
        if stop_event is not None and stop_event.is_set():
            return None, "cancelled"
    image = _load_with_qimage_reader(resolved, size)
    if image is not None:
        return image, ""
    return None, video_code or "decode_failed"


def load_thumbnail_image(path: Path, size: int) -> QImage | None:
    """兼容入口：只要图像，失败返回 ``None``（调用方用占位图）。"""
    image, _ = load_thumbnail_image_detail(path, size)
    return image


# ---------------------------------------------------------------------------
# ThumbnailLoader
# ---------------------------------------------------------------------------


class ThumbnailLoader(QObject):
    """异步缩略图加载器（仅在 GUI 线程调用 ``request``）。"""

    thumbnail_ready = pyqtSignal(str)  # 参数：文件路径字符串
    thumbnail_failed = pyqtSignal(str, str)  # 参数：文件路径字符串、失败原因码

    # 跨线程信号用队列入主线程，规避「非 Qt 线程直接触碰 UI」
    # 注意：mtime_ns 是 64 位，必须声明为 qlonglong，默认 int 会在队列传递时被截断。
    _loaded = pyqtSignal(int, str, "qlonglong", object, str)  # generation, path, mtime_ns, QImage|None, 原因码

    # 失败退避：依次等待后重试，用尽后保持占位（mtime 变化或 retry() 会重新开始）
    _FAILURE_BACKOFF_S: tuple[float, ...] = (1.0, 2.0, 5.0)
    # mtime 缓存寿命：兼顾 paint 时的 stat 开销与「云文件下载完成后 mtime 变化」的感知速度
    _MTIME_TTL_S = 2.0

    def __init__(self, size: int = 96, max_workers: int = 2, cache_limit: int = 3000, parent=None):
        super().__init__(parent)
        self._size = max(8, int(size))
        self._max_workers = max(1, int(max_workers))
        self._cache_limit = max(16, int(cache_limit))
        self._cache: OrderedDict[tuple[str, int], QPixmap] = OrderedDict()
        self._pending: set[tuple[str, int]] = set()
        # 有限失败记录：key -> {'retries': int, 'retry_at': float, 'reason': str}
        self._failures: dict[tuple[str, int], dict[str, Any]] = {}
        # paint 时会高频 request()，mtime 按 TTL 缓存，避免每帧 stat
        self._mtime_cache: dict[str, tuple[int, float]] = {}
        self._queue: queue.Queue[tuple[int, str, int] | None] = queue.Queue()
        self._workers: list[threading.Thread] = []
        self._generation = 0
        self._stopped = False
        self._start_lock = threading.Lock()
        # 每代一个取消信号：clear()/shutdown() 后正在解码的视频可以尽快退出
        self._cancel_event = threading.Event()
        self._loaded.connect(self._on_loaded, Qt.ConnectionType.QueuedConnection)

    # -- 公共接口 ---------------------------------------------------------
    def request(self, path: Path) -> QPixmap:
        """立即返回：缓存命中→缩略图；未命中/重试到头→占位图。"""
        path = Path(path)
        if self._stopped:
            return self._placeholder(path)

        key = (str(path), self._mtime_for(path))
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached

        placeholder = self._placeholder(path)
        if key in self._pending:
            return placeholder
        failure = self._failures.get(key)
        if failure is not None:
            if int(failure.get("retries", 0)) >= len(self._FAILURE_BACKOFF_S):
                return placeholder
            if _now() < float(failure.get("retry_at", 0.0)):
                return placeholder
        self._pending.add(key)
        self._ensure_workers()
        self._queue.put((self._generation, key[0], key[1]))
        return placeholder

    def retry(self, path: Path | None = None) -> None:
        """清掉失败记录并重新排队（用户点「重试」、文件下载完成或重新选中时调用）。"""
        if self._stopped:
            return
        if path is None:
            targets = [key[0] for key in self._failures]
            self._failures.clear()
            self._mtime_cache.clear()
        else:
            wanted = str(Path(path))
            targets = [key[0] for key in list(self._failures) if key[0] == wanted]
            for key in [key for key in self._failures if key[0] == wanted]:
                self._failures.pop(key, None)
            self._mtime_cache.pop(wanted, None)
            if not targets:
                targets = [wanted]
        for target in dict.fromkeys(targets):
            self.request(Path(target))

    def failure_reason(self, path: Path) -> str | None:
        """返回最近一次失败原因码（无失败记录返回 None）。"""
        wanted = str(Path(path))
        for (path_str, _mtime), info in reversed(list(self._failures.items())):
            if path_str == wanted:
                return str(info.get("reason") or "") or None
        return None

    def next_retry_delay(self, path: Path) -> float | None:
        """距离下次自动重试的秒数；已用尽重试次数返回 None（需要手动 retry）。"""
        wanted = str(Path(path))
        for (path_str, _mtime), info in reversed(list(self._failures.items())):
            if path_str != wanted:
                continue
            if int(info.get("retries", 0)) >= len(self._FAILURE_BACKOFF_S):
                return None
            return max(0.0, float(info.get("retry_at", 0.0)) - _now())
        return None

    def _mtime_for(self, path: Path) -> int:
        key = str(path)
        now = _now()
        entry = self._mtime_cache.get(key)
        if entry is not None and now - entry[1] < self._MTIME_TTL_S:
            return entry[0]
        value = _stat_mtime_ns(path)
        self._mtime_cache[key] = (value, now)
        return value

    def clear(self) -> None:
        """清缓存、取消排队任务（新扫描开始时调用）。

        已开始加载的任务无法真正中断，用 generation 让它们的结果被丢弃；
        正在解码的视频通过取消事件尽快退出，不阻塞页面切换。
        """
        self._cancel_event.set()
        self._generation += 1
        self._cancel_event = threading.Event()
        self._cache.clear()
        self._pending.clear()
        self._failures.clear()
        self._mtime_cache.clear()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def shutdown(self) -> None:
        """页面关闭时调用：停止线程池（daemon 线程，不阻塞界面退出）。"""
        if self._stopped:
            return
        self._stopped = True
        self.clear()
        for _ in self._workers:
            self._queue.put(None)
        self._workers.clear()

    # -- 内部 ------------------------------------------------------------
    def _placeholder(self, path: Path) -> QPixmap:
        return placeholder_pixmap(self._size, _kind_for_path(path))

    def _ensure_workers(self):
        if self._workers:
            return
        with self._start_lock:
            if self._workers or self._stopped:
                return
            for index in range(self._max_workers):
                thread = threading.Thread(
                    target=self._worker_loop,
                    name=f"thumbnail-loader-{index}",
                    daemon=True,
                )
                thread.start()
                self._workers.append(thread)

    def _worker_loop(self):
        try:
            while True:
                task = self._queue.get()
                if task is None:
                    return
                generation, path_str, mtime_ns = task
                if generation != self._generation or self._stopped:
                    continue
                cancel = self._cancel_event if generation == self._generation else None
                image, error = load_thumbnail_image_detail(
                    Path(path_str), self._size, stop_event=cancel
                )
                if generation != self._generation or self._stopped:
                    continue
                try:
                    self._loaded.emit(generation, path_str, mtime_ns, image, error)
                except Exception:
                    # 窗口已销毁时 emit 可能失败；缩略图是可丢弃的，安静退出
                    return
        finally:
            _release_shell_api()

    def _record_failure(self, key: tuple[str, int], path_str: str, reason: str) -> None:
        info = self._failures.get(key) or {"retries": 0, "retry_at": 0.0, "reason": reason}
        info["retries"] = int(info.get("retries", 0)) + 1
        info["reason"] = reason
        index = min(info["retries"] - 1, len(self._FAILURE_BACKOFF_S) - 1)
        info["retry_at"] = _now() + self._FAILURE_BACKOFF_S[index]
        self._failures[key] = info
        # 换 key 后旧 mtime 立即过期，下次 request 会重查 stat
        self._mtime_cache.pop(path_str, None)
        self.thumbnail_failed.emit(path_str, reason)

    def _on_loaded(
        self, generation: int, path_str: str, mtime_ns: int, image: Any, error: str = ""
    ):
        # 先判代号：clear() 后到达的旧结果不得影响新一轮的 pending 记录
        if generation != self._generation or self._stopped:
            return
        key = (path_str, mtime_ns)
        self._pending.discard(key)
        if not isinstance(image, QImage) or image.isNull():
            self._record_failure(key, path_str, error or "decode_failed")
            return
        try:
            pixmap = QPixmap.fromImage(image)
        except Exception:
            self._record_failure(key, path_str, "decode_failed")
            return
        if pixmap.isNull():
            self._record_failure(key, path_str, "decode_failed")
            return
        self._failures.pop(key, None)
        self._cache[key] = pixmap
        while len(self._cache) > self._cache_limit:
            self._cache.popitem(last=False)
        self.thumbnail_ready.emit(path_str)


# ---------------------------------------------------------------------------
# 预览面板
# ---------------------------------------------------------------------------

PANEL_TRANSLATIONS = {
    "zh": {
        "no_file": "未选择文件",
        "empty_value": "—",
        "size": "大小",
        "mtime": "修改时间",
        "retry": "重试",
    },
    "en": {
        "no_file": "No file selected",
        "empty_value": "—",
        "size": "Size",
        "mtime": "Modified",
        "retry": "Retry",
    },
}


def _format_size(size: int) -> str:
    value = float(max(0, int(size)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{int(size)} B"


def _format_mtime(mtime_ns: int) -> str:
    try:
        return datetime.fromtimestamp(mtime_ns / 1_000_000_000).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return PANEL_TRANSLATIONS["zh"]["empty_value"]


def _fit_pixmap(pixmap: QPixmap, box: int) -> QPixmap:
    """按比例缩放到 box×box 以内（保留给外部调用方的兼容工具）。"""
    if pixmap.isNull() or box <= 0:
        return pixmap
    if pixmap.width() <= box and pixmap.height() <= box:
        return pixmap
    return pixmap.scaled(
        box,
        box,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class _WrappingLabel(_BodyLabel):
    """任意字符换行标签（``WrapAnywhere``），最小宽度不随长路径增长。

    QLabel 的 ``wordWrap`` 只在词边界换行：长连续文件名（无空格/分隔符）会被横向截断，
    而且 ``minimumSizeHint`` 仍是最长连续字符宽度，会把预览槽和 splitter 一起撑开。
    这里用 ``QTextDocument`` 按 ``WrapAnywhere`` 自行排版，``heightForWidth`` 随宽度变化，
    最小宽度固定为小值，保证预览两槽等宽且完整显示路径。
    """

    _MIN_WIDTH = 48

    def __init__(self, text: str = "", parent=None):
        # qfluentwidgets 的 singledispatch 会把 ``(text, parent)`` 形式转成
        # ``self.__init__(parent)``，所以这里只传 parent，否则会无限递归。
        # ``_doc`` 必须先于任何 setText 可用（QLabel 的 setText 会在 __init__ 期间被调用）。
        self._doc = QTextDocument()
        self._doc_width = -1
        self._selecting = False
        self._drag_origin: QPointF | None = None
        super().__init__(parent)
        self._doc.setParent(self)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self._sync_doc_format()
        self._doc.setDocumentMargin(0)
        option = self._doc.defaultTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self._doc.setDefaultTextOption(option)
        self._doc.setUseDesignMetrics(True)
        if text:
            self.setText(text)

    # -- QLabel 兼容 ------------------------------------------------------
    def setText(self, text: str) -> None:  # noqa: N802 - Qt 命名
        super().setText(text)
        self._doc.setPlainText(text)
        self._doc_width = -1
        self.updateGeometry()
        self.update()

    def _sync_doc_format(self) -> None:
        """QTextDocument 不继承 QLabel 的字体/调色板，显式同步。"""
        self._doc.setDefaultFont(self.font())
        self._doc.setDocumentMargin(0)

    def setFont(self, font: QFont) -> None:  # noqa: N802 - Qt 命名
        super().setFont(font)
        if getattr(self, "_doc", None) is not None:
            self._doc.setDefaultFont(font)
            self._doc_width = -1
            self.updateGeometry()

    def setFontFamily(self, family: str) -> None:  # noqa: N802 - Qt 命名
        font = self.font()
        font.setFamily(family)
        self.setFont(font)

    def setPixelSize(self, size: int) -> None:  # noqa: N802 - Qt 命名
        font = self.font()
        font.setPixelSize(int(size))
        self.setFont(font)

    def setPointSize(self, size: int) -> None:  # noqa: N802 - Qt 命名
        font = self.font()
        font.setPointSize(int(size))
        self.setFont(font)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt 命名
        # 只报一行高度；真实行数由 heightForWidth(当前可用宽度) 决定。
        # 若这里按 _MIN_WIDTH 算全文高度，QVBoxLayout 会拿一个虚高的 sizeHint
        # 与别的控件抢空间，反而把路径压成固定几行。
        return QSize(self._MIN_WIDTH, max(1, self.fontMetrics().height()))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt 命名
        # 高度只保证一行；实际高度由 heightForWidth 根据当前宽度算出
        return QSize(self._MIN_WIDTH, max(1, self.fontMetrics().height()))

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt 命名
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt 命名
        return self._height_for(width)

    def paintEvent(self, event):  # noqa: N802 - Qt 命名
        painter = QPainter(self)
        try:
            self._sync_doc_format()
            width = max(1, self.width())
            self._doc.setTextWidth(width)
            self._doc_width = width
            context = QAbstractTextDocumentLayout.PaintContext()
            context.palette = QPalette(self.palette())
            context.palette.setColor(
                QPalette.ColorRole.Text, self.palette().color(self.foregroundRole())
            )
            context.clip = QRectF(0, 0, width, self._doc.size().height())
            if self._selection_active():
                selection = QAbstractTextDocumentLayout.Selection()
                selection.cursor = self._doc_cursor()
                selection.format.setBackground(context.palette.highlight())
                selection.format.setForeground(context.palette.highlightedText())
                context.selections = [selection]
            self._doc.documentLayout().draw(painter, context)
        finally:
            painter.end()

    # -- 选择/复制 --------------------------------------------------------
    def _doc_cursor(self) -> QTextCursor:
        cursor = getattr(self, "_cursor", None)
        if cursor is None:
            cursor = QTextCursor(self._doc)
            self._cursor = cursor
        return cursor

    def _selection_active(self) -> bool:
        return self._doc_cursor().hasSelection() and self.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction

    def _cursor_active(self) -> bool:
        return False

    def selectedText(self) -> str:  # noqa: N802 - Qt 命名
        return self._doc_cursor().selectedText() if self._selection_active() else ""

    def copy(self) -> None:  # noqa: N802 - Qt 命名
        selected = self.selectedText()
        if selected:
            QApplication.clipboard().setText(selected.replace("\u2029", "\n"))

    def _hit_cursor(self, point: QPointF) -> QTextCursor:
        position = self._doc.documentLayout().hitTest(point, Qt.HitTestAccuracy.FuzzyHit)
        cursor = QTextCursor(self._doc)
        cursor.setPosition(max(0, position))
        return cursor

    def mousePressEvent(self, event):  # noqa: N802 - Qt 命名
        if self.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction:
            return super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            position = event.position()
            cursor = self._hit_cursor(position)
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                anchor = self._doc_cursor().anchor()
                cursor.setPosition(anchor, QTextCursor.MoveMode.KeepAnchor)
            self._doc_cursor().setPosition(cursor.position())
            self._selecting = True
            self._drag_origin = position
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt 命名
        if not self._selecting:
            return super().mouseMoveEvent(event)
        cursor = self._hit_cursor(event.position())
        target = self._doc_cursor()
        target.setPosition(cursor.position(), QTextCursor.MoveMode.KeepAnchor)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt 命名
        if self._selecting and event.button() == Qt.MouseButton.LeftButton:
            self._selecting = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802 - Qt 命名
        if self.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction:
            return super().mouseDoubleClickEvent(event)
        cursor = self._hit_cursor(event.position())
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        if cursor.hasSelection():
            self._doc_cursor().setPosition(cursor.selectionStart())
            self._doc_cursor().setPosition(
                cursor.selectionEnd(), QTextCursor.MoveMode.KeepAnchor
            )
            self.update()
        event.accept()

    def keyPressEvent(self, event):  # noqa: N802 - Qt 命名
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy()
            event.accept()
            return
        if event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.selectAllText()
            event.accept()
            return
        super().keyPressEvent(event)

    def selectAllText(self) -> None:  # noqa: N802 - Qt 命名
        cursor = self._doc_cursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self.update()

    def clearSelection(self) -> None:  # noqa: N802 - Qt 命名
        cursor = self._doc_cursor()
        cursor.clearSelection()
        self.update()

    # -- 内部 ------------------------------------------------------------
    def _height_for(self, width: int) -> int:
        width = max(1, int(width))
        if self._doc_width != width:
            self._doc.setTextWidth(width)
            self._doc_width = width
        return int(math.ceil(self._doc.size().height()))

    def needed_height(self) -> int:
        """当前宽度下完整显示文本所需的高度（测试/调试用）。"""
        return self._height_for(self.width() or self._MIN_WIDTH)


class _PreviewSlot(QWidget):
    """单个预览槽位：标题 + 大图 + 完整路径 + 大小/修改时间。

    图片区域宽度跟随槽位宽度，高度按固定比例缩放（上下限由构造时的 size 决定），
    实际 pixmap 再按 KeepAspectRatio 适应，所以两槽始终等宽、图片等比缩放。
    """

    _MIN_IMAGE_WIDTH = 120
    _MIN_IMAGE_HEIGHT = 90
    _FRAME_ASPECT = 0.72  # 图片框高/宽，接近常见照片比例

    def __init__(self, image_size: int, parent=None):
        super().__init__(parent)
        self.path: Path | None = None
        self.size_bytes: int | None = None
        self.mtime_ns: int | None = None
        self._image_size = max(64, int(image_size))
        self._source_pixmap: QPixmap | None = None

        # 长路径不允许撑开槽位：水平方向按 Ignored 处理，最小宽度只留给图片框
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(self._MIN_IMAGE_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.title_label = _SubtitleLabel("", self)
        title_font = QFont("Microsoft YaHei", 10)
        title_font.setBold(True)
        self.title_label.setFont(title_font)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(self._MIN_IMAGE_WIDTH, self._MIN_IMAGE_HEIGHT)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        initial_height = self._frame_height_for(self._image_size)
        self.image_label.setFixedHeight(initial_height)
        self.image_label.setStyleSheet(
            "border: 1px solid #E4E7EC; border-radius: 8px; background: #F9FAFB;"
        )

        self.path_label = _WrappingLabel("", self)
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )

        self.meta_label = _WrappingLabel("", self)
        self.meta_label.setStyleSheet("color: #667085;")

        # 加载失败提示 + 手动重试（中英文案由 set_failure 传入，不在内部写死）
        self.failure_label = _WrappingLabel("", self)
        self.failure_label.setStyleSheet("color: #B42318;")
        self.failure_label.setVisible(False)

        self.retry_button = QPushButton("", self)
        self.retry_button.setFlat(True)
        self.retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_button.setStyleSheet(
            "QPushButton { border: none; background: transparent; color: #175CD3; padding: 0; text-align: left; }"
        )
        self.retry_button.setVisible(False)
        self.retry_button.clicked.connect(lambda _checked=False: self._on_retry_clicked())
        self._retry_callback = None

        layout.addWidget(self.title_label)
        layout.addWidget(self.image_label)
        layout.addWidget(self.path_label)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.failure_label)
        layout.addWidget(self.retry_button)
        layout.addStretch(1)

    def set_entry(
        self,
        title: str,
        path: Path | None,
        size_bytes: int | None,
        mtime_ns: int | None,
        text: dict[str, str],
        pixmap: QPixmap | None,
        kind: str,
    ):
        self.path = path
        self.size_bytes = size_bytes
        self.mtime_ns = mtime_ns
        self.title_label.setText(title or text["empty_value"])
        self.clear_failure()
        if path is None:
            self.path_label.setText(text["no_file"])
            self.path_label.setToolTip("")
            self.path_label.setStyleSheet("color: #98A2B3;")
            self.meta_label.setText(text["empty_value"])
            self.meta_label.setToolTip("")
            self._source_pixmap = None
            self.image_label.setPixmap(placeholder_pixmap(self._placeholder_size(), KIND_OTHER))
            self._sync_minimum_height()
            return

        self.path_label.setText(str(path))
        self.path_label.setStyleSheet("")
        self.path_label.setToolTip(str(path))  # 路径较长时可悬停查看全文
        meta_parts = []
        if size_bytes is not None:
            meta_parts.append(f"{text['size']}: {_format_size(size_bytes)}")
        if mtime_ns is not None:
            meta_parts.append(f"{text['mtime']}: {_format_mtime(mtime_ns)}")
        self.meta_label.setText(" · ".join(meta_parts) if meta_parts else text["empty_value"])
        self.meta_label.setToolTip(self.meta_label.text())
        shown = pixmap if pixmap is not None else placeholder_pixmap(self._placeholder_size(), kind)
        self.show_pixmap(shown)
        self._sync_minimum_height()

    def show_pixmap(self, pixmap: QPixmap):
        """保存原图并按当前图片框尺寸等比缩放（窗口/分栏拖动时重新调用）。"""
        self._source_pixmap = pixmap
        self._refresh_pixmap()

    def clear(self, text: dict[str, str]):
        self.set_entry("", None, None, None, text, None, KIND_OTHER)

    # -- 加载失败反馈 ----------------------------------------------------
    def set_retry_callback(self, callback) -> None:
        """callback(path) —— 用户点「重试」时回调（由 PreviewPanel 注入）。"""
        self._retry_callback = callback

    def set_failure(self, message: str, retry_text: str) -> None:
        """显示失败原因与可操作的「重试」；message 已由调用方翻译。"""
        self.failure_label.setText(message)
        self.failure_label.setVisible(bool(message))
        self.retry_button.setText(retry_text)
        self.retry_button.setVisible(True)
        self._sync_minimum_height()

    def clear_failure(self) -> None:
        self.failure_label.clear()
        self.failure_label.setVisible(False)
        self.retry_button.setVisible(False)
        self._sync_minimum_height()

    def _on_retry_clicked(self) -> None:
        callback = self._retry_callback
        if callback is not None and self.path is not None:
            callback(self.path)

    # -- 内部 ------------------------------------------------------------
    def _frame_height_for(self, width: int) -> int:
        height = int(round(max(self._MIN_IMAGE_WIDTH, width) * self._FRAME_ASPECT))
        lower = self._MIN_IMAGE_HEIGHT
        upper = int(self._image_size * 1.5)
        return max(lower, min(height, upper))

    def _placeholder_size(self) -> int:
        """占位图统一画一个中等尺寸，再由图片框等比缩放（避免每种宽度都生成一张）。"""
        side = min(self.image_label.width() or self._MIN_IMAGE_WIDTH,
                   self.image_label.height() or self._MIN_IMAGE_HEIGHT)
        return max(96, min(256, side))

    def _refresh_pixmap(self) -> None:
        source = self._source_pixmap
        if source is None or source.isNull():
            return
        target = self.image_label.size()
        if target.width() <= 0 or target.height() <= 0:
            target = QSize(self._MIN_IMAGE_WIDTH, self._MIN_IMAGE_HEIGHT)
        scaled = source.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if not scaled.isNull():
            self.image_label.setPixmap(scaled)

    def _sync_image_height(self) -> None:
        """按当前宽度重算图片框高度；纵向不压缩，空间不足由 PreviewPanel 滚动。"""
        width = self.width()
        if width <= 0:
            return
        height = self._frame_height_for(width)
        if self.image_label.height() != height:
            self.image_label.setFixedHeight(height)

    def _sync_minimum_height(self) -> None:
        """把槽位最小高度设为「图片 + 当前宽度下完整文本」的真实高度。

        该最小高度只作用于 QScrollArea 内部内容；外层 PreviewPanel 不会因此变高。
        """
        width = self.width()
        if width <= 0:
            return
        layout = self.layout()
        spacing = layout.spacing() if layout is not None else 0
        margins = layout.contentsMargins() if layout is not None else None
        left = margins.left() if margins is not None else 0
        right = margins.right() if margins is not None else 0
        top = margins.top() if margins is not None else 0
        bottom = margins.bottom() if margins is not None else 0
        text_width = max(1, width - left - right)
        total = top + bottom + self._frame_height_for(width)
        widgets = [self.title_label, self.path_label, self.meta_label]
        if not self.failure_label.isHidden():
            widgets.append(self.failure_label)
        for widget in widgets:
            total += spacing + widget.heightForWidth(text_width)
        if not self.retry_button.isHidden():
            total += spacing + self.retry_button.sizeHint().height()
        minimum = int(total)
        if self.minimumHeight() != minimum:
            self.setMinimumHeight(minimum)

    def resizeEvent(self, event):  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        self._sync_minimum_height()
        self._sync_image_height()
        self._refresh_pixmap()


class PreviewPanel(QWidget):
    """侧边预览面板：1 或 2 个大图槽位，缩略图走独立的小尺寸加载器。

    内容放在内部纵向 QScrollArea：窄侧栏/矮窗口时长路径可以完整显示，
    由面板内部滚动，绝不把外层页面最小高度或窗口撑高。
    """

    _SLOT_SPACING = 12


    def __init__(self, slots: int = 2, size: int = 256, parent=None):
        super().__init__(parent)
        self._slots_count = max(1, int(slots))
        self._size = max(64, int(size))
        self._lang = "zh"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._scroll.viewport().setAutoFillBackground(False)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self._SLOT_SPACING)

        self._slot_widgets: list[_PreviewSlot] = []
        for _ in range(self._slots_count):
            slot = _PreviewSlot(self._size, content)
            self._slot_widgets.append(slot)
            layout.addWidget(slot, 1)

        self._scroll.setWidget(content)
        outer.addWidget(self._scroll)
        # 横向滚动被禁用：面板最小宽度必须容得下所有槽位的最小宽度之和，
        # 否则拖窄时最右槽位会被裁切。该宽度与路径文本无关（槽位最小宽度固定 120）。
        self.setMinimumWidth(self._minimum_panel_width())

        # 预览大图单个 ~256KB，给小一点的 LRU（槽位自己也会持有当前 pixmap）
        # 槽位会随卡片宽度缩放，按 384 解码避免宽卡片时放大发虚
        self._loader = ThumbnailLoader(
            size=max(self._size, 384), max_workers=2, cache_limit=128, parent=self
        )
        self._loader.thumbnail_ready.connect(self._on_thumbnail_ready)
        self._loader.thumbnail_failed.connect(self._on_thumbnail_failed)

        self._titles: dict[int, str] = {}
        # 每个槽位当前展示的失败原因码（语言切换时用它重渲染文案）
        self._failure_codes: dict[int, str] = {}
        self._auto_retry_pending: set[str] = set()
        for slot in self._slot_widgets:
            slot.set_retry_callback(self._retry_path)
        self.clear()

    # -- 公共接口 ---------------------------------------------------------
    def set_slot(
        self,
        index: int,
        title: str,
        path: Path | None,
        size_bytes: int | None = None,
        mtime_ns: int | None = None,
    ) -> None:
        if not (0 <= index < self._slots_count):
            return
        slot = self._slot_widgets[index]
        text = PANEL_TRANSLATIONS.get(self._lang, PANEL_TRANSLATIONS["zh"])
        self._titles[index] = title or ""
        self._failure_codes.pop(index, None)

        resolved_path = Path(path) if path is not None else None
        if resolved_path is not None:
            if size_bytes is None or mtime_ns is None:
                try:
                    stat = resolved_path.stat()
                except Exception:
                    stat = None
                if stat is not None:
                    if size_bytes is None:
                        size_bytes = int(stat.st_size)
                    if mtime_ns is None:
                        mtime_ns = int(stat.st_mtime_ns)

        pixmap = None
        kind = KIND_OTHER
        if resolved_path is not None:
            kind = _kind_for_path(resolved_path)
            pixmap = self._loader.request(resolved_path)
        slot.set_entry(title, resolved_path, size_bytes, mtime_ns, text, pixmap, kind)

    def clear(self) -> None:
        text = PANEL_TRANSLATIONS.get(self._lang, PANEL_TRANSLATIONS["zh"])
        for index, slot in enumerate(self._slot_widgets):
            self._titles[index] = ""
            self._failure_codes.pop(index, None)
            slot.clear(text)
        self._auto_retry_pending.clear()
        self._loader.clear()

    def set_language(self, lang: str) -> None:
        """只刷新面板内的固定文案，不重新加载缩略图（命中缓存时直接复用）。"""
        if lang not in PANEL_TRANSLATIONS:
            lang = "zh"
        self._lang = lang
        text = PANEL_TRANSLATIONS[lang]
        for index, slot in enumerate(self._slot_widgets):
            path = slot.path
            kind = KIND_OTHER
            pixmap = None
            if path is not None:
                kind = _kind_for_path(path)
                pixmap = self._loader.request(path)
            slot.set_entry(
                self._titles.get(index, ""),
                path,
                slot.size_bytes,
                slot.mtime_ns,
                text,
                pixmap,
                kind,
            )
            code = self._failure_codes.get(index)
            if code:
                slot.set_failure(failure_message(code, lang), text["retry"])

    def loader(self) -> ThumbnailLoader:
        """供页面复用同一个加载器（表格模型与预览面板可共享）。"""
        return self._loader

    def shutdown(self) -> None:
        self._loader.shutdown()

    # -- 内部 ------------------------------------------------------------
    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt 命名
        # 让外层 splitter 也看到「两槽最小宽度」；否则只靠 setMinimumWidth
        # 时布局计算的 minimumSizeHint 仍是 QScrollArea 默认的 68。
        return QSize(self.minimumWidth(), self._scroll.minimumSizeHint().height())

    def _minimum_panel_width(self) -> int:
        """面板最小宽度：所有槽位最小宽度 + 间距 + 纵向滚动条宽度。

        与路径长度无关；只保证两个槽位不会被横向裁切，也不会把外层页面撑宽。
        """
        slot_min = _PreviewSlot._MIN_IMAGE_WIDTH
        scrollbar = self._scroll.verticalScrollBar().sizeHint().width()
        content = self._slots_count * slot_min + (self._slots_count - 1) * self._SLOT_SPACING
        return int(content + max(0, scrollbar))

    def resizeEvent(self, event):  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        # 槽位宽度变了 → 重新计算各自「文本完整显示」所需的最小高度
        for slot in self._slot_widgets:
            slot._sync_minimum_height()

    def _slot_indexes_for(self, path_str: str) -> list[int]:
        return [
            index
            for index, slot in enumerate(self._slot_widgets)
            if slot.path is not None and str(slot.path) == path_str
        ]

    def _on_thumbnail_ready(self, path_str: str):
        for index in self._slot_indexes_for(path_str):
            slot = self._slot_widgets[index]
            self._failure_codes.pop(index, None)
            self._auto_retry_pending.discard(path_str)
            slot.clear_failure()
            if slot.path is not None:
                slot.show_pixmap(self._loader.request(slot.path))

    def _on_thumbnail_failed(self, path_str: str, reason: str):
        """展示失败原因（中英）并提供重试；同时安排有限次自动重试。"""
        text = PANEL_TRANSLATIONS.get(self._lang, PANEL_TRANSLATIONS["zh"])
        indexes = self._slot_indexes_for(path_str)
        if not indexes:
            return
        for index in indexes:
            self._failure_codes[index] = reason or "decode_failed"
            self._slot_widgets[index].set_failure(
                failure_message(reason or "decode_failed", self._lang), text["retry"]
            )
        if path_str in self._auto_retry_pending:
            return
        delay = self._loader.next_retry_delay(Path(path_str))
        if delay is None:
            return  # 自动重试用尽：保留提示，等用户点「重试」
        self._auto_retry_pending.add(path_str)
        QTimer.singleShot(int(delay * 1000) + 50, lambda: self._auto_retry(path_str))

    def _auto_retry(self, path_str: str) -> None:
        self._auto_retry_pending.discard(path_str)
        if not self._slot_indexes_for(path_str):
            return  # 已切换到其他文件
        self._loader.request(Path(path_str))

    def _retry_path(self, path: Path) -> None:
        """用户点「重试」：清失败记录并重新排队（不受退避上限限制）。"""
        self._auto_retry_pending.discard(str(path))
        self._loader.retry(path)


# ---------------------------------------------------------------------------
# 本地手动 demo（不给打包/入口使用，仅用于自测缩略图管线）
# ---------------------------------------------------------------------------


def _run_demo(argv: list[str]) -> int:
    from PyQt6.QtWidgets import QApplication, QGridLayout, QScrollArea

    app = QApplication(argv)
    folder = Path(argv[1]) if len(argv) > 1 else Path.cwd()
    files = [path for path in sorted(folder.iterdir()) if path.is_file()][:160]

    window = QWidget()
    window.setWindowTitle("media_thumbnail demo")
    host = QWidget()
    grid = QGridLayout(host)
    grid.setSpacing(6)
    loader = ThumbnailLoader(size=160, max_workers=2)
    labels: dict[str, QLabel] = {}
    columns = 8
    for index, path in enumerate(files):
        label = QLabel()
        label.setFixedSize(160, 160)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setToolTip(str(path))
        labels[str(path)] = label
        grid.addWidget(label, index // columns, index % columns)

    def on_ready(path_str: str):
        label = labels.get(path_str)
        if label is not None:
            label.setPixmap(loader.request(Path(path_str)))

    loader.thumbnail_ready.connect(on_ready)
    for path in files:
        labels[str(path)].setPixmap(loader.request(path))

    scroll = QScrollArea(window)
    scroll.setWidgetResizable(True)
    scroll.setWidget(host)
    scroll.resize(860, 640)
    window.resize(880, 660)
    window.show()
    try:
        return app.exec()
    finally:
        loader.shutdown()


if __name__ == "__main__":
    sys.exit(_run_demo(sys.argv))