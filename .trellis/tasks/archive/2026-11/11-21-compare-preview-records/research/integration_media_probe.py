"""媒体运行时集成探针（发布 worker 用，不进入 tests/，避免抢占其他 worker 的测试文件）。

作用：在**源码环境**（.venv）验证视频首帧回退链路真实可用，而不只是检查文件存在。
打包产物的后端覆盖由 ``scripts/ci/verify_bundle.py``（静态包自检）与
``verify_frozen_media.py``（单独冻结的探针 exe）负责，本脚本不涉及运行 dist 产物。

用法（仅源码运行）：

    .venv/Scripts/python.exe .trellis/tasks/11-21-compare-preview-records/research/integration_media_probe.py

探针内容：
 1. ``import PyQt6.QtMultimedia`` 是否成功（失败即 video_unavailable）。
 2. Qt 插件目录里是否存在 ``multimedia/ffmpegmediaplugin.dll``。
 3. **强制 Windows Shell 失败**（``_shell_api`` 置空）后，``load_thumbnail_image_detail``
    能否对样例 MP4 取到首帧——这才真正覆盖 QtMultimedia 回退，而不是走 Shell 缓存。

退出码 0 表示全部通过；非 0 便于人工快速判断。本脚本只读文件，不写真实相册；
``APPDATA`` 被强制改写到临时目录，避免污染真实 settings。
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path

REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "duplicate_scan_core.py").is_file()
)


def _pick_sample_video() -> Path | None:
    candidates = sorted((REPO_ROOT / "sample").rglob("*.mp4")) if (REPO_ROOT / "sample").is_dir() else []
    return candidates[0] if candidates else None


def main() -> int:
    # 强制隔离：必须在导入 Qt 之前设置，且不尊重已有值（防止误用真实配置）
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["APPDATA"] = tempfile.mkdtemp(prefix="azurekiln-probe-")
    sys.path.insert(0, str(REPO_ROOT))

    errors: list[str] = []

    try:
        from PyQt6.QtCore import QLibraryInfo
        from PyQt6.QtMultimedia import QMediaDevices  # noqa: F401
        # Shell 缩略图（QPixmap）需要 QGuiApplication，QCoreApplication 不够
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - 环境问题
        print(f"error: PyQt6 QtMultimedia/QtWidgets unavailable: {exc}", file=sys.stderr)
        return 2
    app = QApplication.instance() or QApplication([])
    keep_alive = app  # 进程生命周期内保持引用，避免 Qt teardown 顺序问题

    plugins_dir = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)) / "multimedia"
    ffmpeg_plugin = plugins_dir / "ffmpegmediaplugin.dll"
    if ffmpeg_plugin.is_file():
        print(f"ok: ffmpeg multimedia plugin at {ffmpeg_plugin}")
    else:
        errors.append(f"ffmpegmediaplugin.dll missing under {plugins_dir}")

    video = _pick_sample_video()
    if video is None:
        print("skip: no sample video found under sample/")
    else:
        import media_thumbnail

        # 强制 Shell 失败：确认走的是 QtMultimedia 解码而非系统缩略图缓存
        original_shell_api = media_thumbnail._shell_api
        media_thumbnail._shell_api = lambda: None
        try:
            stop = threading.Event()
            image, code = media_thumbnail.load_thumbnail_image_detail(video, 480, stop_event=stop)
        finally:
            media_thumbnail._shell_api = original_shell_api
        if image is None:
            errors.append(f"Qt fallback first frame failed for {video.name}: {code}")
        else:
            print(f"ok: Qt fallback first frame {image.width()}x{image.height()} from {video.name}")

    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 1
    print("media probe passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
