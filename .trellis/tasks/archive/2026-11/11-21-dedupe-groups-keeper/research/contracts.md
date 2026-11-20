# 核心 / 记录契约（冻结实施版）

状态：已按 root 明确批准冻结，供 core 实现和 p8 GUI 接入。核心保持标准库、无 PyQt；扫描记录维持 schema v1。本文限定核心接口和安全边界，不定义 GUI 的交互细节。

## 1. 现有契约与变更范围

- `duplicate_scan_core.py` 的 `MEDIA_EXTENSIONS` 是现有 media scope 的唯一媒体白名单，共 55 个后缀；本任务只为它们分类，不改变扫描过滤、判重或回收流程。
- `DuplicateGroup` 是 cross/internal 两页共享模型。cross 模式 keeper 必来自 A、duplicates 必来自 B；internal 模式所有成员来自同一根。keeper 重选仅允许 internal 语义，不得改变 compare 的 A/B 角色。
- 扫描已用 size + SHA-256 + 逐字节比对确认组内相同；重选 helper 不重新扫描、不重算 hash、不证明磁盘当前内容仍一致。
- `scan_record_core.py` schema v1 已保存 groups 中的 keeper/duplicates 和按绝对路径索引的 row_states；新关系可由现有结构表达，不需要 schema 或 record-core 变更。

## 2. 冻结的媒体分类 API

```python
from typing import Literal

MediaType = Literal["photo", "video", "other"]

def classify_media_type(path: Path | str) -> MediaType: ...

def classify_duplicate_group(group: DuplicateGroup) -> MediaType: ...
```

### 2.1 `classify_media_type`

- 只看路径文件名最后一个扩展名，大小写不敏感；不 `stat/open`、不解析链接、不读取媒体内容、不依赖 Qt。
- `VIDEO_EXTENSIONS` 是 `MEDIA_EXTENSIONS` 子集，共 22 项：
  `.mp4 .mov .m4v .avi .mkv .3gp .3g2 .wmv .mts .m2ts .m2t .mpg .mpeg .flv .f4v .webm .ts .mxf .vob .asf .rm .rmvb`。
- `MEDIA_EXTENSIONS - VIDEO_EXTENSIONS`（33 项，含普通照片、动图及 RAW）归类为 `photo`。
- 不在 `MEDIA_EXTENSIONS` 中的后缀、无扩展名和点文件（如 `.profile`）归 `other`。本任务不拓展现有格式集。
- 分类只是浏览元数据，不意味着能/应该预览。GUI owner 对 `other` 必须禁止缩略图/详情加载并清除旧图。

### 2.2 `classify_duplicate_group`

- 分类输入为整组 keeper + duplicates，固定优先级 **photo > video > other**，结果不随 keeper 更换而变化，不拆组。
- 合法 schema v1 的 keeper-only 组（`duplicates=[]`）按 keeper 自身类型返回；这类组不能重选 keeper，但必须能分类和导入。

## 3. 冻结的纯内存 keeper 重选 API

```python
def reselect_internal_keeper(
    group: DuplicateGroup,
    new_keeper: FileEntry,
) -> DuplicateGroup: ...
```

语义：从已有 internal 组成员中重选 keeper；返回新的 `DuplicateGroup`，不修改输入对象或原 duplicates 列表。sha256/size 保持不变；剩余成员（包括旧 keeper）成为 duplicates，并按核心现有大小写不敏感路径规则确定性排序。

### 3.1 输入约束和失败语义

- group 必须非空（至少一个 duplicate）；keeper/duplicates 成员及候选必须是 `FileEntry`。
- group 所有成员 root 词法规范化后必须相同（`normpath + normcase`，不解析/触碰磁盘）；因此有效 cross 组（A keeper、B targets）被拒绝，不会反转 A/B。
- 所有成员 `size == group.size`，成员 path 唯一（按平台大小写语义规范化）。
- `new_keeper` 必须匹配组内一个成员的完整扫描快照：规范化 path/root、size、mtime_ns、file_id；候选不属于组或指纹不一致时抛 `ValueError`。返回时采用组内该成员对象。
- 结构不合法时抛 `ValueError`；不部分修改输入。

### 3.2 明确不做的事

- helper 不做文件系统 I/O：不 `exists/stat/open`，不计算 SHA，不读文件字节。
- helper 不判断文件是否已删除/修改，也不是回收授权。GUI 在启用交互时按 PRD 检查 busy/stale/cancelled、当前组和候选快照；所有回收仍必须调用 `recycle_duplicate(..., byte_verify=True)` / `revalidate_pair` 做执行前重新验证。
- helper 只转换单个 group；不改变 `ScanResult` 的 issues/mismatches/counters/cancelled，不改变模式，不处理勾选状态。

## 4. 记录兼容性（schema v1 不变）

- `scan_record_core.py` 不需要修改。重选结果直接写回 `ScanResult.groups[index]`；导出 `row_states` 仍以每个绝对路径的角色/状态描述界面状态。
- 新 keeper 应存为 `status_keep` 且 unchecked；旧 keeper 成为 pending target 的默认勾选由 GUI 实现；其它目标只保留合法 pending 状态。不得把已处理目标变成 pending。
- 现有 record validator 继续负责严格根/角色/重复目标和 checked 约束；导入记录仍强制逐字节回收复核。旧 schema v1 记录继续可读。
- 本次核心行为不要求更改 `tests/test_scan_record_core.py`；其既有 v1 round-trip/角色校验回归继续作为兼容门禁。

## 5. 核心测试要求（`tests/test_duplicate_scan_core.py`）

- `classify_media_type` 遍历 `MEDIA_EXTENSIONS` 全集，确认每个后缀恰属 photo 或 video；分别覆盖大小写、未知后缀、无扩展名、点文件、多后缀；使用不存在路径仍能分类，证明无 I/O。
- `VIDEO_EXTENSIONS` 必须是 `MEDIA_EXTENSIONS` 子集；集合外扩展名仍为 other。
- `classify_duplicate_group` 覆盖纯 photo/video/other、混合优先级、空组拒绝；keeper 重选前后整组类别不变。
- `reselect_internal_keeper` 覆盖三成员 A/B/C 切 keeper、原 group 与 list 不变、候选完整快照精确匹配、确定性剩余排序、same-root/size/唯一路径约束、foreign/伪造快照/cross-root compare 拒绝；用 mock 阻止 `Path.stat` / `open` 验证不做文件 I/O。
- 既有 cross/internal 扫描、三重验证、回收前复核、取消和 schema/dataclass 契约不得回归；核心不得引入 PyQt。

## 6. p8 GUI 接入边界

- 分类 tab 按 `classify_duplicate_group(group)` 归组，保持组边界；每个路径的预览权限仍按自身类型分类。
- 过滤只能隐藏行，不能重建表格/变更 worker 行索引。批量动作只作用于可见合法 pending targets，跨 tab 切换保留勾选。
- 重选前 GUI 检查忙、stale/cancelled、候选当前归属和磁盘快照，已处理组拒绝重选；更新 core group 与同组 rows/keeper refs/status/check/preview/summary 一致。
- 旧 keeper 默认勾选、new keeper 受保护、其它 target 保留原合法 checked 状态均由 GUI 实现；核心 helper 不处理 UI 状态。
- `other` 不发缩略图/详情请求，切换后旧图清除。新增文案需中英两种语言，独立/内嵌均验证。

## 7. 相关规格

- `.trellis/spec/python/duplicate-verification.md`：精确判重、keep/target 角色、回收前复核。
- `.trellis/spec/python/scan-records.md`：v1 group/row_states 严格校验、导入安全。
- `.trellis/spec/python/project-structure.md`、`error-handling.md`、`quality-guidelines.md`：核心无 GUI、显式拒绝结构错误、标准库测试。
- `.trellis/spec/pyqt/page-structure.md`、`threading-and-workers.md`、`translations.md`、`quality-guidelines.md`：稳定行映射、busy/线程约束、中英与独立/内嵌验收。

## 8. 实施状态

已按 root 授权并冻结以下 API：`classify_media_type`、`classify_duplicate_group`、`reselect_internal_keeper`。核心实现/回归位于 `duplicate_scan_core.py`、`tests/test_duplicate_scan_core.py` 与 `tests/test_scan_record_core.py`；`scan_record_core.py` 未修改，schema v1 保持兼容。

兼容性边界：合法 v1 keeper-only 组（`duplicates=[]`）由 `classify_duplicate_group` 按 keeper 类型返回；只有 `reselect_internal_keeper` 对无副本组抛 `ValueError("group_empty")`，因为无可重选 target。
