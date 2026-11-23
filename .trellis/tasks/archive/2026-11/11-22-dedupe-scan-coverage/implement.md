# 实施计划

1. Pi w55:p4 所有权 duplicate_scan_core.py 与 tests/test_duplicate_scan_core.py：实现ScanCoverage、collect_files单次遍历计数与节流快照、internal可选回调和result；覆盖普通/空/过滤/链接/读取失败/取消/Hash候选/回调隔离。其他核心逻辑保持。
2. Pi w55:p8 所有权 folder_dedupe_gui.py：按design接口并行接入worker object信号、醒目主/明细控件和刷新，历史未知/失败/取消不得冒充完整；无文件IO；zh/en与独立内嵌。
3. Pi w55:pA 只读核查 tests/test_scan_record_core.py + scan_record_core.py 旧格式兼容，必要回归写入 tests/test_scan_record_core.py（唯一写权限）；不改记录实现，不升级schema。跑记录定向。
4. Pi w55:pB 所有权 tests/test_folder_dedupe_features.py：3-4个集中实际worker/UI回归覆盖实时统计、混合文件、取消/失败/无候选、历史未知及语言；界面到位后四组合布局与截图验收，并只读交叉审查。
5. 主会话负责task/spec维护、接口协调、差异与全量验证、收尾提交并按已有授权合并推送。所有Pi共用工作区，不撤销别人改动、不切分支/模型、不提交推送。

实施交接：Pi w55:p8 已落地翻译、worker信号与统计卡片，但批量编辑连续失败；主会话通过herdr中断并确认其done后接管 folder_dedupe_gui.py，补齐生命周期刷新与信号连接。卡片放在splitter上方全宽显示，换行标签保留height-for-width且不施加横向最小宽度。其它Pi继续按原所有权完成核心、记录、GUI测试及独立检查。

验证：定向core/record/GUI unittest -> 全量unittest(隔离APPDATA/LOCALAPPDATA/offscreen) -> compileall -> git diff --check -> 四组合布局截图。保持原Hash/逐字节/回收安全测试，必要修复在各自所有权内进行。

## 用户追加交互修复派工（2026-11-22）

四个现有herdr Pi已重新派工，保持原模型：

1. w55:p8接回folder_dedupe_gui.py唯一写权限：keeper明确行级入口、当前分类独立回收、按钮/确认/容量口径统一，接入p4的configure_result_table_scrolling。
2. w55:p4所有权dedupe_table_scroll.py、tests/test_dedupe_table_scroll.py和dir_compare_gui.py仅滚动接入；查实际Fluent实现并以真实wheel事件验证。
3. w55:pB所有权tests/test_folder_dedupe_features.py：真实鼠标重选keeper、三分类独立回收、原记录和扫描覆盖回归、布局验证。
4. w55:pA只读trellis-check审查全部差异，等实现完成给最终阻塞结论。
5. 主会话仅协调和维护task/spec/发布版本，不与Pi同时编辑其产品文件；实现后跑全量并按已有授权提交、归档、合并main、push及新tag触发CI。
