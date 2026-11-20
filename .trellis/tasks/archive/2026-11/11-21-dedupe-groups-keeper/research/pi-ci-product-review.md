# CI 产品语义复核：导入后文件变化的回收状态

结论：当前产品完成语义正确，不需要改运行时代码。

`DedupeRecycleWorker` 完成时先发出每行状态批次和汇总结果；UI 将行更新放入 `_process_update_queue`，由 `_drain_timer` 在主线程应用。`_recycle_thread is None` 仅表示线程引用已清理，不保证队列已 drain，也不保证 `_pending_recycle_result` 已应用。可靠的 idle 条件是 `not window._is_busy()`，它覆盖 `is_recycling`、timer、待处理队列及线程引用。idle 后再检查行状态和 skip 计数，才是页面操作完成。

该回归必须保留的安全结果为：同大小同 mtime 的改写目标因逐字节复核变成 `status_skipped|content_differs`（或允许的 `target_changed`）；删除目标为 `status_skipped|target_missing`；`_skipped_count == 2`、`_recycled_count == 0`，且 `duplicate_scan_core.send2trash` 未调用。

不应为掩盖“只等待线程、不等待 UI drain”的测试时序缺口而修改回收安全核心或产品状态机制。由测试 owner 在真实 drain timer 延长的确定性场景下等待 `_is_busy()` 变为 False 后再断言上述结果。源码未改；按要求未再运行普通速度重试。
