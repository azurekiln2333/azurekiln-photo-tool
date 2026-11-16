# pi-check 复核发现（第一轮增量复核）

Active task: `.trellis/tasks/11-15-folder-media-statistics`
复核范围：`check.jsonl` + PRD/design/implement + 当前产品代码（只读 peers 文件）+ 我的 `unified_gui.py` / 三份 README。
本轮**未修改**任何产品代码（peers 仍在修）；无 commit。最终全范围复核待协调者另行指派。

方法：`.venv/Scripts/python.exe`，`QT_QPA_PLATFORM=offscreen`，`APPDATA` 指向 `tempfile.mkdtemp()`，所有 GUI 断言走真实控件（`btn_save.click()`、`tree.setCurrentIndex()`、`btn_draft_save.click()`）。
**严格模式**：`sys.excepthook` 捕获一切槽函数异常并判失败，不吞 traceback、不用「退出码是既有现象」搪塞。临时脚本验后全部删除。

---

## A. 已复现的缺陷（按严重度）

### A1【阻断·必现】点击「保存」按钮抛 `TypeError: 'bool' object is not callable`

- 位置：`media_statistics_gui.py:572` `self.btn_save.clicked.connect(self.save_readme)`，
  与 `media_statistics_gui.py:1331` `def save_readme(self, on_success=None)`、`:1343` `on_success is not None` → `:1344` `on_success()`，
  实际抛出点 `media_statistics_gui.py:1380` `callback()`。
- 根因：`QPushButton.clicked` 签名是 `clicked(checked: bool)`。直连时 `checked=False` 被当作位置参数传入 `on_success`，
  于是 `on_success=False`（`is not None` 成立）→ 保存成功后调用 `callback()` 即 `False()` → `TypeError`。
- 复现（独立于协调者脚本）：新建临时相册 → 选中 `2026-11` → 编辑框改文本 → `win.btn_save.click()`。
  结果：**文件写盘成功**，但捕获 1 个 `TypeError`：
  ```
  File "media_statistics_gui.py", line 1380, in _on_readme_saved
      callback()
  TypeError: 'bool' object is not callable
  ```
- **每次点击都必现**（连续两次点击两次都抛），不是偶发。
- 影响放大：异常发生在 `_set_readme_status("status_readme_saved")` / `_notify(...)` **之后**、
  `return` 之前，状态栏停在「说明文件已保存」但槽函数以异常结束。`_readme_busy` 仍由
  `_on_readme_thread_finished` 复位，故可再次保存；但所有通过该按钮的保存都会在用户侧产生
  Qt 槽异常（打包版 `console=False` 时用户看不到，仅静默异常）。
- 附带风险：`media_statistics_gui.py:1572-1575` 的 `except Exception: pass` 会在**关闭流程**里
  吞掉同类异常，导致「保存后继续关闭」静默中断而无任何提示。
- 建议修复（**GUI 归属**，pi-gui）：`self.btn_save.clicked.connect(lambda: self.save_readme())`，
  或 `connect(self._on_save_clicked)` 且该槽签名为 `def _on_save_clicked(self, _checked=False)`。
  同类风险点一并自查：`:470 btn_root`、`:502/:505/:508/:511` 均为无参槽，安全；`:587/:589/:591` 用 `lambda`，安全。
- 协调者脚本 `verify_integration.py` 现已断言 `qt_errors`，实测 **`AssertionError: Qt slot exceptions: 1`**，与我的复现一致。

### A2【高·竞态】重扫时旧线程 `finished` 清空新线程引用 → 失去引用 / 误报空闲

- 位置：`media_statistics_gui.py:942-943`（`_start_scan` 立即覆盖 `self._scan_thread` / `self._scan_worker`）
  与 `media_statistics_gui.py:957-960` `_on_scan_thread_finished` **无条件**置 `None`。
- 机制：`_stop_scan_thread()`（`:974`）只 set 停止标志、不等待；旧 QThread 的 `finished`
  稍后触发 `_on_scan_thread_finished`，把**新**线程/worker 引用清空。
- 复现（直接断言，非靠退出码）：
  ```
  scan1 running: True
  scan2 started, distinct: True
  new.isRunning() after loop: True      ← 新扫描仍在运行
  win._scan_thread: None                ← 唯一引用已被旧线程回调清掉
  _has_background_work(): False         ← 误报空闲
  BUG DETECTED: _scan_thread cleared while new thread running; bg_work=False
  ```
- 影响：① 新 QThread 失去 Python 引用，可能在**运行中**被销毁/GC；② `_has_background_work()` 误报
  `False` → `request_close()` 返回 `True` → 统一窗口/独立窗口放行关闭，把仍在跑的线程随父对象销毁。
  实测该路径解释器退出为 `0xC0000005`（访问冲突）且**无任何 Python traceback**，属真实崩溃而非良性析构。
- 说明：该竞态**依赖时序**——另一次运行中同一场景 `_has_background_work()` 正确返回 `True`、
  我的统一 `closeEvent` 也正确返回 `accepted=False`。即：**我的集成层传导正确，但会继承页面的误报**。
- 建议修复（**GUI 归属**）：`_on_scan_thread_finished` 接收线程身份，例如
  `self._scan_thread.finished.connect(lambda t=self._scan_thread: self._on_scan_thread_finished(t))`，
  在槽内 `if sender-ish is not self._scan_thread: return`；或改用 `QThread` 局部变量 + `is` 比较。
  `_on_readme_thread_finished`（`:1212`）同样是无条件 `None`，有相同隐患（读/写各新建 QThread）。

### A3【中】扫描完成时同步全量 `_apply_snapshot`，与分批刷新重复且阻塞主线程

- 位置：`media_statistics_gui.py:1050-1051`
  ```python
  for snapshot in outcome.folders:
      self._apply_snapshot(snapshot)
  ```
- 问题：① `on_batch` 分批已把同一批目录插/更新过，这里**再全量重刷一遍**；
  ② 完全没有 `setUpdatesEnabled(False)`、没有 `UI_ROW_DRAIN_COUNT` 上限，一次槽函数内同步跑完。
  违反 `.trellis/spec/pyqt/threading-and-workers.md`「不要逐行同步插入大量表格行（用队列 + drain）」。
- 实测：365 个目录单次同步全量 **8.3 ms**（≈23 µs/目录）；线性外推 5,000 目录 ≈115 ms、
  20,000 目录 ≈460 ms 的事件循环冻结。`UI_ROW_DRAIN_COUNT=120` 本应 3+ 个 10ms tick 摊开。
- 建议修复（**GUI 归属**）：完成时也走 drain 队列（或仅在最终结果中补差异节点），并包 `setUpdatesEnabled`。

### A4【中低·UX】关闭流程中保存失败后，关闭意图被静默取消且无可见提示

- 位置：`media_statistics_gui.py:1384`/`:1398` `_cancel_close_intent()`（定义 `:1549-1553`）。
- 复现：dirty → `request_close()` 返回 `False`（正确）→ 把 `readme.txt` 置只读使保存失败 →
  点草稿条「保存」→ 结果：`_closing=False`、`dirty=True`、`btn_save` 恢复可用、状态栏显示
  「保存失败：没有写入权限…」（正确），但 **`draft_bar.isVisible()=False`、`_pending_action=None`**。
- 问题：用户点了关闭、又点了「保存」，保存失败后窗口不关，但**没有任何「关闭已取消」的提示**，
  草稿决策条也消失。数据安全（草稿保留、原文件未损）无问题，属可理解性缺陷。
- 建议：`_cancel_close_intent` 后追加一条内嵌提示/状态，如「保存失败，已取消关闭并保留草稿」。
- 注：此处 `_close_intent` 机制本身设计正确（失败绝不关闭），不是缺陷。

---

## B. 经复核**未发现问题**（已澄清，避免重复投入）

请求方点名怀疑但这些项实测正常，建议 pi-scan / pi-readme **不必**再改：

1. **后缀名目录误计**（`media_statistics_core.py:168`/`:330`/`:359`）：先 `_classify_entry`
   再匹配后缀，目录名 `2026-11.JPG`、`2025-01.MOV` 均被判为 `dir`。
   实测根目录 `direct_image=1, direct_video=1`（正确的 `a.JPG`、`b.mp4`），
   后缀名目录自身未被计入，且其内部 `real.JPG` 仍正常汇总（`total=1`）。**通过**。
2. **每条目异常处理**（`media_statistics_core.py:333-336`、`:363-366`）：`_classify_entry`
   抛异常时记 `ScanIssue` 并保留不完整标记，不静默当「非文件」；目录枚举失败同样记录并 `continue`。**符合 spec**。
3. **README 枚举失败伪装成 missing**（`media_readme_core.py` `load_readme`）：
   目录不存在 → `error`（"目录不存在或已被删除"）；`os.scandir` 抛 `PermissionError` → `error`
   （"目录不可访问：…"）；仅真正无 readme → `missing`。**三种状态正确区分**（pi-readme 的修复已生效或本就正确）。
4. **快速切换目录串读**：连续 `_select_folder` 6 个目录，最终编辑器文本与所选目录**完全一致**
   （`_readme_pending_load` 单槽 + `request_id` 丢弃过期结果）。**通过**。
5. **草稿守卫保存路径**：`_resolve_draft("save")` 用 `save_readme(on_success=after_save)` **关键字**传参，
   不触发 A1 的 `TypeError`；保存成功、写盘到原目录、随后继续原动作（切到目标目录）全部正确。**通过**。
   实测：dirty 文本 `DIRTY 2026-11\n` 正确写入 `2026-11/readme.txt`，之后编辑器显示目标目录 `2025-01` 内容。
6. **符号链接/目录联接跳过**：创建目录 symlink → 未被遍历（`linkdir` 不在结果中），
   根 `total=2` 无重复计数，`errors` 为空。与我的 README 陈述一致。**通过**。
7. **翻译完整性**：页面 `tr()` / `_set_readme_status` / `_set_status_text` 共用到 **55** 个键，
   `TRANSLATIONS["zh"]` / `["en"]` 各 **61** 键，缺键 **0**，zh/en 键集**完全一致**。**通过**。
8. **设置页六项兼容**：`SettingsPage` 改 `[:6]` 后，`feature_windows` 6 项、绑定未错位、
   10 个设置分类 key 全建；统计页不进 `_feature_windows`。**通过**（详见 `pi-integrate-report.md`）。
9. **统一窗口七页语言传播 / closeEvent 传导**：导航与表头 zh↔en 全刷、原六页 `lang` 同步；
   后台忙时 `closeEvent` 返回 `accepted=False` 且零阻塞。**通过**。

---

## C. 我的自有文件（`unified_gui.py` + 三份 README）复核结论

- `unified_gui.py`：`compileall` + `ast.parse` 通过；本轮**无需修改**。
  唯一相关风险是 A2 的**上游误报**：我的 `closeEvent` 逻辑正确传导 `request_close` 结果，
  无法也不应在集成层自行猜测线程状态（那会与页面契约重复）。待 pi-gui 修 A2 后自然消除。
- 三份 README 事实核对：七页数量、列名、扩展名集、2 MiB、编码/换行、仅编辑已有文件、
  符号链接跳过（B6 已实测）、仅联机边界措辞均与当前实现一致。`六个`/`three core`/`三個核心` 等
  过期表述已无残留（grep 无命中）。
- 未改 `.trellis/spec/**` 与两份 `.spec`（静态导入经 `ast` 导入图确认三新模块可达，无需改）。

---

## D. 关于无头退出码（按要求不作搪塞，给出对照）

本轮所有崩溃判定均基于**显式断言与 stdout**，不以退出码单独定性。但记录对照结果以免误判：

| 场景 | 退出码 | 有 Python traceback |
|---|---|---|
| 单页 `merge_live_photo_gui.MainWindow(embedded=True)`（**不加载任何新代码**）构造后退出 | `0xC0000005` | 无 |
| 正常 `app.exec()` 事件循环后 `sys.exit(0)` | `0` | — |
| A2 重叠重扫（新线程仍在跑、引用被清空） | `0xC0000005` | 无 |
| A2 对照：不重叠、等扫描彻底结束 | `0xC0000409`（abort） | 无 |

结论：`0xC0000005` 在「完全不涉及新代码」的单页对照里同样出现，故**不能**用它单独证明 A2；
A2 的判定依据是我给出的**运行时状态断言**（`_scan_thread is None` 且 `new.isRunning() is True`
且 `_has_background_work() is False`），与退出码无关。两者共同指向「QThread 生命周期与引用管理」这一根源。

---

## E. 待办归属

| 项 | 归属 | 状态 |
|---|---|---|
| A1 `btn_save.clicked` 直连导致 TypeError | pi-gui | **必现，需修** |
| A2 `_on_scan_thread_finished` / `_on_readme_thread_finished` 无条件置 None | pi-gui | 竞态，需修 |
| A3 完成时同步全量 `_apply_snapshot` | pi-gui | 性能，建议修 |
| A4 关闭中保存失败无可见提示 | pi-gui | UX，建议修 |
| B1–B5 扫描/说明/枚举疑似缺陷 | pi-scan / pi-readme | **复核未复现，可免改** |
| 我的 `unified_gui.py` / 三份 README | pi-integrate | 本轮无需改 |

最终全范围复核（含 pi-gui 修复后的回归、A1 真实按钮点击、A2 竞态压测、打包）待协调者指派。
