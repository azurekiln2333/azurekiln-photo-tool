from __future__ import annotations

import hashlib
import os
import re
import sys
import json
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from qframelesswindow import FramelessMainWindow, StandardTitleBar

from file_context_menu import install_file_context_menu

from PyQt6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QObject, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

try:
    from send2trash import send2trash

    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False

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
    Theme,
    VIDEO_SUFFIXES,
    _get_windows_pictures_dir,
    _safe_resolve,
    setTheme,
    setThemeColor,
    TableView,
)


APP_NAME = "DedupeMediaGUI"
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES + VIDEO_SUFFIXES
HASH_CHUNK_SIZE = 1024 * 1024
ROW_BATCH_SIZE = 100
UI_APPEND_DRAIN_ROWS = 1000
UI_UPDATE_DRAIN_ROWS = 200
RECYCLE_BATCH_SIZE = 25
HASH_THREAD_OPTIONS = (1, 2, 4, 8, 16)
COPY_SUFFIX_RE = re.compile(r"\s*\((\d+)\)$")
TRANSLATIONS = {
    "zh": {
        "app_title": "图片视频去重",
        "header_title": "图片视频去重",
        "header_subtitle": "按文件大小预筛选，再用 SHA-256 校验重复图片和视频",
        "header_note": "重复项会标红；默认移入回收站，勾选永久删除后会直接删除重复文件。",
        "language": "界面语言",
        "source_dir": "扫描目录",
        "source_placeholder": "选择或拖入需要查重的图片/视频目录",
        "choose_source": "选择目录",
        "scan_subdirs": "扫描子目录",
        "permanent_delete": "永久删除",
        "hash_threads": "Hash 线程",
        "drop_hint": "拖入图片、视频或文件夹；同大小文件才会计算完整 SHA-256，提高扫描速度。",
        "table_file": "文件",
        "table_abs_path": "所在目录",
        "table_size": "大小",
        "table_hash": "SHA-256",
        "table_group": "组",
        "table_status": "状态",
        "rescan": "重新扫描",
        "clear_list": "清空列表",
        "start_dedupe": "处理重复文件",
        "waiting_source": "等待选择或拖入文件",
        "scanning": "正在扫描并校验 Hash",
        "scan_none_status": "未找到图片或视频",
        "scan_done_status": "扫描完成：共 {count} 个文件，重复 {duplicates} 个",
        "drop_added": "已添加 {added} 个文件，当前共 {count} 项，重复 {duplicates} 个",
        "drop_no_new": "未添加新文件",
        "list_cleared": "列表已清空",
        "status_unique": "唯一",
        "status_keep": "保留",
        "status_duplicate": "重复",
        "status_processing": "处理中",
        "status_recycled": "已移入回收站",
        "status_deleted": "已永久删除",
        "status_failed": "失败：{error}",
        "missing_trash_title": "缺少回收站支持",
        "missing_trash_content": "当前环境缺少 send2trash，无法移入回收站。请勾选永久删除或安装 send2trash。",
        "cannot_start_title": "无法开始",
        "cannot_start_content": "当前没有重复文件。",
        "confirm_delete_title": "确认永久删除",
        "confirm_delete_content": "将永久删除 {count} 个重复文件，无法从回收站恢复。确定继续？",
        "process_done_title": "处理完成",
        "process_done_status": "处理完成：成功 {success}，失败 {failed}",
        "process_done_message": "重复文件处理完成。\n\n成功: {success}\n失败: {failed}",
    },
    "en": {
        "app_title": "Dedupe Photos and Videos",
        "header_title": "Dedupe Photos and Videos",
        "header_subtitle": "Pre-filter by size, then verify duplicate photos/videos with SHA-256",
        "header_note": "Duplicate rows are highlighted. Files move to recycle bin by default; permanent delete is optional.",
        "language": "Language",
        "source_dir": "Scan folder",
        "source_placeholder": "Choose or drop photos/videos to dedupe",
        "choose_source": "Choose folder",
        "scan_subdirs": "Scan subfolders",
        "permanent_delete": "Permanent delete",
        "hash_threads": "Hash threads",
        "drop_hint": "Drop photos, videos, or folders. Full SHA-256 is calculated only for same-size files.",
        "table_file": "File",
        "table_abs_path": "Folder",
        "table_size": "Size",
        "table_hash": "SHA-256",
        "table_group": "Group",
        "table_status": "Status",
        "rescan": "Rescan",
        "clear_list": "Clear list",
        "start_dedupe": "Process duplicates",
        "waiting_source": "Waiting for files",
        "scanning": "Scanning and hashing",
        "scan_none_status": "No photos or videos found",
        "scan_done_status": "Scan complete: {count} file(s), {duplicates} duplicate(s)",
        "drop_added": "Added {added} file(s), total {count}, {duplicates} duplicate(s)",
        "drop_no_new": "No new files were added",
        "list_cleared": "List cleared",
        "status_unique": "Unique",
        "status_keep": "Keep",
        "status_duplicate": "Duplicate",
        "status_processing": "Processing",
        "status_recycled": "Moved to recycle bin",
        "status_deleted": "Permanently deleted",
        "status_failed": "Failed: {error}",
        "missing_trash_title": "Recycle bin unavailable",
        "missing_trash_content": "send2trash is not available. Enable permanent delete or install send2trash.",
        "cannot_start_title": "Cannot start",
        "cannot_start_content": "There are no duplicate files.",
        "confirm_delete_title": "Confirm permanent delete",
        "confirm_delete_content": "This will permanently delete {count} duplicate file(s). Continue?",
        "process_done_title": "Task complete",
        "process_done_status": "Done: {success} success, {failed} failed",
        "process_done_message": "Duplicate processing complete.\n\nSuccess: {success}\nFailed: {failed}",
    },
}


@dataclass
class DedupeItem:
    scan_id: int
    path: Path
    source_root: Path | None
    rel_path: Path
    size: int
    abs_path: str = ""
    abs_dir: str = ""
    digest: str = ""
    group_id: int = 0
    duplicate: bool = False
    status: str = "status_unique"
    row_index: int = -1


def _pick_icon(*names: str):
    for name in names:
        icon = getattr(FluentIcon, name, None)
        if icon is not None:
            return icon
    return FluentIcon.APPLICATION


def _get_settings_path() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME / "settings.json"
    return Path.home() / ".config" / APP_NAME / "settings.json"


def _is_supported_media(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES


def _relative_path(file_path: Path, source_root: Path | None) -> Path:
    if source_root is not None:
        try:
            return file_path.relative_to(source_root)
        except ValueError:
            pass
    return Path(file_path.name)


def _iter_media_paths(paths: list[Path], recursive: bool):
    for path in paths:
        if path.is_file():
            if _is_supported_media(path):
                yield path, path.parent
            continue
        if not path.is_dir():
            continue
        iterator = path.rglob("*") if recursive else path.glob("*")
        for candidate in iterator:
            if _is_supported_media(candidate):
                yield candidate, path


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while True:
            chunk = file.read(HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _format_size(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def _keeper_sort_key(path: Path):
    match = COPY_SUFFIX_RE.search(path.stem)
    if match:
        base_stem = path.stem[: match.start()]
        copy_index = int(match.group(1))
        copy_rank = 1
    else:
        base_stem = path.stem
        copy_index = 0
        copy_rank = 0
    return (
        str(path.parent).casefold(),
        base_stem.casefold(),
        path.suffix.casefold(),
        copy_rank,
        copy_index,
        path.name.casefold(),
        str(path).casefold(),
    )


def _should_emit_progress(index: int, total: int) -> bool:
    if total <= 100:
        return True
    step = max(1, total // 100)
    return (index + 1) % step == 0 or index + 1 == total


def _default_thread_count() -> int:
    cpu_count = os.cpu_count() or 4
    for option in reversed(HASH_THREAD_OPTIONS):
        if option <= cpu_count:
            return option
    return HASH_THREAD_OPTIONS[0]


def _emit_batch(signal, batch: list[DedupeItem]):
    if batch:
        signal.emit(batch[:])
        batch.clear()


class DedupeTableModel(QAbstractTableModel):
    def __init__(self, items: list[DedupeItem], display_status, headers: list[str], parent=None):
        super().__init__(parent)
        self.items = items
        self.display_status = display_status
        self.headers = headers
        self.duplicate_bg = QBrush(QColor("#FEF3F2"))
        self.duplicate_fg = QBrush(QColor("#B42318"))

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else 6

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.items)):
            return None
        item = self.items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_value(item, index.column())
        if role == Qt.ItemDataRole.ToolTipRole:
            return item.abs_path or str(_safe_resolve(item.path))
        if role == Qt.ItemDataRole.BackgroundRole and item.duplicate:
            return self.duplicate_bg
        if role == Qt.ItemDataRole.ForegroundRole and item.duplicate:
            return self.duplicate_fg
        return None

    def _display_value(self, item: DedupeItem, column: int) -> str:
        if column == 0:
            return str(item.rel_path)
        if column == 1:
            return item.abs_dir or str(_safe_resolve(item.path).parent)
        if column == 2:
            return _format_size(item.size)
        if column == 3:
            return item.digest[:16] if item.digest else "-"
        if column == 4:
            return str(item.group_id) if item.group_id else "-"
        if column == 5:
            return self.display_status(item.status)
        return ""

    def set_headers(self, headers: list[str]):
        self.headers = headers
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)

    def clear(self):
        if not self.items:
            return
        self.beginRemoveRows(QModelIndex(), 0, len(self.items) - 1)
        self.items.clear()
        self.endRemoveRows()

    def append_items(self, items: list[DedupeItem]):
        if not items:
            return
        start = len(self.items)
        self.beginInsertRows(QModelIndex(), start, start + len(items) - 1)
        self.items.extend(items)
        self.endInsertRows()

    def reset_items(self, items: list[DedupeItem]):
        self.beginResetModel()
        self.items[:] = items
        self.endResetModel()

    def update_row(self, row: int):
        if not (0 <= row < len(self.items)):
            return
        left = self.index(row, 0)
        right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(
            left,
            right,
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.BackgroundRole,
                Qt.ItemDataRole.ForegroundRole,
            ],
        )


class ScanWorker(QObject):
    row_batch_ready = pyqtSignal(object)
    row_batch_changed = pyqtSignal(object)
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(
        self,
        paths: list[Path],
        recursive: bool,
        thread_count: int,
        existing: set[Path] | None = None,
    ):
        super().__init__()
        self.paths = paths
        self.recursive = recursive
        self.thread_count = max(1, thread_count)
        self.existing = existing or set()

    def run(self):
        seen: set[Path] = set(self.existing)
        by_size: dict[int, list[DedupeItem]] = {}
        scanned = 0
        ready_batch: list[DedupeItem] = []

        for file_path, source_root in _iter_media_paths(self.paths, self.recursive):
            resolved = _safe_resolve(file_path)
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                size = file_path.stat().st_size
            except Exception:
                continue
            item = DedupeItem(
                scan_id=scanned,
                path=file_path,
                source_root=source_root,
                rel_path=_relative_path(file_path, source_root),
                abs_path=str(resolved),
                abs_dir=str(resolved.parent),
                size=size,
            )
            by_size.setdefault(size, []).append(item)
            scanned += 1
            ready_batch.append(item)
            if len(ready_batch) >= ROW_BATCH_SIZE:
                _emit_batch(self.row_batch_ready, ready_batch)
            if scanned % 50 == 0:
                self.progress_update.emit(0, f"scanning|{scanned}")
        _emit_batch(self.row_batch_ready, ready_batch)

        duplicate_groups: list[list[DedupeItem]] = []
        group_id = 1
        hash_candidates = sum(len(items) for items in by_size.values() if len(items) > 1)
        hashed = 0
        changed_batch: list[DedupeItem] = []

        for items in by_size.values():
            if len(items) == 1:
                continue

            by_hash: dict[str, list[DedupeItem]] = {}
            with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
                futures = {executor.submit(_hash_file, item.path): item for item in items}
                completed_hashes = as_completed(futures)
                for future in completed_hashes:
                    item = futures[future]
                    try:
                        item.digest = future.result()
                    except Exception:
                        item.status = "status_failed|hash"
                        changed_batch.append(item)
                        if len(changed_batch) >= ROW_BATCH_SIZE:
                            _emit_batch(self.row_batch_changed, changed_batch)
                        continue

                    by_hash.setdefault(item.digest, []).append(item)
                    changed_batch.append(item)
                    if len(changed_batch) >= ROW_BATCH_SIZE:
                        _emit_batch(self.row_batch_changed, changed_batch)
                    hashed += 1
                    if hash_candidates and _should_emit_progress(hashed - 1, hash_candidates):
                        percent = int((hashed / hash_candidates) * 100)
                        self.progress_update.emit(percent, f"scanning|{scanned}")
            _emit_batch(self.row_batch_changed, changed_batch)

            status_batch: list[DedupeItem] = []
            for hash_items in by_hash.values():
                hash_items.sort(key=lambda value: _keeper_sort_key(value.path))
                if len(hash_items) == 1:
                    continue
                for index, item in enumerate(hash_items):
                    item.group_id = group_id
                    if index == 0:
                        item.status = "status_keep"
                    else:
                        item.duplicate = True
                        item.status = "status_duplicate"
                    status_batch.append(item)
                    if len(status_batch) >= ROW_BATCH_SIZE:
                        _emit_batch(self.row_batch_changed, status_batch)
                duplicate_groups.append(hash_items)
                group_id += 1
            _emit_batch(self.row_batch_changed, status_batch)

        duplicates = sum(1 for group in duplicate_groups for item in group if item.duplicate)
        self.finished.emit({"count": scanned, "duplicates": duplicates})


class ProcessWorker(QObject):
    row_update_batch = pyqtSignal(object)
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, items: list[DedupeItem], permanent: bool):
        super().__init__()
        self.items = items
        self.permanent = permanent

    def _emit_update_batch(self, updates: list[tuple[int, str]]):
        if updates:
            self.row_update_batch.emit(updates[:])
            updates.clear()

    def run(self):
        success = 0
        failed = 0
        total = len(self.items)
        update_batch: list[tuple[int, str]] = []

        if not self.permanent:
            if not HAS_SEND2TRASH:
                failed = total
                for item in self.items:
                    update_batch.append((item.row_index, "status_failed|send2trash"))
                    if len(update_batch) >= ROW_BATCH_SIZE:
                        self._emit_update_batch(update_batch)
                self._emit_update_batch(update_batch)
                self.progress_update.emit(100, f"{total}/{total}")
                self.finished.emit({"success": success, "failed": failed})
                return
            success, failed = self._run_recycle_batches(update_batch)
            self.finished.emit({"success": success, "failed": failed})
            return

        success, failed = self._run_per_item(update_batch)
        self.finished.emit({"success": success, "failed": failed})

    def _emit_process_progress(self, completed: int, total: int):
        percent = int((completed / total) * 100) if total else 0
        self.progress_update.emit(percent, f"{completed}/{total}")

    def _run_recycle_batches(self, update_batch: list[tuple[int, str]]) -> tuple[int, int]:
        success = 0
        failed = 0
        completed = 0
        total = len(self.items)
        self._emit_process_progress(0, total)

        for start in range(0, total, RECYCLE_BATCH_SIZE):
            batch = self.items[start : start + RECYCLE_BATCH_SIZE]
            try:
                send2trash([str(item.path) for item in batch])
                for item in batch:
                    success += 1
                    completed += 1
                    update_batch.append((item.row_index, "status_recycled"))
            except TypeError:
                batch_success, batch_failed, batch_completed = self._run_recycle_items(batch, update_batch)
                success += batch_success
                failed += batch_failed
                completed += batch_completed
            except Exception:
                batch_success, batch_failed, batch_completed = self._run_recycle_items(batch, update_batch)
                success += batch_success
                failed += batch_failed
                completed += batch_completed

            self._emit_update_batch(update_batch)
            self._emit_process_progress(completed, total)

        return success, failed

    def _run_recycle_items(
        self,
        items: list[DedupeItem],
        update_batch: list[tuple[int, str]],
    ) -> tuple[int, int, int]:
        success = 0
        failed = 0
        completed = 0
        for item in items:
            try:
                send2trash(str(item.path))
                update_batch.append((item.row_index, "status_recycled"))
                success += 1
            except Exception as exc:
                update_batch.append((item.row_index, f"status_failed|{str(exc)[:36]}"))
                failed += 1
            completed += 1
        return success, failed, completed

    def _run_per_item(self, update_batch: list[tuple[int, str]]) -> tuple[int, int]:
        success = 0
        failed = 0
        total = len(self.items)
        for index, item in enumerate(self.items):
            try:
                if self.permanent:
                    item.path.unlink()
                    status = "status_deleted"
                else:
                    send2trash(str(item.path))
                    status = "status_recycled"
                success += 1
                update_batch.append((item.row_index, status))
            except Exception as exc:
                failed += 1
                update_batch.append((item.row_index, f"status_failed|{str(exc)[:36]}"))
            if len(update_batch) >= ROW_BATCH_SIZE:
                self._emit_update_batch(update_batch)
            if _should_emit_progress(index, total):
                self._emit_process_progress(index + 1, total)
        self._emit_update_batch(update_batch)
        return success, failed


class MainWindow(FramelessMainWindow):
    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("Dedupe Photos and Videos")
        self._title_bar_height = 36
        if not self._embedded:
            self.resize(1280, 820)
            self._set_blue_title_bar()

        self.lang = DEFAULT_LANGUAGE
        self._last_status_key = "waiting_source"
        self._last_status_kwargs: dict = {}
        self.file_list: list[DedupeItem] = []
        self._row_by_scan_id: dict[int, int] = {}
        self._pending_row_updates: dict[int, DedupeItem] = {}
        self._append_queue: deque[DedupeItem] = deque()
        self._refresh_queue: deque[DedupeItem] = deque()
        self._process_update_queue: deque[tuple[int, str]] = deque()
        self._pending_scan_result: dict | None = None
        self._pending_process_result: dict | None = None
        self._drain_timer = QTimer(self)
        self._drain_timer.setInterval(10)
        self._drain_timer.timeout.connect(self._drain_table_queues)
        self.table_model = DedupeTableModel(self.file_list, self._display_status, self._table_headers(), self)
        self.is_processing = False
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._process_thread: QThread | None = None
        self._process_worker: ProcessWorker | None = None
        self._settings_path = _get_settings_path()
        self._suspend_settings_save = False

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

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.input_label = BodyLabel(self.tr("source_dir"), self)
        self.input_edit = LineEdit(self)
        self.input_edit.setReadOnly(False)
        self.input_edit.setPlaceholderText(self.tr("source_placeholder"))
        self.btn_input = PushButton(self.tr("choose_source"), self)
        self.btn_input.setIcon(_pick_icon("FOLDER", "FOLDER_ADD"))
        self.btn_input.clicked.connect(self.browse_input)
        row1.addWidget(self.input_label)
        row1.addWidget(self.input_edit, 1)
        row1.addWidget(self.btn_input)

        row2 = QHBoxLayout()
        row2.setSpacing(12)
        self.include_subdirs_check = CheckBox(self.tr("scan_subdirs"), self)
        self.include_subdirs_check.setChecked(True)
        self.include_subdirs_check.toggled.connect(self.scan_files)
        self.permanent_delete_check = CheckBox(self.tr("permanent_delete"), self)
        self.permanent_delete_check.setChecked(False)
        self.hash_thread_label = BodyLabel(self.tr("hash_threads"), self)
        self.thread_count_combo = ComboBox(self)
        self.thread_count_combo.setFixedWidth(96)
        for thread_count in HASH_THREAD_OPTIONS:
            self.thread_count_combo.addItem(str(thread_count), userData=thread_count)
        self._set_thread_count(_default_thread_count())
        row2.addWidget(self.include_subdirs_check)
        row2.addWidget(self.permanent_delete_check)
        row2.addWidget(self.hash_thread_label)
        row2.addWidget(self.thread_count_combo)
        row2.addStretch(1)

        path_layout.addLayout(row1)
        path_layout.addLayout(row2)

        table_card = CardWidget(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(10, 10, 10, 10)
        table_layout.setSpacing(8)
        hint_row = QHBoxLayout()
        hint_row.setSpacing(8)
        self.drop_hint = BodyLabel(self.tr("drop_hint"), self)
        self.drop_hint.setStyleSheet("color: #6b7280; padding: 4px 6px;")
        hint_row.addWidget(self.drop_hint)
        hint_row.addStretch(1)

        self.table = TableView(self)
        self.table.setModel(self.table_model)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setWordWrap(False)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setAcceptDrops(True)
        self.table.viewport().setAcceptDrops(True)
        self.table.viewport().installEventFilter(self)
        self.table_context_menu = install_file_context_menu(self.table, self, self._context_file_paths, lambda: self.lang)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(36)
        table_layout.addLayout(hint_row)
        table_layout.addWidget(self.table)

        action_card = CardWidget(self)
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(16, 12, 16, 12)
        action_layout.setSpacing(8)
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        self.btn_scan = PushButton(self.tr("rescan"), self)
        self.btn_scan.setIcon(_pick_icon("SYNC", "UPDATE"))
        self.btn_scan.clicked.connect(self.scan_files)
        self.btn_clear = PushButton(self.tr("clear_list"), self)
        self.btn_clear.setIcon(_pick_icon("DELETE", "REMOVE"))
        self.btn_clear.clicked.connect(self.clear_list)
        self.btn_start = PrimaryPushButton(self.tr("start_dedupe"), self)
        self.btn_start.setIcon(_pick_icon("DELETE", "PLAY", "SEND"))
        self.btn_start.clicked.connect(self.start_processing)
        row3.addWidget(self.btn_scan)
        row3.addWidget(self.btn_clear)
        row3.addStretch(1)
        row3.addWidget(self.btn_start)
        action_layout.addLayout(row3)

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
        outer.addWidget(table_card, 1)
        outer.addWidget(action_card)
        outer.addWidget(foot_card)

        pics_dir = _get_windows_pictures_dir() or (Path.home() / "Pictures")
        self.input_edit.setText(str(pics_dir))
        self._load_settings()
        self._apply_language()
        self.include_subdirs_check.toggled.connect(lambda _checked=False: self._save_settings())
        self.permanent_delete_check.toggled.connect(lambda _checked=False: self._save_settings())
        self.thread_count_combo.currentIndexChanged.connect(lambda _index=0: self._save_settings())

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

    def _table_headers(self) -> list[str]:
        return [
            self.tr("table_file"),
            self.tr("table_abs_path"),
            self.tr("table_size"),
            self.tr("table_hash"),
            self.tr("table_group"),
            self.tr("table_status"),
        ]

    def _display_status(self, status: str) -> str:
        if status.startswith("status_failed|"):
            return self.tr("status_failed", error=status.split("|", 1)[1])
        return self.tr(status)

    def _thread_count(self) -> int:
        value = self.thread_count_combo.currentData()
        return int(value) if value in HASH_THREAD_OPTIONS else _default_thread_count()

    def _set_thread_count(self, thread_count: int):
        if thread_count not in HASH_THREAD_OPTIONS:
            thread_count = _default_thread_count()
        for index in range(self.thread_count_combo.count()):
            if self.thread_count_combo.itemData(index) == thread_count:
                self.thread_count_combo.setCurrentIndex(index)
                return

    def _settings_payload(self) -> dict:
        return {
            "language": self.lang,
            "include_subdirs": self.include_subdirs_check.isChecked(),
            "permanent_delete": self.permanent_delete_check.isChecked(),
            "hash_threads": self._thread_count(),
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
                for index in range(self.language_combo.count()):
                    if self.language_combo.itemData(index) == lang:
                        self.language_combo.setCurrentIndex(index)
                        break
            self.include_subdirs_check.setChecked(bool(data.get("include_subdirs", True)))
            self.permanent_delete_check.setChecked(bool(data.get("permanent_delete", False)))
            self._set_thread_count(int(data.get("hash_threads", _default_thread_count())))
        finally:
            self._suspend_settings_save = False

    def _set_status_text(self, key: str, **kwargs):
        self._last_status_key = key
        self._last_status_kwargs = kwargs
        self.status.setText(self.tr(key, **kwargs))

    def _is_busy(self) -> bool:
        return (
            self.is_processing
            or (self._scan_thread is not None and self._scan_thread.isRunning())
            or (self._process_thread is not None and self._process_thread.isRunning())
            or self._drain_timer.isActive()
            or bool(self._append_queue)
            or bool(self._refresh_queue)
            or bool(self._process_update_queue)
        )

    def _on_language_changed(self, _index: int):
        lang = self.language_combo.currentData()
        if lang in SUPPORTED_LANGUAGES and lang != self.lang:
            self.lang = lang
            self._apply_language()
            self._save_settings()

    def _apply_language(self):
        self.setWindowTitle(self.tr("app_title"))
        self.title_label.setText(self.tr("header_title"))
        self.subtitle_label.setText(self.tr("header_subtitle"))
        self.subtitle_note_label.setText(self.tr("header_note"))
        self.language_label.setText(self.tr("language"))
        self.input_label.setText(self.tr("source_dir"))
        self.input_edit.setPlaceholderText(self.tr("source_placeholder"))
        self.btn_input.setText(self.tr("choose_source"))
        self.include_subdirs_check.setText(self.tr("scan_subdirs"))
        self.permanent_delete_check.setText(self.tr("permanent_delete"))
        self.hash_thread_label.setText(self.tr("hash_threads"))
        self.drop_hint.setText(self.tr("drop_hint"))
        self.table_model.set_headers(self._table_headers())
        self.btn_scan.setText(self.tr("rescan"))
        self.btn_clear.setText(self.tr("clear_list"))
        self.btn_start.setText(self.tr("start_dedupe"))
        self._set_status_text(self._last_status_key, **self._last_status_kwargs)

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

    def browse_input(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("choose_source"))
        if not folder:
            return
        self.input_edit.setText(folder)
        self.scan_files()

    def clear_list(self):
        if self._is_busy():
            return
        self.table_model.clear()
        self._row_by_scan_id.clear()
        self._pending_row_updates.clear()
        self._append_queue.clear()
        self._refresh_queue.clear()
        self._process_update_queue.clear()
        self._pending_scan_result = None
        self._pending_process_result = None
        self._drain_timer.stop()
        self.progress.setValue(0)
        self._set_status_text("list_cleared")

    def eventFilter(self, obj, event):
        if obj is self.table.viewport():
            if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    return True
            if event.type() == QEvent.Type.Drop:
                paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
                if paths:
                    self.add_dropped_paths(paths)
                    event.acceptProposedAction()
                    return True
        return super().eventFilter(obj, event)

    def _first_source_dir(self, paths: list[Path]) -> Path | None:
        first_dir = next((p for p in paths if p.is_dir()), None)
        if first_dir is not None:
            return first_dir
        first_file = next((p for p in paths if p.is_file()), None)
        return first_file.parent if first_file is not None else None

    def _context_file_paths(self, _row: int, selected_rows: list[int]) -> list[Path]:
        return [
            self.file_list[row].path
            for row in selected_rows
            if 0 <= row < len(self.file_list)
        ]

    def scan_files(self):
        if self._is_busy():
            return
        source_text = self.input_edit.text().strip()
        if not source_text:
            return
        source_dir = Path(source_text)
        if not source_dir.is_dir():
            return
        self.table_model.clear()
        self._row_by_scan_id.clear()
        self._pending_row_updates.clear()
        self._append_queue.clear()
        self._refresh_queue.clear()
        self._process_update_queue.clear()
        self._pending_scan_result = None
        self._pending_process_result = None
        self._drain_timer.stop()
        self._start_scan([source_dir], existing=set())

    def add_dropped_paths(self, paths: list[Path]):
        if self._is_busy():
            return
        first_dir = self._first_source_dir(paths)
        if first_dir is not None:
            self.input_edit.setText(str(first_dir))
        if self.file_list:
            paths = [item.path for item in self.file_list] + paths
            self.table_model.clear()
            self._row_by_scan_id.clear()
            self._pending_row_updates.clear()
            self._append_queue.clear()
            self._refresh_queue.clear()
            self._process_update_queue.clear()
            self._pending_scan_result = None
            self._pending_process_result = None
            self._drain_timer.stop()
        self._start_scan(paths, existing=set())

    def _start_scan(self, paths: list[Path], existing: set[Path]):
        self.progress.setValue(0)
        self._set_status_text("scanning")
        self._scan_thread = QThread(self)
        self._scan_worker = ScanWorker(
            paths,
            self.include_subdirs_check.isChecked(),
            self._thread_count(),
            existing,
        )
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.row_batch_ready.connect(self._queue_append_rows)
        self._scan_worker.row_batch_changed.connect(self._queue_refresh_rows)
        self._scan_worker.progress_update.connect(self._update_scan_progress)
        self._scan_worker.finished.connect(self._scan_finished)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread_finished)
        self._scan_thread.start()

    def _append_row(self, item: DedupeItem):
        self._append_rows([item])

    def _queue_append_rows(self, items: list[DedupeItem]):
        self._append_queue.extend(items)
        self._ensure_drain_timer()

    def _queue_refresh_rows(self, items: list[DedupeItem]):
        self._refresh_queue.extend(items)
        self._ensure_drain_timer()

    def _queue_process_updates(self, updates: list[tuple[int, str]]):
        self._process_update_queue.extend(updates)
        self._ensure_drain_timer()

    def _ensure_drain_timer(self):
        if not self._drain_timer.isActive():
            self._drain_timer.start()

    def _pop_queue_items(self, queue: deque, limit: int) -> list:
        items: list = []
        while queue and len(items) < limit:
            items.append(queue.popleft())
        return items

    def _drain_table_queues(self):
        appended = self._pop_queue_items(self._append_queue, UI_APPEND_DRAIN_ROWS)
        if appended:
            self._append_rows(appended)

        refreshed = self._pop_queue_items(self._refresh_queue, UI_UPDATE_DRAIN_ROWS)
        if refreshed:
            self._refresh_rows(refreshed)

        process_updates = self._pop_queue_items(self._process_update_queue, UI_UPDATE_DRAIN_ROWS)
        if process_updates:
            self._apply_process_updates(process_updates)

        if self._append_queue or self._refresh_queue or self._process_update_queue:
            return

        self._drain_timer.stop()
        if self._pending_scan_result is not None:
            result = self._pending_scan_result
            self._pending_scan_result = None
            self._apply_scan_finished(result)
        if self._pending_process_result is not None:
            result = self._pending_process_result
            self._pending_process_result = None
            self._apply_processing_finished(result)

    def _append_rows(self, items: list[DedupeItem]):
        if not items:
            return
        start_row = len(self.file_list)
        for offset, item in enumerate(items):
            row = start_row + offset
            item.row_index = row
            self._row_by_scan_id[item.scan_id] = row
        self.table_model.append_items(items)
        for item in items:
            pending_item = self._pending_row_updates.pop(item.scan_id, None)
            if pending_item is not None:
                self._refresh_row(pending_item)

    def _refresh_rows(self, items: list[DedupeItem]):
        if not items:
            return
        self.table.setUpdatesEnabled(False)
        try:
            for item in items:
                self._refresh_row(item)
        finally:
            self.table.setUpdatesEnabled(True)

    def _refresh_row(self, item: DedupeItem):
        row = self._row_by_scan_id.get(item.scan_id)
        if row is None:
            self._pending_row_updates[item.scan_id] = item
            return
        if 0 <= row < len(self.file_list):
            self.file_list[row] = item
            item.row_index = row
            self.table_model.update_row(row)

    def _update_scan_progress(self, percent: int, _text: str):
        self.progress.setValue(percent)

    def _scan_finished(self, result: dict):
        self._pending_scan_result = result
        self._ensure_drain_timer()

    def _apply_scan_finished(self, result: dict):
        count = int(result.get("count", 0))
        duplicates = int(result.get("duplicates", 0))
        self._sort_rows_after_scan()
        self.progress.setValue(100)
        if count == 0:
            self._set_status_text("scan_none_status")
        else:
            self._set_status_text("scan_done_status", count=len(self.file_list), duplicates=duplicates)

    def _sort_rows_after_scan(self):
        if not self.file_list:
            return

        def sort_key(item: DedupeItem):
            if item.group_id:
                return (
                    0,
                    item.group_id,
                    1 if item.duplicate else 0,
                    _keeper_sort_key(item.path),
                )
            return (1, 0, 0, str(item.rel_path).casefold())

        sorted_items = sorted(self.file_list, key=sort_key)
        if sorted_items == self.file_list:
            return
        self.table_model.reset_items(sorted_items)
        self._row_by_scan_id.clear()
        for row, item in enumerate(self.file_list):
            item.row_index = row
            self._row_by_scan_id[item.scan_id] = row

    def _scan_thread_finished(self):
        self._scan_worker = None
        self._scan_thread = None

    def start_processing(self):
        if self._is_busy():
            return
        duplicate_items = [item for item in self.file_list if item.duplicate]
        if not duplicate_items:
            self._notify(self.tr("cannot_start_title"), self.tr("cannot_start_content"), is_error=True)
            return

        permanent = self.permanent_delete_check.isChecked()
        if not permanent and not HAS_SEND2TRASH:
            self._notify(self.tr("missing_trash_title"), self.tr("missing_trash_content"), is_error=True)
            return
        if permanent:
            result = QMessageBox.question(
                self,
                self.tr("confirm_delete_title"),
                self.tr("confirm_delete_content", count=len(duplicate_items)),
            )
            if result != QMessageBox.StandardButton.Yes:
                return

        self.is_processing = True
        for row, item in enumerate(self.file_list):
            item.row_index = row
        self.btn_start.setEnabled(False)
        self.btn_scan.setEnabled(False)
        self.btn_clear.setEnabled(False)
        self.progress.setValue(0)

        self._process_thread = QThread(self)
        self._process_worker = ProcessWorker(duplicate_items, permanent=permanent)
        self._process_worker.moveToThread(self._process_thread)
        self._process_thread.started.connect(self._process_worker.run)
        self._process_worker.row_update_batch.connect(self._queue_process_updates)
        self._process_worker.progress_update.connect(self._update_process_progress)
        self._process_worker.finished.connect(self._processing_finished)
        self._process_worker.finished.connect(self._process_thread.quit)
        self._process_worker.finished.connect(self._process_worker.deleteLater)
        self._process_thread.finished.connect(self._process_thread.deleteLater)
        self._process_thread.finished.connect(self._process_thread_finished)
        self._process_thread.start()

    def _apply_process_updates(self, updates: list[tuple[int, str]]):
        self.table.setUpdatesEnabled(False)
        try:
            for row, status in updates:
                self._update_row_status(row, status)
        finally:
            self.table.setUpdatesEnabled(True)

    def _update_row_status(self, row: int, status: str):
        if 0 <= row < len(self.file_list):
            self.file_list[row].status = status
            self.table_model.update_row(row)

    def _update_process_progress(self, percent: int, text: str):
        self.progress.setValue(percent)
        self.status.setText(f"{self.tr('status_processing')} {text}")

    def _processing_finished(self, result: dict):
        self._pending_process_result = result
        self._ensure_drain_timer()

    def _apply_processing_finished(self, result: dict):
        self.is_processing = False
        self.btn_start.setEnabled(True)
        self.btn_scan.setEnabled(True)
        self.btn_clear.setEnabled(True)
        self.progress.setValue(100)
        self._set_status_text("process_done_status", success=result["success"], failed=result["failed"])
        QMessageBox.information(
            self,
            self.tr("process_done_title"),
            self.tr("process_done_message", success=result["success"], failed=result["failed"]),
        )

    def _process_thread_finished(self):
        self._process_worker = None
        self._process_thread = None


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
