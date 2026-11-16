# pi-gui 实施报告

> 第二轮（评审修复）已合入。修复项与证据见文末「第二轮修复」章节。

## 范围与所有权

- 拥有文件：`media_statistics_gui.py`、`.trellis/tasks/11-15-folder-media-statistics/research/pi-gui-report.md`。
- 未修改：`media_statistics_core.py`、`media_readme_core.py`、`unified_gui.py`、README/docs、spec。
- 未执行 git commit/push/merge。验证只使用临时目录 fixture，未触碰用户 OneDrive 数据。

## 交付内容（media_statistics_gui.py，约 1600 行）

### 结构与布局

- `class MainWindow(FramelessMainWindow)`：`__init__(parent=None, embedded=False)`，独立模式
  `resize(1280, 860)` + `_set_blue_title_bar()`（`#1677FF`，`self._title_bar_height` 参与
  `setContentsMargins`），内嵌模式显示语言下拉。
- 标准卡片结构：title/subtitle/note + elevation hint（`attach_elevation_hint`，非 elevated 零占位）
  → 根目录卡片（LineEdit + 选择按钮）→ `QSplitter(Vertical)`（上：树卡片，下：readme 卡片）→ 状态栏卡片。
- 树：`qfluentwidgets.TreeView` + `QStandardItemModel`，4 列「文件夹 / 图片 / 视频 / 总项数」，
  数值列右对齐并带千位分隔；`Stretch` + `ResizeToContents`；`stretchLastSection(False)`；只读、单选。
- 行↔数据映射用 `self._folders: dict[Path, _FolderNode]`，按路径更新，不重建模型。

### 交互

- 根目录：选择按钮、输入框回车/失焦、拖入文件夹（`tree.viewport()` 事件过滤器，DragEnter/DragMove/Drop）。
- 工具条：展开全部 / 折叠全部 / 重新扫描 / 停止扫描 + `IndeterminateProgressBar`。
- 选中目录加载其**直接** readme.txt；下方显示路径、`PlainTextEdit`、保存、重新加载、状态文本。
- 内嵌草稿决策条（保存并继续 / 放弃修改 / 取消），不使用阻塞 QMessageBox；
  普通成功/错误走 `InfoBar`。

### 线程与刷新（遵循 threading-and-workers spec）

- `ScanWorker` 调用 `scan_folders(root, IMAGE_SUFFIXES, VIDEO_SUFFIXES, stop_event=..., on_batch=...)`；
  扩展名从 `timestamp_fix_gui` 导入后传入，**未复制格式集**。
- 批次入队 `self._scan_batch_queue`，`QTimer(10ms)` 每轮最多处理 `UI_ROW_DRAIN_COUNT = 120` 个目录；
  同一批次被拆分时剩余部分保留在队首（已修复初版的丢批次缺陷）。
- 完成结果 `ScanOutcome` 延迟到队列清空后应用，并以最终 `folders` 再补全一次，保证根/父先插入、
  未收到批次的目录也会出现。
- `ReadmeLoadWorker` / `ReadmeSaveWorker` 单活跃线程 + 单调递增 `_readme_request_id`：
  快速切换只保留最新 `_readme_pending_load`，过期结果直接丢弃。
- 每个 worker 的 finished/failed 信号均连接 `thread.quit`、`worker.deleteLater`、`thread.deleteLater`；
  worker 内部 `try/except` 转成 `failed` 信号，异常绝不穿透 Qt 事件循环。
- 主线程**从未**等待/终止线程；停止扫描为协作式 `threading.Event`。

### 草稿守卫与关闭协议

- 统一入口 `_run_with_draft_guard(action_key, action)`：脏 → 决策条；读/写忙 → 暂缓到 IO 结束。
  覆盖切换目录、更换根目录、重新扫描、重新加载、退出。
- `request_close(on_ready) -> bool`：
  - 返回 `True`：无草稿且无后台任务，调用方可直接关闭（同时清空回调，保证幂等）。
  - 返回 `False`：接管关闭；草稿 → 显示决策条；后台任务 → 置 `stop_event`、丢弃待读请求，
    清理完成后由 `_maybe_finish_close()` 调用 `on_ready`。
  - 重复调用幂等：不重复弹决策条、不重复发起保存。
- 独立 `closeEvent` 与统一窗口 `closeEvent` 共用该接口；独立模式 `event.ignore()` 后
  在 `on_ready` 中 `hide()` + `QTimer.singleShot(0, self.close)` 重新关闭。
- `_close_intent` 标志：保存失败/冲突时 `_cancel_close_intent()` 撤销关闭，保留草稿与窗口
  （验证中修正的实际缺陷：初版冲突仍会关窗）。

### 状态与数据保全

- 无 readme / 超 2 MiB / 读失败：清空文本、只读、明确状态（`missing` 与 `error`/`too_large` 区分）。
- 保存失败或冲突：保留草稿、恢复编辑、原文件不动；核心层错误文本直接展示，避免重复前缀。
- 不完整扫描：节点名追加「(不完整)」+ tooltip，状态栏区分 `cancelled` 与 `errors`。

### 中英双语

- `TRANSLATIONS` 61 键，zh/en **完全对齐**（校验：集合相等、无缺失键）。
- `_apply_language()` 刷新标题、副标题、提示条、语言下拉、根目录控件、表头、按钮、
  状态机动态状态、readme 路径与「不完整」标记、决策条。

## 验证结果（全部通过）

环境：`.venv/Scripts/python.exe`（3.14.0）、`QT_QPA_PLATFORM=offscreen`、`APPDATA` 指向临时目录。

| 项 | 结果 |
|----|------|
| `python -m compileall media_statistics_gui.py` | pass |
| `compileall` 含 core ×2 + unified_gui | pass |
| 离屏冒烟：独立 + 内嵌 MainWindow 构造/显示/语言切换 | pass |
| 功能脚本 58 项断言（临时 fixture） | ALL PASSED |

功能脚本覆盖（均为临时目录，脚本已删除）：

1. 扫描计数：根 5 图 3 视频 = 8 项，直属 1 图 1 视频，8 个目录，空目录保留，
   `readme.txt`/`notes.txt` 不计入，大写后缀 `.MP4/.JPG/.HEIC` 正确归类。
2. 多级树：root → 2026 → 2026-01/2026-11 嵌套正确，父目录含子树总数。
3. 展开全部 / 折叠全部无异常。
4. 无 readme：文本清空、只读、`missing` 状态。
5. 有 readme（`README.TXT` 大写）：加载 → 编辑 → 保存，CRLF 往返保持
   （落盘 `第一行\r\n第二行改\r\n`），保存后媒体计数不变。
6. 脏草稿守卫：取消（草稿保留、仍选中原目录、磁盘不变）/ 放弃（切换生效、磁盘不变）/
   保存并继续（落盘后再切换）。
7. 快速连续切换 4 次：最终读取与最终选择一致，无遗留 pending。
8. 外部修改后保存：`conflict`，草稿保留，磁盘内容未被覆盖。
9. `request_close`：脏时 False + 决策条；放弃后 `on_ready` 回调；空闲时 True 且清空回调。
10. 扫描中 `request_close`：False，停止后 0.10s 内回调，无残留线程。
11. 语言切换 zh↔en 表头/按钮刷新。
12. 内嵌模式扫描正常。
13. GB18030 往返（`中文说明\r\n` → 保存后 `\xd6\xd0...\r\n`）。
14. UTF-16 LE BOM 加载（`utf-16-le`）正常。
15. 超 2 MiB：`too_large`，只读、文本为空、消息含上限。
16. 关闭流程中止：关闭时保存遇冲突 → 窗口保持可见、草稿保留、磁盘未覆盖、
    关闭意图与回调已清除。
17. 性能：1532 个目录扫描 0.29s，最大帧间隔 15–19ms（批量 drain 有效）。
18. 统一窗口联调：7 页（`pages` 6 + 独立统计页）、导航中英切换、
    `closeEvent` 切到统计页展示决策条、放弃后窗口正常关闭、无线程残留；
    `SettingsPage` 仍读前六个窗口，原六页设置绑定未破坏。

布局检查：1280×860 与 980×680（最小尺寸）两种模式 `grab()` 非空，中英文横向无裁切
（tree 列 0 宽 415/367px），splitter 上下比例正常。

## 集成说明与已知边界

- 测试友好属性齐备：`lang`、`language_combo`、`tree`、`readme_edit`、`btn_save`、
  `set_root_folder`、`scan_files`、`request_close`、`_apply_language`。
- 额外暴露（供联调/检查）：`root_dir`、`tree_model`、`_folders`、`btn_expand`、`btn_collapse`、
  `btn_scan`、`btn_stop`、`btn_reload`、`draft_bar`、`readme_document`、`_readme_dirty`、
  `_has_background_work()`、`_pending_action`、`_close_callbacks`、`_close_intent`。
- 设置持久化在独立 `APP_NAME = "MediaStatisticsGUI"` 路径，仅保存 language 与 root_dir（不自动扫描）。
- 不新增任何第三方依赖。
- **未覆盖的真实环境边界**：
  - 仅联机 readme 的实际下载/离线失败行为（需真机 OneDrive，未用用户目录验证）。
  - 云占位媒体的枚举延迟与网络副作用（统计路径不打开内容，但目录枚举可能触发元数据取回）。
  - 外部同步冲突的系统级并发编辑（只做基线字节/mtime 尽力检查）。
- 退出期注意：任何 Fluent 页在未 `deleteLater()` 时于解释器退出会触发 Qt 析构崩溃
  （`timestamp_fix_gui` 同样表现）；正式入口走 `app.exec()`/`sys.exit` 不受影响，
  离屏测试需显式 `deleteLater()`。
- 其他 worker 的临时文件（`_pi_check_*_tmp.py`、`_scanlog*.txt`）未改动，留待主会话清理。

---

## 第二轮修复（评审反馈）

环境：`.venv/Scripts/python.exe`（3.14.0）、`QT_QPA_PLATFORM=offscreen`、隔离 `APPDATA`、
`QFontDatabase.addApplicationFont("C:\\Windows\\Fonts\\msyh.ttc")`（离屏默认 0 字体）。
主验证脚本：`D:/AppData/Local/Temp/media-statistics-pi-.../verify_integration.py`，包含
`sys.excepthook` 捕获 Qt 槽位异常。

### 1. btn_save 回调签名错误（确认 bug）

- 复现：`btn_save.clicked.connect(self.save_readme)` → `clicked` 传 `checked=False` 作
  `on_success`，`_on_readme_saved` 内 `callback()` 抛
  `TypeError: 'bool' object is not callable`（verify_integration 报 `Qt slot exceptions: 1`）。
- 修复：`clicked.connect(lambda _checked=False: self.save_readme())`。
- 证据：真实 `btn_save.click()` 后 `qt_errors` 为 0，且磁盘内容正确写入。

### 2. 扫描生命周期（旧线程 finished 清掉新引用）

- 根因：`_start_scan` 在仅发停止信号后就覆写 `_scan_thread/_scan_worker`，旧队列中的
  `finished` 无条件置 None，会清除新线程引用（`isRunning()==False` 不足以判定）。
- 修复：
  - 旧扫描未退出时不启动新扫描，只置 `_pending_scan_restart`，等 `finished` 后
    `_maybe_start_pending_scan_restart()` 再启动。
  - `thread.finished` 用 `lambda t=thread, w=worker` 绑定身份，
    `_on_scan_thread_finished(t, w)` 仅清理自己；`_retired_scan_jobs` 保留强引用到退出。
  - 旧结果依旧按 `_scan_id` 丢弃。
- 证据：连续 `set_root_folder(r1) → r2 → r1` 后树只含 r1、无 r2 残留、
  `_scan_thread is None` 且无退役线程；扫描中 `scan_files()` 也能正常收敛。

### 3. README 生命周期（续动作早于线程退出）

- 根因：成功回调在 `_on_readme_saved` 内执行，此时 `thread.finished` 未到；旧 cleanup
  可能清掉新引用，且回调可立即发起新 IO 形成重叠。
- 修复：
  - `thread.finished` 同样携带身份（`lambda t=thread, w=worker`），旧线程不清新引用。
  - 成功回调只标记 `_readme_save_succeeded`，真正执行推迟到
    `_on_readme_thread_finished()`（旧线程已退出）之后。
  - `_request_readme_load` 以 `_readme_thread is not None` 判存活，保证同一时刻只有一个 IO。
- 证据（强制延迟/身份测试，全部通过）：
  - 伪旧线程迟到 `finished` 不清除新 `_readme_thread`；
  - 成功回调在 cleanup 后执行（回调内看到 `_readme_thread is None`）；
  - 连续切换 a→b→c→d 后内容为 `content-d`、无残留线程；
  - 保存中导航：峰值并发线程恒为 1，保存落盘后再切到目标目录。

### 4. 关闭时保存失败/冲突

- 行为：`_cancel_close_intent()` 清 `_close_intent/_closing/_close_callbacks`，
  `_on_ready` 不被调用；编辑器恢复可编辑，草稿保留且 `dirty=True`，磁盘未被覆盖。
- 证据：真实 `btn_save.click()` 遇外部修改后：`on_ready` 未触发、
  `_close_callbacks` 为空、窗口 `isVisible()==True`、文本仍为草稿、磁盘仍为外部内容。

### 5. 草稿守卫在 IO 期间的决策

- 修复：`_run_with_draft_guard` 在 IO 进行中不弹决策条，而是用
  `_pending_action = (key, action, "io")` 暂缓；`_resolve_draft` 在 IO 中拒绝决策（提示忙）；
  `_maybe_continue_pending_action` 在 IO 完全结束后再重评 dirty：
  脏 → 转 `"draft"` 弹决策条；否则执行原动作。导航与关闭意图均不丢失。
- 证据：保存中点另一节点→ IO 结束后仍按原意切换；`_pending_action` 收敛为 None。

### 6. 扫描完成不得无界全量重放

- 修复：扫描完成处（drain 收尾 `_flush` 分支 → `_queue_missing_final_snapshots()`）
  只把 `outcome.folders` 中**尚未出现**的目录放入
  `_pending_final_snapshots`，由同一 10ms/≤120 行的 `_drain_ui_queues` 限批消费；
  全部插完才 `_finish_scan_ui()`（展开根/选中）。
- 注（最终复核修正）：上段最初写作 `_apply_scan_finished`，该名称已不存在（被移除/重构）；
  当前实际入口为 `_scan_finished`(worker 槽) → drain 收尾分支 → `_queue_missing_final_snapshots`
  → `_finish_scan_ui`。旧名称陈述视为已被取代。
- 同时修正：`_expand_root_only` 不再因扫描完成而抢走用户在扫描中选中的节点；
  重建树后会把当前说明目录重新选中（阻断信号）。
- 证据：2021 个目录（2000 子目录）0.45s 完成，最大帧间隔 17ms；
  `_pending_final_snapshots` 最终为空；重扫后选中与 `_readme_directory` 均保持为原目录。

### 7. 布局（主会话截图中窗口被撑到 ~1532px）

- 修复：
  - `readme_path_label` 改为 `_ElidedLabel`（水平 `QSizePolicy.Ignored`，
    `sizeHint/minimumSizeHint` 宽度归 0，中间省略号 + tooltip）；
  - `readme_status_label` / `draft_label` / `status` 改 `Ignored` 水平策略 + 自动换行；
  - 树 `setStretchLastSection(False)` + `setMinimumSectionSize(72)`；
  - 最小尺寸改为 560×720（原固定高度导致 680 请求被抬到 715），`readme_edit` 最小高 90。
- 证据（254 字符长路径 + 加载 msyh.ttc 字体）：

| 场景 | 请求 | 实际 | 树列宽（文件夹/图片/视频/总项） |
|------|------|------|------------------------------|
| 默认 | — | 1280×860 | 999 / 72 / 72 / 72 |
| 最小 | 980×680 | **980×680** | 699 / 72 / 72 / 72 |
| 英文 | 1000×760 | **1000×760** | 719 / 72 / 72 / 72 |

  `readme_path_label.sizeHint().width() == 0`、`minimumSizeHint().width() == 0`、
  `stretchLastSection == False`；截图确认长路径以省略号收尾且不越界。

### 8. 主线程不做 `is_dir()` 校验

- 修复：`set_root_folder` 只接受非空字符串；目录是否可枚举交给扫描 worker，
  失败时 `_apply_scan_failed` 若树为空则显示 `status_invalid_root` + InfoBar，
  否则显示「不完整」。拖拽也不再在主线程 `path.is_dir()`。
- 选中恢复：新增 `_set_tree_current_index_silently()`，同时阻断 `QTreeView` 与
  `selectionModel()` 信号后再 `setCurrentIndex`。
- 证据：不存在的根目录→状态文本已更新、无 Qt 槽位异常；重扫后选中恢复为原目录。

### 第二轮回归结果

| 项 | 结果 |
|----|------|
| `compileall media_statistics_gui.py` | pass |
| `verify_integration.py`（含 Qt 槽位异常捕获） | **ALL INTEGRATION CHECKS PASSED**，exit 0，连续 18 次均 0 |
| 生命周期脚本（扫描/关闭/冲突/快速切换/延迟 finished） | 28 项断言全过，`qt_errors == 0` |
| 强制延迟脚本（身份判定/回调时序/单 IO） | 9 项断言全过 |
| 布局探测（980×680、1000×760、默认、中英） | 均等于请求尺寸 |

已删除本次自建的临时脚本（`scripts/_pi_*.py`、`scripts/_pi_shot_*.png`），未触碰其他 worker 文件。

### 剩余风险

1. **解释器退出期的 Qt 析构竞争**（非本轮引入）：窗口不 `deleteLater()` 时于解释器退出
   可能 `0xC0000005`。实测本模块 2/5、既有 `timestamp_fix_gui` 5/5 同现象；正式
   `app.exec()`/`sys.exit` 路径不受影响，但主会话若在进程未显式销毁窗口时跑收尾清理，
   可能偶发非零退出码（本轮 18 次均为 0）。建议测试脚本显式 `deleteLater()`。
2. 仅联机 readme 的真实下载/离线失败仍未在真实 OneDrive 验证（临时目录无法覆盖）。
3. 云占位媒体枚举的网络副作用不可控（统计路径仍不打开媒体内容）。
4. 外部同步冲突仅做基线字节/mtime 尽力检查，非系统级并发编辑锁。
5. `_ElidedLabel` 自绘文本：已避开在 `paintEvent` 内改控件状态（早期版本曾因此
   在 `grab()` 时崩溃）；目前 paint 内仅用 `QPainter.drawText`，中英均验证正常。
