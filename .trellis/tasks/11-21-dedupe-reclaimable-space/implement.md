# 最小实施与验证计划

- GUI Pi w55:p8 仅负责 folder_dedupe_gui.py：新增独立可换行统计标签，复用 _format_size 和行资格判定，接入 _refresh_summary、语言刷新及结果重置；禁止新文件 I/O 和核心变更。
- 测试文件 tests/test_folder_dedupe_features.py：覆盖混合角色/状态、勾选和反选、隐藏分类、keeper 重选、失效/取消、真实扫描与导入回收及语言刷新。约定可测控件 space_summary；计算助手 _reclaimable_sizes() 返回 (total_bytes, selected_bytes)。原分派 Pi w55:pA 准备较久未落地，主会话已中断并接收其停笔确认后接管，补入三个集中回归。
- 审查 Pi w55:p4 只读检查计算口径和安全边界；验收 Pi w55:pB 只读独立检查布局及测试。各 Pi 共用工作区，禁止撤销彼此修改、提交、push、tag 或切换模型。
- 主会话维护任务和规范，审核 diff；定向回归、全量 unittest、compileall 和 git diff --check，通过后提交并记录任务结果。
- 统计以整个源模型为准，复用 row.is_checkable() 并守卫有效扫描/取消/失效，排除 entry/keeper 缺失行；布局沿用底部卡片风格，避免水平挤压。
- 回收异步测试等待线程和 UI drain 全部收尾；只用临时目录与 mock 回收。
- 本轮不覆盖 v1.2.4 tag，不自动发新版。
