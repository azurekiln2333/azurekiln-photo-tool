"""media_thumbnail 共享预览/缩略图加载器回归（stdlib unittest）。

覆盖：
- 共享预览 A/B 两槽始终等宽；超长连续路径不撑开 minimumSizeHint；
- 图片随卡片宽度等比缩放；
- 视频首帧回退管线（Shell 失败 → QtMultimedia 解码）、超时/取消/后端缺失路径；
- 失败有限退避重试 + 手动重试 + mtime 变化后重新加载；
- 失败提示订阅（thumbnail_failed）与中英文切换。

运行：
    $env:QT_QPA_PLATFORM = "offscreen"
    .venv/Scripts/python.exe -m unittest tests.test_media_thumbnail -v
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

_TMP_APPDATA = tempfile.mkdtemp(prefix="test-media-thumb-appdata-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = _TMP_APPDATA

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PyQt6.QtCore import QSize, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QFont, QImage, QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QWidget  # noqa: E402

import media_thumbnail as mt  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


LONG_DIR = "C:/Users/someone/OneDrive - Contoso/Pictures/2026/11/HEIC_UM"
LONG_NAME = "IMG_20261121_1234567890_" + "A" * 200 + ".HEIC"


class PreviewLayoutTests(unittest.TestCase):
    """R1：两槽等宽、长路径任意字符换行、图片等比缩放。"""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _build_panel(self, width: int = 820) -> tuple[QWidget, mt.PreviewPanel]:
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        panel = mt.PreviewPanel(slots=2, size=256)
        layout.addWidget(panel)
        host.resize(width, 520)
        host.show()
        self.app.processEvents()
        self.addCleanup(panel.shutdown)
        self.addCleanup(host.close)
        return host, panel

    def test_slots_share_width_with_long_paths(self):
        _host, panel = self._build_panel()
        panel.set_slot(0, "A", Path(LONG_DIR + "/" + LONG_NAME))
        panel.set_slot(1, "B", Path(LONG_DIR + "/" + LONG_NAME.replace(".HEIC", ".MOV")))
        self.app.processEvents()
        widths = [slot.width() for slot in panel._slot_widgets]
        self.assertEqual(len(widths), 2)
        self.assertGreater(widths[0], 0)
        self.assertLessEqual(abs(widths[0] - widths[1]), 1, f"槽宽不等宽: {widths}")

    def test_long_path_does_not_inflate_minimum_width(self):
        _host, panel = self._build_panel()
        panel.set_slot(0, "A", Path("C:/short/a.heic"))
        panel.set_slot(1, "B", Path("C:/short/b.heic"))
        self.app.processEvents()
        baseline = panel.minimumSizeHint().width()

        panel.set_slot(0, "A", Path(LONG_DIR + "/" + LONG_NAME))
        panel.set_slot(1, "B", Path(LONG_DIR + "/" + LONG_NAME.replace(".HEIC", ".MOV")))
        self.app.processEvents()
        inflated = panel.minimumSizeHint().width()

        self.assertLess(inflated, 400, f"长路径把面板最小宽度撑到 {inflated}")
        self.assertLessEqual(abs(inflated - baseline), 1, f"最小宽度随路径变化: {baseline} -> {inflated}")
        for slot in panel._slot_widgets:
            self.assertLess(slot.path_label.minimumSizeHint().width(), 100)

    def test_long_path_wraps_fully_and_height_covers_text(self):
        """视觉 QA 回归：仅 override minimumSizeHint 不够，文本必须真正任意字符换行且不被截断。"""
        host, panel = self._build_panel(820)
        path = Path(LONG_DIR + "/" + LONG_NAME)
        panel.set_slot(0, "A", path, 12_345_678, 1_700_000_000_000_000_000)
        panel.set_slot(1, "B", path.with_suffix(".MOV"), 12_345_678, 1_700_000_000_000_000_000)
        for _ in range(3):
            self.app.processEvents()

        for slot in panel._slot_widgets:
            label = slot.path_label
            self.assertGreater(label.width(), 0)
            # WrapAnywhere：单行宽度不超过控件宽度（否则就是横向截断）
            self.assertLessEqual(
                label._doc.idealWidth(), label.width() + 2, "长路径未按控件宽度折行"
            )
            # 高度覆盖完整文本
            self.assertGreaterEqual(label.height(), label.needed_height(), "路径被纵向裁切")
            line_height = max(1, label.fontMetrics().lineSpacing())
            self.assertGreater(
                label.height() / line_height, 2, "长路径仍被压缩成不到 2 行"
            )
            # meta（大小·修改时间）也要换行而不是横向截断
            meta = slot.meta_label
            self.assertTrue(meta.wordWrap())
            self.assertGreaterEqual(meta.height(), meta.needed_height())
        self.assertLessEqual(abs(panel._slot_widgets[0].width() - panel._slot_widgets[1].width()), 1)
        host.resize(420, 640)
        for _ in range(3):
            self.app.processEvents()
        for slot in panel._slot_widgets:
            self.assertGreaterEqual(
                slot.path_label.height(), slot.path_label.needed_height(), "缩窄后路径被裁切"
            )
            self.assertLessEqual(
                slot.path_label._doc.idealWidth(), slot.path_label.width() + 2
            )

    def test_path_text_is_selectable_and_copyable(self):
        """路径可复制：选择标记必须真的参与绘制，而不是只设了 flag。"""
        _host, panel = self._build_panel()
        panel.set_slot(0, "A", Path(LONG_DIR + "/" + LONG_NAME))
        self.app.processEvents()
        label = panel._slot_widgets[0].path_label
        flags = label.textInteractionFlags()
        self.assertTrue(flags & Qt.TextInteractionFlag.TextSelectableByMouse)

        label.selectAllText()
        expected = os.fspath(Path(LONG_DIR + "/" + LONG_NAME))
        self.assertEqual(label.selectedText(), expected)
        label.copy()
        self.assertEqual(QApplication.clipboard().text(), expected)
        # 选中后重绘不应抛异常且确实画出了选择区
        label.repaint()
        self.app.processEvents()
        label.clearSelection()
        self.assertEqual(label.selectedText(), "")

    def test_font_change_keeps_wrapping(self):
        """字体变化（如中文 UI 字体）后文档字体同步，换行高度仍覆盖文本。"""
        _host, panel = self._build_panel()
        panel.set_slot(0, "A", Path(LONG_DIR + "/" + LONG_NAME))
        label = panel._slot_widgets[0].path_label
        font = QFont("Microsoft YaHei", 10)
        label.setFont(font)
        self.app.processEvents()
        self.assertEqual(label._doc.defaultFont().family(), font.family())
        self.assertGreaterEqual(label.height(), label.needed_height())

    def test_image_scales_proportionally_with_card_width(self):
        host, panel = self._build_panel(820)
        panel.set_slot(0, "A", Path(LONG_DIR + "/" + LONG_NAME))
        panel.set_slot(1, "B", Path(LONG_DIR + "/" + LONG_NAME))
        self.app.processEvents()

        image = QImage(400, 200, QImage.Format.Format_RGB32)
        image.fill(QColor("#336699"))
        slot = panel._slot_widgets[0]
        slot.show_pixmap(QPixmap.fromImage(image))
        self.app.processEvents()

        wide = slot.image_label.pixmap()
        self.assertIsNotNone(wide)
        self.assertFalse(wide.isNull())
        self.assertAlmostEqual(wide.width() / wide.height(), 2.0, delta=0.03)
        self.assertLessEqual(wide.width(), slot.image_label.width())

        host.resize(420, 520)
        self.app.processEvents()
        narrow = slot.image_label.pixmap()
        self.assertFalse(narrow.isNull())
        self.assertLess(narrow.width(), wide.width(), "缩窄卡片后图片未等比缩小")
        self.assertAlmostEqual(narrow.width() / narrow.height(), 2.0, delta=0.03)
        self.assertLessEqual(narrow.width(), slot.image_label.width())

    def test_placeholder_replaces_on_resize(self):
        _host, panel = self._build_panel()
        panel.set_slot(0, "A", Path(LONG_DIR + "/" + LONG_NAME))
        self.app.processEvents()
        # 构造过程不应抛异常，且空槽位也能拿到占位图而不是空 pixmap
        empty_slot = panel._slot_widgets[1]
        self.assertIsNone(empty_slot.path)
        self.assertGreater(empty_slot.image_label.height(), 0)


class ThumbnailFailureTests(unittest.TestCase):
    """R5：失败原因反馈、有限退避重试、手动重试、mtime 变化后重载。"""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self._now = 1000.0
        self._orig_now = mt._now
        self._orig_load = mt.load_thumbnail_image_detail
        mt._now = lambda: self._now
        self.addCleanup(setattr, mt, "_now", self._orig_now)

    def tearDown(self):
        mt.load_thumbnail_image_detail = self._orig_load

    def _make_loader(self) -> mt.ThumbnailLoader:
        loader = mt.ThumbnailLoader(size=64, max_workers=1, cache_limit=64)
        self.addCleanup(loader.shutdown)
        return loader

    def test_failure_is_not_cached_forever(self):
        mt.load_thumbnail_image_detail = lambda path, size, stop_event=None: (None, "video_timeout")
        loader = self._make_loader()
        loader._ensure_workers = lambda: None  # 不启真实线程，手动驱动队列

        path = Path("C:/fake/a.mp4")
        loader.request(path)
        self.assertEqual(len(loader._queue.queue), 1, "首次请求应入队")
        queued = loader._queue.get_nowait()
        loader._on_loaded(queued[0], queued[1], queued[2], None, "video_timeout")

        self.assertEqual(loader.failure_reason(path), "video_timeout")
        # 退避期内不再排队
        loader.request(path)
        self.assertEqual(len(loader._queue.queue), 0)
        # 退避到期后重新排队（不是永久失败）
        self._now += mt.ThumbnailLoader._FAILURE_BACKOFF_S[0] + 0.01
        loader.request(path)
        self.assertEqual(len(loader._queue.queue), 1)

    def test_retries_are_bounded_then_manual_retry_works(self):
        mt.load_thumbnail_image_detail = lambda path, size, stop_event=None: (None, "decode_failed")
        loader = self._make_loader()
        loader._ensure_workers = lambda: None
        path = Path("C:/fake/b.jpg")

        attempts = len(mt.ThumbnailLoader._FAILURE_BACKOFF_S)
        for _ in range(attempts):
            loader.request(path)
            self.assertEqual(len(loader._queue.queue), 1)
            queued = loader._queue.get_nowait()
            loader._on_loaded(queued[0], queued[1], queued[2], None, "decode_failed")
            self._now += 60.0

        self.assertIsNone(loader.next_retry_delay(path), "退避用尽后不应再自动重试")
        loader.request(path)
        self.assertEqual(len(loader._queue.queue), 0, "用尽后 request 不应排队")

        loader.retry(path)
        self.assertEqual(len(loader._queue.queue), 1, "手动 retry 必须重新排队")
        self.assertIsNone(loader.failure_reason(path))

    def test_mtime_change_triggers_reload(self):
        loader = self._make_loader()
        tmp = Path(tempfile.mkdtemp(prefix="thumb-mtime-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        target = tmp / "cloud.jpg"
        target.write_bytes(b"0")

        calls: list[int] = []
        mt.load_thumbnail_image_detail = lambda path, size, stop_event=None: (
            calls.append(1) or None,
            "decode_failed",
        )
        loader._ensure_workers = lambda: None

        first = loader.request(target)
        self.assertFalse(first.isNull())
        queued = loader._queue.get_nowait()
        loader._on_loaded(queued[0], queued[1], queued[2], None, "decode_failed")

        # 模拟云端文件下载完成（mtime 更新）
        time.sleep(0.01)
        os.utime(target, ns=(time.time_ns(), time.time_ns() + 5_000_000_000))
        self._now += 0.5  # 让 mtime 缓存过期
        loader.request(target)
        self.assertEqual(len(loader._queue.queue), 1, "mtime 变化后应重新排队")

    def test_retry_resets_mtime_cache_and_requeues(self):
        mt.load_thumbnail_image_detail = lambda path, size, stop_event=None: (None, "decode_failed")
        loader = self._make_loader()
        loader._ensure_workers = lambda: None
        path = Path("C:/fake/c.mp4")
        loader.request(path)
        queued = loader._queue.get_nowait()
        loader._on_loaded(queued[0], queued[1], queued[2], None, "decode_failed")
        loader.retry(None)
        self.assertEqual(len(loader._queue.queue), 1)

    def test_shutdown_cancels_inflight_video_decode(self):
        """R5 生命周期：关页时正在解码的视频能被取消，线程能退出。"""
        loader = mt.ThumbnailLoader(size=64, max_workers=1)
        seen: dict[str, object] = {}

        def slow_detail(path, size, *, stop_event=None):
            seen["event"] = stop_event
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if stop_event is not None and stop_event.is_set():
                    return None, "cancelled"
                time.sleep(0.02)
            return None, "video_timeout"

        mt.load_thumbnail_image_detail = slow_detail
        loader.request(Path("C:/fake/slow.mp4"))
        for _ in range(200):
            if "event" in seen:
                break
            time.sleep(0.01)
        self.assertIn("event", seen, "工作线程未启动")
        loader.shutdown()
        self.assertTrue(seen["event"].is_set(), "shutdown 未发出取消信号")
        self.assertEqual(loader._workers, [])
        for _ in range(200):
            if not any(t.is_alive() for t in threading.enumerate() if t.name == "thumbnail-loader-0"):
                break
            time.sleep(0.01)
        self.assertFalse(
            any(t.is_alive() for t in threading.enumerate() if t.name == "thumbnail-loader-0"),
            "取消后工作线程未退出",
        )


class VideoPipelineTests(unittest.TestCase):
    """R5：视频首帧回退顺序与失败原因码。"""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self._orig_shell = mt._shell_api
        self._orig_reader = mt._load_with_qimage_reader
        self._orig_video = mt._extract_video_frame_qtmultimedia
        self.addCleanup(self._restore)

    def _restore(self):
        mt._shell_api = self._orig_shell
        mt._load_with_qimage_reader = self._orig_reader
        mt._extract_video_frame_qtmultimedia = self._orig_video

    def _api(self):
        return type("Api", (), {"thumbnail": staticmethod(lambda path, size: None)})()

    def test_shell_failure_falls_back_to_video_decoder(self):
        mt._shell_api = lambda: self._api()
        image = QImage(32, 16, QImage.Format.Format_RGB32)
        image.fill(QColor("#00FF00"))
        seen: list[Path] = []

        def fake_video(path, size, *, timeout_ms=0, stop_event=None):
            seen.append(Path(path))
            return image, ""

        mt._extract_video_frame_qtmultimedia = fake_video
        mt._load_with_qimage_reader = lambda path, size: self.fail("不应再走 QImageReader")
        result, reason = mt.load_thumbnail_image_detail(Path("C:/fake/v.mp4"), 64)
        self.assertEqual(reason, "")
        self.assertIsNotNone(result)
        self.assertEqual(len(seen), 1)

    def test_non_video_skips_video_decoder(self):
        mt._shell_api = lambda: self._api()
        mt._extract_video_frame_qtmultimedia = lambda *a, **kw: self.fail("图片不应调用视频解码")
        fallback = QImage(8, 8, QImage.Format.Format_RGB32)
        mt._load_with_qimage_reader = lambda path, size: fallback
        result, reason = mt.load_thumbnail_image_detail(Path("C:/fake/p.jpg"), 64)
        self.assertIsNotNone(result)
        self.assertEqual(reason, "")

    def test_all_strategies_failed_reports_video_reason(self):
        mt._shell_api = lambda: self._api()
        mt._extract_video_frame_qtmultimedia = lambda path, size, **kw: (None, "video_timeout")
        mt._load_with_qimage_reader = lambda path, size: None
        result, reason = mt.load_thumbnail_image_detail(Path("C:/fake/v.mov"), 64)
        self.assertIsNone(result)
        self.assertEqual(reason, "video_timeout")

    def test_invalid_size(self):
        result, reason = mt.load_thumbnail_image_detail(Path("C:/fake/v.mov"), 0)
        self.assertIsNone(result)
        self.assertEqual(reason, "invalid_size")

    def test_stop_event_cancels_before_video(self):
        import threading

        mt._shell_api = lambda: self._api()
        event = threading.Event()
        event.set()
        mt._extract_video_frame_qtmultimedia = lambda *a, **kw: self.fail("已取消不应解码")
        mt._load_with_qimage_reader = lambda path, size: self.fail("已取消不应再读文件")
        result, reason = mt.load_thumbnail_image_detail(Path("C:/fake/v.mp4"), 64, stop_event=event)
        self.assertIsNone(result)
        self.assertEqual(reason, "cancelled")

    def test_video_decoder_missing_is_reported(self):
        self.assertTrue(mt.failure_message("video_unavailable"))
        # 失败原因必须有中英双语文案
        for code in ("decode_failed", "video_unavailable", "video_timeout", "cancelled", "invalid_size"):
            self.assertIn(code, mt.FAILURE_MESSAGES["zh"])
            self.assertIn(code, mt.FAILURE_MESSAGES["en"])
            self.assertNotEqual(
                mt.failure_message(code, "zh"), mt.failure_message(code, "en"), code
            )


class PanelFailureFeedbackTests(unittest.TestCase):
    """R5 UI：PreviewPanel 订阅 thumbnail_failed，显示中英原因并可重试。"""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_panel_shows_failure_and_retry(self):
        panel = mt.PreviewPanel(slots=1, size=128)
        self.addCleanup(panel.shutdown)
        calls: list[str] = []
        panel._loader.thumbnail_ready.connect(calls.append)

        path = Path("C:/fake/missing-photo.mp4")
        panel.set_slot(0, "A", path)
        slot = panel._slot_widgets[0]
        panel._on_thumbnail_failed(str(path), "video_timeout")

        self.assertTrue(slot.failure_label.isVisibleTo(slot))
        self.assertIn(mt.failure_message("video_timeout", "zh"), slot.failure_label.text())
        self.assertTrue(slot.retry_button.isVisibleTo(slot))
        self.assertEqual(slot.retry_button.text(), mt.PANEL_TRANSLATIONS["zh"]["retry"])

        # 切换语言后文案与按钮都跟着变
        panel.set_language("en")
        self.assertIn("Timed out", slot.failure_label.text())
        self.assertEqual(slot.retry_button.text(), mt.PANEL_TRANSLATIONS["en"]["retry"])

        # 点击「重试」触发 loader.retry（真实按钮点击，覆盖信号参数绑定）
        retried: list[Path] = []
        panel._loader.retry = lambda target=None: retried.append(target)
        slot.retry_button.click()
        self.assertEqual(retried, [path])

    def test_success_clears_failure_banner(self):
        panel = mt.PreviewPanel(slots=1, size=128)
        self.addCleanup(panel.shutdown)
        path = Path("C:/fake/ok.jpg")
        panel.set_slot(0, "A", path)
        slot = panel._slot_widgets[0]
        panel._on_thumbnail_failed(str(path), "decode_failed")
        self.assertTrue(slot.retry_button.isVisibleTo(slot))

        image = QImage(16, 16, QImage.Format.Format_RGB32)
        image.fill(QColor("#123456"))
        key = (str(path), panel._loader._mtime_for(path))
        panel._loader._cache[key] = QPixmap.fromImage(image)
        panel._on_thumbnail_ready(str(path))
        self.assertFalse(slot.retry_button.isVisibleTo(slot))

    def test_failure_for_other_path_is_ignored(self):
        panel = mt.PreviewPanel(slots=1, size=128)
        self.addCleanup(panel.shutdown)
        panel.set_slot(0, "A", Path("C:/fake/current.jpg"))
        slot = panel._slot_widgets[0]
        panel._on_thumbnail_failed("C:/fake/other.jpg", "decode_failed")
        self.assertFalse(slot.retry_button.isVisibleTo(slot))

    def test_auto_retry_is_scheduled_once(self):
        panel = mt.PreviewPanel(slots=1, size=128)
        self.addCleanup(panel.shutdown)
        path = Path("C:/fake/auto.mp4")
        panel.set_slot(0, "A", path)
        loader = panel._loader
        loader._ensure_workers = lambda: None
        queued = loader._queue.get_nowait()
        # 真实链路：worker 结果 → _on_loaded 记失败并发 thumbnail_failed → 面板安排自动重试
        loader._on_loaded(queued[0], queued[1], queued[2], None, "video_timeout")
        self.assertIn(str(path), panel._auto_retry_pending)
        panel._on_thumbnail_failed(str(path), "video_timeout")
        self.assertEqual(len(panel._auto_retry_pending), 1, "重复失败不得叠加多个重试定时器")
        # 自动重试用尽后不再安排
        key = (queued[1], queued[2])
        loader._failures[key] = {
            "retries": len(loader._FAILURE_BACKOFF_S),
            "retry_at": 0.0,
            "reason": "video_timeout",
        }
        panel._auto_retry_pending.clear()
        panel._on_thumbnail_failed(str(path), "video_timeout")
        self.assertNotIn(str(path), panel._auto_retry_pending)


class LocalVideoDecodeTests(unittest.TestCase):
    """AC4：强制 Shell 失败时，本地 H.264/HEVC 样例能解码（需要 ffmpeg 生成样片）。"""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        cls.tmp = Path(tempfile.mkdtemp(prefix="thumb-video-"))
        cls.ffmpeg = shutil.which("ffmpeg")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _make_clip(self, name: str, codec: str) -> Path:
        target = self.tmp / name
        cmd = [
            self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=5", "-t", "1",
            "-c:v", codec, "-pix_fmt", "yuv420p", str(target),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return target

    def _decode_without_shell(self, path: Path) -> tuple[QImage | None, str]:
        orig = mt._shell_api
        mt._shell_api = lambda: None
        try:
            return mt.load_thumbnail_image_detail(path, 96)
        finally:
            mt._shell_api = orig

    @unittest.skipUnless(shutil.which("ffmpeg"), "需要 ffmpeg 生成测试样片")
    def test_h264_decodes_without_shell(self):
        image, reason = self._decode_without_shell(self._make_clip("h264.mp4", "libx264"))
        self.assertIsNotNone(image, f"reason={reason}")
        self.assertFalse(image.isNull())
        self.assertLessEqual(max(image.width(), image.height()), 96)

    @unittest.skipUnless(shutil.which("ffmpeg"), "需要 ffmpeg 生成测试样片")
    def test_hevc_decodes_without_shell(self):
        image, reason = self._decode_without_shell(self._make_clip("hevc.mp4", "libx265"))
        self.assertIsNotNone(image, f"reason={reason}")
        self.assertFalse(image.isNull())

    @unittest.skipUnless(shutil.which("ffmpeg"), "需要 ffmpeg 生成测试样片")
    def test_video_decoder_timeout_is_bounded(self):
        clip = self._make_clip("timeout.mp4", "libx264")
        started = time.monotonic()
        image, reason = mt._extract_video_frame_qtmultimedia(
            clip, 96, timeout_ms=1
        )
        elapsed = time.monotonic() - started
        # 1ms 超时不可能解出首帧，但必须在有限时间内返回
        self.assertLess(elapsed, 3.0, "视频解码超时未生效")
        if image is None:
            self.assertIn(reason, ("video_timeout", "decode_failed"))

    def test_missing_video_returns_reason(self):
        missing = self.tmp / "not-there.mp4"
        image, reason = self._decode_without_shell(missing)
        self.assertIsNone(image)
        self.assertTrue(reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
