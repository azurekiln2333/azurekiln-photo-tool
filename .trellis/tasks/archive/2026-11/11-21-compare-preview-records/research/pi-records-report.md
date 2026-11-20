# records worker 报告：`scan_record_core.py` + `tests/test_scan_record_core.py`

## 状态：本工作包实现完成，38 项测试全部通过

```
$env:PYTHONIOENCODING='utf-8'; .venv/Scripts/python.exe -X utf8 -m unittest tests.test_scan_record_core -v
Ran 38 tests ... OK
```

（Windows 控制台默认 GBK，中文断言消息需要 `-X utf8` 才能正常显示；不加也能跑通。）

## 交付物

- `scan_record_core.py`（新增，仅标准库 + `duplicate_scan_core`，无 Qt）
  - 冻结 API 原样实现：`ScanRecord` / `save_record(path, record)` /
    `load_record(path, *, expected_mode=None)`；失败抛 `ValueError`（内容无效）或
    `OSError`（文件/目录错误）。
  - 额外公开常量：`SCHEMA_VERSION=1`、`MODE_COMPARE`、`MODE_INTERNAL`、
    `ROW_STATUS_BASES`、`MAX_RECORD_BYTES`。
- `tests/test_scan_record_core.py`（新增，stdlib unittest，临时目录 + mock send2trash）。

## 格式

UTF-8 JSON，`schema_version = 1`，顶层键**固定**为
`schema_version / mode / created_at / roots{a,b} / options{scope,keep_strategy} /
result{groups,mismatches,issues,scanned_files,hashed_files,hashed_bytes,cancelled} /
row_states / stale`；多一个键、少一个键都拒绝（unknown field 直接报错）。

- `roots.b` 在 `internal` 模式必须为 `null`；`compare` 模式不得为 `null`。
- 保存前**先走一遍完整读取校验**，所以导出的文件与导入接受的文件严格同构；
  校验失败不落盘。
- 保存用同目录 `mkstemp` 临时文件 + `fsync` + `os.replace` 原子替换；
  任何失败都删除临时文件，旧记录字节不变（`test_replace_failure_keeps_previous_record_and_cleans_temp`）。

## 校验（不可信历史）

| 类别 | 规则 |
| --- | --- |
| 版本 | 必须是整数 `1`（`True`/`"1"`/`2` 均拒绝） |
| 模式 | `compare`/`internal`；`expected_mode` 与记录不符即拒绝 |
| 类型 | 所有字段严格类型；`bool` 不算 `int`；计数为非负整数 |
| 路径 | 必须绝对路径；`realpath` **失败即拒绝**（不回退词法，防止链接越界 fail-open）；条目 `path` 必须位于其 `root` 内，`root` 必须是本次 A/B 之一 |
| 根 | A/B 相同、互相嵌套拒绝；`internal` 只有一个根 |
| 分组角色 | `compare`：keeper 属 A、duplicates 属 B；`internal`：全部属单根；keeper 与副本大小须等于分组 `size` |
| 分组完整性 | 保留项不得跨组重复；目标不得跨组重复；目标不得等于任何保留项；mismatch 的 other 不得是回收目标；分组 `sha256` 必须 64 位小写十六进制 |
| 行状态 | 键必须是 `result` 中真实存在的行；角色决定允许的状态集合（目标= pending/recycled/skipped/failed/cancelled/processing，保留项= keep，mismatch= mismatch，issue= issue）；`status_skipped|reason`、`status_failed|reason`、`status_issue|stage|message` 前缀校验 |
| 勾选 | 只有「目标 + status_pending」允许 `checked=True`；记录声称勾选了保留/异常/已处理行时**归一化为 False**，绝不报错放行 |
| JSON | 拒绝重复键、`NaN/Infinity`、非 UTF-8、语法错误、嵌套过深 |
| 规模 | 文件 ≤ 64 MiB；分组 ≤ 20 万、mismatch ≤ 20 万、issue ≤ 50 万、row_states ≤ 100 万、路径 ≤ 32767 |

`stale` 是 schema 的强类型字段（`bool`），保存与读取都保留，不再恒为 False；
是否允许回收由页面读取后的守卫决定，本模块不做放行。

## 安全语义

- 读写记录**不访问媒体内容**、不 stat 文件、不调用 `send2trash`；历史路径已删除仍可导入展示
  （`test_deleted_history_paths_still_importable`）。
- 历史快照的 `size`/`mtime_ns`/`file_id`/`sha256` 原样保留，但**不代表已复核**；
  导入后回收仍走 `duplicate_scan_core.revalidate_pair`（GUI 强制 `byte_verify=True`）。
  回归：导入后修改 target → `target_changed`/`content_differs` 且 mock 的 `send2trash` 未调用；
  删除 target → `target_missing`；未改动文件才会回收。

## 与页面 worker 的接口

现页面已在用 `from scan_record_core import MODE_COMPARE, ScanRecord, load_record, save_record`，
签名与冻结契约一致。注意：`row_states` 现在会按行角色校验，页面若把 **A 侧的
mismatch 保留项**也写进 `row_states`，请用 `status_mismatch` 角色（取保）；
只写目标和异常项即可。

## 未覆盖边界

- 未做真实 OneDrive/云占位文件的导入回放（仅本地临时目录）。
- 路径归属基于 `realpath` 与 `commonpath`；跨盘符 `commonpath` 抛 `ValueError` 视为不归属（符合预期），
  但未在双盘符机器上做集成验证。
- 未接入 GUI 冒烟（属 pages 工作包）。
