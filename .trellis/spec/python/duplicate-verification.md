# 重复文件判定与安全回收

> 适用于 `duplicate_scan_core.py` 及其调用方（`dir_compare_gui.py` 目录比对页、
> `folder_dedupe_gui.py` 目录内去重页）。任何会把文件移入回收站的"重复"判定都必须遵守本约定。
> 现有旧页 `dedupe_media_gui.py` 尚未迁移到本核心（仅 size + SHA-256，无逐字节复核）。

---

## 判定"一致"的唯一标准

三者同时成立才算重复：

1. 大小相同（只用于预筛，减少哈希量）
2. 完整文件 SHA-256 相同（只用于分组提速，**不是**最终依据）
3. 与参照文件 `files_identical()` 逐字节比对完全相同 —— **最终依据**

SHA-256 相同但逐字节不同 → `HashMismatch`，进入"校验不一致"，绝不回收。
不要用 MD5、不要只比文件头/部分哈希来做最终判定。

## 两页共用同一核心

- 扫描、哈希、比对、复核、回收全部只走 `duplicate_scan_core`，GUI 页面不得自写哈希/枚举逻辑。
- 目录比对：`find_cross_duplicates(A, B)`，keeper 必来自 A，duplicates 必来自 B；B 中多份副本全部列出；B 内部互重但 A 没有的不输出。
- 目录内去重：`find_internal_duplicates(root, keep_strategy=...)`，每组恰好保留 1 个；策略 `shallowest`/`oldest`/`newest`，平手按路径排序保证确定性。

## 类型分组与目录内保留项重选

适用范围：目录内去重的分类展示、手动 keeper 角色转换；不修改扫描判重算法，也不授权回收。

```python
MediaType = Literal["photo", "video", "other"]

def classify_media_type(path: Path | str) -> MediaType: ...
def classify_duplicate_group(group: DuplicateGroup) -> MediaType: ...
def reselect_internal_keeper(
    group: DuplicateGroup, new_keeper: FileEntry
) -> DuplicateGroup: ...
```

- `classify_media_type(path)` 只解析路径后缀，不访问文件内容、元数据或 Qt。媒体全集仍是 `MEDIA_EXTENSIONS`；`VIDEO_EXTENSIONS` 为其中的视频子集（含 `.mkv`），其它已有媒体后缀为 `photo`，未知/无后缀为 `other`，大小写不敏感。
- `classify_duplicate_group(group)` 对整组 keeper + duplicates 分类，固定优先级 `photo > video > other`。组内混合扩展名不拆组；重选 keeper 后成员集合不变，分类也不能跳转。类型不等于解码能力，是否请求预览按具体路径判断。
- `reselect_internal_keeper(group, new_keeper)` 是无文件系统 I/O 的结构转换：返回新的 `DuplicateGroup`，不修改原 group/list；SHA-256、size 保持，剩余成员（含旧 keeper）按既有路径规则确定性排序。
- 重选要求组内所有成员同根、size 与组一致、规范化路径唯一；候选必须匹配已有成员完整快照（path/root/size/mtime_ns/file_id），返回组内成员对象。跨根 compare 组、外来或篡改快照必须拒绝，不得反转 A/B。
- helper 不验证磁盘状态、不执行回收，也不决定 UI 勾选；页面负责非忙、非 stale/cancelled、当前组、未处理状态与候选存在/size/mtime 守卫。真实回收仍走下述执行前复核，不能用“重选成功”代替安全验证。

### 校验 / ValueError 矩阵

| 条件 | 结果 |
| --- | --- |
| group / keeper / duplicates 容器类型错误 | `group_invalid`；成员不是 FileEntry 则 `group_member_invalid` |
| 重选候选不是 FileEntry | `keeper_invalid` |
| 重选无副本组 | `group_empty`；但**分类**合法 v1 keeper-only 组时按 keeper 类型返回 |
| 组成员 root 不同（含有效 compare A/B 组） | `group_cross_root` |
| 成员大小不等于 group.size / 规范化路径重复 | `group_size_mismatch` / `group_duplicate_path` |
| 候选非成员或任一快照字段不同 | `keeper_not_group_member`，输入组不变 |

正常：A/B/C 改保留 B，返回新组 B/A/C，输入仍 A/B/C。基线：选择原 keeper 返回等价新组；旧 v1 单 keeper 仍能分类但不能重选。异常：compare B 侧候选或篡改 mtime 的 FileEntry 必须拒绝。

```python
# 错：只换 keeper 指针会漏掉旧 keeper、可能把新 keeper 同时留在 duplicates。
group.keeper = candidate

# 对：页面先完成资格/快照守卫；整体替换，再按路径同步 rows 的角色与勾选。
updated = reselect_internal_keeper(result.groups[group_index], candidate)
result.groups[group_index] = updated
# 回收仍逐项 recycle_duplicate(target, updated.keeper, byte_verify=True)。
```

必需断言：类型全集/混合优先级、无 stat/open、返回新对象且输入不变、上述错误不部分修改、旧 v1 keeper-only 分类与真实导入、页面真实 worker 使用新 keeper；具体测试位置见文末。

## 回收前复核（不可省略）

GUI 回收 worker 对每一项调用 `recycle_duplicate(target, keeper, byte_verify=...)`，它内部先 `revalidate_pair`：

同一路径（realpath+normcase）/同一物理文件 → `same_path`；target 或 keeper 不存在 → `*_missing`；
size 或 `mtime_ns` 与扫描快照不同 → `*_changed`；`byte_verify=True`（GUI 默认开启）时再逐字节比 → `content_differs`；
读错误 → `read_error`。**任一不通过绝不调用 `send2trash`。** 只提供移入回收站，不提供永久删除。

取消用 `ScanCancelled` 异常传递，不是跳过原因；扫描结果 `cancelled=True` 时 GUI 禁止执行回收。

## 枚举边界

- 目录比对前 `validate_compare_roots`：A/B 相同或互相嵌套直接拒绝（`same_root`/`b_inside_a`/`a_inside_b`）。
- 不跟随符号链接、junction、带重解析属性的目录；带重解析属性的**文件**（OneDrive 云占位）照常纳入，读取时由系统水化（与 [媒体统计](./media-statistics.md) 一致）。
- 跳过 0 字节文件；读/stat 错误写入 `ScanIssue`，不抛出。

## Windows 坑

- `os.DirEntry.stat()` 在 Windows 上 `st_ino`/`st_dev` 恒为 0，`FileEntry.file_id` 不能用于识别硬链接；`_same_file_identity` 遇 0 直接放弃判断，依赖 realpath 比较兜底。
- `files_identical` 先比 `os.stat` 大小，再 1 MiB 分块比较；大文件请保持流式，不要整文件读入内存。

## 测试要求

`tests/test_duplicate_scan_core.py`（stdlib unittest）必须锁住：多副本全回收、同尺寸末字节不同、monkeypatch 哈希碰撞进 mismatches、扫描后改/删 target 或 keeper 被跳过且不调 send2trash、A/B 嵌套拒绝、保留策略确定性、取消不抛异常。
新增分类/重选回归须覆盖：媒体扩展名全集、`.mkv/.MKV` 视频归类、混合组优先级不随 keeper 改变、完整候选快照校验、输入 group/list 不变、cross-root compare 拒绝，以及 patch `Path.stat` / `open` 证明核心 helper 不做文件 I/O。
运行：`.venv/Scripts/python.exe -m unittest tests.test_duplicate_scan_core -v`
