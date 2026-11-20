# records 独立复核报告（trellis-check）

范围：`scan_record_core.py` + `tests/test_scan_record_core.py`，对照 PRD R3/R4、design.md
“共享记录 API”、`.trellis/spec/python/scan-records.md` 与 `check.jsonl`。
只记录**真实执行验证**的结论；本轮未改 core，也未改任何页面/测试文件。

## 实际命令与结果

```powershell
# 1) 记录模块单测（1.2.1 工作区当前版本）
$env:QT_QPA_PLATFORM = "offscreen"
$env:APPDATA = <临时目录>; $env:LOCALAPPDATA = <临时目录>
.venv/Scripts/python.exe -B -m unittest discover -s tests -v
# → Ran 145 tests ... OK（当时全量；主会话后续全量 182 tests OK）

# 2) 真实扫描 → 保存 → 导入 → 修改/删除后回收保护（两模式）
.venv/Scripts/python.exe -X utf8 .trellis/tasks/11-21-compare-preview-records/research/root_records_probe.py
# → PASS: compare ... atomic save failure, changed/deleted historical target protected
# → PASS: internal ... 同上
# → exit 0

# 3) 模拟哈希碰撞（真实可解码 BMP，patch sha256_file 常量）
.venv/Scripts/python.exe -X utf8 .trellis/tasks/11-21-compare-preview-records/research/collision_safety_probe.py
# → groups=0, mismatches=1, recycle=skipped/content_differs, send2trash_calls=0, exit 0
```

### 冒烟碰撞结果的“导出 → 导入 → 保守回收”组合（本轮新增执行，未落盘为脚本）

用真实 `duplicate_scan_core.find_internal_duplicates` + `patch.object(core, "sha256_file", 常量)`，
构造同时含 1 个合法分组（K/D 同字节）与 1 个碰撞 mismatch（P/Q 同大小不同字节）的结果；
`row_states` 完全按 folder 页 `_runtime_row_states` 的写法（keeper=status_keep、
duplicate=status_pending、mismatch.other=status_mismatch）：

```
groups: [('D.bin', ['K.bin'])]
mismatches: [('P.bin', 'Q.bin')]
roundtrip OK: 3 row states; groups 1 mismatches 1
protected: skipped content_differs / skipped content_differs
```

结论：`save_record` → `load_record(expected_mode='internal')` 成功且行状态原样保留；
把合法 target 改成同长度不同内容（并复原 mtime）后 `recycle_duplicate(byte_verify=True)`
返回 `skipped/content_differs`，碰撞对同样被拒，`send2trash` 零调用。**未发现可复现的真实 bug。**

## 逐项契约核对（与 spec 对应）

| 契约 | 结论 | 依据 |
|---|---|---|
| schema_version=1、UTF-8、未知/缺失字段、重复键、NaN 拒绝 | 通过 | `BadInputTest`；代码逐键 `_require_mapping` + `_pairs_hook` + `parse_constant` |
| mode/expected_mode、internal 无 root_b、A/B 同根或嵌套拒绝 | 通过 | `test_wrong_mode_is_rejected`、`test_nested_or_same_roots_rejected`、`test_internal_with_root_b_rejected` |
| 绝对路径、路径归属 root、链接越界、跨根角色 | 通过 | `test_relative_paths_rejected`、`test_target_outside_root_rejected`、`test_traversal_and_symlink_escape_rejected`、`test_wrong_role_rejected` |
| 重复 target、keeper/target 相交、分组大小/SHA 格式 | 通过 | `test_duplicate_target_and_keeper_intersection_rejected`、`test_size_mismatch_rejected` |
| 行状态角色约束 + 仅 pending target 可勾选 | 通过 | `test_unknown_status_and_bad_row_state_rejected`、`test_keeper_or_issue_cannot_be_checked_pending`、`test_checked_flag_normalized_for_non_pending_rows` |
| 原子保存失败保留旧记录并清理临时文件 | 通过 | `test_replace_failure_keeps_previous_record_and_cleans_temp`；真实 probe 同断言 |
| 历史路径已删除仍可导入；实际回收跳过 | 通过 | `test_deleted_history_paths_still_importable`、`test_imported_record_cannot_recycle_deleted_target` |
| 导入后文件修改（同大小/同 mtime）不回收 | 通过 | `test_imported_record_cannot_recycle_modified_target`、真实 probe |
| 哈希碰撞进 mismatches，绝不回收 | 通过 | `collision_safety_probe.py` + 本次导出组合冒烟 |
| 记录读写不访问媒体内容、不触发回收 | 通过 | `load_record`/`save_record` 仅做 JSON 与 stat/realpath 校验；回收只走 `duplicate_scan_core` |

## 一项已验证的 API 边界（非当前 bug，无需改 core）

`row_states` 里若写入 **mismatch.keeper**（A/保留侧），角色被归为 `keeper`，只接受
`status_keep`；写 `status_mismatch` 会被 `ValueError` 拒绝。现有两页都只持久化
`primary_path()` 行（mismatch 行是 `mismatch.other`，状态 `status_mismatch`），因此**当前页面路径
不会触发**；本次按页面写法做的碰撞导出冒烟已通过。建议页面只持久化需要恢复的目标行状态
（keep/mismatch/issue 可从 ScanResult 派生），不要为此放宽 keeper 状态集合，更不可允许
keeper 变成 pending。此结论已在上文冒烟中验证，无需修改代码。

## 未覆盖 / 边界

- 未验证真实 OneDrive 仅联机占位文件的导入回放（始终使用临时本地文件）。
- 未在双盘符/跨卷路径上做集成验证；`commonpath` 跨盘返回不归属，属预期。
- GUI 层（异步导入/导出、关闭协议、内嵌布局）由 pages 工作包与主会话全量测试覆盖，
  本报告只对记录核心与真实回收保护负责。
- 记录文件大小上限的极端内存放大未做压力测试（64 MiB 上限 + 解析前拒绝）。

## 结论

**通过，无需修改 `scan_record_core.py` 或 `tests/test_scan_record_core.py`。**
核心校验、原子保存与导入后强制逐字节复核满足 PRD R3/R4；碰撞保守保护有真实 mock 验证。
