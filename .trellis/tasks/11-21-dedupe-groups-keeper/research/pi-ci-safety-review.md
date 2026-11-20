# CI safety review — imported changed/deleted targets test

结论：根据当前测试与产品代码，**最可能是测试过早断言 UI 行状态的异步时序竞态，不是回收安全校验失效**。本次只读检查，没有运行测试或改源码；没有在工作区找到用户贴出的 branch run 原始 CI 日志，因此对远端失败原因保留“高度符合、需 pA/root 以修正等待条件确认”的限定。

## 代码链与安全判断

- Fixture `_make_duplicates()` 建立同内容 3 个文件；真实扫描后应得到 1 keeper + 2 checked duplicate rows。测试导出记录后，选择一目标改写为**同大小并恢复原 mtime**，删除另一目标，再从记录导入后启动真实回收按钮。
- `start_recycling()` 仅把 `checked && KIND_DUPLICATE && status_pending` 的原始 model rows 转成 `(row_index, entry, keeper)` worker 参数；导入记录时 `byte_verify=True` 被强制，不信任 UI checkbox。
- `DedupeRecycleWorker.run()` 对每个 target 调 `recycle_duplicate(target, keeper, byte_verify=True, ...)`，依据 outcome 生成 `status_skipped|reason`，最后先发剩余 row updates，再发 `finished(result)`。核心 `revalidate_pair()` 对已删除路径返回 `target_missing`；对同大小、同 mtime 的改写会进入强制逐字节比较并返回 `content_differs`（若文件系统 mtime 精度导致快照不同，则 `target_changed` 也被测试接受）。`recycle_duplicate()` 只在复核返回 None 后才调用 `send2trash`。
- 用例 patch 的是核心真实引用点 `duplicate_scan_core.send2trash`，保留 `assert_not_called()`；该安全断言正确，不应删掉或放宽。

因此，只要 worker 真正处理了这些 target，安全路径应阻止回收。远端出现 `modified_target == status_pending` 更符合 GUI 尚未将 worker 结果应用到 row model 的观察时点，而不是内容校验放行。

## 最可能竞态（具体等待条件）

测试只等待：

```python
_pump(app, lambda: window._recycle_thread is None)
```

但 `QThread.finished` 的 UI 清理和结果 UI drain 是不同生命周期：

- `_recycle_thread_finished()` 先清除 `_recycle_thread` 引用并更新按钮；它不负责直接改 row status。
- worker 的 `row_update_batch` 经 `_queue_recycle_updates()` 放入 `_process_update_queue`；`finished(result)` 经 `_recycle_finished()` 保存到 `_pending_recycle_result`，并启动 10ms `_drain_timer`。
- 只有 `_drain_queues()` 才调用 `_apply_recycle_updates()` 更新行状态；队列清空后才调用 `_apply_recycle_finished()` 更新 `is_recycling`、跳过/回收计数及 summary。
- `_is_busy()` 已包括 `is_recycling`、线程引用、`_drain_timer.isActive()` 和 update queue。因此“线程引用为空”并不等于“UI 行更新与最终结果已应用”。该测试忽略了代码已有的更强完成语义。

CI 快速 runner/Qt 调度下，线程引用清空可先于 10ms drain timeout；立即读取旧 model row 会观察到此前导入留下的 `status_pending`。这是一个合理且与症状吻合的时序窗口。它不意味着 worker 没有执行校验；但当前断言可能先于其 UI 结果，因此失败不能被视为回收已发生或安全漏洞的证据。

## 建议 pA / root 的最小测试修复

仅改该用例的等待，不改产品代码、不加长总 timeout：

1. 在点击前把真实 `window._drain_timer` interval 临时延长（例如 100–200ms，显著大于正常 10ms 且仍短），以稳定制造“worker/thread 已结束、drain 尚未执行”的窗口；保存原 interval 并在 `finally`/patch cleanup 中恢复。
2. 可先等待 `_recycle_thread is None`，断言此时 `_is_busy()` 仍为 true（若 drain timer/`is_recycling` 尚在），这一步验证正在覆盖的时序，而不读旧 row 当终态。
3. 再以 `_pump` 有界等待**真实完成语义**：`not window._is_busy()`，并显式确认 `_process_update_queue` 为空、`_pending_recycle_result is None`、`not _drain_timer.isActive()`；其后再核对所有终态与计数。
4. 原样保留安全断言：`send2trash_mock.assert_not_called()`；修改目标为 `status_skipped|content_differs` 或 `target_changed`；删除目标为 `status_skipped|target_missing`；不存在 recycled 行；`_recycled_count == 0`、`_skipped_count == 2`、`errors == []`。

若延长定时器期间观察到队列/结果没有进入 drain，或真实完成语义下仍是 pending，才应继续追产品信号/worker 链路；不可用 sleep 后直接放宽/删除终态断言。

## 证据范围

只读检查了 `tests/test_folder_dedupe_features.py` 用例、`DedupeRecycleWorker.run()`、`MainWindow.start_recycling()`、`_queue_recycle_updates()` / `_drain_queues()` / `_recycle_finished()` / `_recycle_thread_finished()` / `_is_busy()`、`duplicate_scan_core.revalidate_pair()` 与 `recycle_duplicate()`。未重跑定向/全量测试；未改任何源码或测试；未 commit/push/tag。
