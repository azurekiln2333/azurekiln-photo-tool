# 管理员权限拖拽提示

## Goal

在所有功能页标题下方内嵌一条微软 Fluent 风格提示条，当程序以管理员权限（elevated）运行时提醒用户
Windows UIPI 会阻止从资源管理器拖入文件；同时保留 merge 页已有的拖拽健壮性改进。

## 背景

用户反馈「所有页面都拖不进文件，突然就这样」。排查结论：

- 程序内部事件链路（`eventFilter` → `add_dropped_paths` → `DropScanWorker`）在 offscreen 与真实
  windows 平台下均验证正常，可成功加入列表。
- 真因是 **Windows UIPI（用户界面特权隔离）**：程序以管理员（High 完整性，RID 12288）运行时，
  普通权限的资源管理器（Medium，RID 8192）无法向该进程投递 OLE 拖拽数据。
- 因此需要主动提示用户「用普通权限重新启动」，而不是让用户误以为程序坏了。

## Requirements

### R1 权限检测

- Windows 平台检测当前进程是否 elevated。
- 非 Windows 平台直接跳过（不显示提示）。
- 检测失败（异常）时视为非 elevated，不显示提示，不得抛异常影响启动。

### R2 提示位置与形态（微软 Fluent 风格）

- 提示为**内嵌内容**，位于页面标题/副标题**下方**，随页面内容排布。
- 不使用弹窗（QMessageBox），不使用浮层 InfoBar overlay。
- 视觉遵循 Fluent：浅色圆角背景 + 图标 + 文字，区分 info/warning 语义；浅色主题下可读。
- 仅在 elevated 时显示；非 elevated 时该控件完全隐藏（不占位、不残留空白）。

### R3 覆盖入口

需要覆盖以下入口（独立运行与 unified 内嵌都要有）：

- `merge_live_photo_gui.py`
- `split_huawei_live_photo_gui.py`
- `timestamp_fix_gui.py`
- `rename_photo_gui.py`
- `dedupe_media_gui.py`
- `main_gui.py`
- `unified_gui.py`（设置页标题下方）

### R4 文案

- 中英双语，跟随各页现有 `TRANS`/`TRANSLATIONS` 机制与语言切换（`_apply_language`）刷新。
- 中文：`检测到程序以管理员权限运行。Windows 会阻止从资源管理器拖入文件，如需拖拽请以普通权限重新启动。`
- English：`Running as administrator. Windows blocks drag-and-drop from File Explorer; restart without elevation to enable drag-and-drop.`

### R5 保留既有改进

- 保留 `merge_live_photo_gui.py` 已完成的拖拽健壮性改进：
  - `_drag_paths()`：URL 优先，退化为解析 `text/plain` 中的本地路径。
  - `DragEnter/DragMove` 仅在非忙且能解析出路径时接受，光标与真实行为一致。
  - `Drop` 处于忙状态时给出明确提示，不再静默忽略。
  - 新增 `busy_title` / `busy_content` 中英文案。

### R6 复用

- 权限检测与提示条构建应抽成可复用单元（单一实现），避免在 7 个入口重复粘贴逻辑。

## Acceptance Criteria

- [ ] AC1：以管理员权限启动任一入口，标题下方出现内嵌提示条；以普通权限启动，不出现且无空白占位。
- [ ] AC2：提示条位于标题/副标题下方，为页面内嵌内容，非弹窗、非 overlay 浮层。
- [ ] AC3：7 个入口全部覆盖（6 个功能页 + unified 设置页）。
- [ ] AC4：中英文案正确，切换语言后提示文案随页面刷新。
- [ ] AC5：非 Windows 或检测异常时，不显示提示且不影响程序启动。
- [ ] AC6：merge 页原有拖拽改进（R5）保留且功能正常。
- [ ] AC7：`python -m compileall` 或等价语法检查通过；无新增运行期异常。
- [ ] AC8：本次改动以标准化 commit 提交（遵循仓库 `fix:`/`feat:` 前缀风格）。

## Constraints

- 不引入新第三方依赖，复用现有 `qfluentwidgets` / `PyQt6`。
- 不改变现有页面布局主结构，仅在标题区追加一个可隐藏的控件。
- 不修改拖拽核心数据流（`DropScanWorker` 等）。

## Notes

- 轻量任务：PRD-only。
- 相关文件：`merge_live_photo_gui.py`、`split_huawei_live_photo_gui.py`、`timestamp_fix_gui.py`、
  `rename_photo_gui.py`、`dedupe_media_gui.py`、`main_gui.py`、`unified_gui.py`。
