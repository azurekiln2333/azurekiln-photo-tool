from __future__ import annotations

import copy
import ctypes
import json
import os
import sys
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from qframelesswindow import FramelessMainWindow, StandardTitleBar

from file_context_menu import install_file_context_menu

from PyQt6.QtCore import QEvent, QObject, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from timestamp_fix_gui import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    BodyLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    FluentIcon,
    IMAGE_SUFFIXES,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SubtitleLabel,
    TableWidget,
    Theme,
    apply_file_times_only,
    _earliest_file_timestamp,
    _format_timestamp,
    _get_windows_pictures_dir,
    _safe_resolve,
    _timestamp_from_exif,
    _timestamp_from_filename,
    _timestamp_from_windows_shell,
    setTheme,
    setThemeColor,
)


APP_NAME = "RenamePhotoGUI"
VIDEO_RENAME_SUFFIXES = (".mp4", ".mov")
SUPPORTED_RENAME_SUFFIXES = IMAGE_SUFFIXES + VIDEO_RENAME_SUFFIXES
LIVE_VIDEO_STEM_SUFFIXES = ("_HEVC", "_hevc")
DEFAULT_PHOTO_PREFIX = "IMG"
DEFAULT_VIDEO_PREFIX = "VID"
PROCESS_ROW_BATCH_SIZE = 100
SCAN_ROW_DRAIN_COUNT = 80
PROCESS_UPDATE_DRAIN_COUNT = 30
PHOTO_PREFIX_PRESETS = ("IMG", "PXL", "DSC", "PHOTO", "PIC")
VIDEO_PREFIX_PRESETS = ("VID", "MOV", "VIDEO", "CLIP", "PXL")
INVALID_FILENAME_CHARS = '<>:"/\\|?*'
COMPLETED_STATUSES = {
    "status_renamed",
    "status_renamed_timestamped",
    "status_already_named",
    "status_timestamped",
}
PROCESSABLE_STATUSES = {"status_pending"}
TIMESTAMP_PROCESSABLE_STATUSES = PROCESSABLE_STATUSES | {"status_already_named"}
TRANSLATIONS = {
    "zh": {
        "app_title": "照片重命名",
        "header_title": "照片重命名",
        "header_subtitle": "左侧读取原始文件时间，右侧按匹配到的文件名重命名待处理照片",
        "header_note": "匹配优先使用相对路径，其次使用文件名；未匹配时可选择是否允许使用待重命名文件自身时间。",
        "language": "界面语言",
        "reference_dir": "原始文件目录",
        "target_dir": "待重命名目录",
        "reference_placeholder": "选择或拖入用于读取时间信息的原始照片目录",
        "target_placeholder": "选择或拖入实际需要重命名的照片目录",
        "choose_reference": "选择原始目录",
        "choose_target": "选择待重命名目录",
        "scan_subdirs": "扫描子目录",
        "require_reference_match": "必须匹配原始文件",
        "photo_prefix": "照片前缀",
        "video_prefix": "视频前缀",
        "prefix_presets": "常用",
        "reference_drop_hint": "原始文件区：拖入保留正确时间信息的照片或文件夹，只读取信息，不改名。",
        "target_drop_hint": "待重命名区：拖入需要改名的照片或文件夹，按匹配到的原始文件时间生成 IMG_年月日_时分秒。",
        "table_reference_file": "原始文件",
        "table_reference_time": "读取时间",
        "table_reference_source": "来源",
        "table_target_file": "待重命名文件",
        "table_match": "匹配来源",
        "table_target_time": "采用时间",
        "table_target_name": "目标文件名",
        "table_status": "状态",
        "scan_reference": "扫描原始文件",
        "scan_target": "扫描待重命名",
        "rescan": "重新扫描全部",
        "clear_list": "清空列表",
        "start_rename": "开始重命名",
        "waiting_source": "等待放入原始文件和待重命名文件",
        "scanning_reference": "正在扫描原始文件",
        "scanning_target": "正在扫描待重命名文件",
        "scan_reference_none_status": "未找到原始照片",
        "scan_target_none_status": "未找到待重命名照片",
        "scan_reference_done_status": "已读取 {count} 个原始文件",
        "scan_target_done_status": "已读取 {count} 个待重命名文件",
        "scan_done_status": "原始文件 {reference} 个，待重命名 {target} 个",
        "reference_drop_added": "原始文件已添加 {added} 个，当前共 {count} 项",
        "target_drop_added": "待重命名文件已添加 {added} 个，当前共 {count} 项",
        "drop_no_new": "未添加新的文件",
        "list_cleared": "列表已清空",
        "preparing": "准备重命名",
        "progress": "正在处理 {i}/{total}",
        "task_done_status": "重命名完成：成功 {success}，失败 {failed}，跳过 {skipped}",
        "status_pending": "待处理",
        "status_renaming": "正在重命名",
        "status_renamed": "已重命名",
        "status_already_named": "文件名已符合规则",
        "status_no_reference_match": "未匹配原始文件",
        "status_skipped": "已跳过",
        "status_failed": "失败：{error}",
        "source_exif": "拍摄时间",
        "source_filename": "文件名时间",
        "source_earliest": "文件现有最早时间",
        "source_reference": "原始文件匹配",
        "source_unknown": "未知",
        "match_self": "使用自身时间",
        "match_none": "-",
        "invalid_folder_title": "目录无效",
        "invalid_reference_content": "请选择有效的原始文件目录。",
        "invalid_target_content": "请选择有效的待重命名目录。",
        "cannot_start_title": "无法开始",
        "cannot_start_content": "请先添加待重命名文件。",
        "task_done_title": "处理完成",
        "task_done_message": "照片重命名完成。\n\n成功: {success}\n失败: {failed}\n跳过: {skipped}",
        "process_done_notice": "已重命名 {count} 个文件",
        "target_unknown": "-",
    },
    "en": {
        "app_title": "Rename Photos",
        "header_title": "Rename Photos",
        "header_subtitle": "Read original files on the left, then rename matched target photos on the right",
        "header_note": "Matching prefers relative paths, then filenames. Unmatched targets can optionally fall back to their own time.",
        "language": "Language",
        "reference_dir": "Original folder",
        "target_dir": "Target folder",
        "reference_placeholder": "Choose or drop original photos used as the timestamp reference",
        "target_placeholder": "Choose or drop photos that should be renamed",
        "choose_reference": "Choose originals",
        "choose_target": "Choose targets",
        "scan_subdirs": "Scan subfolders",
        "require_reference_match": "Require original match",
        "photo_prefix": "Photo prefix",
        "video_prefix": "Video prefix",
        "prefix_presets": "Presets",
        "reference_drop_hint": "Original area: drop photos or folders with correct timestamps. These files are only read.",
        "target_drop_hint": "Target area: drop photos or folders to rename as IMG_yyyyMMdd_HHmmss from matched originals.",
        "table_reference_file": "Original file",
        "table_reference_time": "Read time",
        "table_reference_source": "Source",
        "table_target_file": "Target file",
        "table_match": "Match",
        "table_target_time": "Applied time",
        "table_target_name": "Target filename",
        "table_status": "Status",
        "scan_reference": "Scan originals",
        "scan_target": "Scan targets",
        "rescan": "Rescan all",
        "clear_list": "Clear list",
        "start_rename": "Rename files",
        "waiting_source": "Waiting for original and target files",
        "scanning_reference": "Scanning originals",
        "scanning_target": "Scanning targets",
        "scan_reference_none_status": "No original photos found",
        "scan_target_none_status": "No target photos found",
        "scan_reference_done_status": "Read {count} original file(s)",
        "scan_target_done_status": "Read {count} target file(s)",
        "scan_done_status": "{reference} original(s), {target} target(s)",
        "reference_drop_added": "Added {added} original file(s), total {count}",
        "target_drop_added": "Added {added} target file(s), total {count}",
        "drop_no_new": "No new files were added",
        "list_cleared": "List cleared",
        "preparing": "Preparing rename",
        "progress": "Processing {i}/{total}",
        "task_done_status": "Done: {success} renamed, {failed} failed, {skipped} skipped",
        "status_pending": "Pending",
        "status_renaming": "Renaming",
        "status_renamed": "Renamed",
        "status_already_named": "Already named",
        "status_no_reference_match": "No original match",
        "status_skipped": "Skipped",
        "status_failed": "Failed: {error}",
        "source_exif": "Capture time",
        "source_filename": "Filename time",
        "source_earliest": "Earliest existing file time",
        "source_reference": "Original match",
        "source_unknown": "Unknown",
        "match_self": "Own timestamp",
        "match_none": "-",
        "invalid_folder_title": "Invalid folder",
        "invalid_reference_content": "Choose a valid original folder.",
        "invalid_target_content": "Choose a valid target folder.",
        "cannot_start_title": "Cannot start",
        "cannot_start_content": "Add target files to rename first.",
        "task_done_title": "Task complete",
        "task_done_message": "Photo rename complete.\n\nRenamed: {success}\nFailed: {failed}\nSkipped: {skipped}",
        "process_done_notice": "Renamed {count} file(s)",
        "target_unknown": "-",
    },
}

TRANSLATIONS["zh"].update(
    {
        "app_title": "照片/视频重命名",
        "header_title": "照片/视频重命名",
        "header_subtitle": "左侧读取原始照片或视频时间，右侧按匹配到的文件时间重命名待处理文件",
        "header_note": "匹配优先使用相对路径，其次使用文件名；未匹配时可选择是否允许使用待重命名文件自身时间。",
        "reference_dir": "原始文件目录",
        "target_dir": "待重命名目录",
        "reference_placeholder": "选择或拖入用于读取时间信息的原始照片/视频目录",
        "target_placeholder": "选择或拖入实际需要重命名的照片/视频目录",
        "reference_drop_hint": "原始文件区：拖入保留正确时间信息的照片、视频或文件夹，只读取信息，不改名。",
        "target_drop_hint": "待重命名区：拖入需要改名的照片、视频或文件夹，照片生成 IMG_年月日_时分秒，视频生成 VID_年月日_时分秒。",
        "scan_reference_none_status": "未找到原始照片或视频",
        "scan_target_none_status": "未找到待重命名照片或视频",
        "cannot_start_content": "请先添加待重命名照片或视频。",
        "no_pending_title": "没有新的待处理文件",
        "no_pending_content": "列表里没有新的待处理照片或视频；已符合命名规则的文件会自动跳过，如需补写时间戳请勾选写入文件时间戳。",
        "task_done_message": "照片/视频重命名完成。\n\n成功: {success}\n失败: {failed}\n跳过: {skipped}",
        "write_timestamps": "写入文件时间戳",
        "status_renamed_timestamped": "已重命名并写入时间戳",
        "status_timestamped": "文件名已符合规则，已写入时间戳",
    }
)
TRANSLATIONS["en"].update(
    {
        "app_title": "Rename Photos and Videos",
        "header_title": "Rename Photos and Videos",
        "header_subtitle": "Read original photo/video times on the left, then rename matched target files on the right",
        "header_note": "Matching prefers relative paths, then filenames. Unmatched targets can optionally fall back to their own time.",
        "reference_dir": "Original folder",
        "target_dir": "Target folder",
        "reference_placeholder": "Choose or drop original photos/videos used as the timestamp reference",
        "target_placeholder": "Choose or drop photos/videos that should be renamed",
        "reference_drop_hint": "Original area: drop photos, videos, or folders with correct timestamps. These files are only read.",
        "target_drop_hint": "Target area: drop photos, videos, or folders. Photos use IMG_yyyyMMdd_HHmmss; videos use VID_yyyyMMdd_HHmmss.",
        "scan_reference_none_status": "No original photos or videos found",
        "scan_target_none_status": "No target photos or videos found",
        "cannot_start_content": "Add target photos or videos to rename first.",
        "no_pending_title": "No new pending files",
        "no_pending_content": "There are no new pending photos or videos. Already named files are skipped unless timestamp writing is enabled.",
        "task_done_message": "Photo/video rename complete.\n\nRenamed: {success}\nFailed: {failed}\nSkipped: {skipped}",
        "write_timestamps": "Write file timestamps",
        "status_renamed_timestamped": "Renamed and timestamped",
        "status_timestamped": "Already named; timestamped",
    }
)


@dataclass
class ReferenceItem:
    path: Path
    source_root: Path | None
    rel_path: Path
    timestamp: float | None
    source: str


@dataclass
class RenameItem:
    path: Path
    source_root: Path | None
    rel_path: Path
    own_timestamp: float | None
    own_source: str
    timestamp: float | None = None
    source: str = "source_unknown"
    match_mode: str = "none"
    matched_reference: str = ""
    target_name: str = ""
    target_path: Path | None = None
    status: str = "status_pending"
    row_index: int = -1


@dataclass
class ReferenceIndex:
    path: dict[Path, ReferenceItem]
    rel_stem: dict[str, ReferenceItem]
    stem: dict[str, ReferenceItem]


@dataclass(frozen=True)
class PrefixConfig:
    photo: str = DEFAULT_PHOTO_PREFIX
    video: str = DEFAULT_VIDEO_PREFIX


def _get_settings_path() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME / "settings.json"
    return Path.home() / ".config" / APP_NAME / "settings.json"


def _should_emit_progress(index: int, total: int) -> bool:
    if total <= 100:
        return True
    step = max(1, total // 100)
    return (index + 1) % step == 0 or index + 1 == total


def _pick_icon(*names: str):
    for name in names:
        icon = getattr(FluentIcon, name, None)
        if icon is not None:
            return icon
    return FluentIcon.APPLICATION


def _relative_path(file_path: Path, source_root: Path | None) -> Path:
    if source_root is not None:
        try:
            return file_path.relative_to(source_root)
        except ValueError:
            pass
    return Path(file_path.name)


def _key_text(value: str) -> str:
    return value.replace("\\", "/").casefold()


def _rel_stem_key(path: Path, source_root: Path | None) -> str:
    return _key_text(str(_rel_stem_match_path(path, source_root)))


def _stem_key(path: Path) -> str:
    return _live_pair_stem(path).casefold()


def _is_hevc_video_path(path: Path) -> bool:
    stem_key = path.stem.casefold()
    return path.suffix.lower() in VIDEO_RENAME_SUFFIXES and any(
        stem_key.endswith(suffix.casefold()) for suffix in LIVE_VIDEO_STEM_SUFFIXES
    )


def _reference_match_priority(item: ReferenceItem) -> int:
    if _is_hevc_video_path(item.path):
        return 2
    if item.path.suffix.lower() in VIDEO_RENAME_SUFFIXES:
        return 1
    return 0


def _live_pair_stem(path: Path) -> str:
    stem = path.stem
    if path.suffix.lower() not in VIDEO_RENAME_SUFFIXES:
        return stem
    stem_key = stem.casefold()
    for suffix in LIVE_VIDEO_STEM_SUFFIXES:
        if stem_key.endswith(suffix.casefold()):
            return stem[: -len(suffix)] or stem
    return stem


def _rel_stem_match_path(path: Path, source_root: Path | None) -> Path:
    rel_path = _relative_path(path, source_root)
    return rel_path.with_name(_live_pair_stem(path)).with_suffix("")


def _normalize_prefix(value: str, default: str) -> str:
    text = "".join("_" if char.isspace() else char for char in value.strip())
    text = "".join(char for char in text if char not in INVALID_FILENAME_CHARS and ord(char) >= 32)
    text = text.strip("._ ")
    return text or default


def _target_prefix_for(path: Path, prefixes: PrefixConfig | None = None) -> str:
    active = prefixes or PrefixConfig()
    return active.video if path.suffix.lower() in VIDEO_RENAME_SUFFIXES else active.photo


def _target_stem(path: Path, timestamp: float, prefixes: PrefixConfig | None = None) -> str:
    timestamp_text = datetime.fromtimestamp(timestamp).strftime("%Y%m%d_%H%M%S")
    return f"{_target_prefix_for(path, prefixes)}_{timestamp_text}"


def _target_filename(path: Path, timestamp: float, index: int = 0, prefixes: PrefixConfig | None = None) -> str:
    stem = _target_stem(path, timestamp, prefixes)
    if index:
        stem = f"{stem}_{index:03d}"
    return f"{stem}{path.suffix.lower()}"


def _is_generated_target_name(path: Path, timestamp: float, prefixes: PrefixConfig | None = None) -> bool:
    expected_stem = _target_stem(path, timestamp, prefixes)
    stem = path.stem
    if stem == expected_stem:
        return True
    if not stem.startswith(f"{expected_stem}_"):
        return False
    suffix = stem[len(expected_stem) + 1 :]
    return len(suffix) == 3 and suffix.isdigit()


def _is_same_path(left: Path, right: Path) -> bool:
    return _safe_resolve(left) == _safe_resolve(right)


def _is_supported_rename_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_RENAME_SUFFIXES


def detect_rename_timestamp(path: Path) -> tuple[float | None, str]:
    # Windows Shell metadata often drops seconds, so it is only a fallback for renaming.
    ts = _timestamp_from_exif(path)
    if ts is not None:
        return ts, "source_exif"
    ts = _timestamp_from_filename(path)
    if ts is not None:
        return ts, "source_filename"
    ts = _timestamp_from_windows_shell(path)
    if ts is not None:
        return ts, "source_exif"
    ts = _earliest_file_timestamp(path)
    if ts is not None:
        return ts, "source_earliest"
    return None, "source_unknown"


def _iter_rename_paths(paths: list[Path], recursive: bool) -> Iterator[tuple[Path, Path | None]]:
    for path in paths:
        if path.is_file():
            if _is_supported_rename_file(path):
                yield path, path.parent
            continue
        if not path.is_dir():
            continue
        iterator = path.rglob("*") if recursive else path.glob("*")
        for candidate in iterator:
            if _is_supported_rename_file(candidate):
                yield candidate, path


def _make_reference_item(file_path: Path, source_root: Path | None) -> ReferenceItem:
    timestamp, source = detect_rename_timestamp(file_path)
    return ReferenceItem(
        path=file_path,
        source_root=source_root,
        rel_path=_relative_path(file_path, source_root),
        timestamp=timestamp,
        source=source,
    )


def _make_target_item(file_path: Path, source_root: Path | None) -> RenameItem:
    timestamp, source = detect_rename_timestamp(file_path)
    return RenameItem(
        path=file_path,
        source_root=source_root,
        rel_path=_relative_path(file_path, source_root),
        own_timestamp=timestamp,
        own_source=source,
    )


def _add_unique(mapping: dict[str, ReferenceItem], duplicates: set[str], key: str, item: ReferenceItem) -> None:
    existing = mapping.get(key)
    if existing is None or _reference_match_priority(item) > _reference_match_priority(existing):
        mapping[key] = item
        return


def _build_reference_index(items: list[ReferenceItem]) -> ReferenceIndex:
    path: dict[Path, ReferenceItem] = {}
    rel_stem: dict[str, ReferenceItem] = {}
    stem: dict[str, ReferenceItem] = {}
    duplicate_rel_stem: set[str] = set()
    duplicate_stem: set[str] = set()
    for item in items:
        if item.timestamp is None:
            continue
        path[_safe_resolve(item.path)] = item
        _add_unique(rel_stem, duplicate_rel_stem, _rel_stem_key(item.path, item.source_root), item)
        _add_unique(stem, duplicate_stem, _stem_key(item.path), item)
    return ReferenceIndex(path=path, rel_stem=rel_stem, stem=stem)


def _find_reference_match(item: RenameItem, index: ReferenceIndex) -> ReferenceItem | None:
    path_match = index.path.get(_safe_resolve(item.path))
    if path_match is not None:
        return path_match
    rel_match = index.rel_stem.get(_rel_stem_key(item.path, item.source_root))
    if rel_match is not None:
        return rel_match
    return index.stem.get(_stem_key(item.path))


def _unique_target_path(item: RenameItem, reserved: set[Path], prefixes: PrefixConfig | None = None) -> Path | None:
    if item.timestamp is None:
        return None
    if _is_generated_target_name(item.path, item.timestamp, prefixes):
        return item.path

    for index in range(10000):
        candidate = item.path.with_name(_target_filename(item.path, item.timestamp, index, prefixes))
        resolved = _safe_resolve(candidate)
        if resolved in reserved:
            continue
        if candidate.exists() and not _is_same_path(candidate, item.path):
            continue
        return candidate
    raise RuntimeError("could not allocate a unique target filename")


def _assign_target_paths(items: list[RenameItem], prefixes: PrefixConfig | None = None) -> None:
    reserved: set[Path] = set()
    for item in items:
        target_path = _unique_target_path(item, reserved, prefixes)
        item.target_path = target_path
        item.target_name = target_path.name if target_path is not None else ""
        if target_path is not None:
            reserved.add(_safe_resolve(target_path))


def _rename_path(source: Path, target: Path):
    if sys.platform == "win32":
        move_file_ex = ctypes.windll.kernel32.MoveFileExW
        move_file_ex.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        move_file_ex.restype = ctypes.c_bool
        MOVEFILE_COPY_ALLOWED = 0x00000002
        if not move_file_ex(str(source), str(target), MOVEFILE_COPY_ALLOWED):
            raise ctypes.WinError()
        return
    source.rename(target)


class ReferenceScanWorker(QObject):
    row_ready = pyqtSignal(object)
    finished = pyqtSignal(int)

    def __init__(self, paths: list[Path], recursive: bool):
        super().__init__()
        self.paths = paths
        self.recursive = recursive

    def run(self):
        seen: set[Path] = set()
        count = 0
        for file_path, source_root in _iter_rename_paths(self.paths, self.recursive):
            resolved = _safe_resolve(file_path)
            if resolved in seen:
                continue
            seen.add(resolved)
            self.row_ready.emit(_make_reference_item(file_path, source_root))
            count += 1

        self.finished.emit(count)


class TargetScanWorker(QObject):
    row_ready = pyqtSignal(object)
    finished = pyqtSignal(int)

    def __init__(self, paths: list[Path], recursive: bool):
        super().__init__()
        self.paths = paths
        self.recursive = recursive

    def run(self):
        seen: set[Path] = set()
        count = 0
        for file_path, source_root in _iter_rename_paths(self.paths, self.recursive):
            resolved = _safe_resolve(file_path)
            if resolved in seen:
                continue
            seen.add(resolved)
            self.row_ready.emit(_make_target_item(file_path, source_root))
            count += 1

        self.finished.emit(count)


class ReferenceDropScanWorker(QObject):
    row_ready = pyqtSignal(object)
    finished = pyqtSignal(int)

    def __init__(self, paths: list[Path], recursive: bool, existing: set[Path]):
        super().__init__()
        self.paths = paths
        self.recursive = recursive
        self.existing = existing

    def run(self):
        seen: set[Path] = set(self.existing)
        count = 0
        for file_path, source_root in _iter_rename_paths(self.paths, self.recursive):
            resolved = _safe_resolve(file_path)
            if resolved in seen:
                continue
            seen.add(resolved)
            self.row_ready.emit(_make_reference_item(file_path, source_root))
            count += 1

        self.finished.emit(count)


class TargetDropScanWorker(QObject):
    row_ready = pyqtSignal(object)
    finished = pyqtSignal(int)

    def __init__(self, paths: list[Path], recursive: bool, existing: set[Path]):
        super().__init__()
        self.paths = paths
        self.recursive = recursive
        self.existing = existing

    def run(self):
        seen: set[Path] = set(self.existing)
        count = 0
        for file_path, source_root in _iter_rename_paths(self.paths, self.recursive):
            resolved = _safe_resolve(file_path)
            if resolved in seen:
                continue
            seen.add(resolved)
            self.row_ready.emit(_make_target_item(file_path, source_root))
            count += 1

        self.finished.emit(count)


class ProcessWorker(QObject):
    row_update_batch = pyqtSignal(object)
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, items: list[RenameItem], write_timestamps: bool = False, prefixes: PrefixConfig | None = None):
        super().__init__()
        self.items = items
        self.write_timestamps = write_timestamps
        self.prefixes = prefixes or PrefixConfig()

    def _emit_update_batch(self, updates: list[tuple[int, str, object]]):
        if updates:
            self.row_update_batch.emit(updates[:])
            updates.clear()

    def run(self):
        success = 0
        failed = 0
        skipped = 0
        total = len(self.items)
        update_batch: list[tuple[int, str, object]] = []
        reserved: set[Path] = set()

        for index, item in enumerate(self.items):
            row_index = item.row_index if item.row_index >= 0 else index
            progress_percent = int(((index + 1) / total) * 100) if total else 0
            try:
                target_path = _unique_target_path(item, reserved, self.prefixes)
            except Exception:
                target_path = None
            item.target_path = target_path
            item.target_name = target_path.name if target_path is not None else ""
            if target_path is not None:
                reserved.add(_safe_resolve(target_path))
            target_path = item.target_path

            if item.timestamp is None or target_path is None:
                skipped += 1
                status = item.status if item.status == "status_no_reference_match" else "status_skipped"
                update_batch.append((row_index, status, None))
                if len(update_batch) >= PROCESS_ROW_BATCH_SIZE:
                    self._emit_update_batch(update_batch)
                if _should_emit_progress(index, total):
                    self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")
                    QThread.msleep(1)
                elif index % 10 == 0:
                    QThread.msleep(1)
                continue

            if _is_same_path(item.path, target_path):
                try:
                    if self.write_timestamps:
                        apply_file_times_only(item.path, item.timestamp)
                        update_batch.append((row_index, "status_timestamped", target_path))
                    else:
                        update_batch.append((row_index, "status_already_named", target_path))
                    skipped += 1
                except Exception as exc:
                    failed += 1
                    update_batch.append((row_index, f"status_failed|{str(exc)[:36]}", target_path))
                if len(update_batch) >= PROCESS_ROW_BATCH_SIZE:
                    self._emit_update_batch(update_batch)
                if _should_emit_progress(index, total):
                    self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")
                    QThread.msleep(1)
                elif index % 10 == 0:
                    QThread.msleep(1)
                continue

            try:
                _rename_path(item.path, target_path)
                if self.write_timestamps:
                    apply_file_times_only(target_path, item.timestamp)
                item.path = target_path
                item.rel_path = _relative_path(target_path, item.source_root)
                item.target_name = target_path.name
                success += 1
                status = "status_renamed_timestamped" if self.write_timestamps else "status_renamed"
                update_batch.append((row_index, status, target_path))
            except Exception as exc:
                failed += 1
                update_batch.append((row_index, f"status_failed|{str(exc)[:36]}", target_path))

            if len(update_batch) >= PROCESS_ROW_BATCH_SIZE:
                self._emit_update_batch(update_batch)
            if _should_emit_progress(index, total):
                self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")
                QThread.msleep(1)
            elif index % 10 == 0:
                QThread.msleep(1)

        self._emit_update_batch(update_batch)
        self.finished.emit({"success": success, "failed": failed, "skipped": skipped})


class MainWindow(FramelessMainWindow):
    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("Rename Photos")
        self._title_bar_height = 36
        if not self._embedded:
            self.resize(1320, 860)
            self._set_blue_title_bar()

        self.lang = DEFAULT_LANGUAGE
        self._last_status_key = "waiting_source"
        self._last_status_kwargs: dict = {}
        self.reference_list: list[ReferenceItem] = []
        self.file_list: list[RenameItem] = []
        self._reference_row_queue: deque[ReferenceItem] = deque()
        self._target_row_queue: deque[RenameItem] = deque()
        self._pending_reference_drop_result: int | None = None
        self._pending_target_drop_result: int | None = None
        self._pending_reference_scan_result: int | None = None
        self._pending_target_scan_result: int | None = None
        self._scan_drain_timer = QTimer(self)
        self._scan_drain_timer.setInterval(10)
        self._scan_drain_timer.timeout.connect(self._drain_scan_rows)
        self._process_update_queue: deque[tuple[int, str, object]] = deque()
        self._pending_process_result: dict | None = None
        self._process_drain_timer = QTimer(self)
        self._process_drain_timer.setInterval(10)
        self._process_drain_timer.timeout.connect(self._drain_process_updates)
        self.is_processing = False
        self._reference_scan_thread: QThread | None = None
        self._reference_scan_worker: ReferenceScanWorker | None = None
        self._target_scan_thread: QThread | None = None
        self._target_scan_worker: TargetScanWorker | None = None
        self._reference_drop_thread: QThread | None = None
        self._reference_drop_worker: ReferenceDropScanWorker | None = None
        self._target_drop_thread: QThread | None = None
        self._target_drop_worker: TargetDropScanWorker | None = None
        self._process_thread: QThread | None = None
        self._process_worker: ProcessWorker | None = None
        self._settings_path = _get_settings_path()
        self._suspend_settings_save = False
        self._syncing_quick_options = False

        root = QWidget(self)
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, (0 if self._embedded else self._title_bar_height) + 12, 20, 18)
        outer.setSpacing(12)

        header_card = QWidget(self)
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(4, 6, 4, 10)
        header_layout.setSpacing(4)

        self.title_label = SubtitleLabel(self.tr("header_title"), self)
        title_font = QFont("Microsoft YaHei", 15)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.subtitle_label = BodyLabel(self.tr("header_subtitle"), self)
        self.subtitle_label.setStyleSheet("color: #667085;")
        self.subtitle_note_label = BodyLabel(self.tr("header_note"), self)
        self.subtitle_note_label.setStyleSheet("color: #98A2B3;")

        self.language_label = BodyLabel(self.tr("language"), self)
        self.language_combo = ComboBox(self)
        self.language_combo.addItem("中文", userData="zh")
        self.language_combo.addItem("English", userData="en")
        self.language_combo.setFixedWidth(128)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        language_row = QHBoxLayout()
        language_row.addStretch(1)
        language_row.addWidget(self.language_label)
        language_row.addWidget(self.language_combo)

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.subtitle_label)
        header_layout.addWidget(self.subtitle_note_label)
        if not self._embedded:
            header_layout.addLayout(language_row)

        self.path_card = QWidget(self)
        self.path_card.hide()
        path_layout = QVBoxLayout(self.path_card)
        path_layout.setContentsMargins(16, 14, 16, 14)
        path_layout.setSpacing(10)

        self.reference_path_row = QWidget(self)
        reference_row = QHBoxLayout(self.reference_path_row)
        reference_row.setContentsMargins(0, 0, 0, 0)
        reference_row.setSpacing(10)
        self.reference_label = BodyLabel(self.tr("reference_dir"), self)
        self.reference_edit = LineEdit(self)
        self.reference_edit.setReadOnly(False)
        self.reference_edit.setPlaceholderText(self.tr("reference_placeholder"))
        self.reference_edit.hide()
        self.btn_reference = PushButton(self.tr("choose_reference"), self)
        self.btn_reference.setIcon(_pick_icon("FOLDER", "FOLDER_ADD"))
        self.btn_reference.clicked.connect(self.browse_reference)
        reference_row.addWidget(self.reference_label)
        reference_row.addStretch(1)
        reference_row.addWidget(self.btn_reference)

        self.target_path_row = QWidget(self)
        target_row = QHBoxLayout(self.target_path_row)
        target_row.setContentsMargins(0, 0, 0, 0)
        target_row.setSpacing(10)
        self.target_label = BodyLabel(self.tr("target_dir"), self)
        self.target_edit = LineEdit(self)
        self.target_edit.setReadOnly(False)
        self.target_edit.setPlaceholderText(self.tr("target_placeholder"))
        self.target_edit.hide()
        self.btn_target = PushButton(self.tr("choose_target"), self)
        self.btn_target.setIcon(_pick_icon("FOLDER", "FOLDER_ADD"))
        self.btn_target.clicked.connect(self.browse_target)
        self.btn_target.hide()
        target_row.addWidget(self.target_label)
        target_row.addStretch(1)
        target_row.addWidget(self.btn_target)

        path_layout.addWidget(self.reference_path_row)
        path_layout.addWidget(self.target_path_row)

        self.option_card = QWidget(self)
        self.option_card.hide()
        option_layout = QVBoxLayout(self.option_card)
        option_layout.setContentsMargins(16, 14, 16, 14)
        option_layout.setSpacing(10)
        option_row = QHBoxLayout()
        option_row.setSpacing(12)
        self.include_subdirs_check = CheckBox(self.tr("scan_subdirs"), self)
        self.include_subdirs_check.setChecked(True)
        self.include_subdirs_check.toggled.connect(self.scan_files)
        self.require_reference_match_check = CheckBox(self.tr("require_reference_match"), self)
        self.require_reference_match_check.setChecked(True)
        self.require_reference_match_check.toggled.connect(self._on_match_option_changed)
        self.write_timestamps_check = CheckBox(self.tr("write_timestamps"), self)
        self.write_timestamps_check.setChecked(False)
        option_row.addWidget(self.include_subdirs_check)
        option_row.addWidget(self.require_reference_match_check)
        option_row.addWidget(self.write_timestamps_check)
        option_row.addStretch(1)
        option_layout.addLayout(option_row)

        self.quick_option_widget = QWidget(self)
        quick_option_layout = QVBoxLayout(self.quick_option_widget)
        quick_option_layout.setContentsMargins(0, 0, 0, 0)
        quick_option_layout.setSpacing(8)
        prefix_row = QHBoxLayout()
        prefix_row.setSpacing(8)
        quick_option_row = QHBoxLayout()
        quick_option_row.setSpacing(12)
        self.quick_require_reference_match_check = CheckBox(self.tr("require_reference_match"), self)
        self.quick_require_reference_match_check.setChecked(self.require_reference_match_check.isChecked())
        self.quick_require_reference_match_check.toggled.connect(self._on_quick_require_reference_match_changed)
        self.quick_write_timestamps_check = CheckBox(self.tr("write_timestamps"), self)
        self.quick_write_timestamps_check.setChecked(self.write_timestamps_check.isChecked())
        self.quick_write_timestamps_check.toggled.connect(self._on_quick_write_timestamps_changed)
        self.photo_prefix_label = BodyLabel(self.tr("photo_prefix"), self)
        self.photo_prefix_edit = LineEdit(self)
        self.photo_prefix_edit.setText(DEFAULT_PHOTO_PREFIX)
        self.photo_prefix_edit.setFixedWidth(96)
        self.video_prefix_label = BodyLabel(self.tr("video_prefix"), self)
        self.video_prefix_edit = LineEdit(self)
        self.video_prefix_edit.setText(DEFAULT_VIDEO_PREFIX)
        self.video_prefix_edit.setFixedWidth(96)
        self.btn_photo_prefix_menu = PushButton(self.tr("prefix_presets"), self)
        self.btn_photo_prefix_menu.setFixedWidth(68)
        self.btn_photo_prefix_menu.clicked.connect(self._show_photo_prefix_menu)
        self.btn_video_prefix_menu = PushButton(self.tr("prefix_presets"), self)
        self.btn_video_prefix_menu.setFixedWidth(68)
        self.btn_video_prefix_menu.clicked.connect(self._show_video_prefix_menu)
        self.photo_prefix_edit.editingFinished.connect(self._on_prefix_changed)
        self.video_prefix_edit.editingFinished.connect(self._on_prefix_changed)
        prefix_row.addStretch(1)
        prefix_row.addWidget(self.photo_prefix_label)
        prefix_row.addWidget(self.photo_prefix_edit)
        prefix_row.addWidget(self.btn_photo_prefix_menu)
        prefix_row.addWidget(self.video_prefix_label)
        prefix_row.addWidget(self.video_prefix_edit)
        prefix_row.addWidget(self.btn_video_prefix_menu)
        quick_option_row.addWidget(self.quick_require_reference_match_check)
        quick_option_row.addWidget(self.quick_write_timestamps_check)
        quick_option_row.addStretch(1)
        quick_option_layout.addLayout(prefix_row)
        quick_option_layout.addLayout(quick_option_row)
        tables_layout = QVBoxLayout()
        tables_layout.setSpacing(12)

        self.reference_card = CardWidget(self)
        reference_layout = QVBoxLayout(self.reference_card)
        reference_layout.setContentsMargins(10, 10, 10, 10)
        reference_layout.setSpacing(8)
        reference_hint_row = QHBoxLayout()
        reference_hint_row.setSpacing(8)
        self.reference_drop_hint = BodyLabel(self.tr("reference_drop_hint"), self)
        self.reference_drop_hint.setStyleSheet("color: #6b7280; padding: 4px 6px;")
        reference_hint_row.addWidget(self.reference_drop_hint)
        reference_hint_row.addStretch(1)

        self.reference_table = TableWidget(self)
        self.reference_table.setColumnCount(3)
        self.reference_table.setHorizontalHeaderLabels(self._reference_headers())
        self._configure_table(self.reference_table)
        reference_header = self.reference_table.horizontalHeader()
        reference_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        reference_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        reference_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.reference_table.viewport().installEventFilter(self)
        self.reference_context_menu = install_file_context_menu(
            self.reference_table,
            self,
            self._reference_context_file_paths,
            lambda: self.lang,
        )
        reference_layout.addLayout(reference_hint_row)
        reference_layout.addWidget(self.reference_table)

        target_card = CardWidget(self)
        target_layout = QVBoxLayout(target_card)
        target_layout.setContentsMargins(10, 10, 10, 10)
        target_layout.setSpacing(8)
        target_hint_row = QHBoxLayout()
        target_hint_row.setSpacing(8)
        self.target_drop_hint = BodyLabel(self.tr("target_drop_hint"), self)
        self.target_drop_hint.setStyleSheet("color: #6b7280; padding: 4px 6px;")
        target_hint_row.addWidget(self.target_drop_hint)
        target_hint_row.addStretch(1)

        self.table = TableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(self._target_headers())
        self._configure_table(self.table)
        target_header = self.table.horizontalHeader()
        target_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        target_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        target_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        target_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        target_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.viewport().installEventFilter(self)
        self.target_context_menu = install_file_context_menu(
            self.table,
            self,
            self._target_context_file_paths,
            lambda: self.lang,
        )
        target_layout.addLayout(target_hint_row)
        target_layout.addWidget(self.table)

        tables_layout.addWidget(target_card, 2)
        tables_layout.addWidget(self.reference_card, 1)

        action_card = CardWidget(self)
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(16, 12, 16, 12)
        action_layout.setSpacing(8)
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.btn_scan_reference = PushButton(self.tr("scan_reference"), self)
        self.btn_scan_reference.setIcon(_pick_icon("SEARCH", "SYNC", "UPDATE"))
        self.btn_scan_reference.clicked.connect(self.scan_reference_files)
        self.btn_scan_target = PushButton(self.tr("scan_target"), self)
        self.btn_scan_target.setIcon(_pick_icon("SEARCH", "SYNC", "UPDATE"))
        self.btn_scan_target.clicked.connect(self.scan_target_files)
        self.btn_scan = PushButton(self.tr("rescan"), self)
        self.btn_scan.setIcon(_pick_icon("SYNC", "UPDATE"))
        self.btn_scan.clicked.connect(self.scan_files)
        self.btn_clear = PushButton(self.tr("clear_list"), self)
        self.btn_clear.setIcon(_pick_icon("DELETE", "REMOVE"))
        self.btn_clear.clicked.connect(self.clear_list)
        self.btn_start = PrimaryPushButton(self.tr("start_rename"), self)
        self.btn_start.setIcon(_pick_icon("EDIT", "TAG", "PLAY"))
        self.btn_start.clicked.connect(self.start_processing)
        action_layout.addWidget(self.quick_option_widget)
        action_row.addWidget(self.btn_scan_reference)
        action_row.addWidget(self.btn_scan_target)
        action_row.addWidget(self.btn_scan)
        action_row.addWidget(self.btn_clear)
        action_row.addStretch(1)
        action_row.addWidget(self.btn_start)
        action_layout.addLayout(action_row)

        foot_card = CardWidget(self)
        foot_layout = QHBoxLayout(foot_card)
        foot_layout.setContentsMargins(16, 12, 16, 12)
        foot_layout.setSpacing(10)
        self.progress = ProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setFixedHeight(10)
        self.progress.setMinimumWidth(280)
        self.progress.setMaximumWidth(420)
        self.status = BodyLabel(self.tr("waiting_source"), self)
        self.status.setStyleSheet("color: #475467;")
        foot_layout.addStretch(1)
        foot_layout.addWidget(self.progress, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        foot_layout.addWidget(self.status, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        outer.addWidget(header_card)
        outer.addLayout(tables_layout, 1)
        outer.addWidget(action_card)
        outer.addWidget(foot_card)

        self._init_default_dirs()
        self._load_settings()
        self._apply_language()
        self._update_reference_area_visibility()
        self.target_path_row.hide()
        self._connect_settings_signals()

    def _configure_table(self, table: TableWidget):
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(table.SelectionBehavior.SelectRows)
        table.setEditTriggers(table.EditTrigger.NoEditTriggers)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setAcceptDrops(True)
        table.viewport().setAcceptDrops(True)
        table.verticalHeader().setDefaultSectionSize(36)

    def _reference_context_file_paths(self, _row: int, selected_rows: list[int]) -> list[Path]:
        return [
            self.reference_list[row].path
            for row in selected_rows
            if 0 <= row < len(self.reference_list)
        ]

    def _target_context_file_paths(self, _row: int, selected_rows: list[int]) -> list[Path]:
        return [
            self.file_list[row].path
            for row in selected_rows
            if 0 <= row < len(self.file_list)
        ]

    def _set_blue_title_bar(self):
        self.setTitleBar(StandardTitleBar(self))
        self._title_bar_height = self.titleBar.height()
        self.titleBar.setObjectName("blueTitleBar")
        self.titleBar.setStyleSheet(
            """
            QWidget#blueTitleBar {
                background: #1677FF;
            }
            QWidget#blueTitleBar QLabel {
                color: #FFFFFF;
                background: transparent;
            }
            """
        )

    def tr(self, key: str, **kwargs) -> str:
        text = TRANSLATIONS.get(self.lang, TRANSLATIONS["zh"]).get(key, key)
        return text.format(**kwargs) if kwargs else text

    def _reference_headers(self) -> list[str]:
        return [
            self.tr("table_reference_file"),
            self.tr("table_reference_time"),
            self.tr("table_reference_source"),
        ]

    def _target_headers(self) -> list[str]:
        return [
            self.tr("table_target_file"),
            self.tr("table_match"),
            self.tr("table_target_time"),
            self.tr("table_target_name"),
            self.tr("table_status"),
        ]

    def _display_status(self, status: str) -> str:
        if status.startswith("status_failed|"):
            return self.tr("status_failed", error=status.split("|", 1)[1])
        translated = self.tr(status)
        return translated if translated != status or status.startswith("status_") else status

    def _display_progress_text(self, text: str) -> str:
        if text.startswith("progress|"):
            _, i, total = text.split("|", 2)
            return self.tr("progress", i=i, total=total)
        return self._display_status(text)

    def _target_match_text(self, item: RenameItem) -> str:
        if item.match_mode == "reference" and item.matched_reference:
            return item.matched_reference
        if item.match_mode == "self":
            return self.tr("match_self")
        return self.tr("match_none")

    def _set_status_text(self, key: str, **kwargs):
        self._last_status_key = key
        self._last_status_kwargs = kwargs
        self.status.setText(self.tr(key, **kwargs))

    def _sync_path_tooltips(self):
        reference_dir = self.reference_edit.text().strip()
        target_dir = self.target_edit.text().strip()
        self.btn_reference.setToolTip(reference_dir or self.tr("reference_placeholder"))
        self.btn_target.setToolTip(target_dir or self.tr("target_placeholder"))

    def _prefix_config(self) -> PrefixConfig:
        return PrefixConfig(
            photo=_normalize_prefix(self.photo_prefix_edit.text(), DEFAULT_PHOTO_PREFIX),
            video=_normalize_prefix(self.video_prefix_edit.text(), DEFAULT_VIDEO_PREFIX),
        )

    def _set_prefix_text(self, photo: str | None = None, video: str | None = None):
        if photo is not None:
            self.photo_prefix_edit.setText(_normalize_prefix(photo, DEFAULT_PHOTO_PREFIX))
        if video is not None:
            self.video_prefix_edit.setText(_normalize_prefix(video, DEFAULT_VIDEO_PREFIX))

    def _show_prefix_menu(self, button: PushButton, presets: tuple[str, ...], setter):
        menu = QMenu(self)
        for prefix in presets:
            action = menu.addAction(prefix)
            action.triggered.connect(lambda _checked=False, value=prefix: setter(value))
        button_pos = button.mapToGlobal(button.rect().bottomLeft())
        menu.exec(button_pos)

    def _show_photo_prefix_menu(self):
        self._show_prefix_menu(self.btn_photo_prefix_menu, PHOTO_PREFIX_PRESETS, self._set_photo_prefix)

    def _show_video_prefix_menu(self):
        self._show_prefix_menu(self.btn_video_prefix_menu, VIDEO_PREFIX_PRESETS, self._set_video_prefix)

    def _set_photo_prefix(self, value: str):
        self._set_prefix_text(photo=value)
        self._on_prefix_changed()

    def _set_video_prefix(self, value: str):
        self._set_prefix_text(video=value)
        self._on_prefix_changed()

    def _on_prefix_changed(self):
        prefixes = self._prefix_config()
        self._set_prefix_text(prefixes.photo, prefixes.video)
        self._refresh_target_matches()
        self._save_settings()

    def _thread_is_running(self, thread: QThread | None) -> bool:
        try:
            return thread is not None and thread.isRunning()
        except RuntimeError:
            return False

    def _is_busy(self) -> bool:
        return (
            self.is_processing
            or self._thread_is_running(self._reference_scan_thread)
            or self._thread_is_running(self._target_scan_thread)
            or self._thread_is_running(self._reference_drop_thread)
            or self._thread_is_running(self._target_drop_thread)
            or self._scan_drain_timer.isActive()
            or bool(self._reference_row_queue)
            or bool(self._target_row_queue)
            or self._process_drain_timer.isActive()
            or bool(self._process_update_queue)
        )

    def _init_default_dirs(self):
        pics_dir = _get_windows_pictures_dir() or (Path.home() / "Pictures")
        self.reference_edit.clear()
        self.target_edit.setText(str(pics_dir))
        self._sync_path_tooltips()
        self._set_status_text("waiting_source")

    def _settings_payload(self) -> dict:
        prefixes = self._prefix_config()
        return {
            "language": self.lang,
            "reference_dir": self.reference_edit.text().strip(),
            "target_dir": self.target_edit.text().strip(),
            "include_subdirs": self.include_subdirs_check.isChecked(),
            "require_reference_match": self.require_reference_match_check.isChecked(),
            "write_timestamps": self.write_timestamps_check.isChecked(),
            "photo_prefix": prefixes.photo,
            "video_prefix": prefixes.video,
        }

    def _save_settings(self):
        if self._suspend_settings_save:
            return
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            self._settings_path.write_text(
                json.dumps(self._settings_payload(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _connect_settings_signals(self):
        self.reference_edit.editingFinished.connect(self._save_settings)
        self.target_edit.editingFinished.connect(self._save_settings)
        self.include_subdirs_check.toggled.connect(lambda _checked=False: self._save_settings())
        self.require_reference_match_check.toggled.connect(lambda _checked=False: self._save_settings())
        self.write_timestamps_check.toggled.connect(self._on_write_timestamps_changed)

    def _load_settings(self):
        if not self._settings_path.exists():
            return
        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except Exception:
            return

        self._suspend_settings_save = True
        try:
            lang = data.get("language")
            if lang in SUPPORTED_LANGUAGES:
                self.lang = lang
                for idx in range(self.language_combo.count()):
                    if self.language_combo.itemData(idx) == lang:
                        self.language_combo.setCurrentIndex(idx)
                        break

            reference_dir = str(data.get("reference_dir", "")).strip()
            if reference_dir:
                self.reference_edit.setText(reference_dir)

            target_dir = str(data.get("target_dir", data.get("input_dir", ""))).strip()
            if target_dir:
                self.target_edit.setText(target_dir)
            self.include_subdirs_check.setChecked(bool(data.get("include_subdirs", True)))
            self.require_reference_match_check.setChecked(bool(data.get("require_reference_match", True)))
            self.write_timestamps_check.setChecked(bool(data.get("write_timestamps", False)))
            self._set_prefix_text(
                photo=str(data.get("photo_prefix", DEFAULT_PHOTO_PREFIX)),
                video=str(data.get("video_prefix", DEFAULT_VIDEO_PREFIX)),
            )
            self._sync_quick_options()
            self._sync_path_tooltips()
        finally:
            self._suspend_settings_save = False

    def _on_language_changed(self, _index: int):
        lang = self.language_combo.currentData()
        if lang not in SUPPORTED_LANGUAGES or lang == self.lang:
            return
        self.lang = lang
        self._apply_language()
        self._save_settings()

    def _sync_quick_options(self):
        if self._syncing_quick_options:
            return
        self._syncing_quick_options = True
        try:
            self.quick_require_reference_match_check.blockSignals(True)
            self.quick_write_timestamps_check.blockSignals(True)
            self.quick_require_reference_match_check.setChecked(self.require_reference_match_check.isChecked())
            self.quick_write_timestamps_check.setChecked(self.write_timestamps_check.isChecked())
        finally:
            self.quick_require_reference_match_check.blockSignals(False)
            self.quick_write_timestamps_check.blockSignals(False)
            self._syncing_quick_options = False

    def _on_quick_require_reference_match_changed(self, checked: bool):
        if self._syncing_quick_options:
            return
        self.require_reference_match_check.setChecked(checked)

    def _on_quick_write_timestamps_changed(self, checked: bool):
        if self._syncing_quick_options:
            return
        self.write_timestamps_check.setChecked(checked)

    def _on_write_timestamps_changed(self, _checked: bool):
        self._sync_quick_options()
        self._save_settings()

    def _update_reference_area_visibility(self):
        show_reference_area = self.require_reference_match_check.isChecked()
        self.reference_path_row.setVisible(show_reference_area)
        self.reference_card.setVisible(show_reference_area)
        self.btn_scan_reference.setVisible(show_reference_area)

    def _on_match_option_changed(self, _checked: bool):
        self._sync_quick_options()
        self._update_reference_area_visibility()
        self._refresh_target_matches()
        self._save_settings()

    def _apply_language(self):
        self.setWindowTitle(self.tr("app_title"))
        self.title_label.setText(self.tr("header_title"))
        self.subtitle_label.setText(self.tr("header_subtitle"))
        self.subtitle_note_label.setText(self.tr("header_note"))
        self.language_label.setText(self.tr("language"))
        self.reference_label.setText(self.tr("reference_dir"))
        self.target_label.setText(self.tr("target_dir"))
        self.reference_edit.setPlaceholderText(self.tr("reference_placeholder"))
        self.target_edit.setPlaceholderText(self.tr("target_placeholder"))
        self.btn_reference.setText(self.tr("choose_reference"))
        self.btn_target.setText(self.tr("choose_target"))
        self._sync_path_tooltips()
        self.include_subdirs_check.setText(self.tr("scan_subdirs"))
        self.require_reference_match_check.setText(self.tr("require_reference_match"))
        self.write_timestamps_check.setText(self.tr("write_timestamps"))
        self.quick_require_reference_match_check.setText(self.tr("require_reference_match"))
        self.quick_write_timestamps_check.setText(self.tr("write_timestamps"))
        self.photo_prefix_label.setText(self.tr("photo_prefix"))
        self.video_prefix_label.setText(self.tr("video_prefix"))
        self.btn_photo_prefix_menu.setText(self.tr("prefix_presets"))
        self.btn_video_prefix_menu.setText(self.tr("prefix_presets"))
        self.btn_photo_prefix_menu.setToolTip(self.tr("prefix_presets"))
        self.btn_video_prefix_menu.setToolTip(self.tr("prefix_presets"))
        self.reference_drop_hint.setText(self.tr("reference_drop_hint"))
        self.target_drop_hint.setText(self.tr("target_drop_hint"))
        self.reference_table.setHorizontalHeaderLabels(self._reference_headers())
        self.table.setHorizontalHeaderLabels(self._target_headers())
        self.btn_scan_reference.setText(self.tr("scan_reference"))
        self.btn_scan_target.setText(self.tr("scan_target"))
        self.btn_scan.setText(self.tr("rescan"))
        self.btn_clear.setText(self.tr("clear_list"))
        self.btn_start.setText(self.tr("start_rename"))
        self._set_status_text(self._last_status_key, **self._last_status_kwargs)
        self._refresh_table_language()

    def _refresh_table_language(self):
        for row, item in enumerate(self.reference_list):
            source_item = self.reference_table.item(row, 2)
            if source_item is not None:
                source_item.setText(self.tr(item.source))
        for row, item in enumerate(self.file_list):
            match_item = self.table.item(row, 1)
            status_item = self.table.item(row, 4)
            if match_item is not None:
                match_item.setText(self._target_match_text(item))
            if status_item is not None:
                status_item.setText(self._display_status(item.status))

    def eventFilter(self, obj, event):
        reference_viewport = self.reference_table.viewport() if hasattr(self, "reference_table") else None
        target_viewport = self.table.viewport() if hasattr(self, "table") else None
        if obj is reference_viewport or obj is target_viewport:
            if event.type() == QEvent.Type.DragEnter:
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    return True
            if event.type() == QEvent.Type.DragMove:
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    return True
            if event.type() == QEvent.Type.Drop:
                paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
                if paths:
                    if obj is reference_viewport:
                        self.add_reference_paths(paths)
                    else:
                        self.add_target_paths(paths)
                    event.acceptProposedAction()
                    return True
        return super().eventFilter(obj, event)

    def _notify(self, title: str, content: str, is_error: bool = False):
        fn = InfoBar.error if is_error else InfoBar.success
        fn(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2600 if is_error else 1800,
            parent=self,
        )

    def _first_source_dir(self, paths: list[Path]) -> Path | None:
        first_dir = next((p for p in paths if p.is_dir()), None)
        if first_dir is not None:
            return first_dir
        first_file = next((p for p in paths if p.is_file()), None)
        return first_file.parent if first_file is not None else None

    def browse_reference(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("choose_reference"))
        if not folder:
            return
        self.reference_edit.setText(folder)
        self._sync_path_tooltips()
        self._save_settings()
        self.scan_reference_files()

    def browse_target(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("choose_target"))
        if not folder:
            return
        self.target_edit.setText(folder)
        self._sync_path_tooltips()
        self._save_settings()
        self.scan_target_files()

    def clear_list(self):
        if self._is_busy():
            return
        self._clear_scan_queues()
        self.reference_list.clear()
        self.file_list.clear()
        self.reference_table.setRowCount(0)
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self._set_status_text("list_cleared")

    def _clear_scan_queues(self):
        self._reference_row_queue.clear()
        self._target_row_queue.clear()
        self._pending_reference_drop_result = None
        self._pending_target_drop_result = None
        self._pending_reference_scan_result = None
        self._pending_target_scan_result = None
        self._scan_drain_timer.stop()

    def add_reference_paths(self, paths: list[Path]):
        if self._is_busy():
            return
        first_dir = self._first_source_dir(paths)
        if first_dir is not None:
            self.reference_edit.setText(str(first_dir))
            self._sync_path_tooltips()
            self._save_settings()

        existing = {_safe_resolve(item.path) for item in self.reference_list}
        self.progress.setValue(0)
        self._set_status_text("scanning_reference")

        self._reference_drop_thread = QThread(self)
        self._reference_drop_worker = ReferenceDropScanWorker(
            paths,
            self.include_subdirs_check.isChecked(),
            existing,
        )
        self._reference_drop_worker.moveToThread(self._reference_drop_thread)
        self._reference_drop_thread.started.connect(self._reference_drop_worker.run)
        self._reference_drop_worker.row_ready.connect(self._queue_reference_row)
        self._reference_drop_worker.finished.connect(self._reference_drop_finished)
        self._reference_drop_worker.finished.connect(self._reference_drop_thread.quit)
        self._reference_drop_worker.finished.connect(self._reference_drop_worker.deleteLater)
        self._reference_drop_thread.finished.connect(self._reference_drop_thread.deleteLater)
        self._reference_drop_thread.finished.connect(self._reference_drop_thread_finished)
        self._reference_drop_thread.start()

    def add_target_paths(self, paths: list[Path]):
        if self._is_busy():
            return
        first_dir = self._first_source_dir(paths)
        if first_dir is not None:
            self.target_edit.setText(str(first_dir))
            self._sync_path_tooltips()
            self._save_settings()

        existing = {_safe_resolve(item.path) for item in self.file_list}
        self.progress.setValue(0)
        self._set_status_text("scanning_target")

        self._target_drop_thread = QThread(self)
        self._target_drop_worker = TargetDropScanWorker(
            paths,
            self.include_subdirs_check.isChecked(),
            existing,
        )
        self._target_drop_worker.moveToThread(self._target_drop_thread)
        self._target_drop_thread.started.connect(self._target_drop_worker.run)
        self._target_drop_worker.row_ready.connect(self._queue_target_row)
        self._target_drop_worker.finished.connect(self._target_drop_finished)
        self._target_drop_worker.finished.connect(self._target_drop_thread.quit)
        self._target_drop_worker.finished.connect(self._target_drop_worker.deleteLater)
        self._target_drop_thread.finished.connect(self._target_drop_thread.deleteLater)
        self._target_drop_thread.finished.connect(self._target_drop_thread_finished)
        self._target_drop_thread.start()

    def scan_files(self):
        if self._is_busy():
            return
        started = False
        if self.require_reference_match_check.isChecked():
            reference_dir_text = self.reference_edit.text().strip()
            if reference_dir_text:
                reference_dir = Path(reference_dir_text)
                if reference_dir.is_dir():
                    self._start_reference_scan(reference_dir)
                    started = True

        target_dir_text = self.target_edit.text().strip()
        if target_dir_text:
            target_dir = Path(target_dir_text)
            if target_dir.is_dir():
                self._start_target_scan(target_dir)
                started = True

        if not started:
            self._notify(self.tr("invalid_folder_title"), self.tr("invalid_target_content"), is_error=True)

    def scan_reference_files(self, notify_invalid: bool = True) -> bool:
        if self._is_busy():
            return False
        reference_dir_text = self.reference_edit.text().strip()
        if not reference_dir_text:
            if notify_invalid:
                self._notify(self.tr("invalid_folder_title"), self.tr("invalid_reference_content"), is_error=True)
            return False
        reference_dir = Path(reference_dir_text)
        if not reference_dir.is_dir():
            if notify_invalid:
                self._notify(self.tr("invalid_folder_title"), self.tr("invalid_reference_content"), is_error=True)
            return False

        self._start_reference_scan(reference_dir)
        return True

    def scan_target_files(self, notify_invalid: bool = True) -> bool:
        if self._is_busy():
            return False
        target_dir_text = self.target_edit.text().strip()
        if not target_dir_text:
            if notify_invalid:
                self._notify(self.tr("invalid_folder_title"), self.tr("invalid_target_content"), is_error=True)
            return False
        target_dir = Path(target_dir_text)
        if not target_dir.is_dir():
            if notify_invalid:
                self._notify(self.tr("invalid_folder_title"), self.tr("invalid_target_content"), is_error=True)
            return False

        self._start_target_scan(target_dir)
        return True

    def _start_reference_scan(self, reference_dir: Path):
        self.reference_list.clear()
        self.reference_table.setRowCount(0)
        self._reference_row_queue.clear()
        self._pending_reference_scan_result = None
        self._pending_reference_drop_result = None
        self.progress.setValue(0)
        self._set_status_text("scanning_reference")
        self._save_settings()

        self._reference_scan_thread = QThread(self)
        self._reference_scan_worker = ReferenceScanWorker([reference_dir], self.include_subdirs_check.isChecked())
        self._reference_scan_worker.moveToThread(self._reference_scan_thread)
        self._reference_scan_thread.started.connect(self._reference_scan_worker.run)
        self._reference_scan_worker.row_ready.connect(self._queue_reference_row)
        self._reference_scan_worker.finished.connect(self._reference_scan_finished)
        self._reference_scan_worker.finished.connect(self._reference_scan_thread.quit)
        self._reference_scan_worker.finished.connect(self._reference_scan_worker.deleteLater)
        self._reference_scan_thread.finished.connect(self._reference_scan_thread.deleteLater)
        self._reference_scan_thread.finished.connect(self._reference_scan_thread_finished)
        self._reference_scan_thread.start()

    def _start_target_scan(self, target_dir: Path):
        self.file_list.clear()
        self.table.setRowCount(0)
        self._target_row_queue.clear()
        self._pending_target_scan_result = None
        self._pending_target_drop_result = None
        self.progress.setValue(0)
        self._set_status_text("scanning_target")
        self._save_settings()

        self._target_scan_thread = QThread(self)
        self._target_scan_worker = TargetScanWorker([target_dir], self.include_subdirs_check.isChecked())
        self._target_scan_worker.moveToThread(self._target_scan_thread)
        self._target_scan_thread.started.connect(self._target_scan_worker.run)
        self._target_scan_worker.row_ready.connect(self._queue_target_row)
        self._target_scan_worker.finished.connect(self._target_scan_finished)
        self._target_scan_worker.finished.connect(self._target_scan_thread.quit)
        self._target_scan_worker.finished.connect(self._target_scan_worker.deleteLater)
        self._target_scan_thread.finished.connect(self._target_scan_thread.deleteLater)
        self._target_scan_thread.finished.connect(self._target_scan_thread_finished)
        self._target_scan_thread.start()

    def _append_reference_row(self, item: ReferenceItem):
        self.reference_list.append(item)
        row = self.reference_table.rowCount()
        self.reference_table.insertRow(row)
        self.reference_table.setItem(row, 0, QTableWidgetItem(str(item.rel_path)))
        self.reference_table.setItem(row, 1, QTableWidgetItem(_format_timestamp(item.timestamp)))
        self.reference_table.setItem(row, 2, QTableWidgetItem(self.tr(item.source)))

    def _append_target_row(self, item: RenameItem):
        self.file_list.append(item)
        self._append_target_table_row(item)

    def _append_target_table_row(self, item: RenameItem):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(item.rel_path)))
        self.table.setItem(row, 1, QTableWidgetItem(self._target_match_text(item)))
        self.table.setItem(row, 2, QTableWidgetItem(_format_timestamp(item.timestamp)))
        self.table.setItem(row, 3, QTableWidgetItem(item.target_name or self.tr("target_unknown")))
        self.table.setItem(row, 4, QTableWidgetItem(self._display_status(item.status)))

    def _queue_reference_row(self, item: ReferenceItem):
        self._reference_row_queue.append(item)
        self._ensure_scan_drain_timer()

    def _queue_target_row(self, item: RenameItem):
        self._target_row_queue.append(item)
        self._ensure_scan_drain_timer()

    def _ensure_scan_drain_timer(self):
        if not self._scan_drain_timer.isActive():
            self._scan_drain_timer.start()

    def _drain_scan_rows(self):
        reference_items: list[ReferenceItem] = []
        while self._reference_row_queue and len(reference_items) < SCAN_ROW_DRAIN_COUNT:
            reference_items.append(self._reference_row_queue.popleft())
        if reference_items:
            self.reference_table.setUpdatesEnabled(False)
            try:
                for item in reference_items:
                    self._append_reference_row(item)
            finally:
                self.reference_table.setUpdatesEnabled(True)

        target_items: list[RenameItem] = []
        while self._target_row_queue and len(target_items) < SCAN_ROW_DRAIN_COUNT:
            target_items.append(self._target_row_queue.popleft())
        if target_items:
            self.table.setUpdatesEnabled(False)
            try:
                for item in target_items:
                    self._append_target_row(item)
            finally:
                self.table.setUpdatesEnabled(True)
                self.table.viewport().update()

        if self._reference_row_queue or self._target_row_queue:
            return

        self._scan_drain_timer.stop()
        if self._pending_reference_drop_result is not None:
            result = self._pending_reference_drop_result
            self._pending_reference_drop_result = None
            self._apply_reference_drop_finished(result)
        if self._pending_target_drop_result is not None:
            result = self._pending_target_drop_result
            self._pending_target_drop_result = None
            self._apply_target_drop_finished(result)
        if self._pending_reference_scan_result is not None:
            result = self._pending_reference_scan_result
            self._pending_reference_scan_result = None
            self._apply_reference_scan_finished(result)
        if self._pending_target_scan_result is not None:
            result = self._pending_target_scan_result
            self._pending_target_scan_result = None
            self._apply_target_scan_finished(result)

    def _rebuild_reference_table(self):
        self.reference_table.setRowCount(0)
        for item in self.reference_list:
            self._append_reference_row_without_append(item)

    def _append_reference_row_without_append(self, item: ReferenceItem):
        row = self.reference_table.rowCount()
        self.reference_table.insertRow(row)
        self.reference_table.setItem(row, 0, QTableWidgetItem(str(item.rel_path)))
        self.reference_table.setItem(row, 1, QTableWidgetItem(_format_timestamp(item.timestamp)))
        self.reference_table.setItem(row, 2, QTableWidgetItem(self.tr(item.source)))

    def _rebuild_target_table(self):
        self.table.setRowCount(0)
        for item in self.file_list:
            self._append_target_table_row(item)

    def _reference_drop_finished(self, added: int):
        self._pending_reference_drop_result = added
        self._ensure_scan_drain_timer()

    def _apply_reference_drop_finished(self, added: int):
        self._refresh_target_matches()
        if added:
            self.progress.setValue(0)
            self._set_status_text("reference_drop_added", added=added, count=len(self.reference_list))
        else:
            self._set_status_text("drop_no_new")

    def _target_drop_finished(self, added: int):
        self._pending_target_drop_result = added
        self._ensure_scan_drain_timer()

    def _apply_target_drop_finished(self, added: int):
        self._refresh_target_matches()
        if added:
            self.progress.setValue(0)
            self._set_status_text("target_drop_added", added=added, count=len(self.file_list))
        else:
            self._set_status_text("drop_no_new")

    def _reference_drop_thread_finished(self):
        self._reference_drop_worker = None
        self._reference_drop_thread = None

    def _target_drop_thread_finished(self):
        self._target_drop_worker = None
        self._target_drop_thread = None

    def _reference_scan_thread_finished(self):
        self._reference_scan_worker = None
        self._reference_scan_thread = None

    def _target_scan_thread_finished(self):
        self._target_scan_worker = None
        self._target_scan_thread = None

    def _reference_scan_finished(self, count: int):
        self._pending_reference_scan_result = count
        self._ensure_scan_drain_timer()

    def _apply_reference_scan_finished(self, count: int):
        self._refresh_target_matches()
        if count == 0:
            self._set_status_text("scan_reference_none_status")
            return
        self._set_status_text("scan_reference_done_status", count=count)

    def _target_scan_finished(self, count: int):
        self._pending_target_scan_result = count
        self._ensure_scan_drain_timer()

    def _apply_target_scan_finished(self, count: int):
        self._refresh_target_matches()
        if count == 0:
            self._set_status_text("scan_target_none_status")
            return
        self._set_status_text("scan_target_done_status", count=count)

    def _refresh_target_matches(self):
        require_match = self.require_reference_match_check.isChecked()
        prefixes = self._prefix_config()
        index = _build_reference_index(self.reference_list) if require_match else ReferenceIndex({}, {}, {})
        for item in self.file_list:
            previous_status = item.status
            if (
                previous_status in COMPLETED_STATUSES
                and item.timestamp is not None
                and _is_generated_target_name(item.path, item.timestamp, prefixes)
            ):
                item.status = previous_status
                continue

            matched = _find_reference_match(item, index) if require_match else None
            if matched is not None:
                item.timestamp = matched.timestamp
                item.source = "source_reference"
                item.match_mode = "reference"
                item.matched_reference = str(matched.rel_path)
            elif require_match:
                if item.own_timestamp is not None and _is_generated_target_name(item.path, item.own_timestamp, prefixes):
                    item.timestamp = item.own_timestamp
                    item.source = item.own_source
                    item.match_mode = "self"
                    item.matched_reference = ""
                    item.status = "status_already_named"
                else:
                    item.timestamp = None
                    item.source = "source_unknown"
                    item.match_mode = "none"
                    item.matched_reference = ""
                    item.status = "status_no_reference_match"
                continue
            else:
                item.timestamp = item.own_timestamp
                item.source = item.own_source
                item.match_mode = "self" if item.own_timestamp is not None else "none"
                item.matched_reference = ""
                if item.own_timestamp is None:
                    item.status = "status_skipped"
                    continue

            if item.timestamp is None:
                item.status = "status_skipped"
            elif previous_status in COMPLETED_STATUSES and _is_generated_target_name(item.path, item.timestamp, prefixes):
                item.status = previous_status
            elif _is_generated_target_name(item.path, item.timestamp, prefixes):
                item.status = "status_already_named"
            else:
                item.status = "status_pending"
        _assign_target_paths(self.file_list, prefixes)
        self._rebuild_target_table()

    def start_processing(self):
        if self._is_busy():
            return
        if not self.file_list:
            self._notify(self.tr("cannot_start_title"), self.tr("cannot_start_content"), is_error=True)
            return

        processable_statuses = (
            TIMESTAMP_PROCESSABLE_STATUSES if self.write_timestamps_check.isChecked() else PROCESSABLE_STATUSES
        )
        pending_items: list[RenameItem] = []
        for row, item in enumerate(self.file_list):
            if item.status not in processable_statuses:
                continue
            item_for_run = copy.copy(item)
            item_for_run.row_index = row
            pending_items.append(item_for_run)

        if not pending_items:
            self._notify(self.tr("no_pending_title"), self.tr("no_pending_content"), is_error=True)
            return

        self._process_update_queue.clear()
        self._pending_process_result = None
        self._process_drain_timer.stop()
        self.is_processing = True
        self.table.setUpdatesEnabled(False)
        for button in (
            self.btn_start,
            self.btn_scan_reference,
            self.btn_scan_target,
            self.btn_scan,
            self.btn_clear,
        ):
            button.setEnabled(False)
        self.progress.setValue(0)
        self._set_status_text("preparing")
        self._save_settings()

        self._process_thread = QThread(self)
        self._process_worker = ProcessWorker(
            pending_items,
            write_timestamps=self.write_timestamps_check.isChecked(),
            prefixes=self._prefix_config(),
        )
        self._process_worker.moveToThread(self._process_thread)
        self._process_thread.started.connect(self._process_worker.run, Qt.ConnectionType.QueuedConnection)
        self._process_worker.row_update_batch.connect(self._queue_process_updates, Qt.ConnectionType.QueuedConnection)
        self._process_worker.progress_update.connect(self._update_progress, Qt.ConnectionType.QueuedConnection)
        self._process_worker.finished.connect(self._processing_finished, Qt.ConnectionType.QueuedConnection)
        self._process_worker.finished.connect(self._process_thread.quit)
        self._process_worker.finished.connect(self._process_worker.deleteLater)
        self._process_thread.finished.connect(self._process_thread.deleteLater)
        self._process_thread.start()

    def _queue_process_updates(self, updates: list[tuple[int, str, object]]):
        self._process_update_queue.extend(updates)
        if not self.is_processing and not self._process_drain_timer.isActive():
            self._process_drain_timer.start()

    def _drain_process_updates(self):
        updates: list[tuple[int, str, object]] = []
        while self._process_update_queue and len(updates) < PROCESS_UPDATE_DRAIN_COUNT:
            updates.append(self._process_update_queue.popleft())

        if updates:
            self.table.setUpdatesEnabled(False)
            try:
                for row, status_text, target_path_obj in updates:
                    self._update_row_status(row, status_text, target_path_obj, update_table=True)
            finally:
                if not self.is_processing:
                    self.table.setUpdatesEnabled(True)
                    self.table.viewport().update()

        if self._process_update_queue:
            return

        self._process_drain_timer.stop()
        if self._pending_process_result is not None:
            result = self._pending_process_result
            self._pending_process_result = None
            self._apply_processing_finished(result)

    def _update_row_status(self, row: int, status_text: str, target_path_obj: object, update_table: bool = True):
        if not (0 <= row < self.table.rowCount()):
            return

        if 0 <= row < len(self.file_list):
            item = self.file_list[row]
            item.status = status_text
            if target_path_obj is not None:
                target_path = Path(target_path_obj)
                item.target_path = target_path
                item.target_name = target_path.name
                if status_text in (
                    "status_renamed",
                    "status_renamed_timestamped",
                    "status_already_named",
                    "status_timestamped",
                ):
                    item.path = target_path
                    item.rel_path = _relative_path(target_path, item.source_root)

        if not update_table:
            return
        status_item = self.table.item(row, 4)
        if status_item is None:
            self.table.setItem(row, 4, QTableWidgetItem(self._display_status(status_text)))
        else:
            status_item.setText(self._display_status(status_text))

    def _update_progress(self, percent: int, text: str):
        self.progress.setValue(percent)
        self.status.setText(self._display_progress_text(text))

    def _processing_finished(self, result: dict):
        self._pending_process_result = result
        self.is_processing = False
        if not self._process_drain_timer.isActive():
            self._process_drain_timer.start()

    def _apply_processing_finished(self, result: dict):
        self.table.setUpdatesEnabled(True)
        self.table.viewport().update()
        for button in (
            self.btn_start,
            self.btn_scan_reference,
            self.btn_scan_target,
            self.btn_scan,
            self.btn_clear,
        ):
            button.setEnabled(True)
        self.progress.setValue(100)
        self._set_status_text(
            "task_done_status",
            success=result["success"],
            failed=result["failed"],
            skipped=result["skipped"],
        )
        QMessageBox.information(
            self,
            self.tr("task_done_title"),
            self.tr(
                "task_done_message",
                success=result["success"],
                failed=result["failed"],
                skipped=result["skipped"],
            ),
        )
        self._notify(self.tr("task_done_title"), self.tr("process_done_notice", count=result["success"]))


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 10))
    setThemeColor("#1677FF")
    setTheme(Theme.LIGHT)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
