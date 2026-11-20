# 技术设计与并行边界

## 分工

- Pi preview：`media_thumbnail.py`、`tests/test_media_thumbnail.py`；布局、视频解码回退、失败重试。预览完成后接手 `folder_dedupe_gui.py`、`tests/test_folder_dedupe_features.py`，实现目录内去重页批量选择/异步记录并验证。
- Pi records：仅 `scan_record_core.py`、`tests/test_scan_record_core.py`；标准库记录格式与安全校验。
- Pi pages：仅 `dir_compare_gui.py`、`tests/test_compare_page_features.py`；目录比对页 splitter、批量勾选、记录入口及异步 I/O。03:12 起目录内去重页转交 preview Pi，双方测试各自独立文件，禁止重叠覆盖。
- Pi release：仅 `AzureKilnPhotoTool_onefile.spec`、`.github/workflows/build.yml`、`scripts/ci/verify_bundle.py`、README 三语；发布视频依赖覆盖、文档与整体验证。
- 主会话：任务/spec、版本号、统一窗口关闭协调、独立复核和发布协调。四个 Pi 在 herdr 的 LivePhotosSpilt 工作区 w55 同工作区并行；preview=p8、records=p4、pages=pA、release=pB。禁止撤销他人改动；worker 不提交/推送/切分支。早期隐藏批次已停止，不再使用。

当前复核分工：records 已交付，p4 转独立 `trellis-check`，负责修复共享预览的实际窄侧栏换行/高度与 `file_context_menu.py` 析构异常（含局部测试），不改两页实施文件。p8 只实施目录内去重页，暂停写共享预览，避免交叉覆盖。主会话拥有 `tests/test_unified_close.py`，验证真实记录线程在统一窗口关闭时安全收尾。保持现有模型与供应商。

## 共享记录 API（先按此契约编码）

`scan_record_core.py` 不依赖 Qt，公开：

```python
@dataclass
class ScanRecord:
    mode: str                      # 'compare' 或 'internal'
    root_a: Path                    # A 或单根
    root_b: Path | None
    scope: str                     # 'all' / 'media'
    keep_strategy: str              # 'shallowest' / 'oldest' / 'newest'
    result: ScanResult
    row_states: dict[str, dict]     # 绝对文件路径 -> {'checked': bool, 'status': str}
    created_at: str = ''
    stale: bool = False

def save_record(path: Path, record: ScanRecord) -> None: ...
def load_record(path: Path, *, expected_mode: str | None = None) -> ScanRecord: ...
```

失败抛 ValueError 或 OSError，保存同目录暂存 + 原子替换，格式 schema_version=1、UTF-8。有合理文件大小/数量边界，严格类型、不允许路径跨根、嵌套根、重复目标、保留项与目标相交。mismatch/issue 路径也受对应根保护。保存/读取不读取媒体内容，不执行回收。历史快照 size/mtime/file_id/sha256 保留，加载不把它当作已复核状态。

## GUI

保存最近完整 ScanResult 和扫描时根/选项快照，导出不能使用后来修改过的目录控件。记录 I/O 放后台线程，使用既有忙/关闭协议；先完整解析成功再替换当前显示。导入恢复 root/options 与行状态，标记 `_record_imported=True`，创建 RecycleWorker 时强制 byte_verify=True；取消/失效仍受已有 guard。已回收行保持不可勾选。两页全选/反选通过模型批量改 checked 一次发刷新。

统一主窗口搬走页面内容后，页面自己的 closeEvent 不会执行。`UnifiedMainWindow.closeEvent` 须检查两页 `_is_busy()`（包含记录 I/O 与队列），请求 `_shutdown_workers()`，用主线程定时器延后再关；不能在记录线程未收尾时只关缩略图池然后销毁窗口。该集成修复仅触及 unified_gui.py，不重构页面 worker。

## 预览与视频

根因在共享预览槽，使用可在任意字符换行且不产生长最小宽度的路径标签、相同水平约束、动态等比图片尺寸。两页 splitter 不允许外层 widget 的最小尺寸反向撑开窗口。

视频回退优先复用已装 QtMultimedia/其 FFmpeg 后端，或 PATH/打包内 FFmpeg；不得新增庞大下载依赖而不通知主会话。worker 先实测选择方案，向主会话明确打包要求。使用后台事件循环/有界超时，图像转换遵循线程约束；负缓存有限过期或显式重试并重查 stat，避免重绘形成无限队列。保留错误信息供 UI 显示。

## 兼容和回滚

保持 PreviewPanel 与 ThumbnailLoader 既有公共接口。记录是新文件，不改变用户设置格式。所有回收仍通过 duplicate_scan_core.revalidate_pair/recycle_duplicate，禁止用导入结果直接 send2trash。发布使用已有 Actions，不碰已有 tag；首次 v1.2.1 的 CI 暴露测试隐式 ExifTool 依赖，保留该标签，修正后最终补丁为 v1.2.2。
