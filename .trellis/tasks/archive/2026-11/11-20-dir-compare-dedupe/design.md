# 技术设计：目录比对与目录内去重

## 模块边界（4 个工作包，文件互不重叠，可并行）

| 工作包 | 文件（只允许改这些） | 说明 |
|---|---|---|
| WP1 核心 | `duplicate_scan_core.py`（新）、`tests/test_duplicate_scan_core.py`（新） | Qt 无关；扫描、哈希、逐字节比对、执行前复核、回收 |
| WP2 缩略图 + 集成 | `media_thumbnail.py`（新）、`unified_gui.py`、`README.md`、`docs/README.en.md`、`docs/README.zh-TW.md`、`*.spec`（仅在需要时） | 共享缩略图加载器与预览面板；导航注册；文档 |
| WP3 比对页 | `dir_compare_gui.py`（新） | 目录比对页面 |
| WP4 去重页 | `folder_dedupe_gui.py`（新） | 目录内去重页面 |

**任何工作包都不得修改其他工作包的文件。** 如果发现契约不够用，在自己文件里做适配，并在汇报里说明，不要改别人的文件。
`dedupe_media_gui.py`、`media_statistics_*`、`media_readme_core.py` 不在本任务范围，禁止修改（工作区里有另一个任务的未提交改动）。

GUI 页面的风格、结构、tr 字典、设置持久化、embedded 模式、send2trash 导入方式、QThread worker 模式，**参照现有 `dedupe_media_gui.py`**（只读参考，不要改它）。

## 契约 1：`duplicate_scan_core.py`（WP1 实现，WP3/WP4 调用）

纯 Python，标准库 + 可选 `send2trash`（导入失败时 `send2trash = None`，回收函数返回失败原因 `send2trash_unavailable`）。

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

ScanScope = Literal["all", "media"]                 # "all" 默认
KeepStrategy = Literal["shallowest", "oldest", "newest"]   # "shallowest" 默认
ProgressCallback = Callable[[str, int, int], None]  # (stage, done, total)；stage ∈ {"enumerate","hash","verify"}
CancelCheck = Callable[[], bool]                    # 返回 True 表示应尽快停止

MEDIA_EXTENSIONS: frozenset[str]   # 小写带点，照片+视频（含 .heic .heif .jpg .jpeg .png .gif .webp .bmp .tif .tiff .dng .raw .cr2 .nef .arw .mp4 .mov .m4v .avi .mkv .3gp .wmv .mts .m2ts 等）

@dataclass(frozen=True)
class FileEntry:
    path: Path          # 绝对路径
    root: Path          # 所属扫描根目录
    size: int
    mtime_ns: int
    file_id: tuple[int, int]   # (st_dev, st_ino)

    @property
    def relative_path(self) -> Path: ...

@dataclass
class DuplicateGroup:
    keeper: FileEntry               # 参照/保留文件。比对模式：A 中的文件；去重模式：按策略选出的保留文件
    duplicates: list[FileEntry]     # 已逐字节确认与 keeper 一致的回收候选（比对模式：全部是 B 中的文件）
    sha256: str
    size: int

@dataclass
class HashMismatch:
    keeper: FileEntry
    other: FileEntry
    sha256: str          # 哈希相同但逐字节不同

@dataclass
class ScanIssue:
    path: Path
    stage: str           # "enumerate" | "hash" | "verify"
    message: str

@dataclass
class ScanResult:
    groups: list[DuplicateGroup] = field(default_factory=list)
    mismatches: list[HashMismatch] = field(default_factory=list)
    issues: list[ScanIssue] = field(default_factory=list)
    scanned_files: int = 0
    hashed_files: int = 0
    hashed_bytes: int = 0
    cancelled: bool = False

def validate_compare_roots(root_a: Path, root_b: Path) -> None:
    """不存在/不是目录/相同/互相嵌套（realpath + normcase 后判断）→ raise ValueError(code)。
    code ∈ {"a_missing","b_missing","same_root","b_inside_a","a_inside_b"}"""

def collect_files(root: Path, scope: ScanScope = "all", *, should_cancel: CancelCheck | None = None,
                  on_progress: ProgressCallback | None = None, issues: list[ScanIssue] | None = None) -> list[FileEntry]:
    """os.scandir 递归；不跟随 symlink/junction/重解析点（检查 is_symlink、st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT、Py3.12+ is_junction）；
    跳过 0 字节文件；scope="media" 时按扩展名过滤；错误写入 issues 不抛出。结果按 path 排序（确定性）。"""

def sha256_file(path: Path, *, chunk_size: int = 1 << 20, should_cancel: CancelCheck | None = None) -> str:
    """完整文件 SHA-256（hex 小写）。取消时抛 ScanCancelled。"""

def files_identical(a: Path, b: Path, *, chunk_size: int = 1 << 20, should_cancel: CancelCheck | None = None) -> bool:
    """先比 size，再分块逐字节比较。取消时抛 ScanCancelled。"""

class ScanCancelled(Exception): ...

def find_cross_duplicates(root_a: Path, root_b: Path, *, scope: ScanScope = "all", threads: int = 4,
                          should_cancel: CancelCheck | None = None,
                          on_progress: ProgressCallback | None = None) -> ScanResult:
    """目录比对。流程：validate_compare_roots → collect A、B → 只保留 B 中 size 在 A 中出现过的、以及对应 A 文件
    → 线程池算完整 SHA-256 → 按 (size, sha256) 匹配 → 每个 B 候选与该组 A 参照文件（A 组内按 path 排序取第一个）逐字节比对
    → 一致的进 group.duplicates，不一致的进 mismatches。一个 A 内容对应一个 DuplicateGroup，B 中多份副本都在 duplicates 里。
    keeper 一定来自 A，duplicates 一定来自 B。取消时 result.cancelled=True 并返回已有部分（GUI 不应允许对取消的结果执行回收）。"""

def find_internal_duplicates(root: Path, *, scope: ScanScope = "all", keep_strategy: KeepStrategy = "shallowest",
                             threads: int = 4, should_cancel: CancelCheck | None = None,
                             on_progress: ProgressCallback | None = None) -> ScanResult:
    """目录内去重。按 size 分组 → 只对 size 组内 >1 的文件算 SHA-256 → 按 (size, sha256) 分组
    → 用 keep_strategy 选 keeper → 其余文件逐字节比对 keeper，一致进 duplicates，不一致进 mismatches。
    只有 duplicates 非空的组才输出。"""

def choose_keeper(entries: list[FileEntry], strategy: KeepStrategy) -> FileEntry:
    """shallowest: (相对路径层级数, len(str(relative_path)), casefold path)
       oldest: (mtime_ns, casefold path)   newest: (-mtime_ns, casefold path)"""

# ---- 执行阶段 ----
SkipReason = Literal["target_missing","keeper_missing","target_changed","keeper_changed",
                     "same_path","content_differs","read_error"]

def revalidate_pair(target: FileEntry, keeper: FileEntry, *, byte_verify: bool = True,
                    should_cancel: CancelCheck | None = None) -> SkipReason | None:
    """返回 None 表示可以回收。检查：target.path != keeper.path（realpath 比较）→ 两者存在 →
    size/mtime_ns 与扫描时一致 → byte_verify 时 files_identical。读错误返回 "read_error"。"""

@dataclass
class RecycleOutcome:
    target: FileEntry
    status: Literal["recycled","skipped","failed"]
    reason: str = ""      # skipped: SkipReason；failed: 异常信息或 "send2trash_unavailable"

def recycle_duplicate(target: FileEntry, keeper: FileEntry, *, byte_verify: bool = True,
                      should_cancel: CancelCheck | None = None) -> RecycleOutcome:
    """revalidate_pair 通过后 send2trash(str(target.path))。单文件粒度，GUI worker 循环调用以支持暂停/停止。"""
```

### 准确性不变量（WP1 必须用测试锁住）
1. 进入 `duplicates` 的文件一定满足：size 相同 ∧ SHA-256 相同 ∧ `files_identical` 为 True。
2. `keeper` 永远不会出现在任何 `duplicates` 里；比对模式下任何 A 中路径都不会出现在 `duplicates`。
3. `recycle_duplicate` 在 `revalidate_pair` 不通过时绝不调用 send2trash。
4. 任何读错误只产生 issue / skipped，不抛到调用方（`ScanCancelled` 除外，由 find_* 内部捕获并设置 cancelled）。

### 性能
- size 预筛后才算哈希；哈希用 `ThreadPoolExecutor(threads)`；分块读取 1 MiB。
- 进度回调节流（例如每 50 个文件或 ≥200ms 一次），避免刷爆 GUI 信号。

## 契约 2：`media_thumbnail.py`（WP2 实现，WP3/WP4 调用）

```python
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

class ThumbnailLoader(QObject):
    thumbnail_ready = pyqtSignal(str)          # 参数：str(path)；收到后调用 request() 会命中缓存

    def __init__(self, size: int = 96, max_workers: int = 2, cache_limit: int = 3000, parent=None): ...
    def request(self, path: Path) -> QPixmap:
        """立即返回：缓存命中→缩略图；未命中→按文件类型的占位图，并在后台排队加载（同一路径不重复排队）。
        必须只在 GUI 线程调用。"""
    def clear(self) -> None: ...        # 清缓存、取消排队任务（新扫描时调用）
    def shutdown(self) -> None: ...     # 页面关闭时调用，停止线程池

class PreviewPanel(QWidget):
    """侧边预览：1 或 2 个大图槽位（默认 256px），每个槽位下方显示 标题/完整路径/大小/mtime。"""
    def __init__(self, slots: int = 2, size: int = 256, parent=None): ...
    def set_slot(self, index: int, title: str, path: Path | None, size_bytes: int | None = None,
                 mtime_ns: int | None = None) -> None: ...
    def clear(self) -> None: ...
    def set_language(self, lang: str) -> None: ...   # 只影响面板内固定文案

def placeholder_pixmap(size: int, kind: str) -> QPixmap: ...   # kind ∈ {"image","video","other"}
```

缩略图实现要求：
- 后台线程只产出 `QImage`（QPixmap 只能在 GUI 线程创建），回到 GUI 线程后转 QPixmap 入缓存再 emit。
- 加载顺序：① Windows Shell 缩略图（ctypes：`SHCreateItemFromParsingName` + `IShellItemImageFactory::GetImage`，照片/视频/HEIC 都依赖系统能力；每个工作线程 `CoInitializeEx`；HBITMAP → QImage 并 `DeleteObject`）→ ② `QImageReader`（`setAutoTransform(True)`，`setScaledSize` 缩放读取）→ ③ 占位图。任一步异常吞掉进入下一步，绝不崩溃。
- 非 Windows 平台跳过 ①。
- LRU 缓存，key 为 `(str(path), mtime_ns)`。
- 表格模型在 `Qt.ItemDataRole.DecorationRole` 里调用 `request()`，因此只有可见行会触发加载；收到 `thumbnail_ready(path)` 后对该路径对应行 emit `dataChanged`（页面自己维护 path→rows 映射）。

## 右键菜单 / 打开
- 复用 `file_context_menu.py` 的现有能力（WP3/WP4 先读它的接口；若其接口只支持单一路径列，则在自己页面里组合调用，不修改该文件）。
- "打开所在目录"在 Windows 上用 `explorer /select,<path>`（若 `file_context_menu.py` 已有就用它的）。
- 双击行 → `QDesktopServices.openUrl(QUrl.fromLocalFile(...))`。

## 页面契约（WP3/WP4 实现，WP2 在 unified_gui 中注册）

两个页面都与现有功能页同形：
```python
class MainWindow(FramelessMainWindow):
    def __init__(self, parent=None, embedded: bool = False): ...
```
并提供与 `dedupe_media_gui.MainWindow` 相同的语言切换接口（方法名/属性以 `dedupe_media_gui.py` 为准，WP2 的 unified_gui 用同样方式调用）。
- `dir_compare_gui.MainWindow` —— 导航 key `"dir_compare"`，中文 "目录比对"，英文 "Folder Compare"
- `folder_dedupe_gui.MainWindow` —— 导航 key `"folder_dedupe"`，中文 "目录内去重"，英文 "Folder Dedupe"
- 设置文件各自独立（参照 dedupe 页的 `_get_settings_path` 方式，文件名分别为 `dir_compare_settings.json`、`folder_dedupe_settings.json`）。

### 页面公共要素
- 控件：目录选择（比对页 A、B 两个；去重页一个）、扫描范围（所有文件/仅照片视频）、哈希线程数、"执行前再次逐字节复核"（默认勾选）、去重页额外"保留策略"。
- 按钮：开始扫描 / 停止扫描 / 移入回收站 / 暂停-继续 / 停止回收。
- 表格：`QTableView` + 自定义 `QAbstractTableModel`；第一列勾选框（`ItemIsUserCheckable`）；缩略图列 `DecorationRole`；行高 = 缩略图尺寸 + 8。
- 状态列：待处理 / 已回收 / 已跳过（原因）/ 失败（原因）/ 校验不一致 / 读取问题。校验不一致与读取问题行不可勾选，红色/橙色标识。
- 右侧 `PreviewPanel`（可用 QSplitter）。
- 汇总标签：可回收 N 个 / 共 X；校验不一致 M；读取问题 K；执行后补充已回收/跳过/失败。
- 扫描结果 `cancelled=True` 时禁止执行回收，并提示重新扫描。
- 执行确认对话框：文件数 + 总大小 + "仅移入回收站"。
- Worker：扫描 worker 调 `find_cross_duplicates` / `find_internal_duplicates`；回收 worker 循环调 `recycle_duplicate`，每个文件之间检查暂停/停止，批量回传状态更新（参照 dedupe 页的批量信号做法）。
- 页面关闭/切换语言时不得中断正在运行的 worker 导致崩溃；关闭时调用 `ThumbnailLoader.shutdown()`。

### 比对页表格列
☐ | B 缩略图 | A 缩略图 | B 文件（相对 B 的路径） | 对应 A 文件（相对 A 的路径） | 大小 | 修改时间 | SHA-256（前 12 位，tooltip 显示完整） | 状态
预览面板：槽位 0 = B 文件，槽位 1 = 对应 A 文件。
右键额外项：打开对应 A 文件、打开 A 文件所在目录。

### 去重页表格列
☐ | 组号 | 缩略图 | 角色（保留/重复） | 路径（相对根目录） | 大小 | 修改时间 | SHA-256（前 12 位） | 状态
同组行底色按组号交替。保留行不可勾选。
预览面板：槽位 0 = 选中文件，槽位 1 = 本组保留文件。
右键额外项：打开保留文件所在目录。

## 取舍
- 用 SHA-256 而非 MD5：MD5 存在可构造碰撞；但最终判定依据是逐字节比对，哈希只用于分组提速。
- 执行前默认再逐字节复核一次：会多读一遍文件，但符合"准确优先"的要求；用户可关闭以提速，关闭后仍做存在性与 size/mtime 检查。
- 不跟随链接：可能漏掉经由联接点才能到达的文件，但避免循环和越界删除。

## 回滚
全部为新增文件 + `unified_gui.py` 少量注册代码；回滚 = 删除新文件并还原 unified_gui 中的注册行。
