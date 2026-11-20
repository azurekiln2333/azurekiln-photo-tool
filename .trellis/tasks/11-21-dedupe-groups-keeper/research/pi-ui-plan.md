# Pi UI 实施研究计划：类型分组与自主保留副本

状态：planning 阶段的只读研究与 UI 计划；**未改产品/测试源码、未激活任务、未启动子代理**。实施须等 root 明确指令及 p4 冻结 `research/contracts.md` 后进行。

## 1. 已读输入与规范

- 任务：`prd.md`、`design.md`、`implement.md`、`implement.jsonl`、`check.jsonl`。
- 指引：
  - `.trellis/spec/pyqt/page-structure.md`：行索引需稳定，筛选用 `setRowHidden`，不重建模型/表格。
  - `.trellis/spec/pyqt/threading-and-workers.md`：后台 worker 通过信号，finished 清理后再开放下一任务；实际按钮 `.click()` 验证。
  - `.trellis/spec/pyqt/translations.md`：所有新增文案中英齐全并接入 `_apply_language()`。
  - `.trellis/spec/python/duplicate-verification.md`：唯一 keeper、完整哈希与逐字节确认；回收仍由 `recycle_duplicate` 执行前复核。
  - `.trellis/spec/python/scan-records.md`：schema v1 中角色由 `result.groups` 决定，row_states 仅路径→状态；只有 pending target 可 checked；旧 v1 记录需保持可读。
  - `.trellis/spec/pyqt/quality-guidelines.md`、`.trellis/spec/python/quality-guidelines.md`：独立/内嵌、中英、外部依赖隔离、跨盘 TEMP 和全量回归要求。
- 核心现状：`duplicate_scan_core.py` 暴露统一 `MEDIA_EXTENSIONS`，但照片/视频/其他分类及组内 keeper 重选尚待 p4 通过 `research/contracts.md` 定名并冻结。本计划不猜测该 API 名称。

## 2. 当前 UI 数据流（`folder_dedupe_gui.py`）

- `DedupeRow` 以平铺列表表达一个组：先 keeper 行，再 duplicate 行；`group_id` 将行映射回扫描组。`start_recycling()` 枚举这份列表，并把**原始行索引**交给 worker 回写 status。
- `DedupeTableModel.DecorationRole` 对任何 `primary_path()` 调 `_thumbnail_for()`；后者无类型限制，直接 `thumbnail_loader.request(path)`。
- `_refresh_preview()` 当前对所选路径和 keeper 路径都调用 PreviewPanel；没有「其他」清空/不发加载请求的策略。
- `_path_cells` 是路径→稳定 `(row_index, column)` 映射，thumbnail_ready 依此刷新。
- `_selectable_rows()` / `select_all_checkable()` / `select_none_checkable()` / `invert_checkable()` 当前遍历全表。需在现有逻辑上增加可见行条件，而非复制新批量体系。
- records：`_build_record()` 保存完整 ScanResult + 按路径生成 row_states；`_apply_imported_record()` 先由 result 重建行，再恢复 checked/status。 keeper 角色必须真实改动 `ScanResult.groups`，不能只改展示行。

## 3. 实施建议（待 root 批准后执行）

### 3.1 照片 / 视频 / 其他筛选

- 新增三个清晰筛选控件/标签，显示**两个独立计数**：当前分类包含的重复组数，以及当前显示文件行数（keeper + duplicates；另明确 mismatch/issue 按自身路径分类并显示）。默认选首个非空类别；空类别仍可切换并展示 0。
- 每个 `DedupeRow` 或同长度旁路数组保存 category，保证 `category[row_index]` 与 model 行和 worker 回写索引永久对齐；任何筛选只 `table.setRowHidden(row_index, category != active_category)`，不 reset rows、不排序、不代理映射行号。
- 一个组保持整体显示/隐藏，不因 keeper 变化而拆组。混合扩展名组的分类按设计固定优先级 `photo > video > other`，基于组的成员路径集合计算，不随 keeper 候选变化；独立 mismatch/issue 使用其自身路径分类。具体类型判定调用 p4 冻结接口。
- 切换筛选只隐藏行，不改变任何路径的 checked/status；切走再切回状态完全保留。当前分类内的全选/全不选/反选仅循环“可见且 model `_checkable(row)`”行。已隐藏类别的历史 checked 保持原状；回收确认仍报告全页总已勾选数，实际回收继续传稳定源 row_index。

### 3.2 非媒体预览门禁

- `_thumbnail_for(path)` 在调用 loader 前用冻结的类型 API 判断，非 photo/video 直接返回 `None`，保证其他文件的 DecorationRole **不产生任何 loader 请求**。
- `_refresh_preview()` 先按当前选中行自身的类型决定策略：选中为 other 时调用 `preview_panel.clear()` 并立即返回，两个槽都不显示/请求旧图（不因该组 keeper 偶然是媒体而留下图）。issue/mismatch 同样以用户当前选中路径归类。
- 对 photo/video 保留现有 PreviewPanel、loader 公共接口与缩略图刷新路径；切换筛选时若当前行被隐藏，应选择当前可见的有效行或清空预览，不能展示隐藏项的旧图。行为应在合同/PRD确认后确定并测试。

### 3.3 “设为保留”真实入口与状态转换

- 加一个显眼的 `btn_set_keeper`，放在现有批量操作行（建议紧邻反选按钮）；仅当当前选中行是本组 pending duplicate 且页空闲、结果未取消/失效、组没有已处理成员、候选快照有效时启用。可在右键菜单增加同义入口，但按钮是必要的真实点击入口。
- 点击后调用 p4 在 `research/contracts.md` 冻结的**纯内存 keeper 重选 API**同步 `ScanResult.groups[group_id]` 的 keeper 与 duplicates；禁止 UI 重写 hash/bytes 判定，禁止仅改表格显示。
- 不重建 `table_model.rows`，使 worker row index、筛选隐藏和选择稳定。按路径重用原 row：B 新 keeper → role keeper/kind keeper、`keeper=B`、unchecked、`status_keep`；A 旧 keeper → role duplicate/kind duplicate、`keeper=B`、pending 并默认 checked；其余 C 的合法 checked/status 保持；所有同组行 `keeper` reference 指向 B。发受影响行区间 dataChanged，刷新当前预览、总结及 action enablement。
- 不允许从别的组、mismatch、issue、已处理/正在处理行提升 keeper；候选须仍存在且 size/mtime 快照匹配。界面不做哈希/逐字节读取，实际回收仍走核心 revalidate+byte_verify。候选快照验证是否有纯内存/元数据 helper，按 p4 合同接线；避免主线程读取媒体内容。
- 结果组从 A/B/C 改为 B/A/C 后导出自然保存新角色；导入后以已验证 `result.groups` 重建行，所以不需要改 v1 schema。旧 v1 文件缺少新 UI category 时仍可通过当前 type helper 衍生显示。

### 3.4 记录与批量选择

- 修改 keeper 后 `row_states` 按绝对路径生成；角色由更新后的 result groups 决定。A/B checked/status 反映转换规则，C 等其它路径状态保持；导入时只接受 keeper/target 状态与角色相符的 row_states。
- 已处理组不可通过切换而被恢复为待处理：在整组 transition 前检查 keeper 与全部 duplicates 的状态；任一 `recycled/skipped/failed/processing/cancelled` 或 stale/cancelled scan 均拒绝。
- 批量 helper 扩展为“可见 + 合法”；单行 checkbox 模型的 `_checkable` 不受过滤器影响（隐藏行仍可在切回来后操作），但实际点击与批量动作仅影响活动类别可见项。`select_none` 只取消当前显示类别，不隐式改隐藏项。

## 4. 必须先等 p4 冻结的接口问题

实际 names/signature 以 `research/contracts.md` 为准，未见契约前不能在代码中自行假设。契约至少应回答：

1. 路径分类函数如何区分 photo/video/other，以及混合组应用 `photo > video > other` 的公共 helper。
2. 组内重新指定 keeper 的参数（result/group identity/candidate path），对 candidate 不属组、组状态不安全、快照不匹配、重复/跨组身份的拒绝方式；返回值是否含旧/新 keeper 与 duplicates。
3. 重选 API 对 `DuplicateGroup` 可变性及原列表顺序的保证；要求保留稳定组索引/组 ID。
4. API 不得修改 checked/status/UI 或执行 I/O；可能阻塞的 stat 检查在哪一层做并如何报告失败。
5. 混合类型同组分类规则与枚举的拼写固定值，供 GUI 和测试共用。

## 5. 测试矩阵（实施获批后）

全部使用临时目录、隔离 APPDATA/LOCALAPPDATA、offscreen、mock 回收；`sys.excepthook` 捕获 Qt 槽错误。点真实筛选、设 keeper、全选/取消/反选按钮；无 `sleep` 驱动 race。

1. **筛选与稳定索引**：生成 jpg/mp4/txt 多组临时同内容文件并真实扫描；断言三类 group/file 计数正确、默认类别稳定；筛选前后 model row 数/对象顺序不变、同组全显/全隐、worker status 用原索引回写正确。
2. **混合类型**：同一字节内容分别使用 photo/video/other 后缀组成一组，分类优先级固定 photo；切 keeper 不改变该组分类。
3. **other 预览无副作用**：spy/mock `thumbnail_loader.request` 和 PreviewPanel `set_slot`；other 行 DecorationRole 不请求 loader；点击其他筛选/选中其他行后 preview.clear 被调用、旧图消失、两槽零 request。媒体行仍可正常预览。
4. **keeper A/B/C**：真实扫描默认 A，设置 C checked 状态后选 B 并点真实 `btn_set_keeper`；断言 `ScanResult` keeper=B，B 受保护且未勾，A 成 pending/可勾选，C 原 checked/status 保留，所有同组 row.keeper=B，原 row indexes/隐藏分类不变。Patch recycle core 捕获真实 worker pair，证明 A 作为 target 时 keeper 参数为 B；不调用真实 `send2trash`。
5. **不可切换矩阵**：busy / cancelled / stale / mismatch / issue / 非本组 / 文件缺失或 size/mtime 变化 / 组内已处理任一状态均拒绝，ScanResult 与所有行状态不变。
6. **可见批量范围**：按 A 类勾选 → 切 B 类反选/全不选，验证只影响当前可见合法 duplicate，隐藏类别选择保留；keeper/issue/mismatch/processed 行永不变化；actual clicks。
7. **记录往返与旧 v1**：选择 B、状态调整后导出→导入，验证 keeper=B、A/C 每条路径角色与 checked/status 复原；旧 schema v1 fixture 无 category 字段照常导入并衍生分类；坏角色记录拒绝且当前显示不变。
8. 中英切换所有新增控件文案；独立与内嵌布局验证，不真实回收，不访问真实媒体。

## 6. 范围和协作边界

- 本 Pi 后续实施只改 `folder_dedupe_gui.py`；测试 owner 是 pA，核心 owner 是 p4，发布/独立 review owner 是 pB。页面按冻结合同集成，不改核心、tests、manifest 或版本发布文件。
- 当前任务仍为 planning；此文档仅给 root review。没有获明确 start/实施指令前，不修改任何产品或测试源码、不切任务状态、不触发 herdr、模型/供应商或工作区操作。
- root 明确批准进入执行后，优先向 w55:p4 读取合同状态，并同 pA 对齐筛选/按钮/spy 断言；不 nested-spawn，不提交、推送或打 tag。
