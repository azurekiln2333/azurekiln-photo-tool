# 共享媒体预览与视频解码

## 1. 适用范围

`media_thumbnail.py` 为目录比对与目录内去重提供统一预览。改动需同时验证独立页面和 `unified_gui.EmbeddedPage`，不能只调整调用页面的 splitter 初始大小来掩盖子控件最小宽度问题。

## 2. 接口

```python
load_thumbnail_image(path: Path, size: int) -> QImage | None
load_thumbnail_image_detail(path: Path, size: int, *, stop_event=None) -> tuple[QImage | None, str]
failure_message(code: str, lang: str = 'zh') -> str
ThumbnailLoader.request(path: Path) -> QPixmap
ThumbnailLoader.retry(path: Path | None = None) -> None
ThumbnailLoader.failure_reason(path: Path) -> str | None
ThumbnailLoader.clear() -> None
ThumbnailLoader.shutdown() -> None
PreviewPanel.set_slot(index, title, path, size_bytes=None, mtime_ns=None) -> None
PreviewPanel.set_language(lang: str) -> None
PreviewPanel.shutdown() -> None
```

`thumbnail_ready(str)` 和 `thumbnail_failed(str, str)` 在 GUI 线程回写；工作线程只产生 `QImage`。保留旧 `load_thumbnail_image` 和预览面板接口，避免影响现有表格调用。

## 3. 契约

- 两槽使用相同水平约束和伸展因子，长路径的 `minimumSizeHint` 不得随最长连续文件名增加；路径必须保留完整文本并允许换行。图片按当前框等比缩放。
- `QLabel.setWordWrap(True)` 不足以约束最小宽度。共享路径标签须限制宽度提示，图片框不能固定 256 像素宽；修在共享槽位。
- `_WrappingLabel` 使用 `QTextDocument` 的 `WrapAnywhere` 计算真实文本高度；
  只实现 `heightForWidth` 仍不足，矮侧栏的布局会压缩可收缩标签。槽位须按当前宽度
  保留完整文本高度；`PreviewPanel` 内部纵向 `QScrollArea` 承接超出内容，
  不将外层窗口撑高，也不在图片上重叠绘字。最小水平约束只取固定槽位数量/间距，
  与路径内容无关，A/B 采用相同伸展因子。
- 加载链：Windows Shell → 视频的 QtMultimedia 回退 → QImageReader → 占位图。正式回退使用 wheel 自带的 FFmpeg 后端，不依赖用户 PATH 的 ffmpeg.exe。
- `QMediaPlayer`、`QVideoSink`、`QTimer` 与局部 `QEventLoop` 在同一工作线程创建/清理；必须有超时与取消检查。不要在工作线程创建 `QPixmap`。
- 失败按路径/mtime 有限退避；缓存的 mtime 必须有 TTL。OneDrive 下载完成可能保留原 mtime，须同时提供可点击重试，不能仅依赖时间戳变化恢复。
- `clear` 改变请求代号并取消旧代任务；旧结果不得改变新代 pending/cache/界面。失败事件只作用于当前展示路径。
- 表格 `thumbnail_loader` 与 `PreviewPanel` 内部 loader 是**两个独立线程池**。页面 `_release_thumbnail_loader()` 必须分别调用 `self.thumbnail_loader.shutdown()` 和 `self.preview_panel.shutdown()`，统一独立/内嵌关闭与退出清理入口；只 clear 或只停表格池会把预览线程留在 `queue.get()` 等待（B2）。两者 shutdown 均应可重复调用；不在 GUI 线程同步等待解码或强杀线程。
- 测试先将 `APPDATA` 设为临时目录，`QT_QPA_PLATFORM=offscreen`；不使用真实云端相册。

## 4. 校验与错误矩阵

| 条件 | 结果 |
|---|---|
| 视频后端不可导入 | `video_unavailable`，占位并允许重试 |
| 到达解码超时 | `video_timeout`，不永久卡住线程 |
| 清缓存或关闭取消 | 丢弃旧代结果，停止可取消解码 |
| 路径错误或无法解码 | `decode_failed` 或明确原因，中英提示 |
| 请求代号过期 | 不更新当前行/槽位 |
| 自动重试次数用尽 | 不因重绘形成无限任务队列，保留手动重试 |

## 5. 正常、基线与异常示例

- 正常：本地 H.264/HEVC 在强制 Shell 不可用时仍取得有限尺寸首帧。
- 基线：短路径和图片沿用 Shell/图片读取器，未选择时显示占位。
- 异常：长连续文件名不能将某一侧拉宽；视频暂时不可读要显示原因，下载后允许重试。

## 6. 必需测试

`tests/test_media_thumbnail.py` 使用标准库 unittest，锁住等宽/最小宽度、图片缩放、失败与中英重试按钮、退避上限、mtime 过期、过期请求不污染新代、视频回退和超时。真实解码测试需验证 Shell 失败分支，不能仅测系统缓存成功。GUI 槽测试用实际按钮 `.click()` 并捕获槽异常；后台解码集成测试保留主事件循环，收尾后进程应正常退出 0。

关闭回归须实际向表格和详情 loader 各发一次请求，使两个池都启动；保存各自线程引用后走页面真实关闭/释放入口，以有界等待断言两个池均 stopped、全部捕获线程已退出。不能只检查 `_workers` 被清空（shutdown 会清列表），也不能放宽既有媒体生命周期测试去掩盖残留线程。

两页需用 Qt 鼠标事件拖 splitter，确认实际宽度改变，并复查独立/内嵌布局。发布包需验证 `QtMultimedia.pyd`、Qt6Multimedia.dll、多媒体插件及 av*/sw* DLL；详见 [打包约定](../python/packaging.md)。

布局回归应在实际约 1360×880 页面窄侧栏与正常字体下断言
`path_label.height() >= path_label.needed_height()`，且 image/path/meta 矩形不相交。
只在宽 820 的独立面板检查换行，会漏掉真实页面的纵向压缩。关闭后处理
`QEvent.DeferredDelete`，再断言异常列表为空；不能在析构前打印 PASS。

## 7. 错误与正确写法

```python
# 错：长文件名的最小宽度仍可能撑开卡片；图片框也无法缩小。
label.setWordWrap(True)
image.setFixedSize(256, 256)

# 对：共享槽位约束宽度提示，图片随可用框等比缩放；两槽同一套约束。
label = _WrappingLabel(path_text)
label.setWordWrap(True)
image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
```
