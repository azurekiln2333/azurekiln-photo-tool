# 视频预览打包契约（preview → release）

状态：preview worker 已选定方案并实测；release worker 按此落包，若落包失败不得声称 R5 已修复。

## 结论：不新增外部 ffmpeg.exe，使用 PyQt6.QtMultimedia 自带 FFmpeg 后端

`media_thumbnail.py` 的视频回退实测（.venv 环境，headless）：

- 工作线程内 `QMediaPlayer` + `QVideoSink` + 本线程 `QEventLoop`/`QTimer`，拿到首帧 `QImage`。
- H.264（libx264）与 HEVC（libx265）320x240 样片均成功，单帧耗时约 0.2s；主线程事件循环不受影响。
- 已有组件：`PyQt6/Qt6/bin/avcodec-61.dll`、`avformat-61.dll`、`avutil-59.dll`、
  `swresample-5.dll`、`swscale-8.dll`；`PyQt6/Qt6/plugins/multimedia/ffmpegmediaplugin.dll`、
  `windowsmediaplugin.dll`。
- 因此不需要下载/分发独立的 ffmpeg 二进制，也不强依赖 PATH 里的 `ffmpeg.exe`。

## 打包要求（onefile spec）

1. `hiddenimports` 必须显式包含（触发 PyInstaller 的 PyQt6 hook 收集多媒体后端与 DLL）：
   - `PyQt6.QtMultimedia`
   - `PyQt6.QtMultimediaWidgets`（仅为 hook 完整性，代码未直接使用）
   - `PyQt6.QtNetwork`（QtMultimedia 依赖，hook 通常自动带入，显式列出更稳）
2. `binaries` 必须包含 Qt6 的 FFmpeg 运行库（缺任一则回退不可用）：
   - `avcodec-61.dll`、`avformat-61.dll`、`avutil-59.dll`、`swresample-5.dll`、`swscale-8.dll`
   - 位于 `PyQt6/Qt6/bin/`，建议用 `collect_dynamic_libs("PyQt6")` 或按 `Path(PyQt6.__file__).parent/"Qt6"/"bin"` 显式收。
3. `datas`/插件目录必须包含 `PyQt6/Qt6/plugins/multimedia/ffmpegmediaplugin.dll`
   （PyQt6 hook 一般会收 `plugins/multimedia`，若被裁剪需显式补 `(".../plugins/multimedia", "PyQt6/Qt6/plugins/multimedia")`）。
4. 运行时插件搜索路径：onefile 下 `QT_PLUGIN_PATH`/`QApplication` 已由 PyQt6 hook 自举；
   若 `QMediaDevices`/player 报 "no multimedia backend"，优先检查 `_MEIPASS` 内
   `PyQt6/Qt6/plugins/multimedia` 是否随包，以及 `qt.conf` 是否指向 `plugins`。

## `scripts/ci/verify_bundle.py` 需要新增的校验

在现有 exiftool 校验之外，断言 CArchive 中存在（大小写不敏感、正斜杠）：

- 任一 Qt6 FFmpeg 运行库：`avcodec-61.dll`（建议同时校验 `avformat-61.dll`、`avutil-59.dll`）
- `ffmpegmediaplugin.dll`（可接受路径含 `plugins/multimedia/`）
- PYZ 模块：`PyQt6.QtMultimedia`（`PyQt6.QtMultimedia.*` 任一即可）

## 运行时自检（release/CI 可选）

`media_thumbnail.load_thumbnail_image_detail()` 对视频返回 `(None, "video_unavailable")`
即表示后端缺失。CI 可在打包后的进程里对样例 mp4 调用它：非 `video_unavailable` 且有图像视为通过。

## 已知边界（不得夸大为已验证）

- 真实 OneDrive 云端占位文件首次水化未做端到端验证；仅验证本地 H.264/HEVC 在 Shell 失败时能解。
- 未在 Windows 未安装 HEVC 扩展的机器上验证系统 Shell 路径；本方案恰恰绕开该系统依赖。
- 未新增 QtMultimediaWidgets 之外的任何依赖，未改 `requirements`。
