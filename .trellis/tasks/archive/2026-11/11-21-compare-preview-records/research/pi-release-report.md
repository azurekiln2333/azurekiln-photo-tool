# 发布集成报告（Pi release worker）

范围（仅本 worker 所有权）：`AzureKilnPhotoTool_onefile.spec`、`.github/workflows/build.yml`、
`scripts/ci/verify_bundle.py`、`README.md`、`docs/README.en.md`、`docs/README.zh-TW.md`、
本任务 `research/` 下脚本。未提交、未推送、未打标签、未创建 Release。

## 视频首帧后端事实（实测）

- `media_thumbnail.py` 使用 `PyQt6.QtMultimedia` 的 `QMediaPlayer` + `QVideoSink` 在工作线程内自建
  `QEventLoop` 解帧，带 6s 超时与串行锁；**不依赖 PATH 里的 ffmpeg**，也不需要下载外部 FFmpeg。
- `.venv`（PyQt6 6.11.0 / Qt 6.11.0）自带的插件与 DLL：
  `PyQt6/Qt6/plugins/multimedia/ffmpegmediaplugin.dll`、
  `PyQt6/Qt6/bin/{Qt6Multimedia.dll, avcodec-61.dll, avformat-61.dll, avutil-59.dll, swresample-5.dll, swscale-8.dll}`。
- PyInstaller 的 `hook-PyQt6.QtMultimedia`（`_modules_info` 里 `plugins=["multimedia", ...]`）会自动收集这些文件；
  实测旧 dist 产物（11-15 构建）已含上述插件与 av*/sw* DLL。
- 真实源码探针（`research/integration_media_probe.py`，强制 Shell 失败）对
  `sample/HarmonyOS2/.../IMG_20260523_030803.mp4` 取到首帧 360x480，退出码 0。

## 本轮发布侧改动

1. `AzureKilnPhotoTool_onefile.spec`
   - hiddenimports 增加 `PyQt6.QtMultimedia`、`scan_record_core`（页面/核心由 importlib 动态导入）。
   - upx_exclude 增加 `Qt6Multimedia.dll` 与 `ffmpegmediaplugin.dll`、`av*.dll`、`sw*` 系列（避免压缩破坏 FFmpeg 后端）。
   - **移除 `excludes` 中的 `PyQt6.QtNetwork`**：PyInstaller warn 文件显示
     `excluded module named PyQt6.QtNetwork - imported by PyQt6.QtMultimedia`，排除它会使视频回退在
     打包环境下失效。
2. `scripts/ci/verify_bundle.py`
   - 新增 Qt 多媒体后端断言：`QtMultimedia.pyd`（CArchive 里的原生扩展）、`Qt6Multimedia.dll`、
     `ffmpegmediaplugin.dll`、`avcodec-*`、`avformat-*`、`avutil-*`、`swresample-*`、`swscale-*`。
   - 新增 `Qt6Network.dll` 存在断言 + spec `excludes=[...]` 文本解析，防止再次把 `PyQt6.QtNetwork` 排除。
   - 新增 PYZ 模块断言：`media_thumbnail`、`scan_record_core`、`dir_compare_gui`、`folder_dedupe_gui`。
3. `.github/workflows/build.yml`
   - 新增门禁 `Run unit tests (offscreen, isolated APPDATA)`：`QT_QPA_PLATFORM=offscreen`，
     `APPDATA`/`LOCALAPPDATA` 指向 `$RUNNER_TEMP` 临时目录，`python -B -m unittest discover -s tests -v`；
     仅用标准库，未引入新测试框架或依赖，失败即中止构建。
4. README 三语同步真实行为：等宽可拖预览、全选/全不选/反选（仅合法副本）、
   视频首帧 Qt FFmpeg 回退 + 超时 + 有限重试与「重试预览」、带版本 JSON 记录导出/导入与
   导入后强制逐字节复核、CI 测试门禁与增强后的产物自检、新增 `scan_record_core.py` 与 `tests/` 说明。

## 最终当前源码完整打包（本地，2026-11-21）

```powershell
.venv/Scripts/python.exe -m PyInstaller --noconfirm AzureKilnPhotoTool_onefile.spec   # 未加 --clean
.venv/Scripts/python.exe scripts/ci/verify_bundle.py dist/AzureKilnPhotoTool.exe
```

增量重建说明：v1.2.1 后 `scan_record_core.py:791` 的 EOF 多余空行由 p4 移除（仅格式，不改语义）；
v1.2.2 将 `APP_VERSION` 改为 1.2.2（唯一行），并为 CI unit tests step 增加 `timeout-minutes: 5`
（不移动/跳过门禁）。最终包完全来自最终源码。重建前 `git diff --check` exit 0，
`tests.test_scan_record_core` 38 tests OK。

> v1.2.2 重建后的交付值见下一节“v1.2.2 最终重建”。

| 项目 | 值 |
| --- | --- |
| PyInstaller 退出码 | `0`（增量重建，耗时 60.2s；未加 `--clean`） |
| verify_bundle 退出码 | `0` |
| 产物 | `dist/AzureKilnPhotoTool.exe` |
| 大小 | 81,410,674 字节（77.64 MB） |
| 修改时间 | 2026-11-21T03:48:25+08:00 |
| SHA-256 | `ef562c420eafefd8931d1089e6d60d2b1ded2b61adec0091e03b6602cadb6654` |
| CArchive 条目 | 927（PYZ 模块 484、`exiftool_files/` 508、多媒体相关 41） |

verify 输出：`bundle check passed: pillow_heif, send2trash, ExifTool, QtMultimedia FFmpeg backend present`
（新增的 `QtMultimedia.pyd`/`Qt6Network.dll`/`ffmpegmediaplugin.dll`/`av*`/`sw*` 与 PYZ
`media_thumbnail`/`scan_record_core`/`dir_compare_gui`/`folder_dedupe_gui` 断言全部包含在内，
原有 ExifTool/HEIC/send2trash 检查保留）。

关键条目实测存在：`PyQt6/QtMultimedia.pyd`、`PyQt6/QtNetwork.pyd`、`PyQt6/Qt6/bin/Qt6Multimedia.dll`、
`PyQt6/Qt6/bin/Qt6Network.dll`、`PyQt6/Qt6/plugins/multimedia/ffmpegmediaplugin.dll`、
`PyQt6/Qt6/bin/avcodec-61.dll`；`PyQt6/Qt6/bin/avformat-61.dll`/`avutil-59.dll`/`swresample-5.dll`/`swscale-8.dll` 同批带入。
构建 warn 文件中已不再出现 `excluded module named PyQt6.QtNetwork`。

## v1.2.2 最终重建（2026-11-21，交付值）

```powershell
.venv/Scripts/python.exe -m PyInstaller --noconfirm AzureKilnPhotoTool_onefile.spec
.venv/Scripts/python.exe scripts/ci/verify_bundle.py dist/AzureKilnPhotoTool.exe
```

| 项目 | 值 |
| --- | --- |
| APP_VERSION | `1.2.2`（`scripts/ci/get_version.py --tag v1.2.2` exit 0） |
| PyInstaller 退出码 | **0**（63.0s，未加 `--clean`） |
| verify_bundle 退出码 | **0** |
| 产物 | `dist/AzureKilnPhotoTool.exe` |
| 大小 | **81,412,521** 字节（77.64 MB） |
| 修改时间 | **2026-11-21T03:58:45+08:00** |
| SHA-256 | **`d52171d56c36264215bd862126851ee26c1d8fcf4e16ea756702cd078b830250`** |
| CArchive | 927 条目 / PYZ 484 / exiftool_files 508 / 多媒体相关 41 |

verify 输出：`bundle check passed: pillow_heif, send2trash, ExifTool, QtMultimedia FFmpeg backend present`。

## 已验证

- 记录复核：`.venv` 全量单测在复核时为 145 tests OK（离屏 + 隔离 APPDATA）；主会话随后全量 182 tests OK。
- `scripts/ci/verify_bundle.py dist/AzureKilnPhotoTool.exe` → 通过（**v1.2.2 最终构建产物**）。
- `research/integration_media_probe.py` → `media probe passed`（强制 Shell 失败后走 Qt 回退）。
- `research/root_records_probe.py` / `research/collision_safety_probe.py` → 均 exit 0；详见
  `research/pi-review-records.md`（结论：记录核心无真实 bug，未改代码）。
- `compileall`（spec 与 `verify_bundle.py`）、`git diff --check`、workflow 步骤结构自检 → 通过。

## 未验证 / 边界

- 未运行 exe 本体做端到端视频预览确认（未改业务入口，也不允许新增任意脚本执行入口）；
  打包侧只做了静态包自检 + 源码态强制 Shell 失败的 Qt 回退实测。
- 未提交 / 未推送 / 未打 `v1.2.1` / 未触发远端 Actions；CI 测试门禁仅在本地等价环境（.venv）验证过。
- 未在真实 OneDrive 仅联机样例上验证首帧失败/重试的端到端表现。
