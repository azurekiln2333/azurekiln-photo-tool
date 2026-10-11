# 控件与组件约定

> 使用 `qfluentwidgets` 保持全应用视觉一致性。

---

## 优先用 Fluent 控件，不要裸 Qt 控件

| 用途 | 用这个（qfluentwidgets） | 不要用 |
|------|--------------------------|--------|
| 表格 | `TableWidget` | `QTableWidget` |
| 卡片容器 | `CardWidget` | `QFrame` + 手写边框 |
| 主操作按钮 | `PrimaryPushButton` | `QPushButton` |
| 普通按钮 | `PushButton` | `QPushButton` |
| 正文标签 | `BodyLabel` | `QLabel` |
| 标题标签 | `SubtitleLabel` | `QLabel` |
| 下拉框 | `ComboBox` | `QComboBox` |
| 勾选框 | `CheckBox` | `QCheckBox` |
| 单选框 | `RadioButton` | `QRadioButton` |
| 进度条 | `ProgressBar` | `QProgressBar` |

这些控件的 import 有两种风格（项目内并存）：

```python
# 直接 import（多数页面）
from qfluentwidgets import TableWidget, CardWidget, PushButton, BodyLabel

# 动态查找（兼容性兜底，见 timestamp_fix_gui.py / unified_gui.py）
FW = {...}
```

新代码优先用**直接 import**；只有在处理版本差异时才用动态查找。

---

## 图标

用项目内的图标选取辅助函数，不要硬编码图标路径：

```python
self.btn_scan.setIcon(_pick_icon("SYNC", "UPDATE"))    # 依次尝试候选图标名
self.btn_clear.setIcon(_pick_icon("DELETE", "REMOVE"))
self.btn_start.setIcon(_pick_icon("PLAY", "SEND"))
```

`_pick_icon(第一候选, 备选...)` 会按顺序取第一个可用的 Fluent 图标。

---

## 卡片布局惯用法

```python
card = CardWidget(self)
layout = QVBoxLayout(card)
layout.setContentsMargins(16, 14, 16, 14)
layout.setSpacing(10)

# 节标题：加粗的 BodyLabel
label = BodyLabel(self.tr("processing_options"), self)
label.setStyleSheet("font-weight: 600;")
layout.addWidget(label)
```

- 卡片内边距统一约 `(16, 14, 16, 14)`，间距 10。
- 节标题加粗；次要说明用灰色 `color: #667085`（次要）/ `#98A2B3`（更弱）。

---

## 用户提示：`InfoBar`

```python
InfoBar.success(
    title=..., content=..., orient=Qt.Orientation.Horizontal,
    isClosable=True, position=InfoBarPosition.TOP_RIGHT, duration=1800, parent=self,
)
InfoBar.error(...)   # 错误用 error，duration 2600
```

项目通常封装成 `self._notify(title, content, is_error=False)`。

⚠️ **例外**：管理员权限提示条**不用** InfoBar overlay，而是**内嵌**在标题下方
（见 `elevation_hint.py`），这是刻意的设计选择（跟随微软 Fluent 的 inline 做法）。

---

## 右键菜单

表格右键菜单统一走 `file_context_menu.install_file_context_menu(...)`，
它用 `win32gui` / `win32com.shell` 调 Windows 系统菜单，各页共享。

---

## 禁止事项

- ❌ 不要混用裸 Qt 控件与 Fluent 控件造成风格割裂。
- ❌ 不要在控件里硬编码中文字符串（走 `self.tr(...)`）。
- ❌ 不要硬编码图标路径。
- ❌ 不要把需要用户注意的提示做成弹窗 `QMessageBox`（阻塞且打断流程），用内嵌提示或 InfoBar。
