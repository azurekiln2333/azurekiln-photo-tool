# 目录内去重扫描覆盖统计

## 1. 适用范围与触发

`duplicate_scan_core.py` 的目录枚举统计，经 `DedupeScanWorker` 传到 `folder_dedupe_gui.py`。用于解释文件总量与 Hash 进度分母的差异，不改变判重、逐字节复核或回收资格。只在既有遍历中计数，不能再启动媒体统计扫描或额外读取文件内容。

## 2. 接口

```python
@dataclass
class ScanCoverage:
    folders: int = 0
    files: int = 0
    included_files: int = 0
    zero_byte_files: int = 0
    filtered_files: int = 0
    skipped_links: int = 0
    other_entries: int = 0
    entry_errors: int = 0
    directory_errors: int = 0
    hash_candidates: int | None = None
    enumeration_complete: bool = False

# ScanResult 最后增加可选字段；既有构造方无需提供。
coverage: ScanCoverage | None = None

collect_files(..., *, coverage: ScanCoverage | None = None,
              on_coverage: Callable[[ScanCoverage], None] | None = None)
find_internal_duplicates(..., *,
    on_coverage: Callable[[ScanCoverage], None] | None = None) -> ScanResult
```

上面的 `*` 表示新参数为 keyword-only，既有参数调用方式和 `on_progress(stage, done, total)` 保持原样。GUI 使用 `coverage_update = pyqtSignal(object)`；`_update_scan_coverage()` 在主线程缓存快照，`_refresh_scan_inventory()` 统一刷新文案。

## 3. 数据与展示契约

- `folders` 是已发现的普通子目录数，不含根；已发现但无法进入的子目录仍计数，其未知后代不推算。
- `files` 是已识别普通文件数，含空文件和范围外文件；`files == included_files + zero_byte_files + filtered_files`。先判空，再判范围，三类互斥。`included_files` 保持既有 `scanned_files` 口径。
- `skipped_links` 单列符号链接、junction、重解析目录，不跟随，不假装是普通文件/文件夹。OneDrive 普通云占位文件继续按普通文件处理。其它可识别但非文件/目录条目进入 `other_entries`。
- 类型/stat 失败进入 `entry_errors`；打开或迭代目录失败进入 `directory_errors`。不能将无法分类的条目算成普通文件。
- 枚举时 `hash_candidates=None`，确定候选后设置为 `len(hash_targets)`，与 Hash 进度分母一致；`0` 是已确定没有候选。`included_files - hash_candidates` 是大小唯一无需 Hash，不是重复数。
- 无枚举错误且遍历结束才有 `enumeration_complete=True`。GUI 还必须结合扫描取消/失败状态，不能只凭此字段宣布任务完成。
- 最后一次逐字节复核或最终进度回调触发的取消也须在返回前检查，设置 `cancelled=True` 并发布不完整快照；不能依赖下一项循环才发现取消。
- 回调发出独立快照（如 `dataclasses.replace`），后续计数不得改变已发对象。常规更新约 100ms 节流；初始化、枚举收尾、确定候选时强制发布。外部回调抛异常不影响扫描。
- 表格上方常驻 `scan_inventory_summary` 显示子文件夹和文件数；`scan_inventory_detail` 换行显示纳入、候选、免 Hash、跳过与读取问题。不能挤压底部预计空间。分类、勾选或 keeper 切换不改变目录统计。
- 底部原有 `len(rows)` 仅是结果行数，必须标“结果行”，不能冒充扫描总文件数；扫描完成状态只显示重复组与可回收文件数，总量由覆盖卡片统一说明。
- 统计属于本次扫描快照，不能声称属于后来编辑过的目录输入框；主行写“本次扫描已发现”，tooltip 展示 `_scan_snapshot["root_a"]`，重置须清除该路径。
- 重扫/清空清除旧统计；完成用 `result.coverage`；取消/失败保留已发现数并标不完整。中英切换刷新主行、明细和 tooltip；独立窗口及真实 `EmbeddedPage` 均需可读。
- coverage 仅为本次运行时信息。严格记录 schema v1 不增加字段，导入得到 `coverage=None`，显示“历史记录未保存目录总数”，可展示原 `scanned_files/hashed_files`；不能显示虚构零或重新扫描冒充历史。

## 4. 校验与错误矩阵

| 条件 | 核心与界面结果 |
| --- | --- |
| 空目录正常完成 | 文件夹/文件为真实 0，候选为 0，完整 |
| 枚举进行中 | 显示已发现数、扫描中，Hash 候选待确定 |
| 大小全部唯一 | 文件计入总数和纳入数，候选 0，不调用 Hash |
| 链接/云占位 | 链接单列且不跟随；普通云占位文件正常计数 |
| 条目 stat 或目录打开/迭代失败 | 保留已发现数、增加对应错误数、统计不完整 |
| 取消或 worker 异常 | 保留最后快照并标不完整，不伪装成完整零结果 |
| coverage 回调异常 | 展示回调异常不影响扫描安全流程 |
| 导入旧/新导出的 v1 记录 | coverage 未知；明确历史未保存总数 |

## 5. 正常、基线与异常示例

正常：发现 24,000 个普通文件，纳入 23,000 个，空文件 200 个，范围外 800 个；其中 17,000 个同大小候选进入 Hash，6,000 个大小唯一无需 Hash。不能把 `24,000 - 17,000` 宣称为重复数。

基线：仅一个唯一大小文件，发现 1、纳入 1、候选 0、免 Hash 1。

异常：发现两个子目录，其中一个不可读；显示已发现数量及目录读取错误，标不完整，不能称已覆盖全部内容。

## 6. 必需测试

- `tests/test_duplicate_scan_core.py`：嵌套/空目录、空文件/范围过滤互斥、云占位与链接、类型/stat/目录迭代错误、取消、候选分母、独立快照、节流及回调异常隔离；保留原 Hash 碰撞和回收安全断言。
- `tests/test_folder_dedupe_features.py`：真实 worker 在完成前发出统计；真实按钮扫描最终数、零候选、取消/失败/重扫/清空、历史未知、中英切换；分类与 keeper 操作不改变目录数。等待有界、线程清理。
- `tests/test_scan_record_core.py`：带 coverage 结果仍输出原 v1 键集合，往返后 coverage 为 None，手工添加 coverage 键仍按未知键拒绝。
- 布局：独立/真实内嵌 × 中文/英文，默认与窄宽下主行/明细不撑宽、不覆盖底部预计空间。

## 7. 错误与正确写法

```python
# 错：Hash 分母冒充目录总数；把同一可变对象发给 GUI。
label.setText(f'全部文件：{hash_total}')
callback(coverage)
coverage.files += 1

# 对：发布独立快照，GUI 分别呈现 files 和 hash_candidates。
callback(dataclasses.replace(coverage))
# hash_candidates 为 None 时显示待确定，不能当作零。
```
