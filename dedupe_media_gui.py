from __future__ import annotations

import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from qframelesswindow import FramelessMainWindow, StandardTitleBar

from PyQt6.QtCore import QEvent, QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
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
    TableWidget,
    Theme,
    VIDEO_SUFFIXES,
    _get_windows_pictures_dir,
    _safe_resolve,
    setTheme,
    setThemeColor,
)


APP_NAME = "DedupeMediaGUI"
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES + VIDEO_SUFFIXES
HASH_CHUNK_SIZE = 1024 * 1024
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
        "drop_hint": "拖入图片、视频或文件夹；同大小文件才会计算完整 SHA-256，提高扫描速度。",
        "table_file": "文件",
        "table_abs_path": "绝对路径",
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
        "drop_hint": "Drop photos, videos, or folders. Full SHA-256 is calculated only for same-size files.",
        "table_file": "File",
        "table_abs_path": "Absolute path",
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


class ScanWorker(QObject):
    row_ready = pyqtSignal(object)
    row_changed = pyqtSignal(object)
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, paths: list[Path], recursive: bool, existing: set[Path] | None = None):
        super().__init__()
        self.paths = paths
        self.recursive = recursive
        self.existing = existing or set()

    def run(self):
        seen: set[Path] = set(self.existing)
        by_size: dict[int, list[DedupeItem]] = {}
        scanned = 0

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
                size=size,
            )
            by_size.setdefault(size, []).append(item)
            scanned += 1
            self.row_ready.emit(item)
            if scanned % 50 == 0:
                self.progress_update.emit(0, f"scanning|{scanned}")

        duplicate_groups: list[list[DedupeItem]] = []
        group_id = 1
        hash_candidates = sum(len(items) for items in by_size.values() if len(items) > 1)
        hashed = 0

        for items in by_size.values():
            if len(items) == 1:
                continue

            by_hash: dict[str, list[DedupeItem]] = {}
            for item in items:
                try:
                    item.digest = _hash_file(item.path)
                except Exception:
                    item.status = "status_failed|hash"
                    self.row_changed.emit(item)
                    continue
                hashed += 1
                if hash_candidates:
                    percent = int((hashed / hash_candidates) * 100)
                    self.progress_update.emit(percent, f"scanning|{scanned}")
                by_hash.setdefault(item.digest, []).append(item)

            for hash_items in by_hash.values():
                hash_items.sort(key=lambda value: _keeper_sort_key(value.path))
                if len(hash_items) == 1:
                    self.row_changed.emit(hash_items[0])
                    continue
                for index, item in enumerate(hash_items):
                    item.group_id = group_id
                    if index == 0:
                        item.status = "status_keep"
                    else:
                        item.duplicate = True
                        item.status = "status_duplicate"
                    self.row_changed.emit(item)
                duplicate_groups.append(hash_items)
                group_id += 1

        duplicates = sum(1 for group in duplicate_groups for item in group if item.duplicate)
        self.finished.emit({"count": scanned, "duplicates": duplicates})


class ProcessWorker(QObject):
    row_update = pyqtSignal(int, str)
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, items: list[DedupeItem], permanent: bool):
        super().__init__()
        self.items = items
        self.permanent = permanent

    def run(self):
        success = 0
        failed = 0
        total = len(self.items)
        for index, item in enumerate(self.items):
            percent = int(((index + 1) / total) * 100) if total else 0
            try:
                if self.permanent:
                    item.path.unlink()
                    status = "status_deleted"
                else:
                    send2trash(str(item.path))
                    status = "status_recycled"
                success += 1
                self.row_update.emit(item.row_index, status)
            except Exception as exc:
                failed += 1
                self.row_update.emit(item.row_index, f"status_failed|{str(exc)[:36]}")
            if _should_emit_progress(index, total):
                self.progress_update.emit(percent, f"{index + 1}/{total}")
        self.finished.emit({"success": success, "failed": failed})


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
        self.is_processing = False
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._process_thread: QThread | None = None
        self._process_worker: ProcessWorker | None = None

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
        row2.addWidget(self.include_subdirs_check)
        row2.addWidget(self.permanent_delete_check)
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

        self.table = TableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(self._table_headers())
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setAcceptDrops(True)
        self.table.viewport().setAcceptDrops(True)
        self.table.viewport().installEventFilter(self)
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
        self._apply_language()

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

    def _set_status_text(self, key: str, **kwargs):
        self._last_status_key = key
        self._last_status_kwargs = kwargs
        self.status.setText(self.tr(key, **kwargs))

    def _is_busy(self) -> bool:
        return (
            self.is_processing
            or (self._scan_thread is not None and self._scan_thread.isRunning())
            or (self._process_thread is not None and self._process_thread.isRunning())
        )

    def _on_language_changed(self, _index: int):
        lang = self.language_combo.currentData()
        if lang in SUPPORTED_LANGUAGES and lang != self.lang:
            self.lang = lang
            self._apply_language()

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
        self.drop_hint.setText(self.tr("drop_hint"))
        self.table.setHorizontalHeaderLabels(self._table_headers())
        self.btn_scan.setText(self.tr("rescan"))
        self.btn_clear.setText(self.tr("clear_list"))
        self.btn_start.setText(self.tr("start_dedupe"))
        self._set_status_text(self._last_status_key, **self._last_status_kwargs)
        for row, item in enumerate(self.file_list):
            status_item = self.table.item(row, 5)
            if status_item is not None:
                status_item.setText(self._display_status(item.status))

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
        self.file_list.clear()
        self._row_by_scan_id.clear()
        self._pending_row_updates.clear()
        self.table.setRowCount(0)
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

    def scan_files(self):
        if self._is_busy():
            return
        source_text = self.input_edit.text().strip()
        if not source_text:
            return
        source_dir = Path(source_text)
        if not source_dir.is_dir():
            return
        self.file_list.clear()
        self._row_by_scan_id.clear()
        self._pending_row_updates.clear()
        self.table.setRowCount(0)
        self._start_scan([source_dir], existing=set())

    def add_dropped_paths(self, paths: list[Path]):
        if self._is_busy():
            return
        first_dir = self._first_source_dir(paths)
        if first_dir is not None:
            self.input_edit.setText(str(first_dir))
        if self.file_list:
            paths = [item.path for item in self.file_list] + paths
            self.file_list.clear()
            self._row_by_scan_id.clear()
            self._pending_row_updates.clear()
            self.table.setRowCount(0)
        self._start_scan(paths, existing=set())

    def _start_scan(self, paths: list[Path], existing: set[Path]):
        self.progress.setValue(0)
        self._set_status_text("scanning")
        self._scan_thread = QThread(self)
        self._scan_worker = ScanWorker(paths, self.include_subdirs_check.isChecked(), existing)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.row_ready.connect(self._append_row)
        self._scan_worker.row_changed.connect(self._refresh_row)
        self._scan_worker.progress_update.connect(self._update_scan_progress)
        self._scan_worker.finished.connect(self._scan_finished)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread_finished)
        self._scan_thread.start()

    def _append_row(self, item: DedupeItem):
        item.row_index = len(self.file_list)
        self.file_list.append(item)
        row = self.table.rowCount()
        self._row_by_scan_id[item.scan_id] = row
        self.table.insertRow(row)
        values = [
            str(item.rel_path),
            str(_safe_resolve(item.path)),
            _format_size(item.size),
            item.digest[:16] if item.digest else "-",
            str(item.group_id) if item.group_id else "-",
            self._display_status(item.status),
        ]
        duplicate_bg = QBrush(QColor("#FEF3F2"))
        duplicate_fg = QBrush(QColor("#B42318"))
        for column, value in enumerate(values):
            table_item = QTableWidgetItem(value)
            if item.duplicate:
                table_item.setBackground(duplicate_bg)
                table_item.setForeground(duplicate_fg)
            self.table.setItem(row, column, table_item)
        pending_item = self._pending_row_updates.pop(item.scan_id, None)
        if pending_item is not None:
            self._refresh_row(pending_item)

    def _style_row(self, row: int, duplicate: bool):
        duplicate_bg = QBrush(QColor("#FEF3F2"))
        duplicate_fg = QBrush(QColor("#B42318"))
        normal_bg = QBrush()
        normal_fg = QBrush()
        for column in range(self.table.columnCount()):
            table_item = self.table.item(row, column)
            if table_item is None:
                continue
            table_item.setBackground(duplicate_bg if duplicate else normal_bg)
            table_item.setForeground(duplicate_fg if duplicate else normal_fg)

    def _refresh_row(self, item: DedupeItem):
        row = self._row_by_scan_id.get(item.scan_id)
        if row is None:
            self._pending_row_updates[item.scan_id] = item
            return
        if 0 <= row < len(self.file_list):
            self.file_list[row] = item
            item.row_index = row
        if not (0 <= row < self.table.rowCount()):
            return
        values = {
            0: str(item.rel_path),
            1: str(_safe_resolve(item.path)),
            2: _format_size(item.size),
            3: item.digest[:16] if item.digest else "-",
            4: str(item.group_id) if item.group_id else "-",
            5: self._display_status(item.status),
        }
        for column, value in values.items():
            table_item = self.table.item(row, column)
            if table_item is None:
                table_item = QTableWidgetItem(value)
                self.table.setItem(row, column, table_item)
            else:
                table_item.setText(value)
        self._style_row(row, item.duplicate)

    def _update_scan_progress(self, percent: int, _text: str):
        self.progress.setValue(percent)

    def _scan_finished(self, result: dict):
        count = int(result.get("count", 0))
        duplicates = int(result.get("duplicates", 0))
        self.progress.setValue(100)
        if count == 0:
            self._set_status_text("scan_none_status")
        else:
            self._set_status_text("scan_done_status", count=len(self.file_list), duplicates=duplicates)

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
        self._process_worker.row_update.connect(self._update_row_status)
        self._process_worker.progress_update.connect(self._update_process_progress)
        self._process_worker.finished.connect(self._processing_finished)
        self._process_worker.finished.connect(self._process_thread.quit)
        self._process_worker.finished.connect(self._process_worker.deleteLater)
        self._process_thread.finished.connect(self._process_thread.deleteLater)
        self._process_thread.finished.connect(self._process_thread_finished)
        self._process_thread.start()

    def _update_row_status(self, row: int, status: str):
        item = self.file_list[row] if 0 <= row < len(self.file_list) else None
        if 0 <= row < len(self.file_list):
            self.file_list[row].status = status
        if 0 <= row < self.table.rowCount():
            status_item = QTableWidgetItem(self._display_status(status))
            if item is not None and item.duplicate:
                status_item.setBackground(QBrush(QColor("#FEF3F2")))
                status_item.setForeground(QBrush(QColor("#B42318")))
            self.table.setItem(row, 5, status_item)

    def _update_process_progress(self, percent: int, text: str):
        self.progress.setValue(percent)
        self.status.setText(f"{self.tr('status_processing')} {text}")

    def _processing_finished(self, result: dict):
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
