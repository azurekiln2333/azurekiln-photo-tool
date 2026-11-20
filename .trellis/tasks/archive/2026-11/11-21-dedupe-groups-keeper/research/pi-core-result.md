# Core / record implementation result

结论：**PASS（核心与 schema v1 记录边界）**。已完成 frozen contract 对应的 core API，并修复独立审查指出的合法 v1 keeper-only 组兼容问题。本轮只修改核心、核心/记录测试和本研究报告；未改 GUI、未改 `scan_record_core.py`、未改任务状态，未 commit/push/tag。

## 实现

- `duplicate_scan_core.py`
  - 新增 `MediaType = Literal["photo", "video", "other"]` 与 `VIDEO_EXTENSIONS`（`MEDIA_EXTENSIONS` 子集，22 项，含 `.mkv`）。
  - 新增 `classify_media_type(path: Path | str)`：仅检查后缀文本；未知后缀、无后缀和点文件返回 `other`，无 stat/open/Qt。
  - 新增 `classify_duplicate_group(group)`：以整组成员按 photo > video > other 分类；兼容 `duplicates=[]` 的合法旧 v1 keeper-only 组，按 keeper 自身类型返回。
  - 新增 `reselect_internal_keeper(group, new_keeper)`：纯内存返回新组；完整快照匹配、同根、size 与唯一成员约束；保持 hash/size，剩余项稳定排序，不改变原对象；拒绝 compare 跨根组与 keeper-only 组。实际文件有效性和字节一致性仍由 GUI/回收前既有验证负责。
- `scan_record_core.py` 未修改：schema v1 已表达 keeper-only 组及完整 keeper/duplicates 角色；不收紧旧记录验证。

## 回归覆盖

- `tests/test_duplicate_scan_core.py` 新增分类全集（55 个媒体后缀）、视频子集、大小写/未知后缀/点文件、多扩展名路径、禁止 stat/open、组分类优先级、keeper 重选纯内存及输入不变、完整快照拒绝、同根/size/路径唯一和 compare 隔离。
- B1 回归：纯核心 singleton photo/video/other 三类均按 keeper 分类；`reselect_internal_keeper` 仍拒绝空 duplicates。
- `tests/test_scan_record_core.py` 新增 schema v1 round-trip 后加载 keeper-only group 并分类为 photo 的集成回归；既有记录格式/角色断言保留。

## 定向验证（真实结果）

```text
.venv/Scripts/python.exe -B -X utf8 -m unittest tests.test_duplicate_scan_core tests.test_scan_record_core -v
Ran 128 tests in 2.685s
OK
exit=0
```

新增的 keeper-only round-trip 回归 `test_internal_single_keeper_group_v1_roundtrip_classifies_by_keeper` 为 `ok`；组分类优先级回归也为 `ok`。root 先前提供的 core 既有基线为 81 tests OK；本次 core + record 合计 128 tests OK。

## 边界

- 未运行全量 GUI suite、未验证 p8 页面集成；由页面 owner / root 按各自验证计划完成。
- 本轮没有修改 schema v1 或持久化内容；无类型检查器运行记录，本次只运行上述定向 unittest。
- 不做文件存在性/mtime/字节验证的分类与重选，不替代 GUI 交互资格守卫和 `recycle_duplicate(..., byte_verify=True)` 执行前复核。
