# UI 测试契约：directory dedupe category / keeper

状态：p8 页面实现与 pA 测试共用的对象名和行为契约。路径仅限 `folder_dedupe_gui.py`，产品行为不依赖测试专用钩子。核心 API 见同目录 `contracts.md`。

## 分类控件

| Object name | 作用 |
|---|---|
| `MainWindow.btn_filter_photo` | 显示 photo 类；按钮文本包含 photo 组数与文件行数 |
| `MainWindow.btn_filter_video` | 显示 video 类；按钮文本包含 video 组数与文件行数 |
| `MainWindow.btn_filter_other` | 显示 other 类；按钮文本包含 other 组数与文件行数 |
| `MainWindow.active_category` | 当前分类字符串：`photo` / `video` / `other` |
| `MainWindow._row_categories` | 与 `table_model.rows` 等长，原始 row index → 固定类别 |
| `MainWindow._group_categories` | group_id → 固定组类别；keeper 重选不得改变类别 |
| `MainWindow.set_active_category(category)` | 公共 UI 行为入口；设置当前类别、逐行 `setRowHidden`、保留原模型行号/勾选状态 |
| `MainWindow._apply_category_filter()` | 仅按 `_row_categories` 调 `table.setRowHidden`; 行不重建、不排序 |
| `MainWindow._visible_checkable_rows()` | 返回当前显示且 model `_checkable` 的 `(row_index, row)`；现有三批量操作基于此结果 |

按钮文字格式（中英）：`照片 · {groups} 组 / {files} 个文件` / `Photos · {groups} groups / {files} files`；Video/Other 同结构。groups 是当前分类下 distinct duplicate group 数；files 是当前显示的所有行数（keeper+duplicates，另含归入该类型的 mismatch/issue 行）。每个重复组完整归入单一类别，不拆组。默认选择首个非空类别，优先 photo→video→other；若完全空则 photo。

## 自主保留项

| Object name / method | 契约 |
|---|---|
| `MainWindow.btn_set_keeper` | 真实可点击按钮；用户选中当前重复组 duplicate 行后点此设为保留 |
| `MainWindow.set_selected_as_keeper()` | 按当前表格行执行受资格守卫的 keeper 转换，成功 True，拒绝/无变化 False |
| `MainWindow._can_reselect_keeper(row_index)` | 只做轻量资格检查：internal group duplicate、非忙/非 stale/非 cancelled、候选存在且 size/mtime 快照匹配、同组仍全 pending；不做 hash/字节 I/O |
| `MainWindow._refresh_keeper_action()` | 按当前选中行与 guard 更新 `btn_set_keeper` enabled |

测试通过选 `table_model.index(row_index, 0)`、真实 `btn_set_keeper.click()`，断言 `window._current_result.groups[group_id-1]` 与原 `table_model.rows` 对象/索引关系已同步。A→B 后 B keeper + `status_keep` + unchecked；A duplicate + pending + checked；其它 duplicate 保留原 status/checked。不可只改 label 或 model 展示字段。

## 预览门禁（每个槽独立判断）

- `DedupeTableModel.data(index, DecorationRole)` → `_thumbnail_for(path)`：`other` 返回 None，绝不调用 `thumbnail_loader.request(path)`。
- `_refresh_preview()` 必须**逐槽**判断路径类型，不以 selected row 类型为全局判据：slot 0 selected row path；slot 1 keeper path。各自 `other` 则 `preview_panel.set_slot(slot, title, None, None, None)` 清掉旧图且不发请求；photo/video 路径可正常 `set_slot`。
- 因此混合扩展名组即使 active group 为 photo，某候选 keeper 本身是 other，keeper slot 仍不得送 loader；反向 selected=other、keeper=photo 时，只清 slot 0、slot 1 可正常预览 photo。
- pA 可 spy `window.thumbnail_loader.request`，另外 spy `window.preview_panel.set_slot`；设置 slot 的 `path` 参数为 None 必须满足 other 路径清图，且该 other path 不在 request call_args 中。

## 批量勾选和跨类别回收

- `btn_select_all` / `btn_select_none` / `btn_invert` 只处理当前类别**可见**且 `DedupeTableModel._checkable(row)` 的行。切换类别时隐藏组 checked/status 保持；再切回来仍可见原勾选。
- `_recyclable_rows()` / `start_recycling()` 必须包括所有类别已 checked 的合法 targets，不按 active_category 过滤；回收 worker row_index 仍是原始 `table_model.rows` 索引。
- `QMessageBox.question` 使用 `confirm_content(count=全类别已勾选 targets 总数, size=全类别总字节数)`，跨两类选中时确认文本展示合计，不只当前 tab 数量。

## 测试稳定性

- 只依赖以上正式 UI object/method 名称；不 mock private test-only selector。
- 真按钮用 `.click()`；回收确认 mock `QMessageBox.question` 返回 Yes，`duplicate_scan_core.send2trash` 必须 mock/assert_not_called。
- 保留 row index/worker status 回写测试；分类筛选仅验证 `setRowHidden`，禁止 reset/重建 rows。
- 中英按钮文本均从 `_apply_language()` 刷新；独立/内嵌模式的真实按钮都应 visible（不要求实际屏幕截图）。
