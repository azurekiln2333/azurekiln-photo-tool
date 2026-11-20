# 独立复核：`media_thumbnail.py` / `tests/test_media_thumbnail.py` / `unified_gui.py` 关窗 / `file_context_menu.py`

角色：trellis-check（读 `.trellis/tasks/11-21-compare-preview-records/check.jsonl` 的 spec）。
所有权内改动仅 `media_thumbnail.py`、`tests/test_media_thumbnail.py`、`file_context_menu.py`、
新增 `tests/test_file_context_menu.py`。`dir_compare_gui.py` / `folder_dedupe_gui.py` / `unified_gui.py`
属 pA / p8 / 主会话，**未改动**。

---

## 一、发现并已修复的真实缺陷

### D1（主验收失败）窄侧栏下长路径被压成固定高度、与图片/后续文本重叠

现象（主会话 `root_layout_probe.py --capture`，1360×880、右栏 ~450px、真实微软雅黑）：
`path_label.height = 108`，`needed_height = 209`；图片与路径视觉重叠、尾部截断。

根因不是换行本身，而是**纵向空间分配**：

1. `_WrappingLabel.sizeHint()` 原先返回 `(_MIN_WIDTH, height_for(_MIN_WIDTH))`，即按 48px
   宽算出的 ~1083px 高度；`_PreviewSlot` 的 `QSizePolicy.Preferred` 因此几乎无限大，
   `QVBoxLayout` 按 sizeHint 分配时，`image_label`（`Fixed` 高度）与 stretch 吃满空间，
   `path_label` 只剩固定的一点高度。
2. `_WrappingLabel.minimumSizeHint().height()` 只有一行；`QLabel` 放进 `QVBoxLayout`
   时不会按 `heightForWidth(实际宽度)` 补足高度，于是文本被纵向裁切（`paintEvent` 直接
   按 `QTextDocument` 画，超出控件矩形就是截断 + 与下方控件视觉重叠）。

修复（`media_thumbnail.py`）：

- `_WrappingLabel.sizeHint()` 只报一行高度（`fontMetrics().height()`），不再虚高。
- 新增 `_PreviewSlot._sync_minimum_height()`：按**当前宽度** `heightForWidth(width)` 计算
  图片 + 标题 + 路径 + 元信息 + 失败提示 + 重试按钮的真实总高，设为槽位 `setMinimumHeight`。
  该最小高度只作用于滚动内容，`PreviewPanel.minimumSizeHint()` 仍然很小，不会撑高页面/窗口。
- `PreviewPanel` 内部包一层 `QScrollArea`（仅纵向滚动，`frameless`、透明背景）：空间不足时
  由面板内部滚动，长路径可完整显示。
- `PreviewPanel.resizeEvent` 在宽度变化后重算各槽位最小高度。

验收（真实字体、真实页面尺寸）：

```
.venv/Scripts/python.exe -X utf8 .trellis/tasks/11-21-compare-preview-records/research/root_layout_probe.py --capture
exit=0   # 两页均通过：path_height >= needed、path 在 image 之下、meta 在 path 之下
```
截图核验（`compare-layout-images-*/dir_compare_gui-standalone-zh.png`）：两槽等宽、长路径
多行完整、右侧出现纵向滚动条、图片/路径/元信息无重叠。
`--embedded`、`--en` 组合亦通过（`panel_minimum = 266`，见 D3）。

### D2（阻塞 pA 16 项测试）析构期 `file_context_menu.py:240` 抛 RuntimeError

`eventFilter` 首句就是 `obj is self.table.viewport()`；页面析构时 `TableView` 的 C++ 对象
已删除，访问 `viewport()` 抛 `RuntimeError: wrapped C/C++ object of type TableView has been deleted`。

修复（`file_context_menu.py`）：**不能**按 `obj` 类型预筛（监听对象是 `table.viewport()`，
是 `QWidget` 而非 `QAbstractItemView`，加了类型条件会让真实右键菜单全部失效——这是过程
中出现并被立即纠正的回归）。最终顺序：

```python
if event.type() != QEvent.Type.ContextMenu:   # 1. 先按事件类型短路
    return super().eventFilter(obj, event)
try:
    viewport = self.table.viewport()          # 2. 再访问表格（可抛 RuntimeError）
except RuntimeError:
    return False                              # 3. 表格已销毁：释放事件，不碰已删除对象
if obj is viewport:
    self.show(event.pos()); return True
```

回归测试 `tests/test_file_context_menu.py`（3 项，真实 `QContextMenuEvent` 发到 viewport）：

- `test_context_menu_on_viewport_reaches_show`：`QCoreApplication.sendEvent(viewport, ...)`
  真的进入 `show()`（mock 记录坐标），防止「守卫把菜单静默吃掉」的回归；
- `test_non_context_menu_event_is_not_swallowed`：用安全的 `QEvent.Type.User`
  （不用 `HoverMove` 冒充，避免 QWidget 按 `QHoverEvent` 读子类数据崩溃）；
- `test_deleted_table_does_not_raise`：owner 取独立保活 `QWidget`，`table.deleteLater()`
  + `sendPostedEvents(DeferredDelete)` 后再发 `ContextMenuEvent`，断言返回 False 且不抛。

### D3（复核新增）拖到最窄时最右槽位会被横向裁切

`PreviewPanel` 关掉横向滚动，而 `QScrollArea` 默认 `minimumSizeHint = 68`：splitter 可以把
面板拖到比「两槽最小宽度之和」更窄，最右槽位被裁掉且无法滚动。

修复：`PreviewPanel.setMinimumWidth(slots * 120 + spacing + 纵向滚动条宽)`，并覆写
`minimumSizeHint()` 返回同一宽度（否则外层布局仍看到 68）。该宽度**与路径文本无关**
（槽位最小宽度固定 `_MIN_IMAGE_WIDTH = 120`），不会退回「长路径撑宽」。

### D4（测试口径）`test_image_scales_proportionally_with_card_width` 按 `places=2` 断言宽高比

`KeepAspectRatio` 取整后为 2.01，原断言失败。改为 `delta=0.03` 的等比容差（图在取整
缩放下的正常误差，不改变被测语义：宽高比保持、且不超过图片框宽度）。

---

## 二、按复核要点逐项结论

| 复核点 | 结论 | 依据 |
| --- | --- | --- |
| 长路径全显示 | ✅ 修复 | `_sync_minimum_height` + 内部纵向滚动；probe 断言 + 截图 |
| 不把窗口撑高 | ✅ | `panel_minimum = 266`（固定值），probe `panel.minimumSizeHint() < 600` 通过 |
| 两槽始终等宽 | ✅ | probe 两页 `slots = [200, 200]` / `[250, 250]`；`tests/test_media_thumbnail` 3 项布局用例 |
| 线程与取消代号 | ✅ | `_on_loaded` 首行判 `generation`/`_stopped`；`clear()` 先 `set()` 旧 `_cancel_event` 再换新 event；`test_shutdown_cancels_inflight_video_decode` 覆盖 |
| 负缓存可重试 | ✅ | `_FAILURE_BACKOFF_S = (1, 2, 5)` 有限退避、`_MTIME_TTL_S = 2.0` 过期重查 stat、`retry()` 手动重置；4 项用例 |
| 历史解码错误不污染新选择 | ✅ | `set_slot`/`clear` 清 `_failure_codes`；`_on_thumbnail_failed` 只对当前槽位路径生效；`test_failure_for_other_path_is_ignored` |
| 统一关窗等待记录线程 | ✅（只读复核） | `closeEvent` 对 `_optional_windows()` 的 `_is_busy()` 先停 worker + 50ms 定时器重试关闭；`tests/test_unified_close.py` 两模式通过；`root_close_probe.py` PASS |
| 视频回退 | ⚠️ 未复验端到端 | 仅 mock/本地 ffmpeg 样片用例；真实 OneDrive 未验证（符合 PRD 声明） |

## 三、执行过的验证（全部取进程真实 exit code）

```
.venv/Scripts/python.exe -X utf8 -m unittest tests.test_file_context_menu    -> exit 0 (3 tests OK)
.venv/Scripts/python.exe -X utf8 -m unittest tests.test_media_thumbnail      -> exit 0 (26 tests OK)
.venv/Scripts/python.exe -X utf8 -m unittest tests.test_unified_close        -> exit 0 (2 tests OK)
.venv/Scripts/python.exe -X utf8 .trellis/.../research/root_close_probe.py   -> exit 0 PASS
.venv/Scripts/python.exe -X utf8 .trellis/.../research/root_layout_probe.py --capture                       -> exit 0
.venv/Scripts/python.exe -X utf8 .trellis/.../research/root_layout_probe.py --capture --embedded --en       -> exit 0
```

`tests/test_media_thumbnail` 需 `QT_QPA_PLATFORM=offscreen`（文件内已默认设置）。

## 四、未覆盖 / 留给主会话的边界

- 真实 OneDrive 占位文件（水化中）的视频首帧与超时，仍只有本地 ffmpeg 样片证据。
- `QScrollArea` 引入后，面板右侧会常驻/按需出现纵向滚动条；页面若对预览区宽度有像素级
  期望（例如等比截图比对），请以 probe 的 `slots` 数值为准而非绝对值。
- `folder_dedupe_gui.py` 同一预览组件自动受益，但页面层（p8）仍负责 splitter 与批量勾选。
