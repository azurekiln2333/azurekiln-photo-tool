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
运行：`.venv/Scripts/python.exe -m unittest tests.test_duplicate_scan_core -v`
