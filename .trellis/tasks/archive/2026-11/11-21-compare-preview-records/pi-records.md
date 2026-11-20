Active task: .trellis/tasks/11-21-compare-preview-records

你是实际 Pi CLI 的 trellis-implement worker。先读 implement.jsonl 列出的 spec，再 prd.md/design.md/implement.md 与 trellis-before-dev，然后立即实施。

所有权仅 scan_record_core.py、tests/test_scan_record_core.py、任务 research/pi-records-report.md。你不是唯一工作者，其他三个 Pi 同工作区并行，不覆盖/恢复他人改动，不提交推送或操作分支。

按 design.md 已冻结 ScanRecord/save_record/load_record API 实现版本化 UTF-8 JSON，保留完整 ScanResult 快照/根/选项/勾选和处理状态。标准库，同目录暂存+原子替换，严格类型/版本/模式/路径根归属验证，防路径穿越/链接越界、嵌套根、重复target、keeper与target集合相交。碰撞和异常路径也验证。路径不存在允许历史展示，但绝不触发媒体读取/回收。row_states key 是绝对文件路径，values={'checked':bool,'status':str}，status允许现有页面状态；ScanRecord stale=False。合理输入大小/数量上限。无效记录必须在替换显示前完整拒绝。

尽快提供可导入 API 给 pages worker，务必遵守冻结接口，不自改名称。用 .venv/Scripts/python.exe 运行 stdlib unittest，涵盖往返及坏输入安全，补记录导入后文件修改/删除仍不能回收的回归（mock send2trash，临时目录）。不写真相册。完成写报告。
