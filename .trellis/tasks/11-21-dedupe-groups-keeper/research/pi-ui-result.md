# Pi UI 实施结果（目录内去重分类 / 自主保留项）

范围：仅修改 `folder_dedupe_gui.py`；测试文件由 pA 所有，核心文件由 p4 所有。未 commit/push/tag。

## 已实现

- 三类筛选按钮 `category_buttons = {"photo", "video", "other"}`，使用核心 `classify_media_type/classify_duplicate_group`；按钮显示各类重复组数与 source row 数。默认选择首个非空类。
- 分类变更和结果刷新只调用 `table.setRowHidden`，不重建/排序 `table_model.rows`；每行固定 `_row_categories`，原 source row / recycle worker index 稳定。批量全选、全不选、反选只操作当前显示且 `_checkable` 的行；隐藏分类勾选状态保留。
- 预览逐槽独立按路径类型门禁。DecorationRole 中 `other` 永不调 thumbnail loader；路径索引排除 other。选中行是 other 时先清旧双槽，再分别对选中项和 keeper 槽判型，媒体 keeper 仍可预览、other keeper 一律传 `None` 清槽，覆盖混合扩展名组。
- `btn_set_keeper` 为真实按钮，`_can_reselect_keeper(row_index)` 检查 busy、cancelled/stale、pending 整组、候选归属和文件 size/mtime 快照，不做 hash/内容 I/O；`set_selected_as_keeper()` 调用 `reselect_internal_keeper` 更新核心组与所有同组行，不改 source row。新 keeper unchecked/keep，旧 keeper checked/pending，其它重复行状态保留。
- 回收仍枚举所有分类已勾选合法 target，worker 使用稳定原始行索引；确认弹窗 count/size 是跨分类总量。
- 新文案中英齐全并加入 `_apply_language()`；独立/内嵌布局证据由 root 提供，见 `research/root-layout-check.md`。

## 验证

- `.venv/Scripts/python.exe -m py_compile folder_dedupe_gui.py`：通过。
- AST 检查：通过，无重复类方法。
- `git diff --check`：通过（仅仓库 CRLF 转换提示）。
- `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m unittest tests.test_folder_dedupe_features.DedupeGroupsKeeperTests.test_other_rows_never_request_thumbnail_and_clear_old_preview tests.test_folder_dedupe_features.DedupeGroupsKeeperTests.test_three_category_buttons_show_correct_counts_and_preserve_source_rows tests.test_folder_dedupe_features.DedupeGroupsKeeperTests.test_keeper_change_record_round_trip_preserves_roles_and_states tests.test_folder_dedupe_features.DedupeGroupsKeeperTests.test_visible_batch_buttons_only_change_active_category tests.test_folder_dedupe_features.DedupeGroupsKeeperTests.test_embedded_mode_and_english_refresh_all_new_controls tests.test_folder_dedupe_features.DedupeGroupsKeeperTests.test_core_media_and_keeper_contracts_are_pure_and_stable tests.test_folder_dedupe_features.FolderDedupePageTests -v`：**21 passed**。
- 完整 `tests.test_folder_dedupe_features`：38 tests，**37 passed / 1 failed**。唯一失败是 pA 所有的 `test_set_keeper_button_changes_core_group_and_real_worker_uses_new_keeper`：其 fixture 只取消目标照片组内一个副本，但新扫描时视频/其他组的副本默认也 checked；按约定回收跨分类合计会把这些 targets 一并交给 worker，所以测试实际看到额外视频/其他 target，与该断言预期“仅旧 keeper”不符。实现行为符合跨类别总勾选回收契约；请 pA 在此测试中将其它组行显式取消勾选/只保留目标行后复测。我没有改 pA 测试。

## 未解决阻塞

本页实现可用；只待 pA 调整上述验收 fixture 使其只勾目标组，再复测整页。其余完整测试、发布与最终 review 由 root/pA/pB 协调。
