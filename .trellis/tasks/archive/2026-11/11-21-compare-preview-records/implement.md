# 实施与验收计划

- [x] 只读复现与边界确认；用户授权快速实施及 push/tag/CI。
- [x] PRD、设计、工作包与 JSONL 上下文收敛。
- [x] task.py start；通过 herdr 将四个工作包派给同工作区 Pi，冻结记录 API。
- [x] 各工作包完成对应回归与语法检查，主会话整合发布包视频依赖。
- [x] 现有 duplicate_scan_core 测试与新增记录/预览/页面测试；独立/内嵌中英/长路径、保存导入、变更跳过回归。
- [x] 独立 trellis-check 全范围审阅并修复，更新 spec 与 README；首次 PASS 后补 CI 无 ExifTool、无 ffmpeg 及 C/D 跨盘临时目录环境回归。
- [x] 首次 v1.2.1 已提交推送；保留原 tag，修复 CI 测试隔离后发布 v1.2.2，分支/标签 Actions 成功且三类资产齐全，ZIP与包内EXE已实际下载验哈希。
- [x] 记录证据、归档任务和开发日志，推送收尾提交（由本次收尾连续执行；最终Git与日志提交为核验依据）。

验证使用 `.venv/Scripts/python.exe`、临时目录、隔离 APPDATA；不读写真 OneDrive 媒体，不执行真实用户文件回收。已有 stdlib unittest 可扩展，无新框架。GUI 检查捕获 Qt 槽异常并清理线程后正常退出。发布前 git diff --check 和 get_version --tag 必须通过；不得用 compileall 代称类型检查。
