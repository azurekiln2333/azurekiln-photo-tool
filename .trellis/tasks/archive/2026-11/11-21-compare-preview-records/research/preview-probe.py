"""临时探针：QLabel 长路径换行行为 + QtMultimedia 视频首帧提取（只读验证，不写入仓库行为）。"""

import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

app = QApplication(sys.argv)

LONG = "C:/Users/someone/OneDrive - Contoso/Pictures/2026/11/HEIC_UM/IMG_20261121_1234567890_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.HEIC"

label = QLabel(LONG)
label.setWordWrap(True)
print("wordwrap sizeHint", label.sizeHint().width(), label.sizeHint().height())
print("wordwrap minimumSizeHint", label.minimumSizeHint().width(), label.minimumSizeHint().height())

label2 = QLabel(LONG)
label2.setWordWrap(False)
print("nowrap minimumSizeHint", label2.minimumSizeHint().width())

# 放进窄容器，看布局是否被撑开
host = QWidget()
lay = QVBoxLayout(host)
lay.setContentsMargins(0, 0, 0, 0)
lay.addWidget(label)
host.setFixedWidth(260)
host.resize(260, 400)
host.show()
app.processEvents()
print("host actual width", host.width(), "label actual width", label.width(), "label height", label.height())


def probe_video(path: Path, timeout_ms: int = 6000):
    """在独立线程里用 QMediaPlayer + QVideoSink 抓首帧。"""
    result = {}

    def run():
        from PyQt6.QtMultimedia import QMediaPlayer, QVideoSink

        loop = QEventLoop()
        player = QMediaPlayer()
        sink = QVideoSink()
        player.setVideoSink(sink)
        state = {"done": False}

        def finish(reason, image=None, error=""):
            if state["done"]:
                return
            state["done"] = True
            result["reason"] = reason
            result["image"] = image
            result["error"] = error
            loop.quit()

        def on_frame(frame):
            image = frame.toImage() if frame.isValid() else QImage()
            if not image.isNull():
                finish("frame", image=image)

        sink.videoFrameChanged.connect(on_frame)
        player.errorOccurred.connect(lambda err, msg: finish("error", error=f"{err} {msg}"))

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: finish("timeout"))
        timer.start(timeout_ms)

        player.setSource(QUrl.fromLocalFile(str(path)))
        player.play()
        loop.exec()
        player.stop()
        player.setSource(QUrl())
        player.setVideoSink(None)

    started = time.monotonic()
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout_ms / 1000 + 4)
    result["elapsed"] = round(time.monotonic() - started, 2)
    return result


tmp = Path(tempfile.mkdtemp(prefix="preview-probe-"))
for name, extra in (
    ("h264.mp4", ["-c:v", "libx264"]),
    ("hevc.mp4", ["-c:v", "libx265"]),
):
    target = tmp / name
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=5", "-t", "1", *extra,
        "-pix_fmt", "yuv420p", str(target),
    ]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        print(name, "generate failed", done.stderr.strip()[:200])
        continue
    info = probe_video(target)
    img = info.get("image")
    print(
        name,
        "reason=", info.get("reason"),
        "size=", None if img is None else (img.width(), img.height()),
        "elapsed=", info.get("elapsed"),
        "error=", info.get("error"),
    )
print("tmp", tmp)
