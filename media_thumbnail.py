"""共享缩略图加载器与侧边预览面板。

本模块负责「目录比对」「目录内去重」两个页面的缩略图与预览显示，接口契约见
`.trellis/tasks/11-20-dir-compare-dedupe/design.md` 的「契约 2」。

设计要点：

- 后台线程只产出 ``QImage``，``QPixmap`` 只在 GUI 线程创建（Qt 硬性约束）。
- 加载顺序：Windows Shell 缩略图（ctypes 调 ``IShellItemImageFactory``，照片/视频/HEIC
  都依赖系统能力）→ ``QImageReader`` → 类型占位图。任一步失败都会安静降级，绝不抛给 UI。
- LRU 缓存，key 为 ``(str(path), mtime_ns)``；加载失败也记入负缓存，避免每次重绘都重试。
- 只加载可见行：表格模型在 ``DecorationRole`` 里调用 ``request()``，未命中先返回占位图。

``QPixmap``/``QImage`` 需要 QGuiApplication，本模块只能在 GUI 进程中导入使用
（不依赖 qfluentwidgets，缺少时回退到裸 QLabel）。
"""

from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QFont, QImage, QImageReader, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

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


def load_thumbnail_image(path: Path, size: int) -> QImage | None:
    """后台线程入口：Shell 缩略图 → QImageReader → None（调用方用占位图）。"""
    if size <= 0:
        return None
    api = _shell_api()
    if api is not None:
        image = api.thumbnail(path, size)
        if image is not None:
            return image
    return _load_with_qimage_reader(path, size)


# ---------------------------------------------------------------------------
# ThumbnailLoader
# ---------------------------------------------------------------------------


class ThumbnailLoader(QObject):
    """异步缩略图加载器（仅在 GUI 线程调用 ``request``）。"""

    thumbnail_ready = pyqtSignal(str)  # 参数：文件路径字符串

    # 跨线程信号用队列入主线程，规避「非 Qt 线程直接触碰 UI」
    # 注意：mtime_ns 是 64 位，必须声明为 qlonglong，默认 int 会在队列传递时被截断。
    _loaded = pyqtSignal(int, str, "qlonglong", object)  # generation, path, mtime_ns, QImage|None

    def __init__(self, size: int = 96, max_workers: int = 2, cache_limit: int = 3000, parent=None):
        super().__init__(parent)
        self._size = max(8, int(size))
        self._max_workers = max(1, int(max_workers))
        self._cache_limit = max(16, int(cache_limit))
        self._cache: OrderedDict[tuple[str, int], QPixmap] = OrderedDict()
        self._pending: set[tuple[str, int]] = set()
        self._missing: set[tuple[str, int]] = set()
        # paint 时会高频 request()，mtime 按 generation 缓存一次，避免每帧 stat
        self._mtime_cache: dict[str, int] = {}
        self._queue: queue.Queue[tuple[int, str, int] | None] = queue.Queue()
        self._workers: list[threading.Thread] = []
        self._generation = 0
        self._stopped = False
        self._start_lock = threading.Lock()
        self._loaded.connect(self._on_loaded, Qt.ConnectionType.QueuedConnection)

    # -- 公共接口 ---------------------------------------------------------
    def request(self, path: Path) -> QPixmap:
        """立即返回：缓存命中→缩略图；未命中→占位图并排队后台加载。"""
        path = Path(path)
        if self._stopped:
            return self._placeholder(path)

        key = (str(path), self._mtime_for(path))
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached

        placeholder = self._placeholder(path)
        if key in self._pending or key in self._missing:
            return placeholder
        self._pending.add(key)
        self._ensure_workers()
        self._queue.put((self._generation, key[0], key[1]))
        return placeholder

    def _mtime_for(self, path: Path) -> int:
        key = str(path)
        cached = self._mtime_cache.get(key)
        if cached is not None:
            return cached
        value = _stat_mtime_ns(path)
        self._mtime_cache[key] = value
        return value

    def clear(self) -> None:
        """清缓存、取消排队任务（新扫描开始时调用）。

        已开始加载的任务无法真正中断，用 generation 让它们的结果被丢弃。
        """
        self._generation += 1
        self._cache.clear()
        self._pending.clear()
        self._missing.clear()
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
                image = load_thumbnail_image(Path(path_str), self._size)
                if generation != self._generation or self._stopped:
                    continue
                try:
                    self._loaded.emit(generation, path_str, mtime_ns, image)
                except Exception:
                    # 窗口已销毁时 emit 可能失败；缩略图是可丢弃的，安静退出
                    return
        finally:
            _release_shell_api()

    def _on_loaded(self, generation: int, path_str: str, mtime_ns: int, image: Any):
        # 先判代号：clear() 后到达的旧结果不得影响新一轮的 pending 记录
        if generation != self._generation or self._stopped:
            return
        key = (path_str, mtime_ns)
        self._pending.discard(key)
        if not isinstance(image, QImage) or image.isNull():
            self._missing.add(key)
            return
        try:
            pixmap = QPixmap.fromImage(image)
        except Exception:
            self._missing.add(key)
            return
        if pixmap.isNull():
            self._missing.add(key)
            return
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
    },
    "en": {
        "no_file": "No file selected",
        "empty_value": "—",
        "size": "Size",
        "mtime": "Modified",
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
    """按比例缩放到 box×box 以内（Shell 缩略图通常不是正方形）。"""
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


class _PreviewSlot(QWidget):
    """单个预览槽位：标题 + 大图 + 完整路径 + 大小/修改时间。"""

    def __init__(self, image_size: int, parent=None):
        super().__init__(parent)
        self.path: Path | None = None
        self.size_bytes: int | None = None
        self.mtime_ns: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.title_label = _SubtitleLabel("", self)
        title_font = QFont("Microsoft YaHei", 10)
        title_font.setBold(True)
        self.title_label.setFont(title_font)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setFixedSize(image_size, image_size)
        self.image_label.setStyleSheet(
            "border: 1px solid #E4E7EC; border-radius: 8px; background: #F9FAFB;"
        )

        self.path_label = _BodyLabel("", self)
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.meta_label = _BodyLabel("", self)
        self.meta_label.setStyleSheet("color: #667085;")

        layout.addWidget(self.title_label)
        layout.addWidget(self.image_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.path_label)
        layout.addWidget(self.meta_label)
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
        if path is None:
            self.path_label.setText(text["no_file"])
            self.path_label.setStyleSheet("color: #98A2B3;")
            self.meta_label.setText(text["empty_value"])
            self.image_label.setPixmap(placeholder_pixmap(self.image_label.width(), KIND_OTHER))
            return

        self.path_label.setText(str(path))
        self.path_label.setStyleSheet("")
        meta_parts = []
        if size_bytes is not None:
            meta_parts.append(f"{text['size']}: {_format_size(size_bytes)}")
        if mtime_ns is not None:
            meta_parts.append(f"{text['mtime']}: {_format_mtime(mtime_ns)}")
        self.meta_label.setText(" · ".join(meta_parts) if meta_parts else text["empty_value"])
        shown = pixmap if pixmap is not None else placeholder_pixmap(self.image_label.width(), kind)
        self.show_pixmap(shown)

    def show_pixmap(self, pixmap: QPixmap):
        self.image_label.setPixmap(_fit_pixmap(pixmap, self.image_label.width()))

    def clear(self, text: dict[str, str]):
        self.set_entry("", None, None, None, text, None, KIND_OTHER)


class PreviewPanel(QWidget):
    """侧边预览面板：1 或 2 个大图槽位，缩略图走独立的小尺寸加载器。"""

    def __init__(self, slots: int = 2, size: int = 256, parent=None):
        super().__init__(parent)
        self._slots_count = max(1, int(slots))
        self._size = max(64, int(size))
        self._lang = "zh"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._slot_widgets: list[_PreviewSlot] = []
        for _ in range(self._slots_count):
            slot = _PreviewSlot(self._size, self)
            self._slot_widgets.append(slot)
            layout.addWidget(slot, 1)

        # 预览大图单个 ~256KB，给小一点的 LRU（槽位自己也会持有当前 pixmap）
        self._loader = ThumbnailLoader(size=self._size, max_workers=2, cache_limit=128, parent=self)
        self._loader.thumbnail_ready.connect(self._on_thumbnail_ready)

        self._titles: dict[int, str] = {}
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
            slot.clear(text)
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

    def loader(self) -> ThumbnailLoader:
        """供页面复用同一个加载器（表格模型与预览面板可共享）。"""
        return self._loader

    def shutdown(self) -> None:
        self._loader.shutdown()

    # -- 内部 ------------------------------------------------------------
    def _on_thumbnail_ready(self, path_str: str):
        for slot in self._slot_widgets:
            if slot.path is not None and str(slot.path) == path_str:
                slot.show_pixmap(self._loader.request(slot.path))


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