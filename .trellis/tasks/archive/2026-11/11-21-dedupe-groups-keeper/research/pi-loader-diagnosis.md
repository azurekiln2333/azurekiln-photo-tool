# Thumbnail loader 生命周期窄诊断

结论：**已定位为预览池未关闭，不是伪 MP4 解码挂起；p8 已补修复。**

- 首次有效的隔离 folder GUI suite 运行结束后，测试进程报告 `POST_SUITE_THUMBNAIL_THREADS=27`；采样到的线程均停在 `media_thumbnail.py:819` 的 `ThumbnailLoader._worker_loop -> queue.get()` / `Condition.wait()`，没有线程栈落在 `_extract_video_frame_qtmultimedia`、FFmpeg 或真实 MP4 解码路径。
- 因此残留线程是空闲 daemon worker 等待队列哨兵，不是视频解码阻塞。残留数量与每个页面同时拥有两个独立池一致：`folder_dedupe_gui.MainWindow.thumbnail_loader`，以及 `PreviewPanel._loader`（`PreviewPanel` 自己创建 `ThumbnailLoader(max_workers=2)`）。
- 根因是 folder 页面旧的 `_release_thumbnail_loader()` 只调用页面级 `self.thumbnail_loader.shutdown()`，没有调用独立的 `self.preview_panel.shutdown()`；`dir_compare_gui` 已有双池 shutdown，对照证明了生命周期差异。
- p8 已补充 `self.preview_panel.shutdown()`；当前工作区方法已同时关闭两个 loader。该修复不涉及媒体测试放宽，也不改变 MP4 解码逻辑。

诊断运行另有两个无关 GUI 断言失败（内嵌语言选择器、worker verify 断言），不作为本结论依据。后续一次“插桩重跑”命令因 PowerShell 未将 here-string 通过管道传给 `python -`，误进入 Python 交互式 `_pyrepl` 并产生 WinError 123 日志，已由 root 终止；该日志不是产品挂起证据，未据此推断任何解码问题，也未再次启动诊断进程。

核心/记录此前定向 **128 tests OK** 保持不变。本诊断未修改源码或测试，仅写入本报告。
