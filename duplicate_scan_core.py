"""目录比对与目录内去重的共享核心（无 PyQt 依赖）。

准确判定「内容一致」的唯一依据是三重校验：
    大小相同 ∧ 完整文件 SHA-256 相同 ∧ 与参照文件逐字节比对完全相同
哈希只用于分组提速，任何进入 ``DuplicateGroup.duplicates`` 的文件都必然经过
``files_identical`` 的逐字节确认；哈希相同但内容不同的文件进入 ``mismatches``，
绝不参与回收。

契约见 ``.trellis/tasks/11-20-dir-compare-dedupe/design.md`` 的「契约 1」。
本模块只依赖标准库（``send2trash`` 可选），禁止在内部 import PyQt。
"""

from __future__ import annotations

import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Callable, Iterable, Literal

try:  # 回收能力是可选依赖：缺失时回收函数返回 send2trash_unavailable
    from send2trash import send2trash
except Exception:  # pragma: no cover - 仅依赖缺失时触发
    send2trash = None  # type: ignore[assignment]

__all__ = [
    "MEDIA_EXTENSIONS",
    "MediaType",
    "VIDEO_EXTENSIONS",
    "CancelCheck",
    "DuplicateGroup",
    "FileEntry",
    "HashMismatch",
    "KeepStrategy",
    "ProgressCallback",
    "RecycleOutcome",
    "ScanCancelled",
    "ScanCoverage",
    "ScanIssue",
    "ScanResult",
    "ScanScope",
    "SkipReason",
    "choose_keeper",
    "classify_duplicate_group",
    "classify_media_type",
    "collect_files",
    "files_identical",
    "find_cross_duplicates",
    "find_internal_duplicates",
    "recycle_duplicate",
    "reselect_internal_keeper",
    "revalidate_pair",
    "send2trash",
    "sha256_file",
    "validate_compare_roots",
]

ScanScope = Literal["all", "media"]                          # "all" 默认
KeepStrategy = Literal["shallowest", "oldest", "newest"]     # "shallowest" 默认
MediaType = Literal["photo", "video", "other"]
ProgressCallback = Callable[[str, int, int], None]           # (stage, done, total)
CancelCheck = Callable[[], bool]                             # True 表示应尽快停止

# 分块读取大小（1 MiB）：哈希与逐字节比对共用，避免大文件抖动
CHUNK_SIZE = 1 << 20

# Windows 文件属性中的「重解析点」标记（junction / 挂载点 / 云占位）
FILE_ATTRIBUTE_REPARSE_POINT = 0x400

# 照片 + 视频扩展名（小写带点）。scope="media" 时按此集合过滤。
MEDIA_EXTENSIONS: frozenset[str] = frozenset(
    {
        # 照片
        ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".gif", ".webp", ".bmp",
        ".heic", ".heif", ".avif", ".tif", ".tiff",
        # 原始格式
        ".dng", ".raw", ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".sr2",
        ".orf", ".rw2", ".raf", ".pef", ".srw", ".3fr", ".erf", ".kdc", ".mrw",
        ".dcr", ".x3f",
        # 视频
        ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".3gp", ".3g2", ".wmv", ".mts",
        ".m2ts", ".m2t", ".mpg", ".mpeg", ".flv", ".f4v", ".webm", ".ts", ".mxf",
        ".vob", ".asf", ".rm", ".rmvb",
    }
)

# ``MEDIA_EXTENSIONS`` 的视频子集；剩余媒体扩展名统一视为照片（含 RAW）。
VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".3gp", ".3g2", ".wmv", ".mts",
        ".m2ts", ".m2t", ".mpg", ".mpeg", ".flv", ".f4v", ".webm", ".ts", ".mxf",
        ".vob", ".asf", ".rm", ".rmvb",
    }
)


class ScanCancelled(Exception):
    """扫描/哈希/比对被取消（由调用方的 CancelCheck 触发）。"""


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileEntry:
    """扫描阶段得到的单个文件快照。"""

    path: Path                  # 绝对路径
    root: Path                  # 所属扫描根目录
    size: int
    mtime_ns: int
    file_id: tuple[int, int]    # (st_dev, st_ino)；用于识别同一物理文件

    @property
    def relative_path(self) -> Path:
        """相对所属扫描根目录的路径（拿不到时退化为文件名）。"""
        try:
            return self.path.relative_to(self.root)
        except ValueError:
            return Path(self.path.name)


@dataclass
class DuplicateGroup:
    """一组内容完全一致的文件。

    比对模式：``keeper`` 来自 A（保留库），``duplicates`` 全部来自 B（待清理）。
    去重模式：``keeper`` 是按策略选出的保留文件，``duplicates`` 是待回收的副本。
    """

    keeper: FileEntry
    duplicates: list[FileEntry]
    sha256: str
    size: int


def classify_duplicate_group(group: DuplicateGroup) -> MediaType:
    """按整组分类，混合扩展名时固定采用 photo > video > other。"""
    if not isinstance(group, DuplicateGroup):
        raise ValueError("group_invalid")
    if not isinstance(group.keeper, FileEntry) or not isinstance(group.duplicates, list):
        raise ValueError("group_invalid")
    if not group.duplicates:
        return classify_media_type(group.keeper.path)
    members = [group.keeper, *group.duplicates]
    if any(not isinstance(member, FileEntry) for member in members):
        raise ValueError("group_member_invalid")
    kinds = {classify_media_type(member.path) for member in members}
    if "photo" in kinds:
        return "photo"
    if "video" in kinds:
        return "video"
    return "other"


def reselect_internal_keeper(group: DuplicateGroup, new_keeper: FileEntry) -> DuplicateGroup:
    """纯内存地为同根 internal 组重选 keeper；不修改输入，不验证磁盘状态。

    候选必须是组内成员的完整扫描快照。此函数不检查文件存在性，也不验证内容；
    实际回收仍须经过 ``revalidate_pair``。
    """
    if not isinstance(group, DuplicateGroup):
        raise ValueError("group_invalid")
    if not isinstance(group.keeper, FileEntry) or not isinstance(group.duplicates, list):
        raise ValueError("group_invalid")
    if not isinstance(new_keeper, FileEntry):
        raise ValueError("keeper_invalid")
    if not group.duplicates:
        raise ValueError("group_empty")

    members = [group.keeper, *group.duplicates]
    if any(not isinstance(member, FileEntry) for member in members):
        raise ValueError("group_member_invalid")

    root_key = _lexical_path_key(group.keeper.root)
    seen_paths: set[str] = set()
    for member in members:
        if _lexical_path_key(member.root) != root_key:
            raise ValueError("group_cross_root")
        if member.size != group.size:
            raise ValueError("group_size_mismatch")
        path_key = _lexical_path_key(member.path)
        if path_key in seen_paths:
            raise ValueError("group_duplicate_path")
        seen_paths.add(path_key)

    selected_key = _entry_snapshot_key(new_keeper)
    selected = next(
        (member for member in members if _entry_snapshot_key(member) == selected_key),
        None,
    )
    if selected is None:
        raise ValueError("keeper_not_group_member")
    remaining = sorted(
        (member for member in members if member is not selected),
        key=_path_sort_key,
    )
    return DuplicateGroup(
        keeper=selected,
        duplicates=remaining,
        sha256=group.sha256,
        size=group.size,
    )


@dataclass
class HashMismatch:
    """SHA-256 相同但逐字节不同的文件对：绝不回收，单独计数展示。"""

    keeper: FileEntry
    other: FileEntry
    sha256: str


@dataclass
class ScanIssue:
    """扫描/哈希/复核过程中的问题项（读取失败、权限不足、扫描中消失等）。"""

    path: Path
    stage: str          # "enumerate" | "hash" | "verify"
    message: str


@dataclass
class ScanCoverage:
    """单次扫描已发现的目录项统计；不推算未能枚举的后代。"""

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


@dataclass
class ScanResult:
    groups: list[DuplicateGroup] = field(default_factory=list)
    mismatches: list[HashMismatch] = field(default_factory=list)
    issues: list[ScanIssue] = field(default_factory=list)
    scanned_files: int = 0
    hashed_files: int = 0
    hashed_bytes: int = 0
    cancelled: bool = False
    coverage: ScanCoverage | None = None


SkipReason = Literal[
    "target_missing",
    "keeper_missing",
    "target_changed",
    "keeper_changed",
    "same_path",
    "content_differs",
    "read_error",
]


@dataclass
class RecycleOutcome:
    target: FileEntry
    status: Literal["recycled", "skipped", "failed"]
    reason: str = ""    # skipped: SkipReason；failed: 异常信息或 "send2trash_unavailable"


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _absolute_root(root: Path) -> Path:
    """把扫描根目录规范成绝对路径（不解析符号链接，避免越界到链接目标）。"""
    return Path(os.path.abspath(os.fspath(root)))


def _suffix(name: str) -> str:
    dot = name.rfind(".")
    if dot <= 0:
        return ""
    return name[dot:].casefold()


def _lexical_path_key(path: Path) -> str:
    """规范化路径文本但不解析链接或访问文件系统。"""
    return os.path.normcase(os.path.normpath(os.fspath(path)))


def _entry_snapshot_key(entry: FileEntry) -> tuple:
    """按路径/root 与完整扫描指纹标识条目，不触碰磁盘。"""
    return (
        _lexical_path_key(entry.path),
        _lexical_path_key(entry.root),
        entry.size,
        entry.mtime_ns,
        entry.file_id,
    )


def classify_media_type(path: Path | str) -> MediaType:
    """按已有扩展名集合分类；只解析路径文本，不访问文件系统。"""
    suffix = _suffix(Path(os.fspath(path)).name)
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in MEDIA_EXTENSIONS:
        return "photo"
    return "other"


def _path_sort_key(value: FileEntry | Path) -> str:
    """确定性排序键（大小写不敏感，跨平台稳定）。"""
    path = value.path if isinstance(value, FileEntry) else value
    return str(path).casefold()


def _is_cancelled(should_cancel: CancelCheck | None) -> bool:
    if should_cancel is None:
        return False
    try:
        return bool(should_cancel())
    except Exception:
        # 取消回调本身出错不能中断扫描，按「不取消」处理
        return False


def _describe_error(exc: BaseException) -> str:
    """把文件系统异常转成中文可读原因（GUI 直接展示）。"""
    if isinstance(exc, PermissionError):
        return "没有访问权限"
    if isinstance(exc, FileNotFoundError):
        return "文件不存在或已被移除"
    if isinstance(exc, IsADirectoryError):
        return "路径是目录，不是文件"
    text = getattr(exc, "strerror", None) or str(exc)
    return f"读取失败：{text}"


def _real_key(path: Path) -> str:
    """真实路径 + 大小写归一，用于判断「是否同一路径」。"""
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def _same_file_identity(a: FileEntry, b: FileEntry) -> bool:
    """是否指向同一物理文件（硬链接）；inode 为 0 时不可信，直接放弃判断。"""
    if not a.file_id[1] or not b.file_id[1]:
        return False
    return a.file_id == b.file_id


class _ProgressReporter:
    """进度回调节流：每 50 项或 200 ms 最多回调一次，避免刷爆 GUI 信号。"""

    def __init__(
        self,
        callback: ProgressCallback | None,
        *,
        min_interval: float = 0.2,
        min_step: int = 50,
        small_total: int = 200,
    ) -> None:
        self._callback = callback
        self._min_interval = min_interval
        self._min_step = min_step
        self._small_total = small_total
        self._last_time = 0.0
        self._last_done = -(10**9)
        self._last_stage = ""

    def __call__(self, stage: str, done: int, total: int, *, force: bool = False) -> None:
        if self._callback is None:
            return
        now = time.monotonic()
        # 小任务逐条回调（开销可忽略），大任务才节流
        never_throttle = 0 < total <= self._small_total
        if not force and not never_throttle and stage == self._last_stage and done != total:
            step_ok = (done - self._last_done) >= self._min_step
            time_ok = (now - self._last_time) >= self._min_interval
            if not (step_ok or time_ok):
                return
        self._last_time = now
        self._last_done = done
        self._last_stage = stage
        try:
            self._callback(stage, done, total)
        except Exception:
            # 进度回调异常不得中断扫描
            pass


class _CoverageReporter:
    """约每 100 ms 发布一次独立快照，阶段边界可强制发布。"""

    def __init__(self, callback: Callable[[ScanCoverage], None] | None) -> None:
        self._callback = callback
        self._last_time = float("-inf")

    def __call__(self, coverage: ScanCoverage | None, *, force: bool = False) -> None:
        if self._callback is None or coverage is None:
            return
        now = time.monotonic()
        if not force and now - self._last_time < 0.1:
            return
        self._last_time = now
        try:
            self._callback(replace(coverage))
        except Exception:
            # 展示回调失败不影响扫描结果。
            pass


def _classify_entry(entry: os.DirEntry) -> tuple[str, os.stat_result | None]:
    """判定条目类型：返回 ("link" | "dir" | "file" | "other", stat)。

    - 真实符号链接 / 目录联接（junction）一律视为 link，绝不跟随。
    - 带重解析属性的**目录**（junction / 挂载点）同样视为 link。
    - 带重解析属性的**文件**不因此排除：OneDrive 云占位也是重解析点，
      按 ``.trellis/spec/python/media-statistics.md`` 的约定，它不是链接，
      打开时由系统按需水化内容；把它当成链接会静默漏掉待清理的副本。
    """
    if entry.is_symlink():
        return "link", None
    is_junction = getattr(entry, "is_junction", None)
    if is_junction is not None and is_junction():
        return "link", None

    stat_result = entry.stat(follow_symlinks=False)
    is_dir = entry.is_dir(follow_symlinks=False)
    if is_dir and getattr(stat_result, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT:
        return "link", stat_result
    if is_dir:
        return "dir", stat_result
    if entry.is_file(follow_symlinks=False):
        return "file", stat_result
    return "other", stat_result


# ---------------------------------------------------------------------------
# 根目录校验与文件枚举
# ---------------------------------------------------------------------------


def validate_compare_roots(root_a: Path, root_b: Path) -> None:
    """校验目录比对的两个根目录。

    ValueError(code)：
        a_missing    A 不存在或不是目录
        b_missing    B 不存在或不是目录
        same_root    A 与 B 是同一个目录
        b_inside_a   B 在 A 内部
        a_inside_b   A 在 B 内部
    """
    path_a = _absolute_root(root_a)
    path_b = _absolute_root(root_b)
    if not path_a.is_dir():
        raise ValueError("a_missing")
    if not path_b.is_dir():
        raise ValueError("b_missing")

    real_a = os.path.normcase(os.path.realpath(os.fspath(path_a)))
    real_b = os.path.normcase(os.path.realpath(os.fspath(path_b)))
    if real_a == real_b:
        raise ValueError("same_root")
    if _is_within(real_b, real_a):
        raise ValueError("b_inside_a")
    if _is_within(real_a, real_b):
        raise ValueError("a_inside_b")


def _is_within(child_real: str, parent_real: str) -> bool:
    """child_real 是否位于 parent_real 之内（两者均已 realpath + normcase）。"""
    try:
        return os.path.commonpath([child_real, parent_real]) == parent_real and child_real != parent_real
    except ValueError:  # 不同盘符
        return False


def collect_files(
    root: Path,
    scope: ScanScope = "all",
    *,
    should_cancel: CancelCheck | None = None,
    on_progress: ProgressCallback | None = None,
    issues: list[ScanIssue] | None = None,
    coverage: ScanCoverage | None = None,
    on_coverage: Callable[[ScanCoverage], None] | None = None,
) -> list[FileEntry]:
    """递归枚举 root 下的文件（不返回目录）。

    - ``os.scandir`` 流式迭代，迭代中持续检查取消标志。
    - 不跟随符号链接 / 目录联接 / 重解析目录。
    - 跳过 0 字节文件（本工具只做内容去重，空文件无意义）。
    - ``scope="media"`` 时只保留 ``MEDIA_EXTENSIONS`` 中的扩展名。
    - 任何枚举/stat 错误写入 ``issues``，不抛出；结果按路径大小写不敏感排序。
    - 可用 ``coverage`` 接收本次枚举计数，或用 ``on_coverage`` 接收节流快照。
    """
    root_path = _absolute_root(root)
    collected: list[FileEntry] = []
    reporter = _ProgressReporter(on_progress)
    report_coverage = _CoverageReporter(on_coverage)
    if coverage is not None:
        # 提供的对象是本次扫描的输出，不沿用上次计数。
        for item in fields(ScanCoverage):
            setattr(coverage, item.name, item.default)
    elif on_coverage is not None:
        coverage = ScanCoverage()
    report_coverage(coverage, force=True)

    if not root_path.is_dir():
        if issues is not None:
            issues.append(
                ScanIssue(path=root_path, stage="enumerate", message="目录不存在或不是目录")
            )
        if coverage is not None:
            coverage.directory_errors += 1
        report_coverage(coverage, force=True)
        return collected

    scope_media = scope == "media"
    cancelled = False
    stack: list[Path] = [root_path]
    while stack:
        if _is_cancelled(should_cancel):
            cancelled = True
            break
        directory = stack.pop()
        try:
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    if _is_cancelled(should_cancel):
                        cancelled = True
                        break
                    entry_path = Path(entry.path)
                    try:
                        kind, stat_result = _classify_entry(entry)
                    except Exception as exc:  # 条目类型判定失败：记录问题，继续扫描
                        if issues is not None:
                            issues.append(
                                ScanIssue(
                                    path=entry_path, stage="enumerate", message=_describe_error(exc)
                                )
                            )
                        if coverage is not None:
                            coverage.entry_errors += 1
                        report_coverage(coverage)
                        continue

                    if kind == "link":
                        if coverage is not None:
                            coverage.skipped_links += 1
                    elif kind == "dir":
                        stack.append(entry_path)
                        if coverage is not None:
                            coverage.folders += 1
                    elif kind != "file" or stat_result is None:
                        if coverage is not None:
                            coverage.other_entries += 1
                    elif stat_result.st_size <= 0:
                        if coverage is not None:
                            coverage.files += 1
                            coverage.zero_byte_files += 1
                    elif scope_media and _suffix(entry.name) not in MEDIA_EXTENSIONS:
                        if coverage is not None:
                            coverage.files += 1
                            coverage.filtered_files += 1
                    else:
                        collected.append(
                            FileEntry(
                                path=entry_path,
                                root=root_path,
                                size=int(stat_result.st_size),
                                mtime_ns=int(stat_result.st_mtime_ns),
                                file_id=(int(stat_result.st_dev), int(stat_result.st_ino)),
                            )
                        )
                        if coverage is not None:
                            coverage.files += 1
                            coverage.included_files += 1
                        reporter("enumerate", len(collected), 0)
                    report_coverage(coverage)
        except Exception as exc:  # 目录枚举失败：记录问题，继续其他目录
            if issues is not None:
                issues.append(
                    ScanIssue(path=directory, stage="enumerate", message=_describe_error(exc))
                )
            if coverage is not None:
                coverage.directory_errors += 1
            report_coverage(coverage)
        if cancelled:
            break

    collected.sort(key=_path_sort_key)
    reporter("enumerate", len(collected), 0, force=True)
    if coverage is not None:
        coverage.enumeration_complete = not (
            cancelled or coverage.entry_errors or coverage.directory_errors
        )
    report_coverage(coverage, force=True)
    return collected


# ---------------------------------------------------------------------------
# 哈希与逐字节比对
# ---------------------------------------------------------------------------


def sha256_file(
    path: Path,
    *,
    chunk_size: int = CHUNK_SIZE,
    should_cancel: CancelCheck | None = None,
) -> str:
    """计算完整文件的 SHA-256（十六进制小写）。取消时抛 ``ScanCancelled``。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            if _is_cancelled(should_cancel):
                raise ScanCancelled(str(path))
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def files_identical(
    a: Path,
    b: Path,
    *,
    chunk_size: int = CHUNK_SIZE,
    should_cancel: CancelCheck | None = None,
) -> bool:
    """先比大小，再分块逐字节比较。取消时抛 ``ScanCancelled``。"""
    if os.stat(a).st_size != os.stat(b).st_size:
        return False
    with open(a, "rb") as left, open(b, "rb") as right:
        while True:
            if _is_cancelled(should_cancel):
                raise ScanCancelled(f"{a} <> {b}")
            chunk_left = left.read(chunk_size)
            chunk_right = right.read(chunk_size)
            if chunk_left != chunk_right:
                return False
            if not chunk_left:
                return True


def _hash_many(
    entries: Iterable[FileEntry],
    threads: int,
    should_cancel: CancelCheck | None,
    reporter: _ProgressReporter,
    result: ScanResult,
) -> tuple[dict[Path, str], bool]:
    """线程池计算 SHA-256；返回 (成功哈希表, 是否被取消)。读错误记入 issues。"""
    items = list(entries)
    total = len(items)
    hashes: dict[Path, str] = {}
    if total == 0:
        return hashes, False

    worker_count = max(1, int(threads or 1))
    done = 0
    cancelled = False
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="dup-hash") as pool:
        future_to_entry = {
            pool.submit(sha256_file, entry.path, should_cancel=should_cancel): entry
            for entry in items
        }
        for future in as_completed(future_to_entry):
            entry = future_to_entry[future]
            try:
                digest = future.result()
            except ScanCancelled:
                cancelled = True
                for pending in future_to_entry:
                    pending.cancel()
                break
            except Exception as exc:
                result.issues.append(
                    ScanIssue(path=entry.path, stage="hash", message=_describe_error(exc))
                )
            else:
                hashes[entry.path] = digest
                result.hashed_files += 1
                result.hashed_bytes += entry.size
            done += 1
            reporter("hash", done, total)

    if not cancelled:
        reporter("hash", total, total, force=True)
    return hashes, cancelled


# ---------------------------------------------------------------------------
# 查找重复
# ---------------------------------------------------------------------------


def _relative_depth(entry: FileEntry) -> int:
    """相对根目录的层级数（文件直接位于根目录下 = 0）。"""
    return max(0, len(entry.relative_path.parts) - 1)


def choose_keeper(entries: list[FileEntry], strategy: KeepStrategy) -> FileEntry:
    """按保留策略选出 keeper（平手按路径大小写不敏感排序，结果确定可复现）。

    shallowest: (相对路径层级数, len(str(relative_path)), casefold path)
    oldest:     (mtime_ns, casefold path)
    newest:     (-mtime_ns, casefold path)
    """
    if not entries:
        raise ValueError("entries_empty")
    if strategy == "shallowest":

        def sort_key(entry: FileEntry) -> tuple:
            relative = entry.relative_path
            return (_relative_depth(entry), len(str(relative)), _path_sort_key(entry))

    elif strategy == "oldest":

        def sort_key(entry: FileEntry) -> tuple:
            return (entry.mtime_ns, _path_sort_key(entry))

    elif strategy == "newest":

        def sort_key(entry: FileEntry) -> tuple:
            return (-entry.mtime_ns, _path_sort_key(entry))

    else:
        raise ValueError(f"unknown_strategy:{strategy}")
    return min(entries, key=sort_key)


def _build_groups(
    buckets: dict[tuple[int, str], list[FileEntry]],
    keepers: dict[tuple[int, str], FileEntry],
) -> list[DuplicateGroup]:
    """把已逐字节确认的候选桶转成 DuplicateGroup（只有非空桶才输出）。"""
    groups: list[DuplicateGroup] = []
    for key, duplicates in buckets.items():
        if not duplicates:
            continue
        keeper = keepers.get(key)
        if keeper is None:  # pragma: no cover - 防御性分支
            continue
        groups.append(
            DuplicateGroup(
                keeper=keeper,
                duplicates=sorted(duplicates, key=_path_sort_key),
                sha256=key[1],
                size=key[0],
            )
        )
    groups.sort(key=lambda group: _path_sort_key(group.keeper))
    return groups


def find_cross_duplicates(
    root_a: Path,
    root_b: Path,
    *,
    scope: ScanScope = "all",
    threads: int = 4,
    should_cancel: CancelCheck | None = None,
    on_progress: ProgressCallback | None = None,
) -> ScanResult:
    """目录比对：找出 B 中与 A 内容逐字节一致的全部文件。

    - ``keeper`` 一定来自 A，``duplicates`` 一定来自 B（B 内所有副本都会列出）。
    - B 内部互相重复但 A 中没有的文件不输出（本页不处理）。
    - 只保留 B 中 size 在 A 中出现过的文件参与哈希（size 预筛）。
    - 取消时返回已有部分并置 ``cancelled=True``；``validate_compare_roots`` 的
      ValueError 原样抛出（属于参数/环境错误，不是扫描问题）。
    """
    path_a = _absolute_root(root_a)
    path_b = _absolute_root(root_b)
    validate_compare_roots(path_a, path_b)

    result = ScanResult()
    entries_a = collect_files(
        path_a, scope, should_cancel=should_cancel, on_progress=on_progress, issues=result.issues
    )
    if _is_cancelled(should_cancel):
        result.cancelled = True
        result.scanned_files = len(entries_a)
        return result
    entries_b = collect_files(
        path_b, scope, should_cancel=should_cancel, on_progress=on_progress, issues=result.issues
    )
    result.scanned_files = len(entries_a) + len(entries_b)
    if _is_cancelled(should_cancel):
        result.cancelled = True
        return result

    a_by_size: dict[int, list[FileEntry]] = {}
    for entry in entries_a:
        a_by_size.setdefault(entry.size, []).append(entry)

    candidates_b = [entry for entry in entries_b if entry.size in a_by_size]
    if not candidates_b:
        return result

    # size 预筛之后才算哈希：只有「B 里有同尺寸候选」的 A 文件才需要参与
    needed_sizes = {entry.size for entry in candidates_b}
    hash_targets: list[FileEntry] = []
    for size in sorted(needed_sizes):
        hash_targets.extend(a_by_size.get(size, []))
    hash_targets.extend(candidates_b)

    reporter = _ProgressReporter(on_progress)
    hashes, hash_cancelled = _hash_many(hash_targets, threads, should_cancel, reporter, result)
    if hash_cancelled or _is_cancelled(should_cancel):
        result.cancelled = True
        return result

    # 每个 (size, sha256) 选一个 A 参照文件（A 组内按路径排序取第一个）
    keepers: dict[tuple[int, str], FileEntry] = {}
    for entry in entries_a:
        digest = hashes.get(entry.path)
        if digest is None:
            continue
        key = (entry.size, digest)
        current = keepers.get(key)
        if current is None or _path_sort_key(entry) < _path_sort_key(current):
            keepers[key] = entry

    pairs: list[tuple[FileEntry, FileEntry, str]] = []
    for entry in sorted(candidates_b, key=_path_sort_key):
        digest = hashes.get(entry.path)
        if digest is None:
            continue
        keeper = keepers.get((entry.size, digest))
        if keeper is None:
            continue
        pairs.append((entry, keeper, digest))

    buckets: dict[tuple[int, str], list[FileEntry]] = {}
    total_pairs = len(pairs)
    done = 0
    cancelled = False
    for entry, keeper, digest in pairs:
        if _is_cancelled(should_cancel):
            cancelled = True
            break
        try:
            identical = files_identical(keeper.path, entry.path, should_cancel=should_cancel)
        except ScanCancelled:
            cancelled = True
            break
        except Exception as exc:
            result.issues.append(
                ScanIssue(path=entry.path, stage="verify", message=_describe_error(exc))
            )
            done += 1
            reporter("verify", done, total_pairs)
            continue
        if identical:
            buckets.setdefault((entry.size, digest), []).append(entry)
        else:
            result.mismatches.append(HashMismatch(keeper=keeper, other=entry, sha256=digest))
        done += 1
        reporter("verify", done, total_pairs)

    result.cancelled = cancelled
    if not cancelled:
        reporter("verify", total_pairs, total_pairs, force=True)
    result.groups = _build_groups(buckets, keepers)
    return result


def find_internal_duplicates(
    root: Path,
    *,
    scope: ScanScope = "all",
    keep_strategy: KeepStrategy = "shallowest",
    threads: int = 4,
    should_cancel: CancelCheck | None = None,
    on_progress: ProgressCallback | None = None,
    on_coverage: Callable[[ScanCoverage], None] | None = None,
) -> ScanResult:
    """目录内去重：按内容分组，每组保留 1 个（按 keep_strategy），其余列为回收候选。

    - 只有 size 组内 >1 的文件才计算哈希。
    - 每组至少保留一个文件；keeper 永远不出现在 duplicates 里。
    - 只有 duplicates 非空的组才输出。
    - ``coverage`` 随结果返回；可用 ``on_coverage`` 订阅枚举及候选数快照。
    """
    if keep_strategy not in ("shallowest", "oldest", "newest"):
        raise ValueError(f"unknown_strategy:{keep_strategy}")

    root_path = _absolute_root(root)
    coverage = ScanCoverage()
    result = ScanResult(coverage=coverage)
    report_coverage = _CoverageReporter(on_coverage)

    def mark_cancelled() -> None:
        result.cancelled = True
        if coverage.enumeration_complete:
            coverage.enumeration_complete = False
            report_coverage(coverage, force=True)

    entries = collect_files(
        root_path, scope, should_cancel=should_cancel, on_progress=on_progress,
        issues=result.issues, coverage=coverage, on_coverage=on_coverage,
    )
    result.scanned_files = len(entries)
    if _is_cancelled(should_cancel):
        mark_cancelled()
        return result

    by_size: dict[int, list[FileEntry]] = {}
    for entry in entries:
        by_size.setdefault(entry.size, []).append(entry)

    hash_targets: list[FileEntry] = []
    for size in sorted(by_size):
        group = by_size[size]
        if len(group) > 1:
            hash_targets.extend(group)

    coverage.hash_candidates = len(hash_targets)
    report_coverage(coverage, force=True)
    reporter = _ProgressReporter(on_progress)
    hashes, hash_cancelled = _hash_many(hash_targets, threads, should_cancel, reporter, result)
    if hash_cancelled or _is_cancelled(should_cancel):
        mark_cancelled()
        return result

    by_hash: dict[tuple[int, str], list[FileEntry]] = {}
    for entry in entries:
        digest = hashes.get(entry.path)
        if digest is None:
            continue
        by_hash.setdefault((entry.size, digest), []).append(entry)

    keepers: dict[tuple[int, str], FileEntry] = {}
    buckets: dict[tuple[int, str], list[FileEntry]] = {}
    total_pairs = sum(max(0, len(members) - 1) for members in by_hash.values())
    done = 0
    cancelled = False

    for key in sorted(by_hash, key=lambda item: (item[0], item[1])):
        members = by_hash[key]
        if len(members) < 2:
            continue
        keeper = choose_keeper(members, keep_strategy)
        keepers[key] = keeper
        for entry in sorted(members, key=_path_sort_key):
            if entry.path == keeper.path:
                continue
            if _is_cancelled(should_cancel):
                cancelled = True
                break
            try:
                identical = files_identical(keeper.path, entry.path, should_cancel=should_cancel)
            except ScanCancelled:
                cancelled = True
                break
            except Exception as exc:
                result.issues.append(
                    ScanIssue(path=entry.path, stage="verify", message=_describe_error(exc))
                )
                done += 1
                reporter("verify", done, total_pairs)
                continue
            if identical:
                buckets.setdefault(key, []).append(entry)
            else:
                result.mismatches.append(HashMismatch(keeper=keeper, other=entry, sha256=key[1]))
            done += 1
            reporter("verify", done, total_pairs)
        if cancelled:
            break

    if cancelled:
        mark_cancelled()
    else:
        reporter("verify", total_pairs, total_pairs, force=True)
    result.groups = _build_groups(buckets, keepers)
    # 最后一次复核/进度回调也可能收到取消，返回前仍须保留取消语义。
    if not result.cancelled and _is_cancelled(should_cancel):
        mark_cancelled()
    return result


# ---------------------------------------------------------------------------
# 执行阶段：执行前复核 + 回收
# ---------------------------------------------------------------------------


def revalidate_pair(
    target: FileEntry,
    keeper: FileEntry,
    *,
    byte_verify: bool = True,
    should_cancel: CancelCheck | None = None,
) -> SkipReason | None:
    """回收前复核：返回 None 表示可以回收，否则返回跳过原因。

    检查顺序：同一路径/同一物理文件 → 两者存在 → size/mtime_ns 未变 →
    （byte_verify）逐字节复核。读错误返回 "read_error"。

    取消（``should_cancel`` 返回 True）**一律**抛出 ``ScanCancelled``（即使
    ``byte_verify=False`` 也在入口先检查），与契约一致：取消不是「跳过原因」，
    GUI worker 据此把整个回收流程置为「已停止」。
    """
    if _is_cancelled(should_cancel):
        # 已请求停止：不再碰文件，也不进回收站
        raise ScanCancelled(f"{target.path} <> {keeper.path}")
    try:
        if _real_key(target.path) == _real_key(keeper.path):
            return "same_path"
    except OSError:
        return "read_error"
    if _same_file_identity(target, keeper):
        # 同一物理文件的另一个硬链接：保守跳过，绝不把 keeper 的链接送去回收站
        return "same_path"

    try:
        target_stat = target.path.stat()
    except FileNotFoundError:
        return "target_missing"
    except OSError:
        return "read_error"

    try:
        keeper_stat = keeper.path.stat()
    except FileNotFoundError:
        return "keeper_missing"
    except OSError:
        return "read_error"

    if int(target_stat.st_size) != target.size or int(target_stat.st_mtime_ns) != target.mtime_ns:
        return "target_changed"
    if int(keeper_stat.st_size) != keeper.size or int(keeper_stat.st_mtime_ns) != keeper.mtime_ns:
        return "keeper_changed"

    if byte_verify:
        try:
            if not files_identical(keeper.path, target.path, should_cancel=should_cancel):
                return "content_differs"
        except ScanCancelled:
            raise
        except Exception:
            return "read_error"
    return None


def recycle_duplicate(
    target: FileEntry,
    keeper: FileEntry,
    *,
    byte_verify: bool = True,
    should_cancel: CancelCheck | None = None,
) -> RecycleOutcome:
    """单个文件的回收（GUI worker 循环调用以支持暂停/停止）。

    复核不通过时绝不调用 ``send2trash``；``send2trash`` 缺失时返回
    ``failed`` + ``"send2trash_unavailable"``。

    取消（``should_cancel`` 返回 True）抛出 ``ScanCancelled``，由 worker 当作
    「停止回收」处理；其余异常一律转为 ``failed/skipped``，不抛给调用方。
    """
    try:
        reason = revalidate_pair(
            target, keeper, byte_verify=byte_verify, should_cancel=should_cancel
        )
    except ScanCancelled:
        raise
    except Exception:
        return RecycleOutcome(target=target, status="skipped", reason="read_error")
    if reason is not None:
        return RecycleOutcome(target=target, status="skipped", reason=reason)

    if send2trash is None:
        return RecycleOutcome(target=target, status="failed", reason="send2trash_unavailable")

    try:
        send2trash(str(target.path))
    except Exception as exc:
        message = getattr(exc, "strerror", None) or str(exc) or exc.__class__.__name__
        return RecycleOutcome(target=target, status="failed", reason=str(message)[:200])
    return RecycleOutcome(target=target, status="recycled")
