# pages worker 报告：目录比对页（compare）批量勾选与扫描记录

日期：2026-11-21
任务：`.trellis/tasks/11-21-compare-preview-records`
所有权（最终）：`dir_compare_gui.py`、`tests/test_compare_page_features.py`、本报告。
`folder_dedupe_gui.py` 在中期已移交 p8，我未修改该文件；`media_thumbnail.py`、
`scan_record_core.py`、`unified_gui.py`、构建/CI 文件均由其它 Pi/主会话负责。

未做任何 commit / push / 分支操作；未调用真实回收（测试中 `send2trash` 被 mock）。

---

## 1. 交付内容

### 1.1 批量勾选（R2）

- `CompareTableModel.apply_check_mode(mode)`：`all` / `none` / `invert` 一次遍历，
  只改「合法待回收」行，所有变更合并成**一次** `dataChanged`（列 `COL_CHECK`），
  返回实际变更行数。
- 新增模型级 `CompareTableModel._checkable(row)`：`row.is_checkable()` 之外再叠加页面
  `_scan_cancelled` / `_scan_stale`。`data(CheckStateRole)`、`setData`、`flags`、
  `apply_check_mode` 全部走它，因此取消/失效结果整体禁勾，不是只靠按钮禁用。
- 工具栏新增独立一行（`row_tools`）：`全选 / 全不选 / 反选` + 右侧 `导出记录 / 导入记录`，
  与原有 scope/线程/逐字节复选行分离，正常窗口宽度下不挤压溢出。
- `Ctrl+A`：`QShortcut(QKeySequence.StandardKey.SelectAll)` 绑在表格上，走同一
  `select_all_checkable()`，不会把异常/碰撞/已处理行当可回收。
- 忙态、取消、失效时点这些按钮：不改变勾选并给 InfoBar 提示（不静默忽略）。

### 1.2 扫描记录导入 / 导出（R3–R4）

- 扫描时保存快照：`_scan_snapshot = {root_a, root_b, scope, keep_strategy, threads}`，
  根用 `os.path.abspath()` 规范化（用户可输入相对路径，记录核心要求绝对根）。
- `_scan_result` 保存**完整 `ScanResult`**；导出 `_build_scan_record()` 只用这两份快照，
  绝不读当前目录控件 → 扫描后改根不会导出错误数据。
- 行状态：duplicate 行导出 `{checked, status}`，键为绝对目标路径。
- 导出/导入 I/O 全部走 `RecordSaveWorker` / `RecordLoadWorker` + `QThread`
  （`_start_record_op`），复用既有忙/关闭协议。
- 导入：`load_record(..., expected_mode="compare")` 完整解析校验成功后才
  `_apply_imported_record()` 替换显示；任何 `ValueError/OSError` 只发 InfoBar 错误，
  **不动现有表格**（坏记录不破坏已有结果）。
- 导入恢复：根目录控件、scope、行勾选/状态、已回收/跳过/失败计数
  （按行状态真实累加，不再一律归零）、`_record_imported=True`。
- 导入时先写入 `_scan_snapshot` 再 `_build_rows()`，异常行分栏使用**记录自己的根**，
  不受导入前界面上残留根影响。
- 取消/失效：`_scan_cancelled` / `_scan_stale` 随记录恢复，整体禁勾 + 禁回收；
  导出时 `stale=bool(self._scan_stale)` 正常往返（记录核心已支持 stale 字段）。
- 回收：`bytes_required = bool(byte_verify_check) or self._record_imported`，
  历史记录一律强制 `byte_verify=True`；仍全部经 `recycle_duplicate → revalidate_pair`，
  没有绕过核心直接 `send2trash` 的路径。
- 真实重扫成功：`_apply_scan_result` 清 `_record_imported` / `_imported_record`。

### 1.3 生命周期（本轮最终修复）

`_is_busy()` 与 `_workers_running()` 原来对 scan/recycle 用
`thread is not None and thread.isRunning()`。`QThread.isRunning()` 变 False 到
`finished` 槽清理之间有一个窗口：此时 `_is_busy()` 已返回 False（测试/程序误以为空闲），
但按钮仍是禁用状态 —— 正是全量 discover 偶发 2 项失败的根因
（`export_to` 点击后文件不存在、按钮点击未改变勾选）。

最终修复：**scan / recycle / record 三个线程只要引用非 None 就算忙**，
由 `_scan_thread_finished` / `_recycle_thread_finished` / `_record_thread_finished`
清理后再更新按钮：

```python
return (
    self.is_scanning
    or self.is_recycling
    or self._scan_thread is not None
    or self._recycle_thread is not None
    or self._record_thread is not None
    or self._drain_timer.isActive()
    or bool(self._process_update_queue)
)
```

`_workers_running()` 同源（引用非 None），保证关闭不会销毁仍在收尾的 QThread；
`closeEvent` 先 `_pending_close=True` + `_shutdown_workers()` 并 `ignore()`，
由 `_maybe_finish_close()` 在 finished/drain 排空后再真正 `close()`。

### 1.4 文案（R6）

`TRANSLATIONS` zh/en 成对新增：`btn_select_all`、`btn_select_none`、`btn_select_invert`、
`btn_export_record`、`btn_import_record`、`record_*`（导出/导入标题、过滤器、成功/失败、
取消提示、忙提示、无结果、历史标记、读写状态）、`scan_stale`、`cannot_start_stale`；
全部在 `_apply_language()` 中刷新。

---

## 2. 验证证据（本人执行）

功能回归（17 项，全部通过，连续 3 次无 flaky）：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.venv/Scripts/python.exe -m unittest tests.test_compare_page_features -v
# Ran 17 tests ... OK   （连跑 3 次均 OK，~1.7–1.9s）
```

覆盖点：

- `SelectionTests.test_select_buttons_only_touch_checkable_rows`（真实 `click()` 三键，
  碰撞/异常/已处理行保持未勾选）
- `SelectionTests.test_blocked_when_cancelled_or_stale`
- `SelectionTests.test_model_apply_check_mode_returns_count`
- `SelectionTests.test_busy_until_thread_reference_cleared` — 本次忙态窗口回归：
  构造「线程已停止但 finished 未清理」状态，断言 `_is_busy()`/`_workers_running()` 为真、
  点按钮不改勾选并提示
- `RecordRoundTripTests.test_round_trip_keeps_groups_and_row_states`（真实扫描按钮 →
  导出 → 清空 → 导入，分组/指纹/勾选恢复）
- `RecordRoundTripTests.test_relative_root_is_absolutized_in_snapshot`
- `RecordRoundTripTests.test_export_uses_scan_time_snapshot`
- `RecordRoundTripTests.test_export_disabled_before_scan`
- `RecordRoundTripTests.test_bad_record_does_not_destroy_current_results`
- `RecordRoundTripTests.test_wrong_mode_record_rejected`（json 改 `mode`，拒绝且保留原表）
- `ImportedRecycleGuardTests.test_import_forces_byte_verify_and_recycles`
  （导入 + 取消勾选“逐字节复核”后仍 `byte_verify=True`，send2trash 为 mock）
- `ImportedRecycleGuardTests.test_changed_file_is_skipped`
  （改内容保 size/mtime → 跳过、原文件仍在、该路径未进回收站）
- `ImportedRecycleGuardTests.test_import_restores_done_counts`
  （已回收/已跳过行恢复 `_recycled_count=1` / `_skipped_count=1`，不可再勾选）
- `ImportedRecycleGuardTests.test_cancelled_record_not_recyclable`
  （`dataclasses.replace(result, cancelled=True)` 往返后仍取消、禁勾、禁回收）
- `ImportedRecycleGuardTests.test_stale_record_round_trip_and_rejected`
  （stale 导出成功、导入仍 stale、禁勾、禁回收）
- `ImportedRecycleGuardTests.test_issue_columns_use_record_root`
- `RecordCoreGuardTests.test_out_of_root_rejected`（越界 row_states 核心拒绝）

隔离：`APPDATA` 指向临时目录（`os.environ["APPDATA"]`），样例文件全在
`tempfile.TemporaryDirectory()`，`send2trash` 全程 mock，未触碰真实相册/回收站。
`tearDown` 会 `sendPostedEvents(DeferredDelete)` 后断言 `_SLOT_ERRORS` 为空（无过滤）。

全量（主会话执行，权威结果）：

```powershell
.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -q
# 182 tests OK
```

（我先前用 `-t .` 报 `Start directory is not importable: 'tests'`，是 discover 参数问题，
不是代码问题；按主会话命令为准，未为此改任何代码。）

语法检查：`ast.parse(dir_compare_gui.py)` 通过。

---

## 3. 未覆盖 / 边界

- 未做真实 `send2trash` 回收端到端（按任务要求只使用 mock），因此“回收站实际落点”
  由核心 `duplicate_scan_core` 既有测试与人工验收负责。
- 未在真实 OneDrive 云占位文件上验证导入/预览（任务明确不碰真实媒体）。
- 导入记录的路径合法性、角色约束、重复/相交拒绝由 `scan_record_core` 负责，
  本页只保证“解析成功才应用”；页面侧仅补了一条越界用例做联动检查。
- 记录文件很大时（接近 64 MB 上限）的界面响应只做了“后台线程 + 忙态”验证，
  未做极限体积压测。
- 内嵌（`unified_gui`）关闭轮询由主会话新增的 `tests/test_unified_close.py` 覆盖；
  本页只保证 `_is_busy` / `_workers_running` 在记录线程生命周期内始终为真。

## 4. 给发布协调的结论

目录比对页（`dir_compare_gui.py`）在本报告范围内**可验收**：批量勾选、记录导入导出/
快照/强制字节复核/取消失效保护、以及 scan/recycle/record 引用忙态均已实现并有
17 项真实按钮回归；全量 182 项由主会话确认通过。`folder_dedupe_gui.py` 的镜像实现
与测试归 p8，本报告不为其背书。
