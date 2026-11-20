"""文件夹媒体统计核心（标准库实现，不依赖 PyQt）。

职责：
- 递归枚举目录，只统计图片与视频文件数量（按扩展名），不做任何内容读取。
- 输出明确的数据结构和错误状态，供 GUI 在后台线程中调用。

关键边界（见任务 PRD/design 与 research/evidence.md）：
- 只读取目录项名称与类型信息（os.scandir），绝不打开媒体文件内容、
  不读 EXIF、不生成缩略图、不计算哈希。
- 先以 follow_symlinks=False 排除真实符号链接 / 目录联接，避免循环；
  **不**因为 OneDrive 的云占位属性（OFFLINE / UNPINNED / RECALL_ON_DATA_ACCESS）
  或一般 REPARSE_POINT 标记而跳过条目。
- 目录枚举失败、条目类型判定失败、迭代中途失败、中途停止都不抛异常：
  返回 partial 结果 + errors，并把“不完整”状态传给祖先。
- 目录优先于扩展名判定：名为 album.JPG / clip.MP4 的**目录**仍会被递归统计。
- on_batch 回调接收绝对路径的 FolderSnapshot 批次，父目录快照先于后代到达；
  同一目录可能再次收到计数值更大的更新快照，调用方按路径覆盖，不可累加。
- 内存中不保留全部媒体文件路径，只保留每个目录的计数。
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

__all__ = [
    "ScanIssue",
    "FolderSnapshot",
    "ScanOutcome",
    "scan_folders",
    "BATCH_SIZE",
]


# 每次回调传给 GUI 的目录快照条数上限（与 GUI 的批量 drain 配合）
BATCH_SIZE = 64


@dataclass(frozen=True)
class ScanIssue:
    """扫描过程中遇到的可恢复问题（路径 + 中文原因）。"""

    path: Path
    message: str


@dataclass(frozen=True)
class FolderSnapshot:
    """单个目录的统计快照。"""

    path: Path
    parent_path: Path | None
    name: str
    direct_image_count: int
    direct_video_count: int
    image_count: int
    video_count: int
    complete: bool
    issue_count: int

    @property
    def total(self) -> int:
        """总项数 = 图片数 + 视频数（不另存字段，避免漂移）。"""
        return self.image_count + self.video_count

    @property
    def direct_total(self) -> int:
        """直属总项数 = 直属图片数 + 直属视频数。"""
        return self.direct_image_count + self.direct_video_count


@dataclass(frozen=True)
class ScanOutcome:
    """一次扫描的最终结果。"""

    root: Path
    folders: tuple[FolderSnapshot, ...]
    errors: tuple[ScanIssue, ...]
    cancelled: bool

    @property
    def complete(self) -> bool:
        """未取消且没有错误时视为完整结果。"""
        return not self.cancelled and not self.errors

    @property
    def total(self) -> int:
        """根目录总项数（图片 + 视频）；找不到根快照时为 0。"""
        for folder in self.folders:
            if folder.parent_path is None:
                return folder.total
        return 0


class _DirNode:
    """扫描过程中的内部目录节点（不保存任何媒体文件路径）。"""

    __slots__ = (
        "path",
        "parent",
        "name",
        "children",
        "direct_image",
        "direct_video",
        "image_count",
        "video_count",
        "has_issue",
        "direct_issue_count",
        "issue_count",
        "needs_emit",
    )

    def __init__(self, path: Path, name: str, parent: "_DirNode | None") -> None:
        self.path = path
        self.parent = parent
        self.name = name
        self.children: list["_DirNode"] = []
        self.direct_image = 0
        self.direct_video = 0
        self.image_count = 0
        self.video_count = 0
        self.has_issue = False  # 自身或后代已记录问题（不完整，且不可被覆盖）
        self.direct_issue_count = 0
        self.issue_count = 0
        self.needs_emit = False  # 已排队待通知的更新快照

    @property
    def complete(self) -> bool:
        """未记录任何问题时才算完整。"""
        return not self.has_issue

    def mark_issue(self) -> None:
        """记录一个问题：本目录不完整。"""
        self.has_issue = True
        self.direct_issue_count += 1
        self.issue_count += 1


def _normalize_suffixes(suffixes: Iterable[str]) -> frozenset[str]:
    """把扩展名集合规范化为 casefold + 前导点形式。"""
    result: set[str] = set()
    for suffix in suffixes:
        text = str(suffix).strip().casefold()
        if not text:
            continue
        if not text.startswith("."):
            text = "." + text
        result.add(text)
    return frozenset(result)


def _file_suffix(name: str) -> str:
    """取文件名扩展名并 casefold（只处理字符串，不接触文件内容）。"""
    dot = name.rfind(".")
    if dot <= 0:
        return ""
    return name[dot:].casefold()


def _classify_entry(entry: os.DirEntry) -> str:
    """判定条目类型：返回 "link" / "dir" / "file" / "other"。

    云占位属性（OFFLINE / UNPINNED / RECALL_ON_DATA_ACCESS）不是链接，
    也不等同于“不存在”，因此这里只使用精确的链接判定。
    类型信息无法取得时抛 OSError，由调用方记录为扫描问题，
    而不是静默当成“非文件/非目录”（否则会产生假的零结果）。
    """
    if entry.is_symlink():
        return "link"
    is_junction = getattr(entry, "is_junction", None)
    if is_junction is not None and is_junction():
        return "link"
    if entry.is_dir(follow_symlinks=False):
        return "dir"
    if entry.is_file(follow_symlinks=False):
        return "file"
    return "other"


def _snapshot(node: _DirNode) -> FolderSnapshot:
    """把内部节点转换为对外快照（绝对路径）。"""
    return FolderSnapshot(
        path=node.path,
        parent_path=node.parent.path if node.parent is not None else None,
        name=node.name,
        direct_image_count=node.direct_image,
        direct_video_count=node.direct_video,
        image_count=node.image_count,
        video_count=node.video_count,
        complete=node.complete,
        issue_count=node.issue_count,
    )


def _describe_error(exc: BaseException) -> str:
    """把目录枚举异常转成中文可读原因。"""
    if isinstance(exc, PermissionError):
        return "没有访问权限，无法列出目录"
    if isinstance(exc, FileNotFoundError):
        return "目录不存在或已被移除"
    if isinstance(exc, NotADirectoryError):
        return "不是有效目录"
    text = getattr(exc, "strerror", None) or str(exc)
    return f"无法列出目录：{text}"


def _describe_entry_error(exc: BaseException) -> str:
    """条目类型判定失败时的中文原因（未打开文件内容）。"""
    if isinstance(exc, PermissionError):
        return "没有访问权限，无法读取条目类型"
    if isinstance(exc, FileNotFoundError):
        return "条目不存在或已被移除"
    text = getattr(exc, "strerror", None) or str(exc)
    return f"无法读取条目类型：{text}"


def _walk(node: _DirNode) -> Iterable[_DirNode]:
    """前序遍历（迭代实现，避免深目录递归限制）。"""
    stack: list[_DirNode] = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def _recount(node: _DirNode) -> None:
    """汇总 node 自身直属计数与当前子目录计数（就地叠加，幂等）。

    扫描过程中的子目录可能尚未汇总完，因此这里只做“叠加 + 继承状态”，
    自底向上重复调用即可得到最终计数与完整性。
    """
    image_total = node.direct_image
    video_total = node.direct_video
    # 反复汇总时只从直属问题开始，避免把上次已聚合的子目录问题再加一遍。
    issue_count = node.direct_issue_count
    has_issue = node.has_issue
    for child in node.children:
        image_total += child.image_count
        video_total += child.video_count
        has_issue = has_issue or child.has_issue
        issue_count += child.issue_count
    node.image_count = image_total
    node.video_count = video_total
    node.has_issue = has_issue
    node.issue_count = issue_count


def scan_folders(
    root: Path | str,
    image_suffixes: Iterable[str],
    video_suffixes: Iterable[str],
    *,
    stop_event: threading.Event | None = None,
    on_batch: Callable[[list[FolderSnapshot]], None] | None = None,
) -> ScanOutcome:
    """递归扫描 root，返回目录级媒体统计。

    参数：
        root: 根目录（str 或 Path）。
        image_suffixes / video_suffixes: GUI 从 timestamp_fix_gui 导入后传入。
        stop_event: 协作式取消标志（threading.Event）。
        on_batch: 批次回调，收到 list[FolderSnapshot]（绝对路径）。
            父目录快照先于后代到达，同一目录可能收到计数值更大的更新快照。

    返回：
        ScanOutcome；目录枚举失败、条目类型判定失败、迭代中途失败或中途停止
        时不抛异常，返回已发现结果（partial）+ errors。
    """

    # 只做绝对化，不 resolve()：不跟随链接，也不产生额外系统调用
    root_path = Path(os.path.abspath(str(root)))

    image_set = _normalize_suffixes(image_suffixes)
    video_set = _normalize_suffixes(video_suffixes)

    errors: list[ScanIssue] = []
    cancelled = False

    # ---- 批次通知（父先于子；同一路径可多次通知，调用方按路径覆盖）----
    pending_batch: list[FolderSnapshot] = []
    pending_updates: set[_DirNode] = set()

    def stopped() -> bool:
        return stop_event is not None and stop_event.is_set()

    def flush() -> None:
        if on_batch is None or not pending_batch:
            pending_batch.clear()
            return
        batch = list(pending_batch)
        pending_batch.clear()
        try:
            on_batch(batch)
        except Exception:
            # GUI 回调异常不应中断扫描（错误由 GUI 自身处理）
            pass

    def emit(snapshot: FolderSnapshot) -> None:
        if on_batch is None:
            return
        pending_batch.append(snapshot)
        if len(pending_batch) >= BATCH_SIZE:
            flush()

    def flush_updates() -> None:
        """通知排队中的祖先更新快照（按路径排序，父先于子）。

        每个快照都必须经 emit() 入队，保证任何一批都不超过 BATCH_SIZE；
        不得在循环内直接 append 后一次性 flush。
        """
        if not pending_updates:
            return
        nodes = sorted(
            pending_updates,
            key=lambda item: (len(item.path.parts), str(item.path).casefold()),
        )
        pending_updates.clear()
        for item in nodes:
            item.needs_emit = False
            emit(_snapshot(item))

    # ---- 错误标记：自身不完整并立即传给祖先，避免父节点计数/状态滞后 ----
    def mark_issue(node: _DirNode) -> None:
        node.mark_issue()
        parent = node.parent
        while parent is not None:
            parent.has_issue = True
            parent = parent.parent

    root_node = _DirNode(root_path, root_path.name or str(root_path), None)
    # 先发根节点，保证 GUI 能先插入父行
    emit(_snapshot(root_node))

    # 显式栈的深度优先遍历：父目录快照一定早于其后代
    stack: list[_DirNode] = [root_node]

    while stack:
        if stopped():
            cancelled = True
            break

        node = stack.pop()
        children: list[_DirNode] = []

        # 流式迭代：大目录不会先整体物化（可及时响应停止），
        # 中途抛错也能保留已统计的条目。
        try:
            with os.scandir(node.path) as iterator:
                while True:
                    if stopped():
                        cancelled = True
                        break
                    try:
                        entry = next(iterator)
                    except StopIteration:
                        break
                    except Exception as exc:  # 迭代中途失败：保留已统计部分
                        mark_issue(node)
                        errors.append(
                            ScanIssue(path=node.path, message=_describe_error(exc))
                        )
                        break

                    name = entry.name
                    try:
                        kind = _classify_entry(entry)
                    except Exception as exc:
                        # 类型判定失败不能静默当成“非文件”：记录问题
                        mark_issue(node)
                        errors.append(
                            ScanIssue(
                                path=node.path / name,
                                message=_describe_entry_error(exc),
                            )
                        )
                        continue

                    # 真实符号链接 / 目录联接：任何类型都跳过，避免循环
                    if kind == "link":
                        continue

                    # 目录优先：album.JPG 这类“看起来像媒体”的目录也必须递归
                    if kind == "dir":
                        child = _DirNode(node.path / name, name, node)
                        node.children.append(child)
                        children.append(child)
                        continue

                    if kind == "file":
                        suffix = _file_suffix(name)
                        if suffix in image_set:
                            node.direct_image += 1
                        elif suffix in video_set:
                            node.direct_video += 1
        except Exception as exc:  # 目录枚举失败：记录错误，继续其他目录
            mark_issue(node)
            errors.append(ScanIssue(path=node.path, message=_describe_error(exc)))
            continue

        if cancelled:
            # 取消发生在当前目录枚举中：保留已计数条目并标记不完整
            mark_issue(node)
            break

        node.image_count = node.direct_image
        node.video_count = node.direct_video
        emit(_snapshot(node))

        # 该目录计数已确定：刷新祖先计数并排队通知（每个目录一次）
        parent = node.parent
        while parent is not None:
            _recount(parent)
            if not parent.needs_emit:
                parent.needs_emit = True
                pending_updates.add(parent)
            parent = parent.parent

        # 逆序压栈，使子目录按名称顺序处理
        for child in reversed(children):
            stack.append(child)

    # 收尾：剩余祖先更新先发出（取消时同样保证父计数不滞后）
    flush_updates()

    # 自底向上汇总（取消时已发现的计数保留，但不完整状态会传给祖先）
    ordered = list(_walk(root_node))
    for node in reversed(ordered):
        _recount(node)

    if cancelled:
        # 取消后整体标记不完整：已发现的所有目录均保持“扫描被中断”语义
        for node in ordered:
            node.mark_issue()
        for node in reversed(ordered):
            _recount(node)

    if on_batch is not None:
        # 汇总会改变子树计数：补发最终快照，调用方按路径覆盖旧值
        for node in ordered:
            emit(_snapshot(node))
        flush()

    folders = tuple(_snapshot(node) for node in _output_order(root_node))
    return ScanOutcome(
        root=root_path,
        folders=folders,
        errors=tuple(errors),
        cancelled=cancelled,
    )


def _output_order(root: _DirNode) -> list[_DirNode]:
    """输出顺序：根在最前，其余按层级再按路径名排序，保证稳定可读。"""
    rest = sorted(
        (node for node in _walk(root) if node is not root),
        key=lambda item: (len(item.path.parts), str(item.path).casefold()),
    )
    return [root, *rest]
