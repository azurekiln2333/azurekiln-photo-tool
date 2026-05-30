from __future__ import annotations

import copy
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from qframelesswindow import FramelessMainWindow, StandardTitleBar

from PyQt6.QtCore import QEvent, QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
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


def _get_settings_path() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME / "settings.json"
    return Path.home() / ".config" / APP_NAME / "settings.json"


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
    return _key_text(str(_relative_path(path, source_root).with_suffix("")))


def _stem_key(path: Path) -> str:
    return path.stem.casefold()


def _target_prefix_for(path: Path) -> str:
    return "VID" if path.suffix.lower() in VIDEO_RENAME_SUFFIXES else "IMG"


def _target_stem(path: Path, timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime(f"{_target_prefix_for(path)}_%Y%m%d_%H%M%S")


def _target_filename(path: Path, timestamp: float, index: int = 0) -> str:
    stem = _target_stem(path, timestamp)
    if index:
        stem = f"{stem}_{index:03d}"
    return f"{stem}{path.suffix.lower()}"


def _is_generated_target_name(path: Path, timestamp: float) -> bool:
    expected_stem = _target_stem(path, timestamp)
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


def _iter_rename_paths(paths: list[Path], recursive: bool) -> list[tuple[Path, Path | None]]:
    files: list[tuple[Path, Path | None]] = []
    for path in paths:
        if path.is_file():
            if _is_supported_rename_file(path):
                files.append((path, path.parent))
            continue
        if not path.is_dir():
            continue
        iterator = path.rglob("*") if recursive else path.glob("*")
        files.extend((candidate, path) for candidate in iterator if _is_supported_rename_file(candidate))
    return files


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
    if key in duplicates:
        return
    if key in mapping:
        duplicates.add(key)
        mapping.pop(key, None)
        return
    mapping[key] = item


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


def _unique_target_path(item: RenameItem, reserved: set[Path]) -> Path | None:
    if item.timestamp is None:
        return None
    if _is_generated_target_name(item.path, item.timestamp):
        return item.path

    for index in range(10000):
        candidate = item.path.with_name(_target_filename(item.path, item.timestamp, index))
        resolved = _safe_resolve(candidate)
        if resolved in reserved:
            continue
        if candidate.exists() and not _is_same_path(candidate, item.path):
            continue
        return candidate
    raise RuntimeError("could not allocate a unique target filename")


def _assign_target_paths(items: list[RenameItem]) -> None:
    reserved: set[Path] = set()
    for item in items:
        target_path = _unique_target_path(item, reserved)
        item.target_path = target_path
        item.target_name = target_path.name if target_path is not None else ""
        if target_path is not None:
            reserved.add(_safe_resolve(target_path))


class ReferenceScanWorker(QObject):
    row_ready = pyqtSignal(object)
    finished = pyqtSignal(int)

    def __init__(self, paths: list[Path], recursive: bool):
        super().__init__()
        self.paths = paths
        self.recursive = recursive

    def run(self):
        seen: set[Path] = set()
        items: list[ReferenceItem] = []
        for file_path, source_root in _iter_rename_paths(self.paths, self.recursive):
            resolved = _safe_resolve(file_path)
            if resolved in seen:
                continue
            seen.add(resolved)
            items.append(_make_reference_item(file_path, source_root))

        for item in sorted(items, key=lambda value: str(value.rel_path)):
            self.row_ready.emit(item)

        self.finished.emit(len(items))


class TargetScanWorker(QObject):
    row_ready = pyqtSignal(object)
    finished = pyqtSignal(int)

    def __init__(self, paths: list[Path], recursive: bool):
        super().__init__()
        self.paths = paths
        self.recursive = recursive

    def run(self):
        seen: set[Path] = set()
        items: list[RenameItem] = []
        for file_path, source_root in _iter_rename_paths(self.paths, self.recursive):
            resolved = _safe_resolve(file_path)
            if resolved in seen:
                continue
            seen.add(resolved)
            items.append(_make_target_item(file_path, source_root))

        for item in sorted(items, key=lambda value: str(value.rel_path)):
            self.row_ready.emit(item)

        self.finished.emit(len(items))


class ProcessWorker(QObject):
    row_update = pyqtSignal(int, str, object)
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, items: list[RenameItem], write_timestamps: bool = False):
        super().__init__()
        self.items = items
        self.write_timestamps = write_timestamps

    def run(self):
        success = 0
        failed = 0
        skipped = 0
        total = len(self.items)
        _assign_target_paths(self.items)

        for index, item in enumerate(self.items):
            row_index = item.row_index if item.row_index >= 0 else index
            progress_percent = int(((index + 1) / total) * 100) if total else 0
            target_path = item.target_path

            if item.timestamp is None or target_path is None:
                skipped += 1
                status = item.status if item.status == "status_no_reference_match" else "status_skipped"
                self.row_update.emit(row_index, status, None)
                self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")
                continue

            if _is_same_path(item.path, target_path):
                try:
                    if self.write_timestamps:
                        apply_file_times_only(item.path, item.timestamp)
                        self.row_update.emit(row_index, "status_timestamped", target_path)
                    else:
                        self.row_update.emit(row_index, "status_already_named", target_path)
                    skipped += 1
                except Exception as exc:
                    failed += 1
                    self.row_update.emit(row_index, f"status_failed|{str(exc)[:36]}", target_path)
                self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")
                continue

            self.row_update.emit(row_index, "status_renaming", target_path)
            try:
                item.path.rename(target_path)
                if self.write_timestamps:
                    apply_file_times_only(target_path, item.timestamp)
                item.path = target_path
                item.rel_path = _relative_path(target_path, item.source_root)
                item.target_name = target_path.name
                success += 1
                status = "status_renamed_timestamped" if self.write_timestamps else "status_renamed"
                self.row_update.emit(row_index, status, target_path)
            except Exception as exc:
                failed += 1
                self.row_update.emit(row_index, f"status_failed|{str(exc)[:36]}", target_path)

            self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")

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
        self.is_processing = False
        self._reference_scan_thread: QThread | None = None
        self._reference_scan_worker: ReferenceScanWorker | None = None
        self._target_scan_thread: QThread | None = None
        self._target_scan_worker: TargetScanWorker | None = None
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

        path_card = CardWidget(self)
        path_layout = QVBoxLayout(path_card)
        path_layout.setContentsMargins(16, 14, 16, 14)
        path_layout.setSpacing(10)

        reference_row = QHBoxLayout()
        reference_row.setSpacing(10)
        self.reference_label = BodyLabel(self.tr("reference_dir"), self)
        self.reference_edit = LineEdit(self)
        self.reference_edit.setReadOnly(False)
        self.reference_edit.setPlaceholderText(self.tr("reference_placeholder"))
        self.btn_reference = PushButton(self.tr("choose_reference"), self)
        self.btn_reference.setIcon(_pick_icon("FOLDER", "FOLDER_ADD"))
        self.btn_reference.clicked.connect(self.browse_reference)
        reference_row.addWidget(self.reference_label)
        reference_row.addWidget(self.reference_edit, 1)
        reference_row.addWidget(self.btn_reference)

        target_row = QHBoxLayout()
        target_row.setSpacing(10)
        self.target_label = BodyLabel(self.tr("target_dir"), self)
        self.target_edit = LineEdit(self)
        self.target_edit.setReadOnly(False)
        self.target_edit.setPlaceholderText(self.tr("target_placeholder"))
        self.btn_target = PushButton(self.tr("choose_target"), self)
        self.btn_target.setIcon(_pick_icon("FOLDER", "FOLDER_ADD"))
        self.btn_target.clicked.connect(self.browse_target)
        target_row.addWidget(self.target_label)
        target_row.addWidget(self.target_edit, 1)
        target_row.addWidget(self.btn_target)

        path_layout.addLayout(reference_row)
        path_layout.addLayout(target_row)

        option_card = CardWidget(self)
        option_layout = QVBoxLayout(option_card)
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

        quick_option_row = QHBoxLayout()
        quick_option_row.setSpacing(12)
        self.quick_require_reference_match_check = CheckBox(self.tr("require_reference_match"), self)
        self.quick_require_reference_match_check.setChecked(self.require_reference_match_check.isChecked())
        self.quick_require_reference_match_check.toggled.connect(self._on_quick_require_reference_match_changed)
        self.quick_write_timestamps_check = CheckBox(self.tr("write_timestamps"), self)
        self.quick_write_timestamps_check.setChecked(self.write_timestamps_check.isChecked())
        self.quick_write_timestamps_check.toggled.connect(self._on_quick_write_timestamps_changed)
        quick_option_row.addStretch(1)
        quick_option_row.addWidget(self.quick_require_reference_match_check)
        quick_option_row.addWidget(self.quick_write_timestamps_check)
        if self._embedded:
            path_layout.addLayout(quick_option_row)
        else:
            self.quick_require_reference_match_check.hide()
            self.quick_write_timestamps_check.hide()

        tables_layout = QHBoxLayout()
        tables_layout.setSpacing(12)

        reference_card = CardWidget(self)
        reference_layout = QVBoxLayout(reference_card)
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
        target_layout.addLayout(target_hint_row)
        target_layout.addWidget(self.table)

        tables_layout.addWidget(reference_card, 1)
        tables_layout.addWidget(target_card, 1)

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
        outer.addWidget(path_card)
        if not self._embedded:
            outer.addWidget(option_card)
        outer.addLayout(tables_layout, 1)
        outer.addWidget(action_card)
        outer.addWidget(foot_card)

        self._init_default_dirs()
        self._load_settings()
        self._apply_language()
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

    def _init_default_dirs(self):
        pics_dir = _get_windows_pictures_dir() or (Path.home() / "Pictures")
        self.reference_edit.clear()
        self.target_edit.setText(str(pics_dir))
        self._set_status_text("waiting_source")

    def _settings_payload(self) -> dict:
        return {
            "language": self.lang,
            "reference_dir": self.reference_edit.text().strip(),
            "target_dir": self.target_edit.text().strip(),
            "include_subdirs": self.include_subdirs_check.isChecked(),
            "require_reference_match": self.require_reference_match_check.isChecked(),
            "write_timestamps": self.write_timestamps_check.isChecked(),
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
            self._sync_quick_options()
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

    def _on_match_option_changed(self, _checked: bool):
        self._sync_quick_options()
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
        self.include_subdirs_check.setText(self.tr("scan_subdirs"))
        self.require_reference_match_check.setText(self.tr("require_reference_match"))
        self.write_timestamps_check.setText(self.tr("write_timestamps"))
        self.quick_require_reference_match_check.setText(self.tr("require_reference_match"))
        self.quick_write_timestamps_check.setText(self.tr("write_timestamps"))
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
        self._save_settings()
        self.scan_reference_files()

    def browse_target(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("choose_target"))
        if not folder:
            return
        self.target_edit.setText(folder)
        self._save_settings()
        self.scan_target_files()

    def clear_list(self):
        if self.is_processing:
            return
        self.reference_list.clear()
        self.file_list.clear()
        self.reference_table.setRowCount(0)
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self._set_status_text("list_cleared")

    def add_reference_paths(self, paths: list[Path]):
        if self.is_processing:
            return
        first_dir = self._first_source_dir(paths)
        if first_dir is not None:
            self.reference_edit.setText(str(first_dir))
            self._save_settings()

        existing = {_safe_resolve(item.path) for item in self.reference_list}
        new_items: list[ReferenceItem] = []
        for file_path, source_root in _iter_rename_paths(paths, self.include_subdirs_check.isChecked()):
            resolved = _safe_resolve(file_path)
            if resolved in existing:
                continue
            new_items.append(_make_reference_item(file_path, source_root))
            existing.add(resolved)

        if new_items:
            new_items.sort(key=lambda value: str(value.rel_path))
            self.reference_list.extend(new_items)
            self._rebuild_reference_table()
            self._refresh_target_matches()
            self.progress.setValue(0)
            self._set_status_text("reference_drop_added", added=len(new_items), count=len(self.reference_list))
        else:
            self._set_status_text("drop_no_new")

    def add_target_paths(self, paths: list[Path]):
        if self.is_processing:
            return
        first_dir = self._first_source_dir(paths)
        if first_dir is not None:
            self.target_edit.setText(str(first_dir))
            self._save_settings()

        existing = {_safe_resolve(item.path) for item in self.file_list}
        new_items: list[RenameItem] = []
        for file_path, source_root in _iter_rename_paths(paths, self.include_subdirs_check.isChecked()):
            resolved = _safe_resolve(file_path)
            if resolved in existing:
                continue
            new_items.append(_make_target_item(file_path, source_root))
            existing.add(resolved)

        if new_items:
            new_items.sort(key=lambda value: str(value.rel_path))
            self.file_list.extend(new_items)
            self._refresh_target_matches()
            self.progress.setValue(0)
            self._set_status_text("target_drop_added", added=len(new_items), count=len(self.file_list))
        else:
            self._set_status_text("drop_no_new")

    def scan_files(self):
        if self.is_processing:
            return
        started = False
        reference_dir_text = self.reference_edit.text().strip()
        if reference_dir_text:
            started = self.scan_reference_files(notify_invalid=False) or started
        started = self.scan_target_files(notify_invalid=False) or started
        if not started:
            self._notify(self.tr("invalid_folder_title"), self.tr("invalid_target_content"), is_error=True)

    def scan_reference_files(self, notify_invalid: bool = True) -> bool:
        if self.is_processing:
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

        self.reference_list.clear()
        self.reference_table.setRowCount(0)
        self.progress.setValue(0)
        self._set_status_text("scanning_reference")
        self._save_settings()

        self._reference_scan_thread = QThread(self)
        self._reference_scan_worker = ReferenceScanWorker([reference_dir], self.include_subdirs_check.isChecked())
        self._reference_scan_worker.moveToThread(self._reference_scan_thread)
        self._reference_scan_thread.started.connect(self._reference_scan_worker.run)
        self._reference_scan_worker.row_ready.connect(self._append_reference_row)
        self._reference_scan_worker.finished.connect(self._reference_scan_finished)
        self._reference_scan_worker.finished.connect(self._reference_scan_thread.quit)
        self._reference_scan_worker.finished.connect(self._reference_scan_worker.deleteLater)
        self._reference_scan_thread.finished.connect(self._reference_scan_thread.deleteLater)
        self._reference_scan_thread.start()
        return True

    def scan_target_files(self, notify_invalid: bool = True) -> bool:
        if self.is_processing:
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

        self.file_list.clear()
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self._set_status_text("scanning_target")
        self._save_settings()

        self._target_scan_thread = QThread(self)
        self._target_scan_worker = TargetScanWorker([target_dir], self.include_subdirs_check.isChecked())
        self._target_scan_worker.moveToThread(self._target_scan_thread)
        self._target_scan_thread.started.connect(self._target_scan_worker.run)
        self._target_scan_worker.row_ready.connect(self._append_target_row)
        self._target_scan_worker.finished.connect(self._target_scan_finished)
        self._target_scan_worker.finished.connect(self._target_scan_thread.quit)
        self._target_scan_worker.finished.connect(self._target_scan_worker.deleteLater)
        self._target_scan_thread.finished.connect(self._target_scan_thread.deleteLater)
        self._target_scan_thread.start()
        return True

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

    def _reference_scan_finished(self, count: int):
        self._refresh_target_matches()
        if count == 0:
            self._set_status_text("scan_reference_none_status")
            return
        self._set_status_text("scan_reference_done_status", count=count)

    def _target_scan_finished(self, count: int):
        self._refresh_target_matches()
        if count == 0:
            self._set_status_text("scan_target_none_status")
            return
        self._set_status_text("scan_target_done_status", count=count)

    def _refresh_target_matches(self):
        index = _build_reference_index(self.reference_list)
        require_match = self.require_reference_match_check.isChecked()
        for item in self.file_list:
            previous_status = item.status
            if (
                previous_status in COMPLETED_STATUSES
                and item.timestamp is not None
                and _is_generated_target_name(item.path, item.timestamp)
            ):
                item.status = previous_status
                continue

            matched = _find_reference_match(item, index)
            if matched is not None:
                item.timestamp = matched.timestamp
                item.source = "source_reference"
                item.match_mode = "reference"
                item.matched_reference = str(matched.rel_path)
            elif require_match:
                if item.own_timestamp is not None and _is_generated_target_name(item.path, item.own_timestamp):
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
            elif previous_status in COMPLETED_STATUSES and _is_generated_target_name(item.path, item.timestamp):
                item.status = previous_status
            elif _is_generated_target_name(item.path, item.timestamp):
                item.status = "status_already_named"
            else:
                item.status = "status_pending"
        _assign_target_paths(self.file_list)
        self._rebuild_target_table()

    def start_processing(self):
        if self.is_processing:
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

        self.is_processing = True
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
        )
        self._process_worker.moveToThread(self._process_thread)
        self._process_thread.started.connect(self._process_worker.run)
        self._process_worker.row_update.connect(self._update_row_status)
        self._process_worker.progress_update.connect(self._update_progress)
        self._process_worker.finished.connect(self._processing_finished)
        self._process_worker.finished.connect(self._process_thread.quit)
        self._process_worker.finished.connect(self._process_worker.deleteLater)
        self._process_thread.finished.connect(self._process_thread.deleteLater)
        self._process_thread.start()

    def _update_row_status(self, row: int, status_text: str, target_path_obj: object):
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
                self.table.setItem(row, 0, QTableWidgetItem(str(item.rel_path)))
                self.table.setItem(row, 3, QTableWidgetItem(item.target_name or self.tr("target_unknown")))

        self.table.setItem(row, 4, QTableWidgetItem(self._display_status(status_text)))
        self.table.scrollToItem(self.table.item(row, 4))

    def _update_progress(self, percent: int, text: str):
        self.progress.setValue(percent)
        self.status.setText(self._display_progress_text(text))

    def _processing_finished(self, result: dict):
        self.is_processing = False
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
