"""目录比对/目录内去重扫描记录的版本化 JSON 存取（无 PyQt 依赖）。

记录保存 ``ScanResult`` 的完整历史快照（文件路径、大小、mtime_ns、file_id、
SHA-256、分组、异常、统计）以及扫描根/选项和每行勾选状态。记录是**不可信历史**：
读取时严格校验模式、版本、类型、路径归属和分组关系；读取/保存都不会读取媒体内容，
更不会触发回收。导入后的文件必须在实际回收前由 ``duplicate_scan_core`` 重新复核。

格式固定为 UTF-8 JSON、``schema_version == 1``；保存使用同目录临时文件 +
``os.replace`` 原子替换，失败不会留下半截目标文件。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from duplicate_scan_core import (
    DuplicateGroup,
    FileEntry,
    HashMismatch,
    ScanIssue,
    ScanResult,
)

__all__ = [
    "MAX_RECORD_BYTES",
    "ROW_STATUS_BASES",
    "SCHEMA_VERSION",
    "ScanRecord",
    "load_record",
    "save_record",
]

SCHEMA_VERSION = 1

# 合理边界：防止损坏/恶意记录造成无界内存或磁盘占用。
MAX_RECORD_BYTES = 64 * 1024 * 1024
MAX_GROUPS = 200_000
MAX_MISMATCHES = 200_000
MAX_ISSUES = 500_000
MAX_ROW_STATES = 1_000_000
MAX_ENTRIES = 1_500_000
MAX_PATH_LENGTH = 32_767
MAX_TEXT_LENGTH = 4_096
MAX_STATUS_LENGTH = 512
MAX_CREATED_AT_LENGTH = 128

MODE_COMPARE = "compare"
MODE_INTERNAL = "internal"
_VALID_MODES = frozenset({MODE_COMPARE, MODE_INTERNAL})
_VALID_SCOPES = frozenset({"all", "media"})
_VALID_KEEP_STRATEGIES = frozenset({"shallowest", "oldest", "newest"})
_VALID_ISSUE_STAGES = frozenset({"enumerate", "hash", "verify"})

# 现有两页可能写入的行状态（基键）；skipped/failed 可带 reason，issue 可带 stage|message。
ROW_STATUS_BASES = frozenset(
    {
        "status_pending",
        "status_keep",
        "status_recycled",
        "status_cancelled",
        "status_mismatch",
        "status_processing",
        "status_paused",
        "status_skipped",
        "status_failed",
        "status_issue",
    }
)

_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_TOP_LEVEL_KEYS = {
    "schema_version",
    "mode",
    "created_at",
    "roots",
    "options",
    "result",
    "row_states",
    "stale",
}
_RESULT_KEYS = {
    "groups",
    "mismatches",
    "issues",
    "scanned_files",
    "hashed_files",
    "hashed_bytes",
    "cancelled",
}
_GROUP_KEYS = {"keeper", "duplicates", "sha256", "size"}
_MISMATCH_KEYS = {"keeper", "other", "sha256"}
_ISSUE_KEYS = {"path", "stage", "message"}
_ENTRY_KEYS = {"path", "root", "size", "mtime_ns", "file_id"}
_ROW_STATE_KEYS = {"checked", "status"}


@dataclass
class ScanRecord:
    """一次扫描的完整可恢复快照（与 GUI 共用的冻结 API）。"""

    mode: str                      # 'compare' 或 'internal'
    root_a: Path                    # A 或单根
    root_b: Path | None
    scope: str                      # 'all' / 'media'
    keep_strategy: str              # 'shallowest' / 'oldest' / 'newest'
    result: ScanResult
    row_states: dict[str, dict]     # 绝对文件路径 -> {'checked': bool, 'status': str}
    created_at: str = ""
    stale: bool = False


# ---------------------------------------------------------------------------
# 基础类型/路径工具
# ---------------------------------------------------------------------------


def _require_mapping(value: Any, field: str, keys: set[str]) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{field} 必须是对象")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        detail = []
        if missing:
            detail.append("缺少 " + ", ".join(missing))
        if extra:
            detail.append("未知 " + ", ".join(extra))
        raise ValueError(f"{field} 字段不正确（{'；'.join(detail)}）")
    return value


def _require_list(value: Any, field: str, maximum: int) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{field} 必须是数组")
    if len(value) > maximum:
        raise ValueError(f"{field} 数量超过上限 {maximum}")
    return value


def _require_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} 必须是整数")
    if value < minimum:
        raise ValueError(f"{field} 不能小于 {minimum}")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} 必须是布尔值")
    return value


def _require_choice(value: Any, field: str, choices: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{field} 不是允许的值")
    return value


def _check_text(value: Any, field: str, *, maximum: int, allow_empty: bool) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} 必须是字符串")
    if not allow_empty and not value:
        raise ValueError(f"{field} 不能为空")
    if len(value) > maximum:
        raise ValueError(f"{field} 超过长度上限 {maximum}")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{field} 包含控制字符")
    return value


def _path_value(value: Any, field: str) -> str:
    """校验绝对路径文本；返回 abspath 规范化后的字符串（不要求存在）。"""
    if not isinstance(value, (str, os.PathLike)):
        raise ValueError(f"{field} 必须是路径字符串")
    text = os.fspath(value)
    if not isinstance(text, str):  # os.PathLike[bytes] 不接受
        raise ValueError(f"{field} 必须是文本路径")
    text = _check_text(text, field, maximum=MAX_PATH_LENGTH, allow_empty=False)
    if not os.path.isabs(text):
        raise ValueError(f"{field} 必须是绝对路径")
    return os.path.abspath(text)


def _path_key(value: str | Path) -> str:
    """真实路径 + 大小写归一；用于归属/重复判断（不读取媒体内容）。

    ``realpath`` 失败时不能退化为词法路径——那会放过符号链接/联接越界；
    无法确认真实归属的记录一律按无效拒绝。
    """
    text = os.fspath(value)
    try:
        real = os.path.realpath(text)
    except OSError as exc:
        raise ValueError(f"无法解析路径归属：{text}") from exc
    return os.path.normcase(real)


def _is_within_key(child: str, parent: str, *, allow_equal: bool) -> bool:
    try:
        common = os.path.commonpath([child, parent])
    except ValueError:  # 不同盘符
        return False
    if common != parent:
        return False
    return allow_equal or child != parent


def _is_within_path(path: str | Path, root: str | Path, *, allow_equal: bool = False) -> bool:
    return _is_within_key(_path_key(path), _path_key(root), allow_equal=allow_equal)


def _validate_roots(mode: str, root_a: Any, root_b: Any) -> tuple[Path, Path | None]:
    path_a = Path(_path_value(root_a, "root_a"))
    if mode == MODE_COMPARE:
        if root_b is None:
            raise ValueError("目录比对记录缺少 root_b")
        path_b = Path(_path_value(root_b, "root_b"))
        key_a = _path_key(path_a)
        key_b = _path_key(path_b)
        if key_a == key_b:
            raise ValueError("目录比对的两个根目录相同")
        if _is_within_key(key_b, key_a, allow_equal=False):
            raise ValueError("目录比对的 B 位于 A 内部")
        if _is_within_key(key_a, key_b, allow_equal=False):
            raise ValueError("目录比对的 A 位于 B 内部")
        return path_a, path_b
    if root_b is not None:
        raise ValueError("目录内去重记录不应包含 root_b")
    return path_a, None


def _validate_created_at(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("created_at 必须是字符串")
    if len(value) > MAX_CREATED_AT_LENGTH:
        raise ValueError("created_at 超过长度上限")
    if any(ord(char) < 32 for char in value):
        raise ValueError("created_at 包含控制字符")
    return value


def _validate_status(value: Any) -> str:
    """只接受两页现有行状态；避免导入任意文本/伪造状态。"""
    if not isinstance(value, str) or not value:
        raise ValueError("row_states.status 必须是非空字符串")
    if len(value) > MAX_STATUS_LENGTH:
        raise ValueError("row_states.status 超过长度上限")
    if any(ord(char) < 32 for char in value):
        raise ValueError("row_states.status 包含控制字符")

    base, has_suffix, rest = value.partition("|")
    if base not in ROW_STATUS_BASES:
        raise ValueError(f"未知的行状态：{base}")
    if base in {"status_skipped", "status_failed"}:
        if has_suffix and not rest.strip():
            raise ValueError(f"{base} 的跳过/失败原因不能为空")
    elif base == "status_issue":
        if has_suffix:
            stage, has_message, message = rest.partition("|")
            if not has_message or stage not in _VALID_ISSUE_STAGES or not message.strip():
                raise ValueError("status_issue 必须为 status_issue|stage|message")
    elif has_suffix:
        raise ValueError(f"{base} 不应携带附加内容")
    return value


# ---------------------------------------------------------------------------
# 条目/分组/异常校验
# ---------------------------------------------------------------------------


def _validate_entry(value: Any, field: str, *, root_a: Path, root_b: Path | None) -> dict:
    """校验文件快照：必须是绝对路径且属于 A 或 B（file_id 的 root 字段必须一致）。"""
    data = _require_mapping(value, field, _ENTRY_KEYS)
    path_text = _path_value(data["path"], f"{field}.path")
    root_text = _path_value(data["root"], f"{field}.root")
    allowed_roots = {_path_key(root_a)}
    if root_b is not None:
        allowed_roots.add(_path_key(root_b))
    if _path_key(root_text) not in allowed_roots:
        raise ValueError(f"{field}.root 不是本次扫描的根目录")
    if not _is_within_path(path_text, root_text, allow_equal=False):
        raise ValueError(f"{field}.path 不在其所属根目录内")
    file_id = data["file_id"]
    if not isinstance(file_id, (list, tuple)) or len(file_id) != 2:
        raise ValueError(f"{field}.file_id 必须是两个整数")
    return {
        "path": path_text,
        "root": root_text,
        "size": _require_int(data["size"], f"{field}.size", minimum=1),
        "mtime_ns": _require_int(data["mtime_ns"], f"{field}.mtime_ns"),
        "file_id": [_require_int(file_id[0], f"{field}.file_id[0]"),
                     _require_int(file_id[1], f"{field}.file_id[1]")],
    }


def _entry_object(data: dict) -> FileEntry:
    return FileEntry(
        path=Path(data["path"]),
        root=Path(data["root"]),
        size=data["size"],
        mtime_ns=data["mtime_ns"],
        file_id=(data["file_id"][0], data["file_id"][1]),
    )


def _validate_group(
    value: Any, index: int, *, root_a: Path, root_b: Path | None, mode: str
) -> dict:
    field = f"result.groups[{index}]"
    data = _require_mapping(value, field, _GROUP_KEYS)
    keeper = _validate_entry(data["keeper"], f"{field}.keeper", root_a=root_a, root_b=root_b)
    duplicates_raw = _require_list(data["duplicates"], f"{field}.duplicates", MAX_ENTRIES)
    # 去重模式每组恰好 1 个保留项，可以没有副本（内核也能产出这种分组）；
    # 比对模式的分组必须至少带一个 B 副本。
    if not duplicates_raw and mode == MODE_COMPARE:
        raise ValueError(f"{field}.duplicates 不能为空")
    duplicates = [
        _validate_entry(item, f"{field}.duplicates[{i}]", root_a=root_a, root_b=root_b)
        for i, item in enumerate(duplicates_raw)
    ]
    sha256 = data["sha256"]
    if not isinstance(sha256, str) or not _SHA256_RE.match(sha256):
        raise ValueError(f"{field}.sha256 必须是 64 位小写十六进制")
    size = _require_int(data["size"], f"{field}.size", minimum=1)

    # 角色约束：比对模式 keeper 必属 A、副本必属 B；去重模式全部属于单根。
    keeper_root = keeper["root"]
    if keeper["size"] != size:
        raise ValueError(f"{field}.keeper 大小与分组不一致")
    if mode == MODE_COMPARE:
        if _path_key(keeper_root) != _path_key(root_a):
            raise ValueError(f"{field}.keeper 必须来自 A 目录")
    for i, item in enumerate(duplicates):
        if mode == MODE_COMPARE:
            if _path_key(item["root"]) != _path_key(root_b):
                raise ValueError(f"{field}.duplicates[{i}] 必须来自 B 目录")
        elif _path_key(item["root"]) != _path_key(keeper_root):
            raise ValueError(f"{field}.duplicates[{i}] 与保留项不属于同一根")
        if item["size"] != size:
            raise ValueError(f"{field}.duplicates[{i}] 大小与分组不一致")
        if _path_key(item["path"]) == _path_key(keeper["path"]):
            raise ValueError(f"{field}.duplicates[{i}] 与保留项是同一文件")

    return {"keeper": keeper, "duplicates": duplicates, "sha256": sha256, "size": size}


def _validate_mismatch(value: Any, index: int, *, root_a: Path, root_b: Path | None) -> dict:
    field = f"result.mismatches[{index}]"
    data = _require_mapping(value, field, _MISMATCH_KEYS)
    keeper = _validate_entry(data["keeper"], f"{field}.keeper", root_a=root_a, root_b=root_b)
    other = _validate_entry(data["other"], f"{field}.other", root_a=root_a, root_b=root_b)
    if root_b is not None:
        if _path_key(keeper["root"]) != _path_key(root_a):
            raise ValueError(f"{field}.keeper 必须来自 A 目录")
        if _path_key(other["root"]) != _path_key(root_b):
            raise ValueError(f"{field}.other 必须来自 B 目录")
    elif _path_key(keeper["root"]) != _path_key(other["root"]):
        raise ValueError(f"{field} 两侧不属于同一根")
    sha256 = data["sha256"]
    if not isinstance(sha256, str) or not _SHA256_RE.match(sha256):
        raise ValueError(f"{field}.sha256 必须是 64 位小写十六进制")
    return {"keeper": keeper, "other": other, "sha256": sha256}


def _validate_issue(value: Any, index: int, *, root_a: Path, root_b: Path | None) -> dict:
    field = f"result.issues[{index}]"
    data = _require_mapping(value, field, _ISSUE_KEYS)
    path_text = _path_value(data["path"], f"{field}.path")
    roots = [root_a] if root_b is None else [root_a, root_b]
    if not any(_is_within_path(path_text, root, allow_equal=True) for root in roots):
        raise ValueError(f"{field}.path 不在扫描根目录内")
    stage = _require_choice(data["stage"], f"{field}.stage", _VALID_ISSUE_STAGES)
    message = _check_text(
        data["message"], f"{field}.message", maximum=MAX_TEXT_LENGTH, allow_empty=True
    )
    return {"path": path_text, "stage": stage, "message": message}


def _validate_row_states(
    value: Any, *, root_a: Path, root_b: Path | None, result: ScanResult
) -> dict[str, dict]:
    """校验行状态表：键必须是结果中真实存在的行，且状态与行角色一致。

    - 回收目标：pending/recycled/skipped/failed/cancelled/processing；
    - 保留项：status_keep；
    - 校验不一致：status_mismatch；
    - 异常项：status_issue。
    只有「目标 + status_pending」允许 checked=True；其余情况一律归一化为未勾选。
    """
    if not isinstance(value, dict):
        raise ValueError("row_states 必须是对象")
    if len(value) > MAX_ROW_STATES:
        raise ValueError(f"row_states 数量超过上限 {MAX_ROW_STATES}")

    roles: dict[str, str] = {}

    def register(path: Path, role: str) -> None:
        key = _path_key(path)
        existing = roles.get(key)
        if existing is not None and existing != role:
            raise ValueError(f"结果中的路径同时承担多个行角色：{path}")
        roles[key] = role

    for group in result.groups:
        register(group.keeper.path, "keeper")
        for duplicate in group.duplicates:
            register(duplicate.path, "target")
    for mismatch in result.mismatches:
        register(mismatch.keeper.path, "keeper")
        register(mismatch.other.path, "mismatch")
    for issue in result.issues:
        register(issue.path, "issue")

    allowed_statuses = {
        "target": {
            "status_pending",
            "status_recycled",
            "status_skipped",
            "status_failed",
            "status_cancelled",
            "status_processing",
        },
        "keeper": {"status_keep"},
        "mismatch": {"status_mismatch"},
        "issue": {"status_issue"},
    }

    states: dict[str, dict] = {}
    seen: set[str] = set()
    roots = [root_a] if root_b is None else [root_a, root_b]
    for raw_key, raw_state in value.items():
        key_text = _path_value(raw_key, "row_states 键")
        # 异常项路径可能就是扫描根本身（根目录缺失/不可读），故允许等于根；
        # 文件行仍会由 role map 和条目归属校验保证不是根本身。
        if not any(_is_within_path(key_text, root, allow_equal=True) for root in roots):
            raise ValueError("row_states 的路径不在扫描根目录内")
        identity = _path_key(key_text)
        if identity in seen:
            raise ValueError("row_states 存在重复路径")
        seen.add(identity)
        role = roles.get(identity)
        if role is None:
            raise ValueError(f"row_states 的路径不是扫描结果中的行：{key_text}")
        state = _require_mapping(raw_state, f"row_states[{key_text}]", _ROW_STATE_KEYS)
        checked = _require_bool(state["checked"], f"row_states[{key_text}].checked")
        status = _validate_status(state["status"])
        base = status.partition("|")[0]
        if base not in allowed_statuses[role]:
            raise ValueError(f"row_states 状态与行角色不匹配：{key_text}")
        # 只有待回收目标可被勾选；其他行即使记录声称勾选也强制取消。
        states[key_text] = {
            "checked": checked and role == "target" and status == "status_pending",
            "status": status,
        }
    return states


def _validate_result(
    value: Any, *, root_a: Path, root_b: Path | None, mode: str
) -> ScanResult:
    data = _require_mapping(value, "result", _RESULT_KEYS)
    groups_raw = _require_list(data["groups"], "result.groups", MAX_GROUPS)
    mismatches_raw = _require_list(data["mismatches"], "result.mismatches", MAX_MISMATCHES)
    issues_raw = _require_list(data["issues"], "result.issues", MAX_ISSUES)

    result = ScanResult(
        groups=[
            DuplicateGroup(
                keeper=_entry_object(group["keeper"]),
                duplicates=[_entry_object(item) for item in group["duplicates"]],
                sha256=group["sha256"],
                size=group["size"],
            )
            for group in [
                _validate_group(item, i, root_a=root_a, root_b=root_b, mode=mode)
                for i, item in enumerate(groups_raw)
            ]
        ],
        mismatches=[
            HashMismatch(
                keeper=_entry_object(mismatch["keeper"]),
                other=_entry_object(mismatch["other"]),
                sha256=mismatch["sha256"],
            )
            for mismatch in [
                _validate_mismatch(item, i, root_a=root_a, root_b=root_b)
                for i, item in enumerate(mismatches_raw)
            ]
        ],
        issues=[
            ScanIssue(
                path=Path(issue["path"]),
                stage=issue["stage"],
                message=issue["message"],
            )
            for issue in [
                _validate_issue(item, i, root_a=root_a, root_b=root_b)
                for i, item in enumerate(issues_raw)
            ]
        ],
        scanned_files=_require_int(data["scanned_files"], "result.scanned_files"),
        hashed_files=_require_int(data["hashed_files"], "result.hashed_files"),
        hashed_bytes=_require_int(data["hashed_bytes"], "result.hashed_bytes"),
        cancelled=_require_bool(data["cancelled"], "result.cancelled"),
    )

    # 重复目标与「保留项/目标相交」：跨分组登记，任何重复都整体拒绝。
    seen_targets: set[str] = set()
    seen_keepers: set[str] = set()
    for index, group in enumerate(result.groups):
        keeper_key = _path_key(group.keeper.path)
        if keeper_key in seen_keepers:
            raise ValueError(f"result.groups[{index}] 的保留项与其它分组重复")
        seen_keepers.add(keeper_key)
        for offset, duplicate in enumerate(group.duplicates):
            target_key = _path_key(duplicate.path)
            if target_key in seen_targets:
                raise ValueError(f"result.groups[{index}].duplicates[{offset}] 重复出现")
            if target_key in seen_keepers:
                raise ValueError(f"result.groups[{index}].duplicates[{offset}] 与保留项相交")
            seen_targets.add(target_key)
    for index, mismatch in enumerate(result.mismatches):
        if _path_key(mismatch.other.path) in seen_targets:
            raise ValueError(f"result.mismatches[{index}] 与回收目标重复")
    for index, group in enumerate(result.groups):
        if _path_key(group.keeper.path) in seen_targets:
            raise ValueError(f"result.groups[{index}] 的保留项与回收目标相交")
    return result


# ---------------------------------------------------------------------------
# 记录 <-> JSON 数据
# ---------------------------------------------------------------------------


def _entry_to_data(entry: FileEntry) -> dict:
    return {
        "path": os.fspath(entry.path),
        "root": os.fspath(entry.root),
        "size": entry.size,
        "mtime_ns": entry.mtime_ns,
        "file_id": [entry.file_id[0], entry.file_id[1]],
    }


def _result_to_data(value: ScanResult) -> dict:
    """把核心结果转成待校验的原始 JSON 结构（不做信任假设）。"""
    if not isinstance(value, ScanResult):
        raise ValueError("result 必须是 ScanResult")
    if not isinstance(value.groups, list) or not isinstance(value.mismatches, list):
        raise ValueError("result 分组必须是列表")
    if not isinstance(value.issues, list):
        raise ValueError("result.issues 必须是列表")
    groups = []
    for group in value.groups:
        if not isinstance(group, DuplicateGroup) or not isinstance(group.duplicates, list):
            raise ValueError("result.groups 含有无效分组")
        groups.append(
            {
                "keeper": _entry_to_data_raw(group.keeper),
                "duplicates": [_entry_to_data_raw(item) for item in group.duplicates],
                "sha256": group.sha256,
                "size": group.size,
            }
        )
    mismatches = []
    for mismatch in value.mismatches:
        if not isinstance(mismatch, HashMismatch):
            raise ValueError("result.mismatches 含有无效条目")
        mismatches.append(
            {
                "keeper": _entry_to_data_raw(mismatch.keeper),
                "other": _entry_to_data_raw(mismatch.other),
                "sha256": mismatch.sha256,
            }
        )
    issues = []
    for issue in value.issues:
        if not isinstance(issue, ScanIssue):
            raise ValueError("result.issues 含有无效条目")
        issues.append(
            {
                "path": os.fspath(issue.path),
                "stage": issue.stage,
                "message": issue.message,
            }
        )
    return {
        "groups": groups,
        "mismatches": mismatches,
        "issues": issues,
        "scanned_files": value.scanned_files,
        "hashed_files": value.hashed_files,
        "hashed_bytes": value.hashed_bytes,
        "cancelled": value.cancelled,
    }


def _entry_to_data_raw(entry: Any) -> dict:
    if not isinstance(entry, FileEntry):
        raise ValueError("文件快照必须是 FileEntry")
    if not isinstance(entry.file_id, (tuple, list)) or len(entry.file_id) != 2:
        raise ValueError("file_id 必须是两个整数")
    return _entry_to_data(entry)


def _record_from_data(data: Any, *, expected_mode: str | None = None) -> ScanRecord:
    data = _require_mapping(data, "记录", _TOP_LEVEL_KEYS)
    version = _require_int(data["schema_version"], "schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(f"不支持的 schema_version：{version}")
    mode = _require_choice(data["mode"], "mode", _VALID_MODES)
    if expected_mode is not None:
        if expected_mode not in _VALID_MODES:
            raise ValueError("expected_mode 不是允许的值")
        if mode != expected_mode:
            raise ValueError("记录模式与当前页面不一致")
    created_at = _validate_created_at(data["created_at"])
    roots = _require_mapping(data["roots"], "roots", {"a", "b"})
    root_a, root_b = _validate_roots(mode, roots["a"], roots["b"])
    options = _require_mapping(data["options"], "options", {"scope", "keep_strategy"})
    scope = _require_choice(options["scope"], "options.scope", _VALID_SCOPES)
    keep_strategy = _require_choice(
        options["keep_strategy"], "options.keep_strategy", _VALID_KEEP_STRATEGIES
    )
    result = _validate_result(data["result"], root_a=root_a, root_b=root_b, mode=mode)
    row_states = _validate_row_states(
        data["row_states"], root_a=root_a, root_b=root_b, result=result
    )
    stale = _require_bool(data["stale"], "stale")
    return ScanRecord(
        mode=mode,
        root_a=root_a,
        root_b=root_b,
        scope=scope,
        keep_strategy=keep_strategy,
        result=result,
        row_states=row_states,
        created_at=created_at,
        stale=stale,
    )


def _record_to_data(record: ScanRecord) -> dict:
    if not isinstance(record, ScanRecord):
        raise ValueError("record 必须是 ScanRecord")
    if not isinstance(record.stale, bool):
        raise ValueError("stale 必须是布尔值")
    try:
        raw = {
            "schema_version": SCHEMA_VERSION,
            "mode": record.mode,
            "created_at": record.created_at,
            "roots": {
                "a": os.fspath(record.root_a),
                "b": None if record.root_b is None else os.fspath(record.root_b),
            },
            "options": {"scope": record.scope, "keep_strategy": record.keep_strategy},
            "result": _result_to_data(record.result),
            "row_states": record.row_states,
            "stale": record.stale,
        }
    except (AttributeError, TypeError) as exc:
        raise ValueError("record 字段类型不正确") from exc
    # 先走一遍完整读取校验，确保导出的文件与导入时接受的文件完全同构。
    canonical = _record_from_data(raw)
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": canonical.mode,
        "created_at": canonical.created_at,
        "roots": {
            "a": os.fspath(canonical.root_a),
            "b": None if canonical.root_b is None else os.fspath(canonical.root_b),
        },
        "options": {"scope": canonical.scope, "keep_strategy": canonical.keep_strategy},
        "result": _result_to_data(canonical.result),
        "row_states": canonical.row_states,
        "stale": canonical.stale,
    }


def _reject_constant(value: str) -> Any:
    raise ValueError(f"记录包含非法数字：{value}")


def _pairs_hook(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON 存在重复键：{key}")
        result[key] = value
    return result


def _read_limited(path: Path) -> bytes:
    try:
        size = path.stat().st_size
    except OSError:
        raise
    if size > MAX_RECORD_BYTES:
        raise ValueError(f"记录文件超过大小上限 {MAX_RECORD_BYTES} 字节")
    with open(path, "rb") as handle:
        data = handle.read(MAX_RECORD_BYTES + 1)
    if len(data) > MAX_RECORD_BYTES:
        raise ValueError(f"记录文件超过大小上限 {MAX_RECORD_BYTES} 字节")
    return data


def load_record(path: Path, *, expected_mode: str | None = None) -> ScanRecord:
    """读取并完整校验记录；任何无效内容抛 ``ValueError``，文件错误抛 ``OSError``。

    返回前不会修改任何 GUI 状态；调用方应只在成功后替换当前显示。
    """
    if expected_mode is not None and expected_mode not in _VALID_MODES:
        raise ValueError("expected_mode 不是允许的值")
    try:
        record_path = Path(path)
    except TypeError as exc:
        raise ValueError("记录路径类型不正确") from exc
    raw = _read_limited(record_path)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("记录文件不是 UTF-8 编码") from exc
    try:
        data = json.loads(
            text,
            object_pairs_hook=_pairs_hook,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"记录 JSON 无效：{exc.msg}") from exc
    except RecursionError as exc:
        raise ValueError("记录 JSON 嵌套过深") from exc
    return _record_from_data(data, expected_mode=expected_mode)


def save_record(path: Path, record: ScanRecord) -> None:
    """校验并原子保存记录；写入失败不会留下半截目标文件。"""
    payload = json.dumps(
        _record_to_data(record),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(payload) > MAX_RECORD_BYTES:
        raise ValueError(f"记录超过大小上限 {MAX_RECORD_BYTES} 字节")
    try:
        target = Path(path)
    except TypeError as exc:
        raise ValueError("记录路径类型不正确") from exc
    parent = target.parent
    if not parent.is_dir():
        raise OSError(f"记录目录不存在：{parent}")
    if target.exists() and not target.is_file():
        raise OSError(f"记录目标不是文件：{target}")

    temp_name: str | None = None
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=os.fspath(parent)
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        os.replace(temp_name, os.fspath(target))
        temp_name = None
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
