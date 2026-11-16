# pi-integrate 实施报告：统一入口集成与文档

Active task: `.trellis/tasks/11-15-folder-media-statistics`
所有权范围：`unified_gui.py`、`README.md`、`docs/README.en.md`、`docs/README.zh-TW.md`、本报告。
未改动：`media_statistics_gui.py`、`media_statistics_core.py`、`media_readme_core.py`、两份 `.spec`、`.trellis/spec/**`、任何真实 OneDrive 文件。无新增依赖，无 git commit/push/merge。

## 1. 已实现改动

### unified_gui.py（+51 / -1）

1. **静态导入**：`from media_statistics_gui import MainWindow as MediaStatisticsWindow`（模块级静态导入，便于 PyInstaller 自动收集）。
2. **导航文案**：`TRANSLATIONS["zh"]["media_statistics"] = "媒体统计"`、`TRANSLATIONS["en"]["media_statistics"] = "Media Statistics"`。
3. **SettingsPage 六项精确解包修正**：`merge, split, flyme, timestamp, rename, dedupe = self.feature_windows[:6]`。
   - 原代码对列表做六项精确解包，列表一旦增长即抛 `ValueError`。
   - 改为只取前六项：既保留原有六页设置绑定（第 0–5 项语义不变），又不依赖列表总长度。
   - 统计页**不**加入 `_feature_windows`，避免污染设置页与 `for feature_window in self._feature_windows` 的语义。
4. **窗口/页面注册**：`self.media_statistics_window = MediaStatisticsWindow(self, embedded=True)`、`self.media_statistics_page = EmbeddedPage("media_statistics", ...)`；路由名 `media_statistics`；导航项 `self.media_statistics_item`（`NavigationItemPosition.TOP`，去重页之后）。
5. **语言传播**：`apply_language` 中刷新 `media_statistics_item` 文案/tooltip，并在原六页循环之后单独调用 `self._apply_feature_language(self.media_statistics_window, lang)`（复用既有 `lang` / `language_combo` / `_apply_language` 约定，七页全覆盖）。
6. **非阻塞 closeEvent 协调**（新增，此前项目无任何 `closeEvent`）：
   - `stats.request_close(self.close)` 返回 `True` → `super().closeEvent(event)` 正常关闭。
   - 返回 `False` → `self.switchTo(self.media_statistics_page)` 切到统计页展示内嵌草稿/状态条，然后 `event.ignore()`。
   - `_closing_through_media_statistics` 防重入标志：避免 `on_ready → self.close()` 递归，且在 `try/finally` 中复位。
   - 不在主线程等待工作线程；实测 `closeEvent` 耗时 0.000 s。

### README.md / docs/README.en.md / docs/README.zh-TW.md

三份文档同步更新，均无 BOM（与原文件一致）：

- 功能页数量：六 → **七**（英文原文仍写「three core workflows」，繁体写「三個核心流程」，一并更正）。
- 首段功能列表补全为七项（原英文/繁体只列三项），新增「媒体统计」。
- 新增「媒体统计」特性小节：列名（文件夹/图片/视频/总项数）、总数=图片+视频、直属+后代累计、按路径计一次、既有扩展名集、只枚举不读内容、OneDrive 仅联机占位项计入、跳过符号链接/目录联接、展开/折叠/重扫/停止、不完整标记、**仅编辑已存在 readme.txt**、2 MiB 上限、编码/BOM/换行保留与原文件不受损、草稿保存/放弃/取消与冲突提示。
- **在线-only 边界**：明确「选中目录时才按需读取 readme.txt，OneDrive 可能因此下载该文本；离线/读失败只影响说明区，不影响统计，也不触发其他媒体下载；目录枚举本身可能取回目录元数据，故不承诺完全无网络」。三种语言一致表述。
- 使用说明：导航列表补「媒体统计」；独立入口由三个扩为七个（含 `media_statistics_gui.py`）。
- 项目结构：`unified_gui.py` 描述改为七页；新增 `media_statistics_gui.py` / `media_statistics_core.py` / `media_readme_core.py` 三条（注明后两者为纯标准库、不依赖 PyQt）。

## 2. PyInstaller spec 静态导入核查（未改 spec，未改版本）

- 两份 spec 均以 `Analysis(["unified_gui.py"], ...)` 为根，无「仅显式列模块」的白名单；新模块属普通**模块级静态导入**，PyInstaller 分析器可自动收集，故**不改 spec**（符合 implement.md「只在确有遗漏时改 spec」）。
- 证据一（静态导入图）：自 `unified_gui.py` 出发用 `ast` 遍历本地模块导入，结果 `REACHABLE media_statistics_gui` / `REACHABLE media_statistics_core` / `REACHABLE media_readme_core`。
- 证据二（导入形式）：`media_statistics_gui.py` 用 `from media_readme_core import (...)`、`from media_statistics_core import ...`、`from timestamp_fix_gui import IMAGE_SUFFIXES, VIDEO_SUFFIXES` 全部为顶层静态 import，无 `importlib` 动态加载路径。
- `APP_VERSION` 保持 `1.1.0` 未动。

## 3. 执行过的验证（命令与结果）

环境：`.venv/Scripts/python.exe`（Python 3.14）；GUI 测试 `QT_QPA_PLATFORM=offscreen` + `APPDATA` 指向 `tempfile.mkdtemp()`；同时 monkeypatch `QMessageBox.information/warning/question` 防模态挂起；临时脚本验证后删除。

| # | 命令 | 结果 |
|---|---|---|
| 1 | `.venv/Scripts/python.exe -m compileall -q unified_gui.py media_statistics_gui.py media_statistics_core.py media_readme_core.py` | `EXIT=0`（语法通过） |
| 2 | `ast.parse(unified_gui.py)` | `AST OK` |
| 3 | 集成冒烟 `UnifiedMainWindow`（临时脚本） | **32 PASS / 0 FAIL** |
| 4 | 关闭协调冒烟（临时脚本） | **13 PASS / 0 FAIL** |
| 5 | 静态导入图可达性 | 三个新模块均 `REACHABLE` |
| 6 | 干净退出 `app.exec()` + `sys.exit(0)` | `EXIT=0`，`visible: False`（close 被接受） |

### 集成冒烟覆盖（17 页/导航 + 语言 + 设置 + 关闭）

- `len(_feature_windows)==6`、`len(pages)==6`（原六页结构未被破坏）。
- `media_statistics_window` / `media_statistics_page` 存在；`objectName()=="media_statistics"`；`_embedded is True`；页面已在 `stackedWidget` 中。
- `switchTo(media_statistics_page)` 切换成功。
- **设置页兼容**：`settings.feature_windows` 长度 6、`feature_windows[0] is _feature_windows[0]`（绑定未错位）、设置卡片全部构建成功（`merge/split/flyme/timestamp/dedupe_settings` 等 10 个 key），未触发六项解包异常。
- **语言七页传播**：`apply_language("en")` → 导航 `Media Statistics`、`stats.lang=="en"`、`stats.language_combo.currentData()=="en"`、表头 `['Folder','Images','Videos','Total']`；原六页 `lang` 全部 `en`；切回 `zh` → 导航 `媒体统计`、表头 `['文件夹','图片','视频','总项数']`、表头 zh≠en、原六页全部 `zh`。
- `request_close` 空闲态返回 `True`。

### 关闭协调冒烟覆盖（含真实临时 readme.txt，不触碰 OneDrive）

- 空闲态统一 `closeEvent` → **accepted**。
- 临时目录写入 `readme.txt` → `set_root_folder` + `_select_folder` → `readme_document` 加载成功、编辑器文本 `'hello\n'` 一致。
- 编辑框改文本 → `_readme_dirty is True`（真实 dirty，非伪造）。
- 从合并页触发关闭 → **ignored**、自动切到 `media_statistics_page`、`_pending_action == ('action_close', ...)` 草稿决策条出现。
- 连续两次关闭 → 回调未累积（`len(_close_callbacks) <= 1`，幂等）。
- 草稿解决后 `_has_background_work() is False` → 关闭 **accepted**。
- 模拟后台忙（`_readme_busy=True`）→ 关闭 **ignored**，且 `closeEvent` 耗时 **0.000 s**（主线程未阻塞）。

## 4. 需要主会话知道的既有环境现象（非本次回归）

无头脚本在**解释器析构阶段**返回 `EXIT=-1073741819`（0xC0000005）。已用三组对照确认这是**项目既有现象**，与本次集成无关：

1. 仅 `UnifiedMainWindow` 构造 + `del`，不触碰统计页 → 同样 `-1073741819`。
2. 仅原单页 `merge_live_photo_gui.MainWindow(embedded=True)`，完全不加载任何新代码 → 同样 `-1073741819`。
3. 正常事件循环 `app.exec()` 后 `sys.exit(0)` → `EXIT=0`。

结论：崩溃发生在 PyQt/Qt 解释器退出析构顺序上，不是新页或统一 `closeEvent` 引入；脚本内所有断言均已执行完毕（`FAILURES: []`）。建议主会话在 CI/真机验证时用 `app.exec()` + 显式退出码判断，勿以无头脚本进程退出码判定失败。

## 5. 未做 / 边界

- **未**运行完整 PyInstaller 打包（体积大且 implement.md 标注为「如需」）；以静态导入图 + spec 结构分析替代，结论为新模块自动收集。若主会话要求，可跑 `.venv/Scripts/python.exe -m PyInstaller --noconfirm AzureKilnPhotoTool_onefile.spec` + `scripts/ci/verify_bundle.py`。
- **未**读写真实 OneDrive 相册与真实 `readme.txt`（PRD/契约要求写回测试只用临时目录）。
- **未**执行真实 GUI 交互（拖拽、真机渲染、云占位下载），仅 offscreen 无头验证；拖拽与云下载按既有 spec 属真机/环境范畴。
- 未改 `.trellis/spec/**`：静态导入正常则不改 spec（按契约），新增页的规格更新留给主会话 Phase 3。
