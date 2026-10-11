# 质量约定（界面层）

> GUI 改动的验证方式与验收标准。

---

## 无头冒烟测试（主要手段）

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:APPDATA = "<临时目录>"      # 隔离真实 settings
```

要点：
- `APPDATA` 指向临时目录，否则会污染真实 `%APPDATA%\<APP_NAME>\settings.json`。
- **monkeypatch `QMessageBox.information`**，否则弹窗会永久阻塞无头测试。
- 构造每个受影响页面的 `MainWindow`（以及 `UnifiedMainWindow`），断言无异常。
- 模拟交互时要走完整事件握手（如拖拽需 `DragEnter` + `DragMove` + `Drop`）。

### ⚠️ 无头测试的局限

`QApplication.sendEvent(widget, QDropEvent(...))` **绕过 Windows OLE 层**。
因此它**无法**复现「真实拖拽失效」类问题（例如管理员权限触发 UIPI）。
判断标准：若代码链路正常但真机仍失效，优先怀疑**环境/系统机制**，而非代码。

---

## 布局验收

- **隐藏控件零占位**：`setVisible(False)` 可能仍占 setSpacing 的空隙。
  隐藏后应让 `sizeHint()` 归零（如 `elevation_hint.ElevationHintBar` 的做法），
  或从布局中移除。验证时看 `QVBoxLayout.itemAt(i).sizeHint()`。
- **内嵌模式不塌**：嵌入 `unified_gui` 后，各 card 不被裁切、不重叠。
- 两种模式（独立 / 内嵌）都要过一遍。

---

## 语言切换验收

切换 zh↔en 后，**所有**带文案的控件都要刷新，包括：
- 窗口标题、页面标题
- 表格表头
- 按钮、勾选框、单选框
- 状态栏、进度文案
- 内嵌提示条

新加控件必须接入 `_apply_language()`。

---

## 可访问性（现状）

- 本项目**没有**系统的无障碍/可访问性测试。
- 保持基本可读性：灰色文字对比度足够（`#667085` 用于次要信息）、控件有可见标签。
- 不要为「无障碍合规」引入新依赖。

---

## 审查要点

- 事件处理器（`eventFilter`）保持简单；复杂逻辑给 worker。
- 忙状态必须给用户反馈，不能静默忽略用户操作。
- 新增控件用 Fluent 组件（见 component-guidelines）。
- 大表格用队列 + drain，不逐行同步插入。

---

## 提交规范

同核心逻辑层：`feat:` / `fix:` / `refactor:` / `docs:` / `chore:` + 英文短句，一 commit 一语义。

---

## 禁止事项

- ❌ 不同时验证「独立运行」和「内嵌」两种模式。
- ❌ 用 `sendEvent` 的成功结果断言「真机拖拽正常」。
- ❌ 新增控件却忘了 `_apply_language()` 刷新。
- ❌ 把 `%APPDATA%` 的真实配置写进提交。
