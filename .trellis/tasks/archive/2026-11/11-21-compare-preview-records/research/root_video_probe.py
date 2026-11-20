"""验证产品实际后台加载器的 H.264/HEVC 解帧，不使用系统 Shell。"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

REPO = next(parent for parent in Path(__file__).resolve().parents
            if (parent / 'duplicate_scan_core.py').is_file())
sys.path.insert(0, str(REPO))
isolated = tempfile.TemporaryDirectory(prefix="compare-video-")
os.environ["APPDATA"] = isolated.name
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication
import media_thumbnail as thumbnail

app = QApplication([])
for codec in ("libx264", "libx265"):
    clip = Path(isolated.name) / f"{codec}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=5", "-t", "1", "-c:v", codec, "-pix_fmt", "yuv420p", str(clip)], check=True, capture_output=True, timeout=20)
    loader = thumbnail.ThumbnailLoader(size=128, max_workers=1)
    loop = QEventLoop()
    received = []
    loader.thumbnail_ready.connect(lambda value: (received.append(value), loop.quit()))
    loader.thumbnail_failed.connect(lambda _path, _reason: loop.quit())
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(10000)
    with patch.object(thumbnail, "_shell_api", return_value=None):
        loader.request(clip)
        loop.exec()
        timer.stop()
        try:
            assert received == [str(clip)], (codec, received, loader.failure_reason(clip))
            pixmap = loader.request(clip)
            assert not pixmap.isNull()
            assert pixmap.width() <= 128 and pixmap.height() <= 128
            print(f"PASS: background {codec}: {pixmap.width()}x{pixmap.height()}")
        finally:
            workers = list(loader._workers)
            loader.shutdown()
            for worker in workers:
                worker.join(timeout=2)
                assert not worker.is_alive(), worker.name
    app.processEvents()
print("PASS: actual worker video pipeline and clean thread shutdown")
