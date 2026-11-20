Active task: .trellis/tasks/11-21-compare-preview-records

你是实际 Pi CLI 的 trellis-implement worker。现在执行任务，不再停在方案。先读 implement.jsonl 所列 spec，然后 prd.md/design.md/implement.md 与 trellis-before-dev。用户已经明确授权实施和最终发版。

所有权：仅 media_thumbnail.py、tests/test_media_thumbnail.py、任务 research/pi-preview-report.md。你不是仓库唯一工作者，其他三个 Pi 正并行；不要修改/恢复他人文件，不 commit/push/merge/stash/reset/checkout，不停止其他进程。

完成：共享预览 A/B 始终各半等宽；任意字符路径换行且 minimumSizeHint 不被路径撑开；图片可随卡片宽度等比缩放；保留公共 PreviewPanel/ThumbnailLoader API。两个页面 splitter 由 pages worker 修，协调不要越界。

视频现仅 Windows Shell → QImageReader；增加独立视频首帧回退（QtMultimedia 后端优先，已有 Qt6FFmpeg 组件，必要时外部 FFmpeg），有超时、不阻塞 GUI、可以取消/关闭。解决负缓存永久失败和 mtime 缓存导致文件下载完不重试；有限退避、适当错误/重试反馈。真实 OneDrive 不碰，临时文件与 APPDATA 隔离；生成 H264/HEVC 或用 sample 本地视频强制 Shell 失败验证。主机 ffmpeg 在 PATH，但发版机器不应强依赖 PATH。

请尽快把选定解码方案与所需 PyInstaller hiddenimports/binaries 写到 research/video-packaging-contract.md，release worker 将读取它。若依赖未能落包就不能声称发布修复通过。注释中文，新 UI 中英。使用 .venv/Scripts/python.exe，stdlib unittest 回归。完成后报告精确测试命令/结果及未覆盖边界。
