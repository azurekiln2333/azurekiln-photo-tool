from __future__ import annotations

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
    _format_timestamp,
    _get_windows_pictures_dir,
    _safe_resolve,
    detect_timestamp,
    setTheme,
    setThemeColor,
)


APP_NAME = "RenamePhotoGUI"
TARGET_PREFIX = "IMG"
TRANSLATIONS = {
    "zh": {
        "app_title": "照片重命名",
        "header_title": "照片重命名",
        "header_subtitle": "读取拍摄时间，并按 IMG_年月日_时分秒 的格式重命名原文件",
        "header_note": "优先使用媒体拍摄时间；没有拍摄时间时，使用文件名时间或文件现有最早时间。",
        "language": "界面语言",
        "source_dir": "源目录",
        "source_placeholder": "选择或拖入需要重命名的照片目录",
        "choose_source": "选择源目录",
        "scan_subdirs": "扫描子目录",
        "table_file": "当前相对路径",
        "table_shot_time": "采集时间",
        "table_target": "目标文件名",
        "table_source": "来源",
        "table_status": "状态",
        "drop_hint": "拖入照片或文件夹后预览目标文件名；重命名会直接修改原文件名，同名自动追加序号。",
        "rescan": "重新扫描",
        "clear_list": "清空列表",
        "start_rename": "开始重命名",
        "waiting_source": "等待选择或拖入文件",
        "scanning": "正在扫描文件",
        "scan_none_status": "未找到可重命名文件",
        "scan_done_status": "共扫描到 {count} 个文件，准备就绪",
        "drop_added": "已拖拽添加 {added} 个文件，当前共 {count} 项",
        "drop_no_new": "未添加新的文件",
        "list_cleared": "列表已清空",
        "preparing": "准备重命名",
        "progress": "正在处理 {i}/{total}",
        "task_done_status": "重命名完成：成功 {success}，失败 {failed}，跳过 {skipped}",
        "status_pending": "待处理",
        "status_renaming": "正在重命名",
        "status_renamed": "已重命名",
        "status_already_named": "文件名已符合规则",
        "status_skipped": "已跳过",
        "status_failed": "失败：{error}",
        "source_exif": "拍摄时间",
        "source_filename": "文件名时间",
        "source_earliest": "文件现有最早时间",
        "source_unknown": "未知",
        "yes": "是",
        "no": "否",
        "invalid_folder_title": "目录无效",
        "invalid_folder_content": "请选择有效的源目录。",
        "cannot_start_title": "无法开始",
        "cannot_start_content": "请先添加需要重命名的文件。",
        "task_done_title": "处理完成",
        "task_done_message": "照片重命名完成。\n\n成功: {success}\n失败: {failed}\n跳过: {skipped}",
        "process_done_notice": "已重命名 {count} 个文件",
        "target_unknown": "-",
    },
    "en": {
        "app_title": "Rename Photos",
        "header_title": "Rename Photos",
        "header_subtitle": "Read capture time and rename originals as IMG_yyyyMMdd_HHmmss",
        "header_note": "Media capture time is preferred; filename time or the earliest existing file time is used as fallback.",
        "language": "Language",
        "source_dir": "Source folder",
        "source_placeholder": "Choose or drop a folder containing photos to rename",
        "choose_source": "Choose source",
        "scan_subdirs": "Scan subfolders",
        "table_file": "Current relative path",
        "table_shot_time": "Detected time",
        "table_target": "Target filename",
        "table_source": "Source",
        "table_status": "Status",
        "drop_hint": "Drop photos or folders to preview target names. Renaming modifies original filenames in place.",
        "rescan": "Rescan",
        "clear_list": "Clear list",
        "start_rename": "Rename files",
        "waiting_source": "Waiting for files",
        "scanning": "Scanning files",
        "scan_none_status": "No renameable files found",
        "scan_done_status": "Scanned {count} file(s), ready",
        "drop_added": "Dropped {added} file(s), total {count}",
        "drop_no_new": "No new files were added",
        "list_cleared": "List cleared",
        "preparing": "Preparing rename",
        "progress": "Processing {i}/{total}",
        "task_done_status": "Done: {success} renamed, {failed} failed, {skipped} skipped",
        "status_pending": "Pending",
        "status_renaming": "Renaming",
        "status_renamed": "Renamed",
        "status_already_named": "Already named",
        "status_skipped": "Skipped",
        "status_failed": "Failed: {error}",
        "source_exif": "Capture time",
        "source_filename": "Filename time",
        "source_earliest": "Earliest existing file time",
        "source_unknown": "Unknown",
        "yes": "Yes",
        "no": "No",
        "invalid_folder_title": "Invalid folder",
        "invalid_folder_content": "Choose a valid source folder.",
        "cannot_start_title": "Cannot start",
        "cannot_start_content": "Add files to rename first.",
        "task_done_title": "Task complete",
        "task_done_message": "Photo rename complete.\n\nRenamed: {success}\nFailed: {failed}\nSkipped: {skipped}",
        "process_done_notice": "Renamed {count} file(s)",
        "target_unknown": "-",
    },
}


@dataclass
class RenameItem:
    path: Path
    source_root: Path | None
    rel_path: Path
    timestamp: float | None
    source: str
    target_name: str = ""
    target_path: Path | None = None
    status: str = "status_pending"


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


def _target_stem(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime(f"{TARGET_PREFIX}_%Y%m%d_%H%M%S")


def _target_filename(path: Path, timestamp: float, index: int = 0) -> str:
    stem = _target_stem(timestamp)
    if index:
        stem = f"{stem}_{index:03d}"
    return f"{stem}{path.suffix.lower()}"


def _is_same_path(left: Path, right: Path) -> bool:
    return _safe_resolve(left) == _safe_resolve(right)


def _is_supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


def _iter_rename_paths(paths: list[Path], recursive: bool) -> list[tuple[Path, Path | None]]:
    files: list[tuple[Path, Path | None]] = []
    for path in paths:
        if path.is_file():
            if _is_supported_image(path):
                files.append((path, path.parent))
            continue
        if not path.is_dir():
            continue
        iterator = path.rglob("*") if recursive else path.glob("*")
        files.extend((candidate, path) for candidate in iterator if _is_supported_image(candidate))
    return files


def _unique_target_path(item: RenameItem, reserved: set[Path]) -> Path | None:
    if item.timestamp is None:
        return None

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


def _make_item(file_path: Path, source_root: Path | None) -> RenameItem:
    timestamp, source = detect_timestamp(file_path)
    return RenameItem(
        path=file_path,
        source_root=source_root,
        rel_path=_relative_path(file_path, source_root),
        timestamp=timestamp,
        source=source,
    )


class ScanWorker(QObject):
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
            items.append(_make_item(file_path, source_root))

        items.sort(key=lambda value: str(value.rel_path))
        _assign_target_paths(items)
        for item in items:
            self.row_ready.emit(item)

        self.finished.emit(len(items))


class ProcessWorker(QObject):
    row_update = pyqtSignal(int, str, object)
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, items: list[RenameItem]):
        super().__init__()
        self.items = items

    def run(self):
        success = 0
        failed = 0
        skipped = 0
        total = len(self.items)
        _assign_target_paths(self.items)

        for index, item in enumerate(self.items):
            progress_percent = int(((index + 1) / total) * 100) if total else 0
            target_path = item.target_path

            if item.timestamp is None or target_path is None:
                skipped += 1
                self.row_update.emit(index, "status_skipped", None)
                self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")
                continue

            if _is_same_path(item.path, target_path):
                skipped += 1
                self.row_update.emit(index, "status_already_named", target_path)
                self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")
                continue

            self.row_update.emit(index, "status_renaming", target_path)
            try:
                item.path.rename(target_path)
                item.path = target_path
                item.rel_path = _relative_path(target_path, item.source_root)
                item.target_name = target_path.name
                success += 1
                self.row_update.emit(index, "status_renamed", target_path)
            except Exception as exc:
                failed += 1
                self.row_update.emit(index, f"status_failed|{str(exc)[:36]}", target_path)

            self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")

        self.finished.emit({"success": success, "failed": failed, "skipped": skipped})


class MainWindow(FramelessMainWindow):
    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("Rename Photos")
        self._title_bar_height = 36
        if not self._embedded:
            self.resize(1280, 820)
            self._set_blue_title_bar()

        self.lang = DEFAULT_LANGUAGE
        self._last_status_key = "waiting_source"
        self._last_status_kwargs: dict = {}
        self.file_list: list[RenameItem] = []
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
        path_layout.addLayout(row1)

        option_card = CardWidget(self)
        option_layout = QVBoxLayout(option_card)
        option_layout.setContentsMargins(16, 14, 16, 14)
        option_layout.setSpacing(10)
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        self.include_subdirs_check = CheckBox(self.tr("scan_subdirs"), self)
        self.include_subdirs_check.setChecked(True)
        self.include_subdirs_check.toggled.connect(self.scan_files)
        row2.addWidget(self.include_subdirs_check)
        row2.addStretch(1)
        option_layout.addLayout(row2)

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
        self.table.setColumnCount(5)
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
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
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
        self.btn_start = PrimaryPushButton(self.tr("start_rename"), self)
        self.btn_start.setIcon(_pick_icon("EDIT", "TAG", "PLAY"))
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
        if not self._embedded:
            outer.addWidget(option_card)
        outer.addWidget(table_card, 1)
        outer.addWidget(action_card)
        outer.addWidget(foot_card)

        self._init_default_input_dir()
        self._load_settings()
        self._apply_language()
        self._connect_settings_signals()

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
            self.tr("table_shot_time"),
            self.tr("table_target"),
            self.tr("table_source"),
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

    def _set_status_text(self, key: str, **kwargs):
        self._last_status_key = key
        self._last_status_kwargs = kwargs
        self.status.setText(self.tr(key, **kwargs))

    def _init_default_input_dir(self):
        pics_dir = _get_windows_pictures_dir() or (Path.home() / "Pictures")
        self.input_edit.setText(str(pics_dir))
        self._set_status_text("waiting_source")

    def _settings_payload(self) -> dict:
        return {
            "language": self.lang,
            "input_dir": self.input_edit.text().strip(),
            "include_subdirs": self.include_subdirs_check.isChecked(),
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
        self.input_edit.editingFinished.connect(self._save_settings)
        self.include_subdirs_check.toggled.connect(lambda _checked=False: self._save_settings())

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

            input_dir = str(data.get("input_dir", "")).strip()
            if input_dir:
                self.input_edit.setText(input_dir)
            self.include_subdirs_check.setChecked(bool(data.get("include_subdirs", True)))
        finally:
            self._suspend_settings_save = False

    def _on_language_changed(self, _index: int):
        lang = self.language_combo.currentData()
        if lang not in SUPPORTED_LANGUAGES or lang == self.lang:
            return
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
        self.drop_hint.setText(self.tr("drop_hint"))
        self.table.setHorizontalHeaderLabels(self._table_headers())
        self.btn_scan.setText(self.tr("rescan"))
        self.btn_clear.setText(self.tr("clear_list"))
        self.btn_start.setText(self.tr("start_rename"))
        self._set_status_text(self._last_status_key, **self._last_status_kwargs)
        self._refresh_table_language()

    def _refresh_table_language(self):
        for row, item in enumerate(self.file_list):
            source_item = self.table.item(row, 3)
            status_item = self.table.item(row, 4)
            if source_item is not None:
                source_item.setText(self.tr(item.source))
            if status_item is not None:
                status_item.setText(self._display_status(item.status))

    def eventFilter(self, obj, event):
        if obj is self.table.viewport():
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
                    self.add_dropped_paths(paths)
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

    def browse_input(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("choose_source"))
        if not folder:
            return
        self.input_edit.setText(folder)
        self._save_settings()
        self.scan_files()

    def clear_list(self):
        if self.is_processing:
            return
        self.file_list.clear()
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self._set_status_text("list_cleared")

    def add_dropped_paths(self, paths: list[Path]):
        if self.is_processing:
            return
        first_dir = next((p for p in paths if p.is_dir()), None)
        if first_dir is None:
            first_file = next((p for p in paths if p.is_file()), None)
            first_dir = first_file.parent if first_file is not None else None
        if first_dir is not None:
            self.input_edit.setText(str(first_dir))
            self._save_settings()

        existing = {_safe_resolve(item.path) for item in self.file_list}
        new_items: list[RenameItem] = []
        for file_path, source_root in _iter_rename_paths(paths, self.include_subdirs_check.isChecked()):
            resolved = _safe_resolve(file_path)
            if resolved in existing:
                continue
            new_items.append(_make_item(file_path, source_root))
            existing.add(resolved)

        if new_items:
            new_items.sort(key=lambda value: str(value.rel_path))
            self.file_list.extend(new_items)
            _assign_target_paths(self.file_list)
            self._rebuild_table()
            self.progress.setValue(0)
            self._set_status_text("drop_added", added=len(new_items), count=len(self.file_list))
        else:
            self._set_status_text("drop_no_new")

    def scan_files(self):
        if self.is_processing:
            return
        input_dir_text = self.input_edit.text().strip()
        if not input_dir_text:
            return
        input_dir = Path(input_dir_text)
        if not input_dir.is_dir():
            self._notify(self.tr("invalid_folder_title"), self.tr("invalid_folder_content"), is_error=True)
            return

        self.file_list.clear()
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self._set_status_text("scanning")
        self._save_settings()

        self._scan_thread = QThread(self)
        self._scan_worker = ScanWorker([input_dir], self.include_subdirs_check.isChecked())
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.row_ready.connect(self._append_scan_row)
        self._scan_worker.finished.connect(self._scan_finished)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.start()

    def _append_scan_row(self, item: RenameItem):
        self.file_list.append(item)
        self._append_table_row(item)

    def _append_table_row(self, item: RenameItem):
        row = self.table.rowCount()
        self.table.insertRow(row)
        target_name = item.target_name or self.tr("target_unknown")
        self.table.setItem(row, 0, QTableWidgetItem(str(item.rel_path)))
        self.table.setItem(row, 1, QTableWidgetItem(_format_timestamp(item.timestamp)))
        self.table.setItem(row, 2, QTableWidgetItem(target_name))
        self.table.setItem(row, 3, QTableWidgetItem(self.tr(item.source)))
        self.table.setItem(row, 4, QTableWidgetItem(self._display_status(item.status)))

    def _rebuild_table(self):
        self.table.setRowCount(0)
        for item in self.file_list:
            self._append_table_row(item)

    def _scan_finished(self, count: int):
        if count == 0:
            self._set_status_text("scan_none_status")
            self._notify(self.tr("invalid_folder_title"), self.tr("scan_none_status"), is_error=True)
            return
        self._set_status_text("scan_done_status", count=count)

    def start_processing(self):
        if self.is_processing:
            return
        if not self.file_list:
            self._notify(self.tr("cannot_start_title"), self.tr("cannot_start_content"), is_error=True)
            return

        self.is_processing = True
        self.btn_start.setEnabled(False)
        self.btn_scan.setEnabled(False)
        self.btn_clear.setEnabled(False)
        self.progress.setValue(0)
        self._set_status_text("preparing")
        self._save_settings()

        self._process_thread = QThread(self)
        self._process_worker = ProcessWorker(list(self.file_list))
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
                if status_text in ("status_renamed", "status_already_named"):
                    item.path = target_path
                    item.rel_path = _relative_path(target_path, item.source_root)
                self.table.setItem(row, 0, QTableWidgetItem(str(item.rel_path)))
                self.table.setItem(row, 2, QTableWidgetItem(item.target_name or self.tr("target_unknown")))

        self.table.setItem(row, 4, QTableWidgetItem(self._display_status(status_text)))
        self.table.scrollToItem(self.table.item(row, 4))

    def _update_progress(self, percent: int, text: str):
        self.progress.setValue(percent)
        self.status.setText(self._display_progress_text(text))

    def _processing_finished(self, result: dict):
        self.is_processing = False
        self.btn_start.setEnabled(True)
        self.btn_scan.setEnabled(True)
        self.btn_clear.setEnabled(True)
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
