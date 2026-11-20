# CI 回归：回收线程结束早于 UI drain 完成

任务：`.trellis/tasks/11-21-dedupe-groups-keeper`
日期：2026-11-21
所有权范围：仅 `tests/test_folder_dedupe_features.py`；没有修改产品源码或其它测试文件。
当前状态：测试源码已按 root 要求冻结。后续全量由 root 执行，CI-like 由 pB 执行。

## 现象与根因

CI branch run `44834696733` 中，`test_imported_record_then_changed_files_skipped_without_send2trash` 失败：
`modified_target` 行仍是 `status_pending`，而预期它已由回收前逐字节复核标记为 `status_skipped|...`。同一 commit `cdf4176` 的 tag run `44834696476` 成功，表明是线程/事件时序敏感，不可把重跑当成修复。

实际调用链：

1. `DedupeRecycleWorker` 为每个文件完成 revalidate 后，经 `row_update_batch` 入队回写行状态；worker 完成时 `_recycle_finished()` 把结果放进 `_pending_recycle_result` 并启动真实 `_drain_timer`。
2. `QThread.finished` 可先于后续定时 drain 清理 `_recycle_thread` 引用。
3. 旧测试只等待 `_recycle_thread is None`，随后立刻读取行状态；此时真正的回写仍在 `_process_update_queue` / `_pending_recycle_result` 中，行仍合法显示旧 `status_pending`。
4. 这与产品已有 busy 语义相符：`_is_busy()` 同时覆盖线程引用、drain timer、更新队列；该测试等待条件没有等待完整 UI 完成语义。没有证据表明有真实 send2trash 或文件内容安全检查被绕过。

root 提供的复现：仅把真实 `window._drain_timer` interval 设为 250ms，运行旧测试即可稳定复现 `status_pending`（脚本 `D:/AppData/Local/Temp/dedupe-drain-race-2cfd7bbe73ad4ab9b747a9ba8f162149.py`）。这是具体确认的 drain 竞态，不是猜测。

## 修复

仅修订该测试的时序门禁，不改产品逻辑、不删除或放宽安全断言：

- 保留真实扫描、记录导出/导入、真实 recycle 按钮、真实 `DedupeRecycleWorker` 和真实回收前核心调用。
- 仍 mock `duplicate_scan_core.send2trash`，确认从未调用。
- 用 `drain_timer.blockSignals(True)` 暂停真实 timer 的 timeout 信号；**不修改 timer interval、不 sleep**。等待 `_recycle_thread is None` 后明确断言：
  - `_is_busy()` 仍为真；
  - `_pending_recycle_result` 或 `_process_update_queue` 尚有真实待处理工作；
  - 两个目标行仍为旧 `status_pending`，直接证明处于“线程结束、UI 尚未 drain”的窗口。
- `finally` 恢复 timer 原有 `signalsBlocked()` 状态，然后在有界等待内要求 `_recycle_thread is None`、`_is_busy() is False`、pending result 为 None、queue 为空，最后再断言状态。
- 保留并最终执行原有全部断言：mock 回收站未调用、同大小同 mtime 内容篡改被 `content_differs` 或 `target_changed` 跳过、删除目标为 `target_missing`、没有 recycled 行、recycled=0、skipped=2、无 Qt 槽异常。

## 已执行验证

### 问题用例重复运行

```powershell
$env:QT_QPA_PLATFORM='offscreen'
# 每轮分别使用新的临时 APPDATA/LOCALAPPDATA
.venv/Scripts/python.exe -X utf8 -B -m unittest \
  tests.test_folder_dedupe_features.FolderDedupePageTests.test_imported_record_then_changed_files_skipped_without_send2trash
```

结果：修复后 **8/8 独立进程通过**，每轮 `Ran 1 test ... OK`（约 0.24–0.26 秒）。

### 页面定向回归

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -p 'test_folder_dedupe_features.py' -q
```

结果：**25 tests，OK，exit 0**（2.924 秒）。

本次未运行全量测试或 CI-like；按 root 指示交由 root / pB。未运行失败的旧版之前，不能把修复后的重复 PASS 单独当作全量 PASS。

## 最终状态

当前只有测试等待条件增加对“真实 drain 中间态”的验证；所有安全断言保留。没有修改 `folder_dedupe_gui.py`、`duplicate_scan_core.py` 或其它测试。测试文件已冻结，等待 root 的标准全量与 pB 的 CI-like 结果。
