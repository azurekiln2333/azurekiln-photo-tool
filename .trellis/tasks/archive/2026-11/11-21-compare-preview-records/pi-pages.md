Active task: .trellis/tasks/11-21-compare-preview-records

你是实际 Pi CLI 的 trellis-implement worker。先读 implement.jsonl 对应 spec，再 prd/design/implement 与 trellis-before-dev，然后实施。

当前所有权仅 dir_compare_gui.py、tests/test_compare_page_features.py、任务 research/pi-pages-report.md。目录内去重页已转 p8，禁止交叉改动。另三个 Pi 同工作区，不撤销他人改动，不commit/push/分支操作。

目录比对页修复合理可拖splitter（media_thumbnail.py共享根因另worker负责）、全选/全不选/反选，仅合法待回收行，可加Ctrl+A；保留/异常/碰撞/已处理/取消/失效行禁勾。新增JSON导入导出入口，scan_record_core.py API严格见design.md，由records worker实现。保存完整ScanResult和扫描时根/选项快照，不能导出后改根的错误数据。I/O后台执行，沿用忙和异步关闭协议；坏记录不破坏已有结果。导入恢复根/选项/勾选/状态，_record_imported=True，RecycleWorker强制byte_verify=True，且cancelled/stale禁止回收。重扫成功清除import标记。

中英完整，正常宽度工具栏不溢出。通过实际按钮click、事件循环/Qt槽异常捕获、隔离APPDATA、临时样例做回归，不操作真实用户回收站。核心模块没就绪按契约先编码，完成后联调。完成写准确报告。
