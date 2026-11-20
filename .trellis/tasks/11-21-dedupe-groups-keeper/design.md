# 技术设计

## 边界与数据流

- 界面仅修改 `folder_dedupe_gui.py`，保持 source row 与 worker 更新索引稳定。使用三组筛选控件和 `setRowHidden`，不在筛选时重建核心行。
- 共享核心 `duplicate_scan_core.py` 提供媒体类型判断和纯内存保留项重选，保持无 Qt 依赖、复用现有扩展名全集。接口由核心 Pi 确认后记录到 research/contracts.md，GUI/测试按此接入。
- 同一重复组保持同一类型分组；混合扩展名按固定优先级 photo > video > other 分类，避免切换 keeper 导致组跳转。每个路径的预览权限仍按该路径自身类型判断。
- 三组数量明确区分文件数与重复组数。默认展示首个非空分组。批量动作仅作用于可见合法行；切组保留既有勾选，回收确认显示全部已勾选数。

## 保留项切换

选中合法 pending 副本，点击“设为保留”或等价右键入口：检查非忙、非失效/取消、属于本组、文件仍存在且快照未变；已处理组禁切。更新 `ScanResult.groups` 的 keeper/duplicates，再同步同组行角色、keeper 引用、勾选与状态、预览和按钮计数。新 keeper 强制不勾选，旧 keeper 转 pending 并默认勾选，其他副本保留合法状态。

不在 GUI 做完整 hash/字节比较；耗时工作仍在 worker。扫描已确认组的字节一致性；实际回收继续核心执行前验证。不得把错误候选或已回收文件提升为 keeper。

## 记录兼容

优先不改 schema v1：新角色通过更新后的 result.groups 自然保存，row_states 按路径生成；不能仅改表格文字。导入继续严格根/角色验证并强制逐字节回收复核。不放宽 compare 模式 A/B 约束。

## 风险与回滚

主要风险为筛选后行索引错位、切换后历史角色不一致、旧预览残留、批量选择误选保留项。分别以真实按钮/worker、记录往返、loader spy、非法状态测试锁住。回滚为本任务独立 commit 的 revert，不覆盖已有发布 tag。
