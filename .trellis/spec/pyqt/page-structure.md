# 页面结构约定

> 功能页的布局方式，以及如何被 `unified_gui.py` 嵌入。

---

## 每个功能页都是一个独立的 `MainWindow`

每个功能页（`merge_live_photo_gui.py` / `split_huawei_live_photo_gui.py` /
`timestamp_fix_gui.py` / `rename_photo_gui.py` / `dedupe_media_gui.py` / `main_gui.py`）
都定义 `class MainWindow(FramelessMainWindow)`，既能独立运行，也能被嵌入统一 GUI。

```python
def __init__(self, parent=None, embedded: bool = False):
    super().__init__(parent)
    self._embedded = embedded
    if not self._embedded:
        self.resize(1280, 860)
        self._set_blue_title_bar()      # 独立运行时才有自绘标题栏

    root = QWidget(self)
    self.setCentralWidget(root)
    outer = QVBoxLayout(root)
    outer.setContentsMargins(20, (0 if self._embedded else self._title_bar_height) + 12, 20, 18)
    outer.setSpacing(12)
    ...
```

**`embedded` 分支的差异：**
- 独立运行：有标题栏、放宽 `resize`、显示语言下拉等。
- 内嵌：无标题栏、内容带内边距、语言由统一 GUI 控制（`unified_gui` 的 settings 页驱动）。

写代码时必须同时照顾两种模式，常见写法：

```python
if not self._embedded:
    header_layout.addLayout(language_row)
```

---

## 页面标准结构（自上而下）

```
QVBoxLayout (outer)
├── header_card       标题区（title_label / subtitle_label / subtitle_note_label / 提示条）
├── path_card         源目录 / 输出目录选择
├── option_card       扫描选项、冲突策略
├── summary_card      输出内容选项（部分页有）
├── table_card        结果表格（TableWidget + 拖拽提示）
├── action_card       操作按钮（重扫 / 清空 / 开始）
└── foot_card         进度条 + 状态栏
```

新增内容通常**追加到某个 card 的 layout**，不要打乱主结构。

### 标题区与内嵌提示条

管理员权限提示条（`elevation_hint.py`）就是追加到 `header_layout` 的**标题下方**：

```python
from elevation_hint import attach_elevation_hint
...
self.elevation_hint = attach_elevation_hint(header_layout, self, lang=self.lang)
```

它在非 elevated 时完全隐藏（`sizeHint` 归零），不残留空白。这是本项目「跟随微软 Fluent 设计」
的提示呈现方式：**内嵌内容，不用弹窗、不用 overlay InfoBar**。

---

## 表格：`TableWidget` + 列约定

```python
self.table = TableWidget(self)
self.table.setColumnCount(4)
self.table.setHorizontalHeaderLabels(self._table_headers())
self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
self.table.setFrameShape(QFrame.Shape.NoFrame)
self.table.setAcceptDrops(True)
self.table.viewport().setAcceptDrops(True)
self.table.viewport().installEventFilter(self)
```

**行号与数据的一一对应（重要）**：`rename_photo_gui.py` 中表格行号与 `self.file_list` 下标
**严格一一对应**。过滤/隐藏只能用 `setRowHidden()`，**不能重建表格**，否则后台处理回写会错位。

---

## 嵌入机制（`unified_gui.EmbeddedPage`）

```python
class EmbeddedPage(QWidget):
    def __init__(self, object_name, feature_window, parent=None):
        super().__init__(parent)
        content = feature_window.takeCentralWidget()   # 搬走功能页的内容
        feature_window.hide()
        feature_window.setParent(self)
        layout = QVBoxLayout(self)
        layout.addWidget(content)
```

`takeCentralWidget()` 只搬走内容 widget，**不重建** `self.table` 等控件，因此各页安装的
事件过滤器（拖拽、右键菜单）在内嵌后依然有效。

---

## 禁止事项

- ❌ 不要假设页面一定独立运行或一定内嵌——两处代码都要能跑。
- ❌ 不要为过滤表格行而 `setRowCount(0)` 重建（会破坏行↔数据映射）。
- ❌ 不要在 `*_core.py` / `exiftool_resolver.py` 里 import PyQt（那两层必须无 GUI 依赖）。
- ❌ 不要用硬编码像素标题栏偏移；用 `self._title_bar_height` 与 `self._embedded` 判断。
