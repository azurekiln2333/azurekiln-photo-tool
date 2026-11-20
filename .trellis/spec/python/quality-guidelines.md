# 质量约定（核心逻辑层）

> 本项目实际的验证方式与验收标准。

---

## 自动回归与人工验证

本项目已有标准库 `unittest` 套件（`tests/test_duplicate_scan_core.py`），涉及精确判重和回收安全的变更必须运行。质量保证包括：

1. 标准库单元回归：`.venv/Scripts/python.exe -B -m unittest discover -s tests -v`
2. 语法检查（`compileall`，不能替代测试或类型检查）
3. 无头 GUI 冒烟测试（隔离 `APPDATA`，确认进程正常退出）
4. `sample/` 真实样例的回归验证

新增回归沿用标准库 `unittest`；不为本轮修复引入 pytest 等第三方框架。GUI 测试先设置 `QT_QPA_PLATFORM=offscreen` 和临时 `APPDATA`，再导入页面模块，禁止触碰真实相册或真实回收站。

---

## 验证命令

### 语法检查（改完必跑）

```powershell
.venv/Scripts/python.exe -m compileall -q <改动的文件>
```

### 无头 GUI 冒烟

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
# 并把 APPDATA 指向临时目录，隔离真实 settings
```

要点（见 `.workbuddy-ai/memory/MEMORY.md`）：
- `APPDATA` 指向临时目录，避免污染真实 `%APPDATA%\<APP_NAME>\settings.json`
- monkeypatch `QMessageBox.information`，否则模态框会**永久阻塞**
- 构造各页面 `MainWindow`，断言无异常

### GUI 关闭/集成测试的外部依赖隔离

构造「全功能统一窗口」的集成测试（如 `tests/test_unified_close.py`）会**初始化未受测页面**，这些页面可能依赖外部可执行工具（ExifTool、ffmpeg 等）或外部副作用库（send2trash），并可能弹出**模态**对话框。

- 必须隔离或替身**非受测**依赖：外部可执行工具用临时目录/解析器替身，外部副作用（如 send2trash）用 mock，确保被测流程不依赖本机安装状态。
- 阻塞只来自**模态**对话框：`QMessageBox.critical/warning/question` 在无头环境会永久阻塞。`InfoBar` 是非模态轻量提示，**不阻塞**，不需要为了防死锁而屏蔽。
- 对**预期会出现的**对话框，mock 后要断言其确实被触发（或让它返回明确的选择，如 `QMessageBox.StandardButton.Yes`），以证明分支真的走到了。
- **不要笼统 mock 掉所有提示来掩盖意外错误**：信息提示（`InfoBar` 等）应保留，或在测试末尾汇总断言未出现意外错误提示；否则真实缺陷会被静默吞掉。
- 至少验证一次「外部工具缺失」环境：把工具解析器指向空目录或直接 patch 为 `None`，断言流程不阻塞、不弹模态框、进程能正常退出。
- **不能以「本机已安装该工具」判定测试可移植**。本地有 ExifTool，而 CI 单测先于 `ConfigureExifTool` 步骤，本机通过 ≠ CI 通过（实际教训：旧 Flyme 页找不到 ExifTool 后 `main_gui.py:463` 的 `QMessageBox.critical` 模态卡死整个作业）。
- 集成测试内部等待（事件循环、线程收尾）都要有超时，超时即失败，不允无限等。

### CI 测试超时

CI 的单元测试步骤必须有 **step 级有界超时**（如 `timeout-minutes: 5`）。测试挂起（模态框、线程未退出）在无超时的作业里会占满配额直到平台默认上限，既耗时又让失败原因不可区分（挂起 vs 断言失败）。

### 关键回归样例

- `IMG_20010101_000000.jpg`（项目根）：占位文件名 + 真实 EXIF 时间 → 必须识别为 `2006-05-30`
- `sample/HarmonyOS2|4|6/`：各类 LivePhoto 样例
- 测试 AVI：时间应识别为 `2019-07-04`

---

## 代码审查要点

- **共用层影响面**：改了 `timestamp_fix_gui.py` 的共用函数，必须确认所有引用页面仍正常。
- **翻译完整性**：新增 UI 文案必须补齐 zh/en 两个键，否则界面显示原始 key。
- **线程安全**：`QThread` worker 不得直接操作 UI，必须通过信号 + 队列 + 主线程定时器 drain。
- **打包影响**：新增模块/数据文件需同步 `.spec`。

---

## 提交规范（仓库约定）

- 前缀：`feat:` / `fix:` / `refactor:` / `docs:` / `chore:`
- 语言：**英文**短句（观察自 `git log`）
- 长度：单行，简洁描述；一个 commit 一个语义单元。

示例（取自真实历史）：

```
fix: speed up rename scanning
feat: add exiftool resolver for bundled runtime
refactor: use shared exiftool resolver in flyme fix core
docs: document all six feature pages
```

---

## 禁止事项

- ❌ 不要把调试 `print()` 提交。
- ❌ 不要提交 `%APPDATA%` 下的真实配置文件。
- ❌ 不要用「本机已装 ExifTool/ffmpeg」证明 GUI 集成测试可移植；不隔离外部工具就跑全功能统一窗会卡在模态框。
- ❌ 不要为了「优雅」而大范围重命名/重构扁平结构。
- ❌ 不要在没跑 `compileall` 的情况下声称「验证通过」。
