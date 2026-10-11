# PyQt / 界面层开发约定

> AzureKiln Photo Tool 的 GUI 约定。技术栈：**PyQt6 + PyQt6-Fluent-Widgets + qframelesswindow**。

---

## 技术栈实情

- 窗口基类：`qframelesswindow.FramelessMainWindow`（自绘标题栏的无边框窗口）。
- 控件库：`qfluentwidgets`（Fluent 风格：`TableWidget` / `CardWidget` / `PushButton` /
  `PrimaryPushButton` / `BodyLabel` / `SubtitleLabel` / `ComboBox` / `CheckBox` / `RadioButton` /
  `ProgressBar` / `InfoBar`）。
- 主入口：`unified_gui.py`，用左侧导航栏承载 6 个功能页，把各页 `MainWindow(embedded=True)` 的
  内容搬进 `EmbeddedPage`。

**没有** HTML/CSS/JS 前端、没有 React/Vue、没有 hook、没有状态管理库、没有 TypeScript。
`trellis init` 生成的 `hook-guidelines.md` / `state-management.md` / `type-safety.md` 对本项目
无意义，已由本目录的真实文档取代。

---

## 指南索引

| 指南 | 内容 |
|------|------|
| [页面结构](./page-structure.md) | 功能页布局、嵌入 unified 的方式 |
| [控件与组件约定](./component-guidelines.md) | qfluentwidgets 控件用法、图标、样式 |
| [线程与异步](./threading-and-workers.md) | QThread + Worker + 信号 + 主线程 drain 模式 |
| [多语言文案](./translations.md) | zh/en 翻译机制、翻译键约定 |
| [质量约定](./quality-guidelines.md) | GUI 冒烟测试、布局、可访问性 |

---

## 预开发检查表（改界面前逐条过一遍）

- [ ] 改动会同时作用于**独立运行**和 **unified 内嵌**两种模式吗？（`self._embedded` 分支）
- [ ] 新增文案是否补了 zh/en 两个翻译键？
- [ ] 是否碰了后台 worker 的信号/队列？确认主线程 drain 逻辑同步更新。
- [ ] 是否新增控件到 `header_layout` / `content_layout`？确认隐藏时零占位。
- [ ] 控件是否用了 Fluent 组件而非裸 Qt 控件？（保持视觉一致）

---

## 质量检查（改完界面后逐条过一遍）

- [ ] `.venv/Scripts/python.exe -m compileall -q <改动文件>`
- [ ] 无头冒烟：构造所有受影响页面 `MainWindow`，无异常
- [ ] 管理员权限提示条：elevated 显示、非 elevated 隐藏且**零空白占位**
- [ ] 语言切换后文案全部刷新（含新控件）
- [ ] 内嵌模式下布局不塌（无控件被裁切/重叠）

---

**语言约定**：注释用中文；UI 文案中英双语。
