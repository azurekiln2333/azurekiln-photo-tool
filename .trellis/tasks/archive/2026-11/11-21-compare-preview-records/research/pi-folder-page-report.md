# Pi folder page 报告（11-21 目录内去重页：批量勾选 + 扫描记录）

所有权：仅 `folder_dedupe_gui.py`、`tests/test_folder_dedupe_features.py`、本报告。
未修改 `dir_compare_gui.py`、`tests/test_compare_page_features.py`、`media_thumbnail.py`、
`scan_record_core.py`、spec 与发布文件。无 commit/push/分支操作。

## 1. 实现内容

### 1.1 批量勾选（全选 / 全不选 / 反选 / Ctrl+A）

- `row4` 工具栏新增三个按钮（第二行，1360 宽不溢出），`QShortcut(StandardKey.SelectAll)`
  绑定 `select_all_checkable`。
- 判定与表格模型 `_checkable()` 完全一致：`row.is_checkable()`
  （`kind==duplicate and status==status_pending`）且 `not _scan_stale and not _scan_cancelled`。
  因此保留行、校验不一致、读取问题、已处理（recycled/skipped/failed）、取消、失效结果
  一律不可被批量选中。
- 批量变更只发一次 `dataChanged(CHECK 列区间)` + 一次 `_on_row_check_changed()`，不逐行刷新。
- 失效/取消时按钮禁用；`select_all_checkable()` 返回变更行数并直接拒绝过期状态。

### 1.2 异步 JSON 扫描记录

- 新增 `RecordSaveWorker` / `RecordLoadWorker`（QObject + QThread），调用冻结 API
  `save_record(path, record)` / `load_record(path, expected_mode="internal")`，不读写媒体内容。
- `export_scan_record()`：校验有完整结果 → 构记录 → `QFileDialog.getSaveFileName` → 后台写。
- `import_scan_record()`：`getOpenFileName` → 后台完整解析，**只有解析成功才替换显示**；
  坏 JSON / 错误 schema / 错误 mode 只弹错误提示，当前行、勾选、计数完全不变。
- 记录内容：`ScanRecord(mode="internal", root_a=绝对路径, root_b=None, scope, keep_strategy,
  result=完整 ScanResult, row_states={normcase(abspath): {checked, status}}, created_at, stale)`。
- **扫描时快照**：`start_scan` 时记录 `root_a/scope/keep_strategy/created_at`（绝对路径），
  导出只用快照，扫描后改根目录/选项不会污染记录（有专门回归）。

### 1.3 导入后的安全约束

- `_record_imported=True`；`start_recycling` 时 `byte_verify = True if _record_imported else 勾选框`。
- 导入时 `_scan_cancelled`/`_scan_stale` 由记录恢复，两者都会禁用回收与批量勾选。
- 行状态恢复只接受 `ROW_STATUS_BASES` 内的基键；`checked` 只在
  `row.is_checkable() and not stale and not cancelled` 时为 True。
- 恢复后按行状态重算 `_recycled_count/_skipped_count/_failed_count`，汇总不会把历史说成 0。
- 新扫描成功会清除 `_record_imported`，`_reset_results()` 同时清快照与结果。

### 1.4 忙状态与关闭生命周期

- `_is_busy()` 对 **scan / recycle / record 三类线程统一按「引用非 None」判定**：
  `isRunning()==False` 到 `finished` 回调清理之间按钮不会提前启用，避免紧接着的用户点击
  被忽略或覆盖唯一线程引用（与 pA 在 compare 页的修法一致）。
- `_threads_pending()` 覆盖同类三类引用；`closeEvent` 在 pending 或 busy 时 `ignore()` 并置
  `_pending_close`，`_record_thread_finished` / `_scan_thread_finished` /
  `_recycle_thread_finished` / `_drain_queues` 末尾都会调 `_maybe_finish_close()`，
  保证延后关闭不会漏掉 drain-only 的忙态。
- 关闭时先 `thumbnail_loader.shutdown()` 再真正 close。

### 1.5 文案

- 新增 20 个键全部中英双写（按钮、状态、错误），`_apply_language()` 覆盖全部新按钮；
  语言切换回归断言中英文案。

## 2. 测试

```
$env:QT_QPA_PLATFORM = "offscreen"
.venv/Scripts/python.exe -m unittest tests.test_folder_dedupe_features -v     # 16 passed, exit 0（1.56s）
.venv/Scripts/python.exe -m unittest tests.test_unified_close -v              # 2 passed, exit 0（主会话用例）
```

`tests.test_folder_dedupe_features`（16 个，全部真实按钮 `.click()` + 真实 QThread 扫描）：

1. 真实扫描 + 全选/全不选/反选 + Ctrl+A：保留/异常/已处理行守恒不变。
2. stale 后批量按钮禁用且 `select_all_checkable()==0`。
3. 导出只用扫描时快照（扫描后改根目录与 scope，记录仍是原值）。
4. 无结果时导出按钮禁用 + 不发文件对话框。
5. 导入恢复行/状态/已处理计数（skipped 计入汇总，已处理行不可勾选）。
6. 导入后回收 worker 强制 `byte_verify=True`（勾选框故意取消勾选）。
7. 取消记录导入后禁用回收、批量选中数为 0。
8. 失效记录导入后禁用回收。
9. 坏 JSON 导入保留当前显示与 `_record_imported=False`。
10. 错误 mode（compare）记录被拒绝。
11. 重扫成功清除导入标记。
12. 记录线程存在即算忙（按钮禁用），清理后 `_is_busy()==False`。
13. **停止但未 finished 清理的线程仍算忙**：用真实 `QThread`（空 run + `thread.wait()`，
    不靠 sleep）造出 `isRunning()==False` 且引用未清的状态；断言 `_is_busy()` 为 True、
    扫描/批量/导入按钮禁用、真实点击 `btn_scan` 被忽略且不覆盖 `_scan_thread`；
    recycle 引用同理，忙时 `select_all_checkable()` 返回 0；清引用后恢复。
14. 语言切换后新按钮中英正确。
15. **合并安全回归**：真实扫描 → 导出 → 导入 →（同大小同 mtime 改写一个目标 + 删除另一个）
    → 勾选框取消 byte_verify → 点真实回收按钮；`duplicate_scan_core.send2trash` 用 Mock，
    `assert_not_called()`；被改写的行 `status_skipped|content_differs`（或 target_changed），
    被删除的行 `status_skipped|target_missing`，无 `status_recycled` 行，
    `_recycled_count==0`、`_skipped_count==2`。
16. `DedupeRecycleWorker` 把 `byte_verify` 透传给 `recycle_duplicate`（mock，不真实回收）。

全局（主会话全量）：**182 tests OK**。此前两处失败已由相关 owner 修复，不再列为阻塞：

- `tests/test_compare_page_features.py::RecordRoundTripTests::test_export_uses_scan_time_snapshot`
  —— compare 页同类忙态竞争，pA 已修（线程引用非 None 即忙）。
- `tests/test_media_thumbnail.py::test_image_scales_proportionally_with_card_width`
  —— 过严的 `ratio == 2.0 @ places=2` 断言，p4 已改为容差比较；截图/布局问题早已
  由 p4 在 media_thumbnail.py 内修复（窄右栏不再重叠/裁切）。

Qt 槽异常：每个用例安装 `sys.excepthook` 收集器，关键用例末尾断言 `self.errors` 为空。
不再重建 `DedupeContextMenu`、不再 `removeEventFilter`；窗口真实
`release loader → close → deleteLater → sendPostedEvents(DeferredDelete) → processEvents`，
在 p4 修复 `file_context_menu` 真实析构后无 `TableView deleted` 噪声。

主会话验收（最终）：全量 **182 tests OK**；`tests/test_unified_close.py` 两页真实记录保存时
关统一窗口均通过。

## 3. 归档可靠性（research 脚本自定位）

本任务 archive 后路径层级会变，三个研究脚本原先用 `Path(__file__).resolve().parents[4]`
固定取仓库根，归档后会指错且无任何提示。已统一改为与 `root_layout_probe.py` 相同的
向上查找：

```python
REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "duplicate_scan_core.py").is_file()
)
sys.path.insert(0, str(REPO_ROOT))
```

涉及：`research/integration_media_probe.py`、`research/preview-layout-smoke.py`、
`research/wrap-probe.py`（`parents[4]` 已全部清除）。验证仅 `py_compile` 三文件全部通过，
三者在现路径下均解析到 `D:\MyNewProject\LivePhotosSpilt`；按主会话要求未重跑过时布局探针。

## 4. 剩余项 / 未覆盖边界

状态：本页功能与回归全部完成，无未解决阻塞；剩下的是“未做/做不了”的已知边界，供发布
报告如实引用，不当作待办。

- **未做**：上千行表格的性能回归（批量勾选为 O(n) 直改 + 单次刷新，未在万行级别实测）。
- **测试手段限制**：忙态回归用真实 QThread 的「已停未清理」引用模拟窗口期，而非真实
  扫描/回收的毫秒级竞争复现（同一机制，触发路径不同）。
- **设计使然**：记录导入不校验媒体内容，回收时逐字节复核；因此导入后文件被修改/删除
  只会得到 `skipped/content_differs｜target_changed｜target_missing`，不会误回收
  （已由合并回归 + `send2trash` Mock 断言锁住）。
- **环境限制**：未对真实 OneDrive 云端占位文件做端到端（测试只用本地临时文件；
  改写时保持 size 与 mtime，以证明强制逐字节复核而非仅靠 stat）。
- 本页不再需要改动；四页预览的视频回退打包由 pB 负责，**若产物内缺少 QtMultimedia
  后端，R5 即不成立**（见 `research/video-packaging-contract.md` 与 `verify_bundle.py`）。
