# Pi preview 报告（11-21 目录比对预览/视频回退）

范围所有权：仅 `media_thumbnail.py`、`tests/test_media_thumbnail.py`、本目录 research。
未修改 dir_compare_gui.py / folder_dedupe_gui.py / scan_record_core.py / spec / 发布文件。

## 1. R1 布局：A/B 等宽 + 任意字符换行（已完成，含视觉 QA 二次修复）

### 根因（实测，非推测）

- `QLabel(wordWrap=True)` 只在词边界断行；`minimumSizeHint()` 仍为最长连续字符宽度
  （长连续文件名实测 1092 px），把预览槽和 splitter 一起撑开。
- **首轮仅 override `minimumSizeHint` 不足**：视觉 QA（`root_layout_probe.py --capture`，
  真实 msyh.ttc 字体）显示长文件名只 2 行、其余横向截断。已按 QA 要求做实质修复。

### 修复

- 新增 `_WrappingLabel`（继承 Fluent `BodyLabel`）：用 `QTextDocument` +
  `QTextOption.WrapMode.WrapAnywhere` 自行排版；`hasHeightForWidth()`/`heightForWidth()`
  随宽度返回真实高度；`minimumSizeHint` 固定 48×行高，不再随路径长度增长。
- 字体/调色板同步：`setFont/setFontFamily/setPixelSize/setPointSize` 同步到文档；
  绘制上下文使用控件自身 palette + `foregroundRole()` 颜色，QQSS 颜色仍生效。
- 选择/复制是**真实现**而非只设 flag：`paintEvent` 用
  `QAbstractTextDocumentLayout.PaintContext.selections` 画高亮；支持鼠标拖动、
  双击选词、Shift 扩选、Ctrl+A 全选、Ctrl+C/`copy()`，`selectedText()` 归一化换行。
  `textInteractionFlags = TextSelectableByMouse | TextSelectableByKeyboard`，I-beam 光标。
- 长路径与 meta（大小·修改时间）都改为 `_WrappingLabel` 并带 tooltip 全文。
- 图片框改为宽度自适应、高度=宽度×0.72（上下限约束），`resizeEvent` 中重新按
  `KeepAspectRatio` 缩放源 pixmap；占位图统一 96–256 尺寸后再等比缩放。
- 预览 loader 解码尺寸提到 `max(size, 384)`，宽卡片时放大不发虚（不改公共 API）。

### 实测数据

- 真实 msyh.ttc 渲染截图（`research/wrap-probe.py --capture`）：两槽均 404 px，
  路径完整 5 行、无截断，meta 换行，失败提示+重试正常显示。
- `root_layout_probe.py`（主会话）：两页 slots 207/207，panel_minimum 252（与路径无关），
  splitter 拖动 450→550 生效。
- 高度断言：`label.height() >= label.needed_height()`，且行数 > 2。

## 2. R5 视频首帧回退（已完成）

- 管线顺序：Windows Shell → QtMultimedia（`QMediaPlayer`+`QVideoSink`，自带 FFmpeg 后端）
  → `QImageReader` → 占位图。视频判定用 `_kind_for_path`。
- 解码在工作线程内自建 `QEventLoop`/`QTimer`；主线程事件循环不受影响。
  `QImage` 跨线程回主线程后才 `QPixmap.fromImage`（Qt 线程约束）。
- 超时 6000 ms；全局 `_VIDEO_LOCK` 串行化解码器，避免多线程互相干扰；
  `stop_event` 每 100 ms 轮询，`clear()/shutdown()` 可取消在途解码。
- 失败原因码：`decode_failed` / `video_unavailable` / `video_timeout` / `cancelled` /
  `invalid_size`，`FAILURE_MESSAGES` 中英双语。
- **失败不再永久缓存**：`_failures` 记录 `retries/retry_at/reason`，退避 `(1s, 2s, 5s)`
  有限重试；`_mtime_cache` 改为 2 s TTL，云端文件下载完成（mtime 变化）后自然重载；
  `retry(path)` 手动重置。`thumbnail_failed(path, reason)` 新增信号。
- PreviewPanel **实际订阅** `thumbnail_failed`：显示中英原因 + 可点击「重试/Retry」
  按钮，并安排有限次自动重试（每路径只挂一个定时器，切走后丢弃）。
  语言切换时用 `_failure_codes` 重渲染中英文案。
- 公共 API 兼容：`PreviewPanel`、`ThumbnailLoader.request/clear/shutdown`、
  `load_thumbnail_image()`（保留签名，失败返回 None）均未破坏；新增
  `load_thumbnail_image_detail()`、`ThumbnailLoader.retry/failure_reason/next_retry_delay`。

## 3. 打包（已交付 pB）

`research/video-packaging-contract.md`：无需外部 ffmpeg.exe，只需 hiddenimports
`PyQt6.QtMultimedia`(+Widgets/QtNetwork)、Qt6 FFmpeg DLL（avcodec/avformat/avutil/
swresample/swscale 61 系列）与 `plugins/multimedia/ffmpegmediaplugin.dll`；
并给出 verify_bundle 应新增的断言与运行时自检方法。

## 4. 测试

```
$env:QT_QPA_PLATFORM = "offscreen"
.venv/Scripts/python.exe -m unittest tests.test_media_thumbnail -v        # 26 passed
.venv/Scripts/python.exe -m unittest tests.test_media_thumbnail tests.test_duplicate_scan_core tests.test_scan_record_core
                                                                          # 145 passed, exit 0
```

覆盖：槽等宽、长路径最小宽度不膨胀、**路径完整换行且高度覆盖文本**（含缩窄后复验）、
**选择/复制**、字体切换后仍换行、图片等比缩放、失败有限退避、手动重试、mtime 变化重载、
shutdown 取消在途解码并退出线程、视频管线顺序/原因码/取消、面板失败提示中英 + 真实
按钮点击、强制 Shell=None 的本地 H.264/HEVC 解码（ffmpeg 生成样片，缺失则 skip）。

## 5. 未覆盖边界（不得夸大）

- 真实 OneDrive 云端占位文件首次水化：**未**端到端验证（只用本地样片强制 Shell=None）。
- 真实 MSIX/打包产物内的 QtMultimedia 后端未在本 worker 内验证，由 release worker
  与 CI 的 `verify_bundle.py` 断言；未落包即 R5 不通过。
- 视频解码失败的自动重试在 GUI 中依赖 `QTimer`，测试中直接验证调度逻辑，未等待真实 6s 超时。
- `QTextDocument` 选择不支持双向光标拖拽起始点在文本末尾后的扩展（从左向右拖拽正常）。
- 表格缩略图（`ThumbnailLoader`）仍走同一回退，但未对上千行表格做性能回归。
