# 线程与异步约定

> 本项目处理重活（扫描、元数据解析、合并、去重）的固定模式。改这里前务必理解。

---

## 核心原则：后台算，主线程画

Qt 只允许主线程操作 UI。所有耗时工作跑在 `QObject` Worker + `QThread` 上，
通过 `pyqtSignal` 把结果送回主线程。

---

## 标准模式

### 1. Worker：普通 QObject，用信号输出

```python
class ScanWorker(QObject):
    row_ready = pyqtSignal(dict)
    finished = pyqtSignal(int)

    def __init__(self, input_dir, recursive, output_dir):
        super().__init__()
        ...

    def run(self):
        for task in ...:
            self.row_ready.emit(task)
        self.finished.emit(count)
```

### 2. 启动：moveToThread + 全生命周期连接

```python
self._scan_thread = QThread(self)
self._scan_worker = ScanWorker(...)
self._scan_worker.moveToThread(self._scan_thread)
self._scan_thread.started.connect(self._scan_worker.run)
self._scan_worker.row_ready.connect(self._queue_scan_row)   # 只入队，不直接碰 UI
self._scan_worker.finished.connect(self._scan_finished)
self._scan_worker.finished.connect(self._scan_thread.quit)
self._scan_worker.finished.connect(self._scan_worker.deleteLater)
self._scan_thread.finished.connect(self._scan_thread.deleteLater)
self._scan_thread.start()
```

### 3. UI 批量刷新：队列 + 单定时器 drain（**关键性能模式**）

大量行如果逐行 `insertRow` 会卡死界面。项目采用**入队 + 10ms 定时器批量 drain**：

```python
self._scan_row_queue: deque[dict] = deque()
self._ui_drain_timer = QTimer(self)
self._ui_drain_timer.setInterval(10)
self._ui_drain_timer.timeout.connect(self._drain_ui_queues)

def _queue_scan_row(self, task):
    self._scan_row_queue.append(task)
    self._ensure_ui_drain_timer()

def _drain_ui_queues(self):
    # 一次最多处理 UI_ROW_DRAIN_COUNT(=120) 行
    while self._scan_row_queue and len(batch) < UI_ROW_DRAIN_COUNT:
        batch.append(self._scan_row_queue.popleft())
    self.table.setUpdatesEnabled(False)
    try:
        for task in batch:
            self._append_scan_row(task)
    finally:
        self.table.setUpdatesEnabled(True)
    if self._scan_row_queue or self._process_update_queue:
        return
    self._ui_drain_timer.stop()          # 空了才停
    # 再统一应用 pending 结果（drop/scan/process finished）
```

要点：
- Worker **只 emit 信号入队**，绝不直接调 `self.table.insertRow`。
- 一次 drain 上限 `UI_ROW_DRAIN_COUNT = 120`，保证「每帧可响应」，避免长任务冻结 UI。
- 刷新时用 `setUpdatesEnabled(False)` + `finally` 恢复，减少重绘。
- **定时器只在队列全空时 `stop()`**；`finished` 结果延迟到队列清空后再统一应用。

---

## 忙状态守卫：`_is_busy()`

各页都有 `_is_busy()`，用于禁止重入（防止用户重复点击 / 扫描中再次拖拽）：

```python
def _is_busy(self) -> bool:
    return (
        self.is_processing
        or self._thread_is_running(self._scan_thread)
        or self._thread_is_running(self._drop_thread)
        or self._thread_is_running(self._process_thread)
        or self._ui_drain_timer.isActive()     # ← 批量刷新期间也算忙
        or bool(self._scan_row_queue)
        or bool(self._process_update_queue)
    )
```

⚠️ **陷阱**：`_ui_drain_timer.isActive()` 与队列检查会让「忙」持续一段时间。
`add_dropped_paths` 等在 `_is_busy()` 时**静默 return**，用户会觉得「拖拽没反应」。
因此事件处理里必须先判断忙状态并**给出提示**（而不是静默忽略）——见 `merge_live_photo_gui.eventFilter`。

---

## 队列模式的一致性

`rename_photo_gui.py` 用了两条独立队列 + 两个 drain 定时器（参考区/目标区），
命名如 `_reference_row_queue` / `_scan_drain_timer`。改多区页面时注意同步。
`split_huawei_live_photo_gui.py` / `timestamp_fix_gui.py` 与 merge 同构（单队列）。

---

## 拖拽事件与线程的关系

- `eventFilter` 收到 `Drop` 后**不能**在事件里做重活，只能：
  1. 解析出路径（`_drag_paths`）
  2. 起 `DropScanWorker` 线程
  3. 立即返回
- 扫描结果照常走 `row_ready` → 队列 → drain。

---

## 禁止事项

- ❌ 不要在 Worker 里直接访问任何 UI 控件。
- ❌ 不要逐行同步插入大量表格行（用队列 + drain）。
- ❌ 不要在 `eventFilter` / 按钮回调里跑耗时 IO。
- ❌ 不要忘记 `finished` 连接 `thread.quit` + `deleteLater`（会泄漏线程）。
- ❌ 不要用 `thread.terminate()` 强杀线程。
