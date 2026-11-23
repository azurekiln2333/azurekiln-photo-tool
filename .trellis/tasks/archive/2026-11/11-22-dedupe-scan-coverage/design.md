# 设计

## 边界和数据流
现有 collect_files 仅返回纳入查重的非空文件列表。单次递归遍历中同时收集轻量覆盖统计，经 find_internal_duplicates 的可选回调传入 DedupeScanWorker 的 object 信号，主线程只格式化、显示快照。ScanResult 新增可选 coverage，既有 scanned_files 语义不变；跨目录比对调用和记录 schema v1 保持原契约。

## 共享接口

```python
@dataclass
class ScanCoverage:
    folders: int = 0  # 已发现可识别的普通子目录，不含根；不可读取的子目录仍计数
    files: int = 0  # 可识别的普通文件，含0字节及scope范围外
    included_files: int = 0  # 正数大小且符合scope，即scanned_files
    zero_byte_files: int = 0
    filtered_files: int = 0  # 先判空再判scope，与zero互斥
    skipped_links: int = 0  # 不跟随的symlink/junction/重解析目录，可能文件或目录
    other_entries: int = 0
    entry_errors: int = 0  # 类型/stat失败，不能推断文件还是目录
    directory_errors: int = 0  # scandir打开或迭代失败
    hash_candidates: int | None = None  # None=枚举中未确定，0=确定无候选
    enumeration_complete: bool = False  # 枚举完且无枚举错误、未取消

ScanResult.coverage: ScanCoverage | None = None
collect_files(..., coverage: ScanCoverage | None = None,
              on_coverage: Callable[[ScanCoverage], None] | None = None) -> list[FileEntry]
find_internal_duplicates(..., on_coverage: Callable[[ScanCoverage], None] | None = None) -> ScanResult
```

可选新增参数均为keyword-only。核心负责唯一口径：files=included_files+zero_byte_files+filtered_files。已知目录在发现时计数；根不计。links不归入files/folders，未知other_entries单列。发生entry_errors/directory_errors或取消则enumeration_complete=False。Hash阶段前计算hash_candidates=len(hash_targets)，与哈希分母严格一致；included_files-hash_candidates表示大小唯一且无需Hash的项，而不是重复数量。

回调发送独立快照（dataclasses.replace），不得发送随后会变更的同一对象。正常节流约100ms/适当批量，在初始化、枚举收尾、候选确定时强制发布；外部回调异常不得中断扫描。保留现有on_progress(stage,done,total)签名与语义，哈希任务完成计数含失败尝试，hashed_files仍仅成功。

## GUI
结果表格上方新增CardWidget中的醒目 scan_inventory_summary（主行，folders/files）与换行 scan_inventory_detail（纳入/Hash候选/免Hash/跳过原因）。枚举进行中显示“扫描中”，有错误或取消的最终结果显示“统计不完整”；完成不表示已扫描链接目标。tooltip明确根不计、链接不跟随、读不到的后代未知、Hash分母说明。复用既有progress/status，不挤压底部预计空间。

DedupeScanWorker.coverage_update=pyqtSignal(object)，连接 MainWindow._update_scan_coverage；窗口保存 self._scan_coverage 与扫描阶段标记，重置清空；扫描完成使用 result.coverage 最终替换，错误保留最后计数标记不完整。导入记录切换为history state：coverage=None，只展示已有 scanned_files/hashed_files并注明历史未记录总量。语言切换统一_refresh_scan_inventory。

## 兼容与回退
ScanCoverage是本轮运行时展示快照，scan_record_core显式投影仍输出原v1字段，不新增记录键；导出后再导入不保留覆盖统计，UI明确未知。其他ScanResult使用方由默认None兼容。删除新增控件/信号/可选参数即可回退，不涉及数据迁移。

## 补充交互修复边界

差距在结果表的交互与回收目标收集：已有底部keeper按钮不够直观，分类隐藏只改变展示而回收仍扫全模型，Fluent滚动需检查其实际像素步长。keeper增加明确行级选择入口，仍统一调用原角色转换，不重建行、不放宽stale/cancelled/已处理组限制。当前分类目标列表作为按钮可用性、确认框和worker提交的共同来源；隐藏类不修改。容量明示全局总量及当前分类选中容量，避免与本次回收数量混淆。

文件边界：folder_dedupe_gui.py实现keeper及分类回收；dedupe_table_scroll.py集中配置两张大缩略图结果表滚动，dir_compare_gui.py仅接入；tests/test_folder_dedupe_features.py和tests/test_dedupe_table_scroll.py验证真实鼠标、wheel事件与worker。扫描、哈希、安全复核和schema不改。无需新增第三方依赖，不调整其它功能页滚动。
