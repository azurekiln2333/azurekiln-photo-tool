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
- ❌ 不要为了「优雅」而大范围重命名/重构扁平结构。
- ❌ 不要在没跑 `compileall` 的情况下声称「验证通过」。
