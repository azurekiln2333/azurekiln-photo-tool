# pA GUI 回归测试计划：目录内去重分组与自主保留副本

任务：`.trellis/tasks/11-21-dedupe-groups-keeper`
角色：pA / GUI 回归测试
测试所有权：`tests/test_folder_dedupe_features.py` 及必要的专项 GUI 测试。
当前阶段：planning；本次只读研究和计划，不修改产品源码或测试源码，不启动子代理，不激活/归档任务。

## 1. 研究结论与冻结边界

### 已确认的稳定边界

- 页面入口是 `folder_dedupe_gui.MainWindow`，同时支持独立模式和 `embedded=True` 内嵌模式。
- 扫描必须通过真实 `btn_scan.click()` 启动 `DedupeScanWorker` / `QThread`；测试不得只调用 `_apply_scan_result()` 伪造“扫描成功”。
- 当前行模型是 `DedupeRow`，角色包括 `keeper`、`duplicate`、`mismatch`、`issue`；`DedupeTableModel` 负责勾选权限和行状态展示。
- 真实回收入口是 `btn_recycle.click()`，回收 worker 每项应继续调用共享核心 `recycle_duplicate(target, keeper, byte_verify=...)`；测试只 mock `duplicate_scan_core.send2trash` 或页面的核心调用，不接触真实回收站。
- 记录边界是无 Qt 的 `ScanRecord` / `save_record()` / `load_record()`，模式必须是 `internal`，`root_b` 为 `None`；导入是完整解析成功后才替换页面显示。
- 线程验证必须覆盖 scan、recycle、record I/O 的 `_is_busy()`、finished 清理和关闭协议；`QThread.isRunning()==False` 但引用尚未由 finished 清除时仍属于 busy。
- 所有 GUI 回归使用标准库 `unittest`、offscreen Qt、隔离 `APPDATA`/`LOCALAPPDATA`、临时目录和有界事件循环；捕获 `sys.excepthook`，DeferredDelete 后再断言没有 Qt 槽异常。

### 当前不能猜测、必须等 p8/p4 契约确认的 API

设计明确要求 p4 在 `research/contracts.md` 冻结核心接口，pA 不在契约出现前猜名称或签名。以下内容暂不写入测试实现：

1. 媒体类型判断函数/常量的模块路径、函数签名和返回值（photo/video/other 的规范值）。
2. “同一重复组”稳定身份的字段（当前 `group_id` 是否足够，还是需要核心 group key）。
3. 切换 keeper 的核心函数名称、参数、返回对象，以及它是原地更新 `ScanResult` 还是返回新结果。
4. keeper 切换是否允许直接使用当前内存 `FileEntry`，以及对已处理组、取消/失效结果、快照变化的拒绝错误类型。
5. p8 提供的分组筛选控件对象名、按钮对象名、当前分组状态字段和“设为保留”入口；测试只在契约确定后绑定这些对象，不用字符串查找或私自调用未确认方法。
6. 非媒体“其他”行的预览抑制接口：需要确认是模型 `DecorationRole` 不请求、`_thumbnail_for` 过滤，还是 `_refresh_preview` 清空；测试按外部可观察行为（loader 无请求、旧预览清空）锁定，不依赖未冻结私有实现。
7. dynamic keeper 写入记录时的角色/row_states 规则，尤其是旧 keeper 变成 pending 后默认勾选是否由核心规定，还是由页面保存前计算。

在上述契约落地前，不新增测试源码；本文件是实现 gate。

## 2. 测试 fixture 设计

### 2.1 临时目录与数据

每个测试使用独立 `TemporaryDirectory`，根目录为 `album/`，不使用真实用户目录。准备至少三组内容：

- **照片组**：A/B/C 三个相同内容的 `.jpg` 文件；用于 keeper 从 A 切到 B，验证 A/B/C 角色变化。
- **视频组**：至少两个相同内容的视频后缀文件（内容可为测试占位字节，若预览实现要求真实视频则使用仓库已有最小样例或 p8 契约指定 fixture）。
- **其他组**：至少两个相同内容的非媒体扩展名（例如 `.bin`/`.dat`），用于“其他”分组和无预览。

另加：

- 一个不重复文件，确认不会被错误归入重复组；
- 可选 mismatch/issue 行，用于批量选择保护；若核心不便稳定构造，则使用已确认的 `ScanResult` 测试 fixture，但仍通过页面真实按钮验证批量动作；
- 每个组至少 3 个副本，保证“保留 A、目标 B、目标 C”的角色切换有明确断言。

文件内容必须保证大小、SHA-256、逐字节相同；不在页面测试里自写扫描/哈希逻辑。fixture 只负责写文件和等待真实扫描。

### 2.2 通用测试辅助

待实施时补充到 `tests/test_folder_dedupe_features.py` 的最小 helper：

- `QApplication` 单例和 `offscreen` 环境初始化；
- `_pump(predicate, timeout)`：持续 `processEvents()`，超时失败，不使用无限等待；
- `run_real_scan(root)`：填入 `root_edit`，调用 `btn_scan.click()`，等待 `_scan_thread is None` 且页面不 busy；断言扫描结果存在；
- `export_via_button()` / `import_via_button()`：mock `QFileDialog`，实际点击导出/导入按钮，等待 `_record_thread is None`；
- `close_and_drain()`：请求关闭、等待所有 worker 引用清理、发送 DeferredDelete，再检查槽异常；
- `FileEntry` fixture helper 仅用于构造核心允许的记录/坏记录测试，不代替真实扫描验证；
- 用 `mock.patch.object(duplicate_scan_core, "send2trash", ...)`，因为核心导入的是自己的 alias，不能只 patch `send2trash` 包模块。

不使用 `os.path.relpath()` 假设临时目录和仓库同盘；相对路径测试必须在临时根内有恢复保证的 cwd 上下文，或直接使用绝对路径。

## 3. 验收测试矩阵

### A. 分组与数量（R1）

**测试目标**：照片、视频、其他三组可独立查看；组边界不被拆散；文件数和重复组数含义明确。

步骤：

1. 真实点击开始扫描，等待完成。
2. 通过 p8 契约确认的三个分组按钮逐个 `click()`。
3. 断言当前可见行/隐藏行和当前组统计与 fixture 对应。
4. 每个重复组的所有行拥有同一稳定组身份；切换组不会重建 source row，不改变后台回写索引。
5. 断言默认进入首个非空组（具体首组顺序按契约，不在测试中硬编码实现细节）。

禁止只断言按钮存在；必须断言实际显示数据和组边界。

### B. “其他”不请求预览（R2）

**测试目标**：选择其他文件/其他分组时，不请求缩略图或详情预览，旧图片清空。

步骤：

1. 真实扫描后先选择照片或视频行，建立一个可观测的预览/缩略图请求。
2. 用真实分组控件切到“其他”；选中其他行。
3. 用 loader `request` spy 记录调用，断言切换和选择其他行期间没有对该行发起请求。
4. 断言 `PreviewPanel` 两侧/选中预览被清空或进入明确的“无预览”状态；不得残留上一行图像。
5. 切回照片/视频，确认仍能按该路径类型正常请求（防止通过全局禁用预览取得假通过）。

测试不依赖具体 thumbnail 私有缓存字段；只观察 loader 调用、panel slot 路径/清空状态。

### C. 自主切换 keeper 与回收参数（R3/R6）

**测试目标**：A/B/C 默认 A；切到 B 后只有 B 受保护，A 可回收，C 的合法状态保持；实际回收 worker 把 B 作为 keeper。

步骤：

1. 真实扫描三副本照片组，定位同一组的 A/B/C 行。
2. 确认默认 keeper 是 A，A 为 `keeper/status_keep`，B/C 为 duplicate/pending。
3. 预先记录 C 的 checked 状态，然后通过真实“设为保留”入口选择 B 并点击。
4. 断言核心结果组的 keeper 路径为 B，duplicates 只含 A/C；不是只改变表格文字。
5. 断言 B 不可勾选；A 变为合法 pending 目标；C 的 checked 状态按契约保留；组内 keeper 引用同步到所有相关行。
6. 通过真实回收按钮点击，mock 确认框为 Yes，并让实际 `DedupeRecycleWorker` 在线程中运行；捕获传给 `recycle_duplicate` 的 `(target, keeper)`，断言待回收目标包含 A（以及按 C 状态决定的 C），每项 keeper 都是 B。
7. `byte_verify` 断言保持页面设置语义；若记录来源为 imported，必须强制为 True。
8. mock `duplicate_scan_core.send2trash`，不允许真实回收；同时验证回收前复核仍走核心，文件变化/删除时不调用 send2trash。

若 p8 的切换入口不是按钮而是右键动作，测试仍必须使用用户可点击的真实 QAction/按钮，不直接调用切换私有方法。

### D. 当前组批量勾选与保护（R4）

**测试目标**：全选、取消全选、反选只作用当前显示分组的合法 pending 副本；隐藏分组、keeper、异常、碰撞、已处理、取消、失效不被改变。

步骤：

1. 真实扫描后把至少两个组设置为不同 checked 状态。
2. 通过真实分组按钮切到其中一个组，分别点击“全选”“取消全选”“反选”。
3. 断言当前组合法 duplicate 行按操作变化；当前组 keeper 不变；隐藏组的 checked 状态完全保持。
4. 构造或扫描出 mismatch/issue/已处理行，断言三种按钮均不改变其 checked 状态。
5. 在 stale/cancelled 状态下真实点击批量按钮，断言按钮 disabled 或操作被拒绝，且没有行获得回收资格。
6. 若保留 Ctrl+A，则实际发送/触发快捷键，不能只直接调用批量方法。

核心断言应基于 `row.is_checkable()` / 已冻结的页面权限，不用“所有 duplicate 行都可勾选”这种过宽断言。

### E. 记录往返、旧记录、坏记录与状态保护（R5）

#### E1. 动态 keeper 往返

1. 真实扫描 A/B/C，真实切 keeper 为 B。
2. 真实点击导出；记录必须保留更新后的 `result.groups` keeper/duplicates、完整指纹和每路径 row state。
3. 清空当前结果，真实点击导入。
4. 断言 B 恢复为 keeper，A/C 角色和 checked/status 恢复；`_record_imported=True`；随后真实回收仍强制 `byte_verify=True`。

#### E2. 已处理状态计数

构造一个合法记录，给 duplicate 行分别设 `status_recycled`、`status_skipped|...`、`status_failed|...`，再通过真实导入按钮导入。断言：

- 行状态恢复；已处理行不可勾选；
- `_recycled_count` / `_skipped_count` / `_failed_count` 按行状态恢复，而不是全部归零；
- 汇总文字与计数一致；
- keeper 不会因 row_states 的 checked 字段获得回收资格。

#### E3. 旧 v1 记录

使用 schema v1、未包含新字段/动态切换信息但符合 p4 兼容契约的旧 internal 记录 fixture，通过真实导入按钮读取；断言旧默认 keeper、分组和 pending 状态仍可展示。不得通过放宽 `load_record` 校验或跳过测试实现兼容。

#### E4. 坏记录保留原表

对错误模式、越界路径、重复目标、keeper/target 相交、未知状态、损坏 JSON 各至少覆盖一种。导入失败后断言原表行数、角色、checked/status、当前结果引用保持不变；不先清空再报错。

### F. busy / stale / cancelled / 关闭（R5/R6）

- **busy**：真实扫描、记录导入/导出、回收期间，所有互斥入口禁用；线程引用存在但 `isRunning()` 已变 False、finished 尚未清理时仍 busy，不能覆盖旧引用。
- **stale**：触发 p8 定义的 keeper/策略变更使结果失效；断言分组切换、keeper 切换、批量选择和回收均禁止；已有勾选不会因 stale 重新获得资格。
- **cancelled**：真实停止扫描或导入 `ScanResult.cancelled=True` 记录；断言不可批量勾选、不可回收、导入后标记不丢失。
- **关闭**：独立模式和内嵌模式都触发关闭；记录 I/O 或回收线程未完成时窗口保持存活，后台完成并 finished 清理后才关闭；事件循环有超时，DeferredDelete 后无槽异常。

### G. 独立 / 内嵌与中英（R7）

1. 分别构造 `MainWindow(embedded=False)` 与 `MainWindow(embedded=True)`；两者都完成无头构造、真实扫描按钮和分组/批量控件布局基本检查。
2. 内嵌模式不显示独立语言下拉，但由统一 GUI/`_apply_language()` 传播语言；不因隐藏控件留下异常占位。
3. 真实切换 zh → en → zh，断言新增分组、数量、keeper、筛选、批量、导入导出、状态按钮文案均更新；不出现原始 translation key。
4. 关闭两种页面并清理线程；不依赖真实 ExifTool/ffmpeg/send2trash。

## 4. 预计测试组织

在现有 `tests/test_folder_dedupe_features.py` 中按以下类组织，实际命名待 p8 契约确定后调整：

- `FolderDedupeGroupingTests`：R1/R2，组统计、其他禁预览、切组保留 source row 映射；
- `KeeperSwitchTests`：A/B/C 角色切换、真实回收按钮与 worker 参数、变化/删除安全；
- `FolderDedupeSelectionTests`：当前组全选/全不选/反选/Ctrl+A 和保护行；
- `FolderDedupeRecordTests`：动态 keeper 往返、旧记录、坏记录、状态计数；
- `FolderDedupeLifecycleTests`：busy/stale/cancelled/线程引用/关闭；
- `FolderDedupeLayoutLanguageTests`：独立/内嵌和 zh/en；
- 已有 `RecycleWorkerVerifyTests` 保留，并扩展为确认动态 keeper 参数，而不是替换为只测构造函数的弱断言。

如果 p8 的实现提供了更少或不同的公共控件名，先更新本计划的“待确认契约”记录，再修改测试；不得在测试中通过 `getattr(..., fallback)` 兼容未知 API，因为那会掩盖实现缺失。

## 5. 验证命令与门禁

目标测试文件实现后：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:APPDATA = (Join-Path $env:TEMP "folder-dedupe-test-appdata")
$env:LOCALAPPDATA = (Join-Path $env:TEMP "folder-dedupe-test-local")
.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -p "test_folder_dedupe_features.py" -v
```

再运行：

```powershell
.venv/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -q
.venv/Scripts/python.exe -m compileall -q tests/test_folder_dedupe_features.py
git diff --check
```

验收证据必须包括：真实按钮点击、真实 Qt 事件循环、真实 scan/save/import/recycle worker 生命周期；只 mock 外部回收副作用和与被测功能无关的外部工具。禁止以 `skip`、`expectedFailure`、取消断言或无限延长 timeout 掩盖失败。

## 6. 实施前 review gate

pA 等待以下条件后才能进入 execute：

- p4 的 `research/contracts.md` 已冻结类型分类和 keeper 重选 API；
- p8 的实现已出现，且明确三组控件/keeper 入口/非媒体预览抑制行为；
- 主会话确认任务从 planning 进入 in_progress，并明确允许写 `tests/test_folder_dedupe_features.py`；
- 当前工作区其它 Pi 的修改不被覆盖，pA 只改测试所有权文件。

当前结论：测试范围、fixture、真实按钮/线程/安全断言和未知接口清单已完成；在 p8 API 确认前不应开始编码测试。
