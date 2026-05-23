#!/usr/bin/env python3
from __future__ import annotations

import ctypes
import importlib
import json
import os
import shutil
import sys
from pathlib import Path

from qframelesswindow import FramelessMainWindow, StandardTitleBar

from split_huawei_live_photo import is_huawei_live_photo, split_live_photo
from split_huawei_live_photo_translations import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, TRANSLATIONS

from PyQt6.QtCore import QEvent, QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "SplitHuaweiLivePhotoGUI"
IMAGE_SUFFIXES = (".jpg", ".jpeg")
VIDEO_SUFFIXES = (".mp4",)


def _get_windows_pictures_dir() -> Path | None:
    if sys.platform != "win32":
        return None
    try:
        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        f_id_pictures = GUID(
            0x33E28130,
            0x4E1E,
            0x4676,
            (ctypes.c_ubyte * 8)(0x83, 0x5A, 0x98, 0x39, 0x5C, 0x3B, 0xC3, 0xBB),
        )
        out_path = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        hr = shell32.SHGetKnownFolderPath(ctypes.byref(f_id_pictures), 0, None, ctypes.byref(out_path))
        if hr != 0 or not out_path.value:
            return None
        path = Path(out_path.value)
        ole32.CoTaskMemFree(out_path)
        return path
    except Exception:
        return None


def _get_settings_path() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME / "settings.json"
    return Path.home() / ".config" / APP_NAME / "settings.json"


def _import_fluent():
    module_candidates = (
        ("qfluentwidgetspro", True),
        ("qfluentwidgets_pro", True),
        ("qfluentwidgets", False),
    )

    module = None
    is_pro = False
    last_exc = None
    for mod_name, pro_flag in module_candidates:
        try:
            module = importlib.import_module(mod_name)
            is_pro = pro_flag
            break
        except Exception as exc:
            last_exc = exc

    if module is None:
        raise ImportError(
            "qfluentwidgets is not installed.\n"
            "Install it with: pip install PyQt6-Fluent-Widgets"
        ) from last_exc

    return {
        "theme": module.Theme,
        "set_theme": module.setTheme,
        "PrimaryPushButton": module.PrimaryPushButton,
        "PushButton": module.PushButton,
        "LineEdit": module.LineEdit,
        "TableWidget": module.TableWidget,
        "ProgressBar": module.ProgressBar,
        "CheckBox": module.CheckBox,
        "ComboBox": module.ComboBox,
        "RadioButton": module.RadioButton,
        "CardWidget": module.CardWidget,
        "SubtitleLabel": module.SubtitleLabel,
        "BodyLabel": module.BodyLabel,
        "InfoBar": module.InfoBar,
        "InfoBarPosition": module.InfoBarPosition,
        "FluentIcon": module.FluentIcon,
        "set_theme_color": module.setThemeColor,
        "is_pro": is_pro,
    }


FW = _import_fluent()
Theme = FW["theme"]
setTheme = FW["set_theme"]
PrimaryPushButton = FW["PrimaryPushButton"]
PushButton = FW["PushButton"]
LineEdit = FW["LineEdit"]
TableWidget = FW["TableWidget"]
ProgressBar = FW["ProgressBar"]
CheckBox = FW["CheckBox"]
ComboBox = FW["ComboBox"]
RadioButton = FW["RadioButton"]
CardWidget = FW["CardWidget"]
SubtitleLabel = FW["SubtitleLabel"]
BodyLabel = FW["BodyLabel"]
InfoBar = FW["InfoBar"]
InfoBarPosition = FW["InfoBarPosition"]
FluentIcon = FW["FluentIcon"]
setThemeColor = FW["set_theme_color"]


def _pick_icon(*names: str):
    for name in names:
        icon = getattr(FluentIcon, name, None)
        if icon is not None:
            return icon
    return FluentIcon.APPLICATION


def _is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


def _find_matching_video(img_path: Path) -> Path | None:
    for suffix in VIDEO_SUFFIXES:
        for candidate_suffix in (suffix, suffix.upper()):
            video_path = img_path.with_suffix(candidate_suffix)
            if video_path.exists():
                return video_path
    return None


def _apply_source_timestamp(output_path: Path, source_path: Path):
    try:
        stat = source_path.stat()
        os.utime(output_path, (stat.st_atime, stat.st_mtime))
    except Exception:
        pass


def _make_task(img_path: Path, base_dir: Path | None = None) -> dict:
    is_embedded = is_huawei_live_photo(img_path)
    video_path = _find_matching_video(img_path)

    if base_dir is not None:
        try:
            rel_path = img_path.relative_to(base_dir)
        except ValueError:
            rel_path = Path(img_path.name)
    else:
        rel_path = Path(img_path.name)

    if is_embedded:
        task_type = "type_embedded"
    elif video_path is not None:
        task_type = "type_cloud_pair"
    else:
        task_type = "type_static"

    return {
        "img_path": img_path,
        "mp4_path": video_path,
        "rel_path": rel_path,
        "type": task_type,
        "has_mp4_text": "yes" if video_path is not None else "no",
        "status": "status_pending" if task_type != "type_static" else "status_skip_static",
    }


class ScanWorker(QObject):
    row_ready = pyqtSignal(dict)
    finished = pyqtSignal(int, int)

    def __init__(self, input_dir: Path, recursive: bool, output_dir: Path | None = None):
        super().__init__()
        self.input_dir = input_dir
        self.recursive = recursive
        self.output_dir = output_dir.resolve() if output_dir is not None else None

    def run(self):
        iterator = self.input_dir.rglob("*") if self.recursive else self.input_dir.glob("*")
        img_files = []
        for path in iterator:
            if not _is_image_file(path):
                continue
            if self.output_dir is not None:
                try:
                    path.resolve().relative_to(self.output_dir)
                    continue
                except ValueError:
                    pass
            img_files.append(path)
        img_files = sorted(img_files)
        processable = 0

        for img_path in img_files:
            task = _make_task(img_path, self.input_dir)
            if task["type"] != "type_static":
                processable += 1
            self.row_ready.emit(task)

        self.finished.emit(len(img_files), processable)


class ProcessWorker(QObject):
    row_update = pyqtSignal(int, str)
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, tasks: list[dict], options: dict):
        super().__init__()
        self.tasks = tasks
        self.options = options

    def _target_paths(self, task: dict, out_path: Path) -> tuple[Path, Path]:
        rel_path = task["rel_path"]
        jpg_target = out_path / rel_path.with_suffix(".jpg")
        mp4_target = out_path / rel_path.with_suffix(".mp4")
        return jpg_target, mp4_target

    def _target_exists_blocked(self, jpg_target: Path, mp4_target: Path) -> str | None:
        if jpg_target.exists() and self.options["photo_exist_action"] == "skip":
            return "status_photo_exists"
        if mp4_target.exists() and self.options["video_exist_action"] == "skip":
            return "status_video_exists"
        return None

    def run(self):
        out_path = Path(self.options["output_dir"])
        out_path.mkdir(parents=True, exist_ok=True)

        total = len(self.tasks)
        embedded_success = 0
        pair_success = 0
        exists_skip = 0
        static_skip = 0
        failed = 0

        for index, task in enumerate(self.tasks):
            progress_percent = int(((index + 1) / total) * 100) if total else 0
            task_type = task["type"]

            if task_type == "type_static":
                static_skip += 1
                self.row_update.emit(index, "status_skip_static")
                self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")
                continue

            jpg_target, mp4_target = self._target_paths(task, out_path)
            blocked_status = self._target_exists_blocked(jpg_target, mp4_target)
            if blocked_status is not None:
                exists_skip += 1
                self.row_update.emit(index, blocked_status)
                self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")
                continue

            jpg_target.parent.mkdir(parents=True, exist_ok=True)
            mp4_target.parent.mkdir(parents=True, exist_ok=True)

            try:
                if task_type == "type_embedded":
                    self.row_update.emit(index, "status_splitting")
                    split_live_photo(str(task["img_path"]), str(jpg_target.parent))
                    embedded_success += 1
                    self.row_update.emit(index, "status_split_success")
                else:
                    self.row_update.emit(index, "status_pair_copying")
                    shutil.copy2(task["img_path"], jpg_target)
                    shutil.copy2(task["mp4_path"], mp4_target)
                    _apply_source_timestamp(jpg_target, task["img_path"])
                    _apply_source_timestamp(mp4_target, task["mp4_path"])
                    pair_success += 1
                    self.row_update.emit(index, "status_pair_success")
            except Exception as exc:
                failed += 1
                self.row_update.emit(index, f"status_failed|{str(exc)[:36]}")

            self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")

        self.finished.emit(
            {
                "embedded_success": embedded_success,
                "pair_success": pair_success,
                "exists_skip": exists_skip,
                "static_skip": static_skip,
                "failed": failed,
                "out_path": str(out_path),
            }
        )


class MainWindow(FramelessMainWindow):
    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("华为LivePhoto批量分离工具")
        self._title_bar_height = 36
        if not self._embedded:
            self.resize(1280, 820)
            self._set_blue_title_bar()

        self.lang = DEFAULT_LANGUAGE
        self._last_status_key = "waiting_source"
        self._last_status_kwargs: dict = {}
        self.file_list: list[dict] = []
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
        row2.setSpacing(10)
        self.output_label = BodyLabel(self.tr("output_dir"), self)
        self.output_edit = LineEdit(self)
        self.output_edit.setReadOnly(False)
        self.output_edit.setPlaceholderText(self.tr("output_placeholder"))
        self.btn_output = PushButton(self.tr("choose_output"), self)
        self.btn_output.setIcon(_pick_icon("SAVE", "DOWNLOAD"))
        self.btn_output.clicked.connect(self.browse_output)
        row2.addWidget(self.output_label)
        row2.addWidget(self.output_edit, 1)
        row2.addWidget(self.btn_output)

        if not self._embedded:
            path_layout.addLayout(row1)
        path_layout.addLayout(row2)

        option_card = CardWidget(self)
        option_layout = QVBoxLayout(option_card)
        option_layout.setContentsMargins(16, 14, 16, 14)
        option_layout.setSpacing(10)

        row3 = QHBoxLayout()
        row3.setSpacing(12)
        self.include_subdirs_check = CheckBox(self.tr("scan_subdirs"), self)
        self.include_subdirs_check.setChecked(True)
        self.include_subdirs_check.toggled.connect(self.scan_files)
        row3.addWidget(self.include_subdirs_check)
        row3.addStretch(1)
        option_layout.addLayout(row3)

        self.output_settings_label = BodyLabel(self.tr("processing_options"), self)
        self.output_settings_label.setStyleSheet("font-weight: 600;")
        option_layout.addWidget(self.output_settings_label)

        exists_row = QHBoxLayout()
        exists_row.setSpacing(12)
        self.photo_exists_label = BodyLabel(self.tr("photo_exists"), self)
        self.photo_skip_radio = RadioButton(self.tr("skip"), self)
        self.photo_overwrite_radio = RadioButton(self.tr("overwrite"), self)
        self.photo_skip_radio.setChecked(True)
        self.video_exists_label = BodyLabel(self.tr("video_exists"), self)
        self.video_skip_radio = RadioButton(self.tr("skip"), self)
        self.video_overwrite_radio = RadioButton(self.tr("overwrite"), self)
        self.video_skip_radio.setChecked(True)
        exists_row.addWidget(self.photo_exists_label)
        exists_row.addWidget(self.photo_skip_radio)
        exists_row.addWidget(self.photo_overwrite_radio)
        exists_row.addSpacing(18)
        exists_row.addWidget(self.video_exists_label)
        exists_row.addWidget(self.video_skip_radio)
        exists_row.addWidget(self.video_overwrite_radio)
        exists_row.addStretch(1)
        option_layout.addLayout(exists_row)

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
        self.table.setColumnCount(4)
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
        self.table.setSortingEnabled(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(36)

        table_layout.addLayout(hint_row)
        table_layout.addWidget(self.table)

        action_card = CardWidget(self)
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(16, 12, 16, 12)
        action_layout.setSpacing(8)

        row4 = QHBoxLayout()
        row4.setSpacing(8)
        self.btn_scan = PushButton(self.tr("rescan"), self)
        self.btn_scan.setIcon(_pick_icon("SYNC", "UPDATE"))
        self.btn_scan.clicked.connect(self.scan_files)
        self.btn_clear = PushButton(self.tr("clear_list"), self)
        self.btn_clear.setIcon(_pick_icon("DELETE", "REMOVE"))
        self.btn_clear.clicked.connect(self.clear_list)
        self.btn_start = PrimaryPushButton(self.tr("start_split"), self)
        self.btn_start.setIcon(_pick_icon("PLAY", "SEND"))
        self.btn_start.clicked.connect(self.start_processing)
        row4.addWidget(self.btn_scan)
        row4.addWidget(self.btn_clear)
        row4.addStretch(1)
        row4.addWidget(self.btn_start)
        action_layout.addLayout(row4)

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

        self._init_default_output_dir()
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
        for btn in (self.titleBar.minBtn, self.titleBar.maxBtn):
            btn.setNormalColor("#1F2937")
            btn.setHoverColor("#1F2937")
            btn.setPressedColor("#1F2937")
            btn.setNormalBackgroundColor("#00000000")
            btn.setHoverBackgroundColor("#4DFFFFFF")
            btn.setPressedBackgroundColor("#80FFFFFF")

        self.titleBar.closeBtn.setNormalColor("#1F2937")
        self.titleBar.closeBtn.setHoverColor("#FFFFFF")
        self.titleBar.closeBtn.setPressedColor("#FFFFFF")
        self.titleBar.closeBtn.setNormalBackgroundColor("#00000000")
        self.titleBar.closeBtn.setHoverBackgroundColor("#E81123")
        self.titleBar.closeBtn.setPressedBackgroundColor("#F1707A")

    def _sync_title_bar(self):
        if not hasattr(self, "titleBar"):
            return
        self.titleBar.move(0, 0)
        self.titleBar.resize(self.width(), self._title_bar_height)
        self.titleBar.raise_()

    def showEvent(self, e):
        super().showEvent(e)
        if not self._embedded:
            self._sync_title_bar()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self._embedded:
            self._sync_title_bar()

    def tr(self, key: str, **kwargs) -> str:
        text = TRANSLATIONS.get(self.lang, TRANSLATIONS["zh"]).get(key, key)
        return text.format(**kwargs) if kwargs else text

    def _table_headers(self) -> list[str]:
        return [self.tr("table_image"), self.tr("table_type"), self.tr("table_video"), self.tr("table_status")]

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
        self.output_label.setText(self.tr("output_dir"))
        self.output_edit.setPlaceholderText(self.tr("output_placeholder"))
        self.btn_output.setText(self.tr("choose_output"))
        self.include_subdirs_check.setText(self.tr("scan_subdirs"))
        self.output_settings_label.setText(self.tr("processing_options"))
        self.photo_exists_label.setText(self.tr("photo_exists"))
        self.photo_skip_radio.setText(self.tr("skip"))
        self.photo_overwrite_radio.setText(self.tr("overwrite"))
        self.video_exists_label.setText(self.tr("video_exists"))
        self.video_skip_radio.setText(self.tr("skip"))
        self.video_overwrite_radio.setText(self.tr("overwrite"))
        self.drop_hint.setText(self.tr("drop_hint"))
        self.table.setHorizontalHeaderLabels(self._table_headers())
        self.btn_scan.setText(self.tr("rescan"))
        self.btn_clear.setText(self.tr("clear_list"))
        self.btn_start.setText(self.tr("start_split"))
        self._set_status_text(self._last_status_key, **self._last_status_kwargs)
        self._refresh_table_language()

    def _refresh_table_language(self):
        for row, task in enumerate(self.file_list):
            type_item = self.table.item(row, 1)
            video_item = self.table.item(row, 2)
            status_item = self.table.item(row, 3)
            if type_item is not None:
                type_item.setText(self.tr(task["type"]))
            if video_item is not None:
                video_item.setText(self.tr(task["has_mp4_text"]))
            if status_item is not None:
                status_item.setText(self._display_status(task["status"]))

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

    def _init_default_output_dir(self):
        pics_dir = _get_windows_pictures_dir() or (Path.home() / "Pictures")
        base = pics_dir / "HuaweiLivePhotoSplit_Output"
        try:
            base.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.output_edit.setText(str(base))

    def _settings_payload(self) -> dict:
        return {
            "language": self.lang,
            "input_dir": self.input_edit.text().strip(),
            "output_dir": self.output_edit.text().strip(),
            "include_subdirs": self.include_subdirs_check.isChecked(),
            "photo_exist_action": "skip" if self.photo_skip_radio.isChecked() else "overwrite",
            "video_exist_action": "skip" if self.video_skip_radio.isChecked() else "overwrite",
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
        self.output_edit.editingFinished.connect(self._save_settings)
        for widget in (
            self.include_subdirs_check,
            self.photo_skip_radio,
            self.photo_overwrite_radio,
            self.video_skip_radio,
            self.video_overwrite_radio,
        ):
            widget.toggled.connect(lambda _checked=False: self._save_settings())

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
            output_dir = str(data.get("output_dir", "")).strip()
            if input_dir:
                self.input_edit.setText(input_dir)
            if output_dir:
                self.output_edit.setText(output_dir)

            self.include_subdirs_check.setChecked(bool(data.get("include_subdirs", True)))
            self.photo_skip_radio.setChecked(data.get("photo_exist_action", "skip") != "overwrite")
            self.photo_overwrite_radio.setChecked(data.get("photo_exist_action", "skip") == "overwrite")
            self.video_skip_radio.setChecked(data.get("video_exist_action", "skip") != "overwrite")
            self.video_overwrite_radio.setChecked(data.get("video_exist_action", "skip") == "overwrite")
        finally:
            self._suspend_settings_save = False

    def browse_input(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("dialog_choose_source"))
        if not folder:
            return
        self.input_edit.setText(folder)
        self.output_edit.setText(str(Path(folder) / "Split_Output"))
        self._save_settings()
        self.scan_files()

    def browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("dialog_choose_output"))
        if not folder:
            return
        Path(folder).mkdir(parents=True, exist_ok=True)
        self.output_edit.setText(folder)
        self._save_settings()

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

        recursive = self.include_subdirs_check.isChecked()
        existing = {task["img_path"].resolve() for task in self.file_list}
        img_files: list[tuple[Path, Path | None]] = []

        for path in paths:
            if path.is_dir():
                iterator = path.rglob("*") if recursive else path.glob("*")
                img_files.extend((candidate, path) for candidate in iterator if _is_image_file(candidate))
            elif _is_image_file(path):
                img_files.append((path, path.parent))

        added = 0
        for img_path, base_dir in sorted(img_files, key=lambda item: str(item[0])):
            resolved = img_path.resolve()
            if resolved in existing:
                continue
            self._append_scan_row(_make_task(img_path, base_dir))
            existing.add(resolved)
            added += 1

        if added:
            self.progress.setValue(0)
            self._set_status_text("drop_added", added=added, count=len(self.file_list))
            if not self.input_edit.text().strip():
                first_dir = next((p for p in paths if p.is_dir()), None)
                if first_dir is None:
                    first_file = next((p for p in paths if p.is_file()), None)
                    first_dir = first_file.parent if first_file is not None else None
                if first_dir is not None:
                    self.input_edit.setText(str(first_dir))
                    self.output_edit.setText(str(first_dir / "Split_Output"))
                    self._save_settings()
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
        output_dir_text = self.output_edit.text().strip()
        output_dir = Path(output_dir_text) if output_dir_text else None
        self._scan_worker = ScanWorker(input_dir, self.include_subdirs_check.isChecked(), output_dir)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.row_ready.connect(self._append_scan_row)
        self._scan_worker.finished.connect(self._scan_finished)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.start()

    def _append_scan_row(self, task: dict):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(task["rel_path"])))
        self.table.setItem(row, 1, QTableWidgetItem(self.tr(task["type"])))
        self.table.setItem(row, 2, QTableWidgetItem(self.tr(task["has_mp4_text"])))
        self.table.setItem(row, 3, QTableWidgetItem(self._display_status(task["status"])))
        self.file_list.append(task)

    def _scan_finished(self, count: int, processable: int):
        if count == 0:
            self._set_status_text("scan_none_status")
            self._notify(self.tr("scan_complete_title"), self.tr("scan_none_content"), is_error=True)
            return
        self._set_status_text("scan_done_status", count=count, processable=processable)
        self._notify(self.tr("scan_complete_title"), self.tr("scan_done_content", count=count, processable=processable))

    def start_processing(self):
        if self.is_processing:
            return
        if not self.file_list:
            self._notify(self.tr("cannot_start_title"), self.tr("cannot_start_content"), is_error=True)
            return

        input_dir = self.input_edit.text().strip()
        output_dir = self.output_edit.text().strip()
        if not input_dir or not output_dir:
            self._notify(self.tr("missing_paths_title"), self.tr("missing_paths_content"), is_error=True)
            return

        if Path(input_dir).resolve() == Path(output_dir).resolve():
            reply = QMessageBox.question(
                self,
                self.tr("risk_title"),
                self.tr("same_dir_warning"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.is_processing = True
        self.btn_start.setEnabled(False)
        self.btn_scan.setEnabled(False)
        self.btn_clear.setEnabled(False)
        self.progress.setValue(0)
        self._set_status_text("preparing")
        self._save_settings()

        options = {
            "output_dir": output_dir,
            "photo_exist_action": "skip" if self.photo_skip_radio.isChecked() else "overwrite",
            "video_exist_action": "skip" if self.video_skip_radio.isChecked() else "overwrite",
        }

        self._process_thread = QThread(self)
        self._process_worker = ProcessWorker(list(self.file_list), options)
        self._process_worker.moveToThread(self._process_thread)
        self._process_thread.started.connect(self._process_worker.run)
        self._process_worker.row_update.connect(self._update_row_status)
        self._process_worker.progress_update.connect(self._update_progress)
        self._process_worker.finished.connect(self._processing_finished)
        self._process_worker.finished.connect(self._process_thread.quit)
        self._process_worker.finished.connect(self._process_worker.deleteLater)
        self._process_thread.finished.connect(self._process_thread.deleteLater)
        self._process_thread.start()

    def _update_row_status(self, row: int, status_text: str):
        if 0 <= row < self.table.rowCount():
            if 0 <= row < len(self.file_list):
                self.file_list[row]["status"] = status_text
            self.table.setItem(row, 3, QTableWidgetItem(self._display_status(status_text)))
            self.table.scrollToItem(self.table.item(row, 3))

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
            embedded=result["embedded_success"],
            pairs=result["pair_success"],
        )

        processed_count = result["embedded_success"] + result["pair_success"]
        msg = self.tr(
            "task_done_message",
            embedded_success=result["embedded_success"],
            pair_success=result["pair_success"],
            exists_skip=result["exists_skip"],
            static_skip=result["static_skip"],
            failed=result["failed"],
            out_path=result["out_path"],
        )
        QMessageBox.information(self, self.tr("task_done_title"), msg)
        self._notify(self.tr("task_done_title"), self.tr("process_done_notice", count=processed_count))


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
