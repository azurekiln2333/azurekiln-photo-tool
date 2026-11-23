"""目录比对页：把 B 目录中与 A 目录内容完全一致的文件移入回收站。

准确性优先：扫描与校验全部委托给 ``duplicate_scan_core``（大小 → 完整 SHA-256 →
逐字节比对，三者缺一不可），本文件只负责界面、线程调度与回收流程。
本页不修改、不删除 A 目录中的任何文件，只把 B 中的副本移入回收站。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import file_context_menu as fcm
from dedupe_table_scroll import configure_result_table_scrolling
from duplicate_scan_core import (
    FileEntry,
    ScanCancelled,
    ScanResult,
    find_cross_duplicates,
    recycle_duplicate,
    validate_compare_roots,
)
from elevation_hint import attach_elevation_hint
from file_context_menu import FileContextMenu
from media_thumbnail import PreviewPanel, ThumbnailLoader
from scan_record_core import MODE_COMPARE, ScanRecord, load_record, save_record
from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QSize,
    QThread,
    QTimer,
    Qt,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QDesktopServices,
    QFont,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QMessageBox,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from qframelesswindow import FramelessMainWindow, StandardTitleBar

from timestamp_fix_gui import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    BodyLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SubtitleLabel,
    TableView,
    Theme,
    _get_windows_pictures_dir,
    _safe_resolve,
    setTheme,
    setThemeColor,
)


APP_NAME = "DirCompareGUI"
SETTINGS_FILENAME = "dir_compare_settings.json"

THUMBNAIL_SIZE = 96
ROW_HEIGHT = THUMBNAIL_SIZE + 8
PREVIEW_SIZE = 256
HASH_THREAD_OPTIONS = (1, 2, 4, 8, 16)
UI_UPDATE_DRAIN_ROWS = 200
RECYCLE_BATCH_SIZE = 20

SCOPE_ALL = "all"
SCOPE_MEDIA = "media"
SCOPES = (SCOPE_ALL, SCOPE_MEDIA)

KIND_DUPLICATE = "duplicate"
KIND_MISMATCH = "mismatch"
KIND_ISSUE = "issue"

COL_CHECK = 0
COL_THUMB_B = 1
COL_THUMB_A = 2
COL_PATH_B = 3
COL_PATH_A = 4
COL_SIZE = 5
COL_MTIME = 6
COL_HASH = 7
COL_STATUS = 8
COLUMN_COUNT = 9

KNOWN_ROOT_CODES = ("a_missing", "b_missing", "same_root", "b_inside_a", "a_inside_b")

TRANSLATIONS = {
    "zh": {
        "app_title": "目录比对",
        "header_title": "目录比对",
        "header_subtitle": "用「大小 → 完整 SHA-256 → 逐字节比对」三重校验，"
        "把 B 目录中与 A 目录完全一致的文件移入回收站",
        "header_note": "A 目录只读，绝不修改或删除；B 目录中同一内容的全部副本都会被列出。"
        "只提供移入回收站，不提供永久删除。",
        "language": "界面语言",
        "root_a": "A 目录（保留库，只读）",
        "root_b": "B 目录（待清理）",
        "root_a_placeholder": "选择作为参照的 A 目录",
        "root_b_placeholder": "选择待清理的 B 目录",
        "choose_dir": "选择目录",
        "scope": "扫描范围",
        "scope_all": "所有文件",
        "scope_media": "仅照片/视频",
        "hash_threads": "Hash 线程",
        "byte_verify": "执行前再次逐字节复核",
        "btn_scan": "开始扫描",
        "btn_stop_scan": "停止扫描",
        "btn_recycle": "移入回收站",
        "btn_pause": "暂停",
        "btn_resume": "继续",
        "btn_stop_recycle": "停止回收",
        "table_check": "☐",
        "table_thumb_b": "B 预览",
        "table_thumb_a": "A 预览",
        "table_path_b": "B 文件",
        "table_path_a": "对应 A 文件",
        "table_size": "大小",
        "table_mtime": "修改时间",
        "table_hash": "SHA-256",
        "table_status": "状态",
        "btn_select_all": "全选",
        "btn_select_none": "全不选",
        "btn_select_invert": "反选",
        "btn_export_record": "导出记录",
        "btn_import_record": "导入记录",
        "record_export_title": "导出扫描记录",
        "record_import_title": "导入扫描记录",
        "record_filter": "扫描记录 (*.json)",
        "record_export_ok": "已导出 {count} 行扫描记录",
        "record_export_failed": "导出失败：{error}",
        "record_import_ok": "已导入记录：可回收 {count} 个文件，本轮回收将强制逐字节复核",
        "record_import_failed": "导入失败：{error}",
        "record_import_cancelled": "该记录来自已取消的扫描，导入后不可回收",
        "record_io_busy": "正在读写扫描记录，请稍候。",
        "record_none": "当前没有可导出的扫描结果",
        "record_imported_badge": "（历史记录）",
        "record_saved_title": "扫描记录",
        "record_saving": "正在保存扫描记录",
        "record_loading": "正在读取扫描记录",
        "preview_b": "B 文件",
        "preview_a": "对应 A 文件",
        "preview_issue": "问题文件",
        "tabs_hint": "勾选要回收的 B 文件；双击行打开文件，右键查看更多操作。",
        "waiting": "等待选择 A、B 目录",
        "scanning": "正在扫描",
        "status_scanning_stage": "{stage} {done}/{total}",
        "stage_enumerate": "枚举文件",
        "stage_hash": "计算哈希",
        "stage_verify": "逐字节复核",
        "stage_recycle": "回收",
        "scan_done": "扫描完成：可回收 {count} 个文件，共 {total} 个文件",
        "scan_none": "未找到与 A 完全一致的文件",
        "scan_cancelled": "扫描已取消，结果不可执行回收，请重新扫描",
        "scan_stale": "记录已失效，结果不可回收，请重新扫描",
        "status_cancelled": "已取消，请重新扫描",
        "scan_failed": "扫描失败：{error}",
        "summary_ready": "可回收 {count} 个 / 共 {total}",
        "summary_detail": "校验不一致 {mismatch}；读取问题 {issue}",
        "summary_done": "已回收 {success} / 跳过 {skipped} / 失败 {failed} / "
        "校验不一致 {mismatch} / 读取问题 {issue}",
        "summary_empty": "",
        "status_pending": "待处理",
        "status_recycled": "已回收",
        "status_skipped": "已跳过：{reason}",
        "status_failed": "失败：{reason}",
        "status_mismatch": "校验不一致",
        "status_issue": "读取问题：{message}",
        "status_processing": "处理中",
        "status_paused": "已暂停",
        "status_stopping": "正在停止",
        "recycle_done_status": "回收完成：已回收 {success}，跳过 {skipped}，失败 {failed}",
        "status_stopped": "已停止：已回收 {success}，跳过 {skipped}，失败 {failed}",
        "skip_target_missing": "目标文件不存在",
        "skip_keeper_missing": "参照文件不存在",
        "skip_target_changed": "目标文件已变化",
        "skip_keeper_changed": "参照文件已变化",
        "skip_same_path": "路径相同",
        "skip_content_differs": "内容已不一致",
        "skip_read_error": "读取失败",
        "fail_send2trash_unavailable": "缺少 send2trash",
        "confirm_title": "确认移入回收站",
        "confirm_content": "将把 {count} 个文件（共 {size}）移入回收站，不会永久删除。\n"
        "执行前会对每个文件重新校验，任一校验不通过则跳过。确定继续？",
        "missing_trash_title": "缺少回收站支持",
        "missing_trash_content": "当前环境缺少 send2trash，无法移入回收站。请先安装 send2trash。",
        "cannot_start_title": "无法开始",
        "cannot_start_content": "当前没有可回收的文件。",
        "cannot_start_cancelled": "扫描已取消，请重新扫描后再执行回收。",
        "cannot_start_stale": "记录已失效，请重新扫描后再执行回收。",
        "invalid_root_title": "无法扫描",
        "invalid_root_a_missing": "A 目录不存在或不是目录",
        "invalid_root_b_missing": "B 目录不存在或不是目录",
        "invalid_root_same_root": "A 与 B 是同一个目录",
        "invalid_root_b_inside_a": "B 目录位于 A 目录内部",
        "invalid_root_a_inside_b": "A 目录位于 B 目录内部",
        "recycle_done_title": "回收完成",
        "recycle_done_message": "已回收: {success}\n跳过: {skipped}\n失败: {failed}",
        "recycle_blocked_busy": "正在处理中，请稍候。",
        "menu_open": "打开文件",
        "menu_open_folder": "打开所在目录",
        "menu_open_a": "打开对应 A 文件",
        "menu_open_a_folder": "打开 A 文件所在目录",
        "menu_copy_path": "复制路径",
        "menu_copy_files": "复制文件",
        "menu_cut_files": "剪切文件",
        "menu_system": "系统右键菜单...",
    },
    "en": {
        "app_title": "Folder Compare",
        "header_title": "Folder Compare",
        "header_subtitle": "Triple-check (size → full SHA-256 → byte compare) moves files in "
        "folder B that are identical to folder A into the recycle bin",
        "header_note": "Folder A is read-only and never modified or deleted. Every copy of the "
        "same content in B is listed. Recycle bin only, no permanent delete.",
        "language": "Language",
        "root_a": "Folder A (reference, read-only)",
        "root_b": "Folder B (to clean)",
        "root_a_placeholder": "Choose the reference folder A",
        "root_b_placeholder": "Choose the folder B to clean",
        "choose_dir": "Choose folder",
        "scope": "Scan scope",
        "scope_all": "All files",
        "scope_media": "Photos/videos only",
        "hash_threads": "Hash threads",
        "byte_verify": "Byte-verify again before recycle",
        "btn_scan": "Start scan",
        "btn_stop_scan": "Stop scan",
        "btn_recycle": "Move to recycle bin",
        "btn_pause": "Pause",
        "btn_resume": "Resume",
        "btn_stop_recycle": "Stop recycle",
        "table_check": "☐",
        "table_thumb_b": "B preview",
        "table_thumb_a": "A preview",
        "table_path_b": "B file",
        "table_path_a": "Matching A file",
        "table_size": "Size",
        "table_mtime": "Modified",
        "table_hash": "SHA-256",
        "table_status": "Status",
        "btn_select_all": "Select all",
        "btn_select_none": "Select none",
        "btn_select_invert": "Invert",
        "btn_export_record": "Export record",
        "btn_import_record": "Import record",
        "record_export_title": "Export scan record",
        "record_import_title": "Import scan record",
        "record_filter": "Scan record (*.json)",
        "record_export_ok": "Exported {count} row(s) to the scan record",
        "record_export_failed": "Export failed: {error}",
        "record_import_ok": "Record imported: {count} recyclable file(s); this run always byte-verifies",
        "record_import_failed": "Import failed: {error}",
        "record_import_cancelled": "This record came from a cancelled scan and cannot be recycled",
        "record_io_busy": "A scan record is being read or written, please wait.",
        "record_none": "There is no scan result to export",
        "record_imported_badge": " (imported record)",
        "record_saved_title": "Scan record",
        "record_saving": "Saving scan record",
        "record_loading": "Reading scan record",
        "preview_b": "B file",
        "preview_a": "Matching A file",
        "preview_issue": "Problem file",
        "tabs_hint": "Check the B files to recycle. Double-click to open; right-click for more.",
        "waiting": "Waiting for folders A and B",
        "scanning": "Scanning",
        "status_scanning_stage": "{stage} {done}/{total}",
        "stage_enumerate": "Enumerating",
        "stage_hash": "Hashing",
        "stage_verify": "Byte verifying",
        "stage_recycle": "Recycling",
        "scan_done": "Scan complete: {count} recyclable of {total} file(s)",
        "scan_none": "No file identical to folder A was found",
        "scan_cancelled": "Scan cancelled; results cannot be recycled. Please rescan.",
        "scan_stale": "This record is stale; results cannot be recycled. Please rescan.",
        "status_cancelled": "Cancelled, please rescan",
        "scan_failed": "Scan failed: {error}",
        "summary_ready": "Recyclable {count} / total {total}",
        "summary_detail": "Mismatch {mismatch}; read issues {issue}",
        "summary_done": "Recycled {success} / skipped {skipped} / failed {failed} / "
        "mismatch {mismatch} / read issues {issue}",
        "summary_empty": "",
        "status_pending": "Pending",
        "status_recycled": "Recycled",
        "status_skipped": "Skipped: {reason}",
        "status_failed": "Failed: {reason}",
        "status_mismatch": "Verification mismatch",
        "status_issue": "Read issue: {message}",
        "status_processing": "Processing",
        "status_paused": "Paused",
        "status_stopping": "Stopping",
        "recycle_done_status": "Recycle complete: {success} recycled, {skipped} skipped, {failed} failed",
        "status_stopped": "Stopped: {success} recycled, {skipped} skipped, {failed} failed",
        "skip_target_missing": "target file is missing",
        "skip_keeper_missing": "reference file is missing",
        "skip_target_changed": "target file changed",
        "skip_keeper_changed": "reference file changed",
        "skip_same_path": "same path",
        "skip_content_differs": "content no longer matches",
        "skip_read_error": "read error",
        "fail_send2trash_unavailable": "send2trash unavailable",
        "confirm_title": "Confirm recycle",
        "confirm_content": "Move {count} file(s) ({size}) to the recycle bin. Nothing is "
        "permanently deleted.\nEach file is revalidated right before recycling; any check "
        "failure skips it. Continue?",
        "missing_trash_title": "Recycle bin unavailable",
        "missing_trash_content": "send2trash is not available. Install send2trash first.",
        "cannot_start_title": "Cannot start",
        "cannot_start_content": "There is no recyclable file.",
        "cannot_start_cancelled": "The scan was cancelled. Please rescan before recycling.",
        "cannot_start_stale": "This record is stale. Please rescan before recycling.",
        "invalid_root_title": "Cannot scan",
        "invalid_root_a_missing": "Folder A does not exist or is not a folder",
        "invalid_root_b_missing": "Folder B does not exist or is not a folder",
        "invalid_root_same_root": "A and B are the same folder",
        "invalid_root_b_inside_a": "Folder B is inside folder A",
        "invalid_root_a_inside_b": "Folder A is inside folder B",
        "recycle_done_title": "Recycle complete",
        "recycle_done_message": "Recycled: {success}\nSkipped: {skipped}\nFailed: {failed}",
        "recycle_blocked_busy": "A task is running, please wait.",
        "menu_open": "Open file",
        "menu_open_folder": "Show in folder",
        "menu_open_a": "Open matching A file",
        "menu_open_a_folder": "Show A file in folder",
        "menu_copy_path": "Copy path",
        "menu_copy_files": "Copy files",
        "menu_cut_files": "Cut files",
        "menu_system": "System context menu...",
    },
}


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
            return Path(appdata) / APP_NAME / SETTINGS_FILENAME
    return Path.home() / ".config" / APP_NAME / SETTINGS_FILENAME


def _format_size(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(max(0, int(size or 0)))
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def _format_mtime(mtime_ns: int) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(mtime_ns) / 1_000_000_000))
    except Exception:
        return "-"


def _default_thread_count() -> int:
    cpu_count = os.cpu_count() or 4
    for option in reversed(HASH_THREAD_OPTIONS):
        if option <= cpu_count:
            return option
    return HASH_THREAD_OPTIONS[0]


def _is_under(path: Path, root: Path) -> bool:
    """判断 path 是否位于 root 之下（大小写不敏感，仅用于展示分栏）。"""
    try:
        return str(_safe_resolve(path)).casefold().startswith(
            str(_safe_resolve(root)).casefold() + os.sep
        )
    except Exception:
        return False


def _reveal_in_explorer(path: Path):
    try:
        subprocess.run(["explorer", "/select,", str(path)], check=False)
    except Exception:
        pass


def _open_path(path: Path):
    try:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    except Exception:
        pass


@dataclass
class CompareRow:
    """表格一行：已确认一致的副本 / 校验不一致 / 读取问题。"""

    kind: str                                    # "duplicate" | "mismatch" | "issue"
    target: FileEntry | None = None              # B 文件
    keeper: FileEntry | None = None              # A 参照文件
    sha256: str = ""
    size: int = 0
    mtime_ns: int = 0
    issue_path: Path | None = None
    issue_column: int = COL_PATH_B
    checked: bool = False
    status: str = "status_pending"

    def is_checkable(self) -> bool:
        """只有扫描阶段已逐字节确认一致的 B 副本才能勾选回收。"""
        return self.kind == KIND_DUPLICATE and self.status == "status_pending"

    def primary_path(self) -> Path | None:
        if self.target is not None:
            return self.target.path
        return self.issue_path

    def keeper_path(self) -> Path | None:
        return self.keeper.path if self.keeper is not None else None


class CompareTableModel(QAbstractTableModel):
    def __init__(self, rows: list[CompareRow], owner: "MainWindow"):
        super().__init__(owner)
        self.rows = rows
        self.owner = owner
        self.mismatch_bg = QBrush(QColor("#FFF4E5"))
        self.issue_bg = QBrush(QColor("#FEF3F2"))
        self.mismatch_fg = QBrush(QColor("#B54708"))
        self.issue_fg = QBrush(QColor("#B42318"))

    # ---- Qt 模型接口 ----
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else COLUMN_COUNT

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        headers = self.owner._table_headers()
        if 0 <= section < len(headers):
            return headers[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.rows)):
            return None
        row = self.rows[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_value(row, column)
        if role == Qt.ItemDataRole.CheckStateRole and column == COL_CHECK:
            if not self._checkable(row):
                return None
            return Qt.CheckState.Checked if row.checked else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.DecorationRole and column in (COL_THUMB_B, COL_THUMB_A):
            return self._thumbnail(row, column)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(row, column)
        if role == Qt.ItemDataRole.BackgroundRole:
            if row.kind == KIND_MISMATCH:
                return self.mismatch_bg
            if row.kind == KIND_ISSUE:
                return self.issue_bg
            return None
        if role == Qt.ItemDataRole.ForegroundRole:
            if row.kind == KIND_MISMATCH:
                return self.mismatch_fg
            if row.kind == KIND_ISSUE:
                return self.issue_fg
            if row.status.startswith(("status_recycled", "status_skipped")):
                return QBrush(QColor("#667085"))
            return None
        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or not (0 <= index.row() < len(self.rows)):
            return False
        if role != Qt.ItemDataRole.CheckStateRole or index.column() != COL_CHECK:
            return False
        row = self.rows[index.row()]
        if not self._checkable(row):
            return False
        checked = Qt.CheckState(value) == Qt.CheckState.Checked
        if row.checked == checked:
            return True
        row.checked = checked
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        self.owner._on_row_check_changed()
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        row = self.rows[index.row()]
        if index.column() == COL_CHECK and self._checkable(row):
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    # ---- 展示 ----
    def _checkable(self, row: CompareRow) -> bool:
        """取消/失效的历史结果全部禁勾；导入未处理行仍可勾。"""
        if not row.is_checkable():
            return False
        return not getattr(self.owner, "_scan_cancelled", False) and not getattr(
            self.owner, "_scan_stale", False
        )
    def _display_value(self, row: CompareRow, column: int) -> str:
        if column == COL_CHECK:
            return ""
        if column in (COL_THUMB_B, COL_THUMB_A):
            return ""
        if column == COL_PATH_B:
            if row.kind == KIND_ISSUE and row.issue_column == COL_PATH_B:
                return str(self._relative(row.issue_path, None))
            return str(row.target.relative_path) if row.target is not None else ""
        if column == COL_PATH_A:
            if row.kind == KIND_ISSUE and row.issue_column == COL_PATH_A:
                return str(self._relative(row.issue_path, None))
            return str(row.keeper.relative_path) if row.keeper is not None else ""
        if column == COL_SIZE:
            return _format_size(row.size) if row.size else ""
        if column == COL_MTIME:
            return _format_mtime(row.mtime_ns) if row.mtime_ns else ""
        if column == COL_HASH:
            return row.sha256[:12] if row.sha256 else "-"
        if column == COL_STATUS:
            return self.owner._display_status(row.status)
        return ""

    def _relative(self, path: Path | None, root: Path | None) -> Path:
        if path is None:
            return Path("")
        if root is not None:
            try:
                return path.relative_to(root)
            except Exception:
                pass
        return Path(path.name)

    def _thumbnail(self, row: CompareRow, column: int) -> QPixmap | None:
        path: Path | None = None
        if column == COL_THUMB_B:
            path = row.target.path if row.target is not None else (
                row.issue_path if row.issue_column == COL_PATH_B else None
            )
        else:
            path = row.keeper.path if row.keeper is not None else (
                row.issue_path if row.issue_column == COL_PATH_A else None
            )
        if path is None:
            return None
        return self.owner._thumbnail_for(path)

    def _tooltip(self, row: CompareRow, column: int) -> str | None:
        if column == COL_PATH_B:
            if row.kind == KIND_ISSUE and row.issue_column == COL_PATH_B:
                return str(row.issue_path)
            return str(row.target.path) if row.target is not None else None
        if column == COL_PATH_A:
            if row.kind == KIND_ISSUE and row.issue_column == COL_PATH_A:
                return str(row.issue_path)
            return str(row.keeper.path) if row.keeper is not None else None
        if column == COL_HASH:
            return row.sha256 or None
        if column == COL_STATUS:
            return self.owner._display_status(row.status)
        return None

    # ---- 批量更新 ----
    def reset_rows(self, rows: list[CompareRow]):
        self.beginResetModel()
        self.rows[:] = rows
        self.endResetModel()

    def update_row(self, row_index: int):
        if not (0 <= row_index < len(self.rows)):
            return
        self.dataChanged.emit(
            self.index(row_index, 0),
            self.index(row_index, COLUMN_COUNT - 1),
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.DecorationRole,
                Qt.ItemDataRole.CheckStateRole,
                Qt.ItemDataRole.BackgroundRole,
                Qt.ItemDataRole.ForegroundRole,
            ],
        )

    def refresh_cells(self, cells: list[tuple[int, int]]):
        if not cells:
            return
        for row_index, column in cells:
            if 0 <= row_index < len(self.rows):
                index = self.index(row_index, column)
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])

    def apply_check_mode(self, mode: str) -> int:
        """批量改勾选：只动可回收行，所有变更合并成一次 dataChanged。

        ``mode``：``"all"`` 全选 / ``"none"`` 全不选 / ``"invert"`` 反选。
        保留文件、异常、碰撞、已处理、取消/失效行一律跳过。
        """
        changed = 0
        first = -1
        last = -1
        for row_index, row in enumerate(self.rows):
            if not self._checkable(row):
                continue
            if mode == "all":
                desired = True
            elif mode == "none":
                desired = False
            else:
                desired = not row.checked
            if row.checked == desired:
                continue
            row.checked = desired
            changed += 1
            if first < 0:
                first = row_index
            last = row_index
        if changed:
            self.dataChanged.emit(
                self.index(first, COL_CHECK),
                self.index(last, COL_CHECK),
                [Qt.ItemDataRole.CheckStateRole],
            )
        return changed


class CompareContextMenu(FileContextMenu):
    """在共用右键菜单基础上追加"打开对应 A 文件 / A 文件所在目录"。

    复用 ``file_context_menu`` 的选中/定位/剪贴板/系统菜单能力，不另起一套。
    """

    def __init__(self, table, owner, path_provider, keeper_provider, language_provider, label_provider):
        super().__init__(table, owner, path_provider, language_provider)
        self.keeper_provider = keeper_provider
        self.label_provider = label_provider

    def _label(self, key: str) -> str:
        return self.label_provider(key)

    def show(self, pos):
        row = fcm._row_at(self.table, pos)
        if row < 0:
            return
        selected = fcm._selected_rows(self.table)
        if row not in selected:
            selected = [row]
            fcm._select_row(self.table, row)
        paths = [path for path in self.path_provider(row, selected) if path is not None]
        if not paths:
            return

        lang = self.language_provider()
        global_pos = self.table.viewport().mapToGlobal(pos)
        menu = QMenu(self.owner)
        keeper_paths = [path for path in self.keeper_provider(row) if path is not None]

        if len(paths) == 1:
            first_path = paths[0]
            act_open = menu.addAction(fcm._label(lang, "open"))
            act_open.triggered.connect(lambda _checked=False, p=first_path: _open_path(p))

        first_path = paths[0]
        act_reveal = menu.addAction(fcm._label(lang, "open_folder"))
        act_reveal.triggered.connect(lambda _checked=False, p=first_path: _reveal_in_explorer(p))

        if keeper_paths:
            keeper_path = keeper_paths[0]
            act_open_a = menu.addAction(self._label("menu_open_a"))
            act_open_a.triggered.connect(lambda _checked=False, p=keeper_path: _open_path(p))
            act_open_a_folder = menu.addAction(self._label("menu_open_a_folder"))
            act_open_a_folder.triggered.connect(
                lambda _checked=False, p=keeper_path: _reveal_in_explorer(p)
            )

        menu.addSeparator()
        act_copy_files = menu.addAction(fcm._label(lang, "copy_files"))
        act_copy_files.triggered.connect(
            lambda _checked=False: fcm._set_file_clipboard(self.owner, paths, cut=False)
        )
        act_cut_files = menu.addAction(fcm._label(lang, "cut_files"))
        act_cut_files.triggered.connect(
            lambda _checked=False: fcm._set_file_clipboard(self.owner, paths, cut=True)
        )
        act_copy_path = menu.addAction(self._label("menu_copy_path"))
        act_copy_path.triggered.connect(lambda _checked=False: fcm._copy_paths_text(paths))

        if sys.platform == "win32":
            menu.addSeparator()
            same_parent = len({str(path.parent) for path in paths}) == 1
            act_shell = menu.addAction(fcm._label(lang, "system_context_menu"))
            act_shell.setEnabled(fcm.HAS_SHELL_CONTEXT and same_parent)
            act_shell.triggered.connect(
                lambda _checked=False: QTimer.singleShot(
                    0,
                    lambda: fcm._show_explorer_context_menu(self.owner, paths, QCursor.pos()),
                )
            )

        menu.exec(global_pos)


class CompareScanWorker(QObject):
    """目录比对扫描 worker：只调用核心模块，绝不碰 UI。"""

    progress_update = pyqtSignal(str, int, int)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, root_a: Path, root_b: Path, scope: str, threads: int):
        super().__init__()
        self._root_a = root_a
        self._root_b = root_b
        self._scope = scope if scope in SCOPES else SCOPE_ALL
        self._threads = max(1, int(threads))
        self._cancel = False

    def request_stop(self):
        self._cancel = True

    def _should_cancel(self) -> bool:
        return self._cancel

    def _on_progress(self, stage: str, done: int, total: int):
        self.progress_update.emit(str(stage), int(done), int(total))

    def run(self):
        try:
            result = find_cross_duplicates(
                self._root_a,
                self._root_b,
                scope=self._scope,
                threads=self._threads,
                should_cancel=self._should_cancel,
                on_progress=self._on_progress,
            )
        except ValueError as exc:
            # validate_compare_roots 的 code（a_missing / same_root / ...）
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # 环境/权限类意外：不让异常穿透 Qt 事件循环
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(result)


class RecordSaveWorker(QObject):
    """扫描记录写入 worker：保存是大 JSON，放后台避免阻塞主线程。"""

    done = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self, path: Path, record: ScanRecord):
        super().__init__()
        self._path = Path(path)
        self._record = record

    def run(self):
        try:
            save_record(self._path, self._record)
        except (ValueError, OSError) as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.done.emit(len(self._record.row_states))


class RecordLoadWorker(QObject):
    """扫描记录读取 worker：完整解析校验成功才把记录交回主线程替换显示。"""

    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, path: Path):
        super().__init__()
        self._path = Path(path)

    def run(self):
        try:
            record = load_record(self._path, expected_mode=MODE_COMPARE)
        except (ValueError, OSError) as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # 不让意外异常穿透 Qt 事件循环
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.done.emit(record)


class RecycleWorker(QObject):
    """回收 worker：单文件粒度调用 recycle_duplicate，支持暂停/停止。"""

    row_update_batch = pyqtSignal(object)          # list[tuple[int, str]]
    progress_update = pyqtSignal(int, int)
    finished = pyqtSignal(dict)

    def __init__(self, items: list[tuple[int, FileEntry, FileEntry]], byte_verify: bool):
        super().__init__()
        self._items = list(items)
        self._byte_verify = bool(byte_verify)
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop_event = threading.Event()

    def set_paused(self, paused: bool):
        if paused:
            self._pause_event.clear()
        else:
            self._pause_event.set()

    def request_stop(self):
        self._stop_event.set()
        self._pause_event.set()

    def _wait_if_paused_or_stopped(self) -> bool:
        while not self._pause_event.wait(0.1):
            if self._stop_event.is_set():
                return True
        return self._stop_event.is_set()

    def _should_cancel(self) -> bool:
        return self._stop_event.is_set()

    def _emit_update_batch(self, updates: list[tuple[int, str]]):
        if updates:
            self.row_update_batch.emit(updates[:])
            updates.clear()

    def run(self):
        success = 0
        skipped = 0
        failed = 0
        completed = 0
        total = len(self._items)
        updates: list[tuple[int, str]] = []
        stopped = False
        self.progress_update.emit(0, total)

        for row_index, target, keeper in self._items:
            if self._wait_if_paused_or_stopped():
                stopped = True
                break
            try:
                outcome = recycle_duplicate(
                    target,
                    keeper,
                    byte_verify=self._byte_verify,
                    should_cancel=self._should_cancel,
                )
            except ScanCancelled:
                stopped = True
                break
            except Exception as exc:
                failed += 1
                updates.append((row_index, f"status_failed|{str(exc)[:80]}"))
            else:
                if outcome.status == "recycled":
                    success += 1
                    updates.append((row_index, "status_recycled"))
                elif outcome.status == "skipped":
                    skipped += 1
                    updates.append((row_index, f"status_skipped|{outcome.reason}"))
                else:
                    failed += 1
                    updates.append((row_index, f"status_failed|{outcome.reason}"))
            completed += 1
            if len(updates) >= RECYCLE_BATCH_SIZE:
                self._emit_update_batch(updates)
            self.progress_update.emit(completed, total)

        self._emit_update_batch(updates)
        self.finished.emit(
            {
                "success": success,
                "skipped": skipped,
                "failed": failed,
                "completed": completed,
                "total": total,
                "stopped": stopped or self._stop_event.is_set(),
            }
        )


class MainWindow(FramelessMainWindow):
    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("Folder Compare")
        self._title_bar_height = 36
        if not self._embedded:
            self.resize(1360, 880)
            self._set_blue_title_bar()

        self.lang = DEFAULT_LANGUAGE
        self._last_status_key = "waiting"
        self._last_status_kwargs: dict = {}
        self._scan_cancelled = False
        self._mismatch_count = 0
        self._issue_count = 0
        self._recycled_count = 0
        self._skipped_count = 0
        self._failed_count = 0
        self._has_scan = False
        self._scan_total = 0
        self.is_scanning = False
        self.is_recycling = False
        self._recycle_paused = False
        self._recycle_stopping = False
        self._pending_close = False

        self._scan_thread: QThread | None = None
        self._scan_worker: CompareScanWorker | None = None
        self._recycle_thread: QThread | None = None
        self._recycle_worker: RecycleWorker | None = None
        self._record_thread: QThread | None = None
        self._record_worker: QObject | None = None
        self._record_op: str = ""                    # "save" | "load"
        # 扫描时的完整结果与根/选项快照：导出只能用这份，不能读后来的控件值
        self._scan_result: ScanResult | None = None
        self._scan_snapshot: dict = {}
        self._scan_stale = False
        self._record_imported = False
        self._imported_record: ScanRecord | None = None

        self._process_update_queue: deque[tuple[int, str]] = deque()
        self._pending_recycle_result: dict | None = None
        self._drain_timer = QTimer(self)
        self._drain_timer.setInterval(10)
        self._drain_timer.timeout.connect(self._drain_queues)

        self._path_cells: dict[str, list[tuple[int, int]]] = {}
        self._settings_path = _get_settings_path()
        self._suspend_settings_save = False

        self.thumbnail_loader = ThumbnailLoader(size=THUMBNAIL_SIZE, parent=self)
        self.thumbnail_loader.thumbnail_ready.connect(self._on_thumbnail_ready)

        self.table_model = CompareTableModel([], self)

        self._build_ui()
        self._load_settings()
        self._apply_language()
        self._update_action_states()

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._on_about_to_quit)

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------
    def _build_ui(self):
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
        self.subtitle_label.setWordWrap(True)
        self.subtitle_note_label = BodyLabel(self.tr("header_note"), self)
        self.subtitle_note_label.setStyleSheet("color: #98A2B3;")
        self.subtitle_note_label.setWordWrap(True)

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
        self.elevation_hint = attach_elevation_hint(header_layout, self, lang=self.lang)
        if not self._embedded:
            header_layout.addLayout(language_row)

        # ---- 目录选择 ----
        path_card = CardWidget(self)
        path_layout = QVBoxLayout(path_card)
        path_layout.setContentsMargins(16, 14, 16, 14)
        path_layout.setSpacing(10)

        row_a = QHBoxLayout()
        row_a.setSpacing(10)
        self.root_a_label = BodyLabel(self.tr("root_a"), self)
        self.root_a_edit = LineEdit(self)
        self.root_a_edit.setReadOnly(False)
        self.root_a_edit.setPlaceholderText(self.tr("root_a_placeholder"))
        self.btn_root_a = PushButton(self.tr("choose_dir"), self)
        self.btn_root_a.setIcon(_pick_icon("FOLDER", "FOLDER_ADD"))
        self.btn_root_a.clicked.connect(lambda _checked=False: self.browse_root("a"))
        row_a.addWidget(self.root_a_label)
        row_a.addWidget(self.root_a_edit, 1)
        row_a.addWidget(self.btn_root_a)

        row_b = QHBoxLayout()
        row_b.setSpacing(10)
        self.root_b_label = BodyLabel(self.tr("root_b"), self)
        self.root_b_edit = LineEdit(self)
        self.root_b_edit.setReadOnly(False)
        self.root_b_edit.setPlaceholderText(self.tr("root_b_placeholder"))
        self.btn_root_b = PushButton(self.tr("choose_dir"), self)
        self.btn_root_b.setIcon(_pick_icon("FOLDER", "FOLDER_ADD"))
        self.btn_root_b.clicked.connect(lambda _checked=False: self.browse_root("b"))
        row_b.addWidget(self.root_b_label)
        row_b.addWidget(self.root_b_edit, 1)
        row_b.addWidget(self.btn_root_b)

        row_opts = QHBoxLayout()
        row_opts.setSpacing(12)
        self.scope_label = BodyLabel(self.tr("scope"), self)
        self.scope_combo = ComboBox(self)
        self.scope_combo.setFixedWidth(140)
        self.scope_combo.addItem(self.tr("scope_all"), userData=SCOPE_ALL)
        self.scope_combo.addItem(self.tr("scope_media"), userData=SCOPE_MEDIA)
        self.byte_verify_check = CheckBox(self.tr("byte_verify"), self)
        self.byte_verify_check.setChecked(True)
        self.hash_thread_label = BodyLabel(self.tr("hash_threads"), self)
        self.thread_count_combo = ComboBox(self)
        self.thread_count_combo.setFixedWidth(96)
        for thread_count in HASH_THREAD_OPTIONS:
            self.thread_count_combo.addItem(str(thread_count), userData=thread_count)
        self._set_thread_count(_default_thread_count())
        row_opts.addWidget(self.scope_label)
        row_opts.addWidget(self.scope_combo)
        row_opts.addWidget(self.byte_verify_check)
        row_opts.addWidget(self.hash_thread_label)
        row_opts.addWidget(self.thread_count_combo)
        row_opts.addStretch(1)

        path_layout.addLayout(row_a)
        path_layout.addLayout(row_b)
        path_layout.addLayout(row_opts)

        # 批量勾选 + 记录入口：单独一行，避免正常宽度下工具栏被挤爆
        row_tools = QHBoxLayout()
        row_tools.setSpacing(8)
        self.btn_select_all = PushButton(self.tr("btn_select_all"), self)
        self.btn_select_all.setIcon(_pick_icon("CHECKBOX", "ACCEPT", "SELECT_ALL"))
        self.btn_select_all.clicked.connect(lambda _checked=False: self.select_all_checkable())
        self.btn_select_none = PushButton(self.tr("btn_select_none"), self)
        self.btn_select_none.setIcon(_pick_icon("CHECKBOX", "CLOSE"))
        self.btn_select_none.clicked.connect(lambda _checked=False: self.select_none())
        self.btn_select_invert = PushButton(self.tr("btn_select_invert"), self)
        self.btn_select_invert.setIcon(_pick_icon("SYNC", "UPDATE", "CHECKBOX"))
        self.btn_select_invert.clicked.connect(lambda _checked=False: self.invert_selection())
        self.btn_export_record = PushButton(self.tr("btn_export_record"), self)
        self.btn_export_record.setIcon(_pick_icon("SAVE", "DOWNLOAD"))
        self.btn_export_record.clicked.connect(lambda _checked=False: self.export_record())
        self.btn_import_record = PushButton(self.tr("btn_import_record"), self)
        self.btn_import_record.setIcon(_pick_icon("FOLDER", "DOCUMENT", "UPDATE"))
        self.btn_import_record.clicked.connect(lambda _checked=False: self.import_record())
        row_tools.addWidget(self.btn_select_all)
        row_tools.addWidget(self.btn_select_none)
        row_tools.addWidget(self.btn_select_invert)
        row_tools.addStretch(1)
        row_tools.addWidget(self.btn_export_record)
        row_tools.addWidget(self.btn_import_record)
        path_layout.addLayout(row_tools)

        # ---- 表格 + 预览 ----
        table_card = CardWidget(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(10, 10, 10, 10)
        table_layout.setSpacing(8)
        self.tabs_hint = BodyLabel(self.tr("tabs_hint"), self)
        self.tabs_hint.setStyleSheet("color: #6b7280; padding: 4px 6px;")

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
        self.table.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        configure_result_table_scrolling(self.table)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_CHECK, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_THUMB_B, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_THUMB_A, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_PATH_B, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_PATH_A, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_MTIME, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_HASH, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(COL_CHECK, 34)
        self.table.setColumnWidth(COL_THUMB_B, THUMBNAIL_SIZE + 12)
        self.table.setColumnWidth(COL_THUMB_A, THUMBNAIL_SIZE + 12)

        self.table_context_menu = CompareContextMenu(
            self.table,
            self,
            self._context_file_paths,
            self._context_keeper_paths,
            lambda: self.lang,
            self.tr,
        )
        # 与 file_context_menu.install_file_context_menu 保持同一约定
        setattr(self.table, "_file_context_menu_helper", self.table_context_menu)
        self.table.doubleClicked.connect(self._on_table_double_clicked)
        self.table.selectionModel().currentChanged.connect(self._on_current_row_changed)
        # Ctrl+A 在表格里只选可回收行，不把只读/异常行当作可回收
        self._select_all_shortcut = QShortcut(QKeySequence.StandardKey.SelectAll, self.table)
        self._select_all_shortcut.activated.connect(lambda: self.select_all_checkable())

        table_layout.addWidget(self.tabs_hint)
        table_layout.addWidget(self.table)

        preview_card = CardWidget(self)
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)
        self.preview_panel = PreviewPanel(slots=2, size=PREVIEW_SIZE, parent=preview_card)
        preview_layout.addWidget(self.preview_panel)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.addWidget(table_card)
        self.splitter.addWidget(preview_card)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([900, 340])

        # ---- 操作 ----
        action_card = CardWidget(self)
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(16, 12, 16, 12)
        action_layout.setSpacing(8)
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        self.btn_scan = PushButton(self.tr("btn_scan"), self)
        self.btn_scan.setIcon(_pick_icon("SYNC", "UPDATE", "SEARCH"))
        self.btn_scan.clicked.connect(lambda _checked=False: self.start_scan())
        self.btn_stop_scan = PushButton(self.tr("btn_stop_scan"), self)
        self.btn_stop_scan.setIcon(_pick_icon("CANCEL", "CLOSE"))
        self.btn_stop_scan.setEnabled(False)
        self.btn_stop_scan.clicked.connect(lambda _checked=False: self.stop_scan())
        self.btn_recycle = PrimaryPushButton(self.tr("btn_recycle"), self)
        self.btn_recycle.setIcon(_pick_icon("DELETE", "REMOVE"))
        self.btn_recycle.setEnabled(False)
        self.btn_recycle.clicked.connect(lambda _checked=False: self.start_recycling())
        self.btn_pause = PushButton(self.tr("btn_pause"), self)
        self.btn_pause.setIcon(_pick_icon("PAUSE", "PLAY"))
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(lambda _checked=False: self.toggle_recycle_pause())
        self.btn_stop_recycle = PushButton(self.tr("btn_stop_recycle"), self)
        self.btn_stop_recycle.setIcon(_pick_icon("CANCEL", "CLOSE", "DELETE"))
        self.btn_stop_recycle.setEnabled(False)
        self.btn_stop_recycle.clicked.connect(lambda _checked=False: self.stop_recycle())
        row3.addWidget(self.btn_scan)
        row3.addWidget(self.btn_stop_scan)
        row3.addStretch(1)
        row3.addWidget(self.btn_pause)
        row3.addWidget(self.btn_stop_recycle)
        row3.addWidget(self.btn_recycle)
        action_layout.addLayout(row3)

        # ---- 底部 ----
        foot_card = CardWidget(self)
        foot_layout = QHBoxLayout(foot_card)
        foot_layout.setContentsMargins(16, 12, 16, 12)
        foot_layout.setSpacing(10)
        self.summary = BodyLabel(self.tr("summary_empty"), self)
        self.summary.setStyleSheet("color: #475467;")
        self.progress = ProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setFixedHeight(10)
        self.progress.setMinimumWidth(240)
        self.progress.setMaximumWidth(360)
        self.status = BodyLabel(self.tr("waiting"), self)
        self.status.setStyleSheet("color: #475467;")
        foot_layout.addWidget(self.summary, 1)
        foot_layout.addWidget(self.progress, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        foot_layout.addWidget(self.status, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        outer.addWidget(header_card)
        outer.addWidget(path_card)
        outer.addWidget(self.splitter, 1)
        outer.addWidget(action_card)
        outer.addWidget(foot_card)

        self.scope_combo.currentIndexChanged.connect(lambda _index=0: self._save_settings())
        self.thread_count_combo.currentIndexChanged.connect(lambda _index=0: self._save_settings())
        self.byte_verify_check.toggled.connect(lambda _checked=False: self._save_settings())
        self.root_a_edit.editingFinished.connect(lambda: self._save_settings())
        self.root_b_edit.editingFinished.connect(lambda: self._save_settings())

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

    # ------------------------------------------------------------------
    # 翻译 / 设置
    # ------------------------------------------------------------------
    def tr(self, key: str, **kwargs) -> str:
        text = TRANSLATIONS.get(self.lang, TRANSLATIONS["zh"]).get(key, key)
        return text.format(**kwargs) if kwargs else text

    def _translate_or_raw(self, key: str, raw: str) -> str:
        text = self.tr(key)
        return raw if text == key else text

    def _table_headers(self) -> list[str]:
        return [
            self.tr("table_check"),
            self.tr("table_thumb_b"),
            self.tr("table_thumb_a"),
            self.tr("table_path_b"),
            self.tr("table_path_a"),
            self.tr("table_size"),
            self.tr("table_mtime"),
            self.tr("table_hash"),
            self.tr("table_status"),
        ]

    def _display_status(self, status: str) -> str:
        if "|" not in status:
            return self._translate_or_raw(status, status)
        key, _, extra = status.partition("|")
        if key == "status_skipped":
            return self.tr("status_skipped", reason=self._translate_or_raw(f"skip_{extra}", extra))
        if key == "status_failed":
            return self.tr("status_failed", reason=self._translate_or_raw(f"fail_{extra}", extra))
        if key == "status_issue":
            stage, _, message = extra.partition("|")
            stage_label = self._translate_or_raw(f"stage_{stage}", stage)
            detail = f"{stage_label}: {message}" if message else stage_label
            return self.tr("status_issue", message=detail)
        return self._translate_or_raw(key, key)

    def _scope(self) -> str:
        value = self.scope_combo.currentData()
        return value if value in SCOPES else SCOPE_ALL

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

    def _refresh_scope_options(self):
        current = self._scope()
        labels = {SCOPE_ALL: self.tr("scope_all"), SCOPE_MEDIA: self.tr("scope_media")}
        for index in range(self.scope_combo.count()):
            scope = self.scope_combo.itemData(index)
            if scope in labels:
                self.scope_combo.setItemText(index, labels[scope])
        for index in range(self.scope_combo.count()):
            if self.scope_combo.itemData(index) == current:
                self.scope_combo.setCurrentIndex(index)
                break

    def _settings_payload(self) -> dict:
        return {
            "language": self.lang,
            "scope": self._scope(),
            "hash_threads": self._thread_count(),
            "byte_verify": self.byte_verify_check.isChecked(),
            "root_a": self.root_a_edit.text().strip(),
            "root_b": self.root_b_edit.text().strip(),
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
        if not isinstance(data, dict):
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
            scope = data.get("scope")
            if scope in SCOPES:
                for index in range(self.scope_combo.count()):
                    if self.scope_combo.itemData(index) == scope:
                        self.scope_combo.setCurrentIndex(index)
                        break
            self._set_thread_count(int(data.get("hash_threads", _default_thread_count())))
            self.byte_verify_check.setChecked(bool(data.get("byte_verify", True)))
            root_a = str(data.get("root_a", "") or "")
            root_b = str(data.get("root_b", "") or "")
            if root_a:
                self.root_a_edit.setText(root_a)
            if root_b:
                self.root_b_edit.setText(root_b)
        except Exception:
            pass
        finally:
            self._suspend_settings_save = False

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
        self.elevation_hint.set_language(self.lang)
        self.language_label.setText(self.tr("language"))
        self.root_a_label.setText(self.tr("root_a"))
        self.root_b_label.setText(self.tr("root_b"))
        self.root_a_edit.setPlaceholderText(self.tr("root_a_placeholder"))
        self.root_b_edit.setPlaceholderText(self.tr("root_b_placeholder"))
        self.btn_root_a.setText(self.tr("choose_dir"))
        self.btn_root_b.setText(self.tr("choose_dir"))
        self.scope_label.setText(self.tr("scope"))
        self._refresh_scope_options()
        self.byte_verify_check.setText(self.tr("byte_verify"))
        self.hash_thread_label.setText(self.tr("hash_threads"))
        self.tabs_hint.setText(self.tr("tabs_hint"))
        self.btn_select_all.setText(self.tr("btn_select_all"))
        self.btn_select_none.setText(self.tr("btn_select_none"))
        self.btn_select_invert.setText(self.tr("btn_select_invert"))
        self.btn_export_record.setText(self.tr("btn_export_record"))
        self.btn_import_record.setText(self.tr("btn_import_record"))
        self.btn_scan.setText(self.tr("btn_scan"))
        self.btn_stop_scan.setText(self.tr("btn_stop_scan"))
        self.btn_recycle.setText(self.tr("btn_recycle"))
        self.btn_pause.setText(self.tr("btn_resume") if self._recycle_paused else self.tr("btn_pause"))
        self.btn_stop_recycle.setText(self.tr("btn_stop_recycle"))
        self.table_model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, COLUMN_COUNT - 1)
        self._set_status_text(self._last_status_key, **self._last_status_kwargs)
        self._refresh_summary()
        set_language = getattr(self.preview_panel, "set_language", None)
        if callable(set_language):
            set_language(self.lang)
        self._refresh_preview()

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

    def _set_status_text(self, key: str, **kwargs):
        self._last_status_key = key
        self._last_status_kwargs = kwargs
        self.status.setText(self.tr(key, **kwargs))

    # ------------------------------------------------------------------
    # 缩略图 / 预览
    # ------------------------------------------------------------------
    def _thumbnail_for(self, path: Path) -> QPixmap | None:
        try:
            return self.thumbnail_loader.request(path)
        except Exception:
            return None

    def _on_thumbnail_ready(self, path: str):
        cells = self._path_cells.get(path)
        if not cells:
            # 核心可能返回未规范化路径，而加载器可能回传规范化后的字符串
            try:
                cells = self._path_cells.get(str(_safe_resolve(Path(path))))
            except Exception:
                cells = None
        if cells:
            self.table_model.refresh_cells(cells)

    def _rebuild_path_index(self):
        self._path_cells.clear()

        def register(path: Path | None, row: int, column: int):
            if path is None:
                return
            for key in {str(path), str(_safe_resolve(path))}:
                self._path_cells.setdefault(key, []).append((row, column))

        for row_index, row in enumerate(self.table_model.rows):
            if row.target is not None:
                register(row.target.path, row_index, COL_THUMB_B)
            if row.keeper is not None:
                register(row.keeper.path, row_index, COL_THUMB_A)
            if row.issue_path is not None:
                column = COL_THUMB_B if row.issue_column == COL_PATH_B else COL_THUMB_A
                register(row.issue_path, row_index, column)

    def _refresh_preview(self):
        row_index = self.table.currentIndex().row()
        rows = self.table_model.rows
        if not (0 <= row_index < len(rows)):
            self.preview_panel.clear()
            return
        row = rows[row_index]
        if row.target is not None:
            self.preview_panel.set_slot(
                0, self.tr("preview_b"), row.target.path, row.target.size, row.target.mtime_ns
            )
        elif row.issue_path is not None and row.issue_column == COL_PATH_B:
            self.preview_panel.set_slot(0, self.tr("preview_issue"), row.issue_path, None, None)
        else:
            self.preview_panel.set_slot(0, self.tr("preview_b"), None, None, None)

        if row.keeper is not None:
            self.preview_panel.set_slot(
                1, self.tr("preview_a"), row.keeper.path, row.keeper.size, row.keeper.mtime_ns
            )
        elif row.issue_path is not None and row.issue_column == COL_PATH_A:
            self.preview_panel.set_slot(1, self.tr("preview_issue"), row.issue_path, None, None)
        else:
            self.preview_panel.set_slot(1, self.tr("preview_a"), None, None, None)

    def _on_current_row_changed(self, _current: QModelIndex, _previous: QModelIndex):
        self._refresh_preview()

    # ------------------------------------------------------------------
    # 右键 / 双击
    # ------------------------------------------------------------------
    def _context_file_paths(self, _row: int, selected_rows: list[int]) -> list[Path]:
        rows = self.table_model.rows
        paths: list[Path] = []
        for row_index in selected_rows:
            if 0 <= row_index < len(rows):
                path = rows[row_index].primary_path()
                if path is not None:
                    paths.append(path)
        return paths

    def _context_keeper_paths(self, row_index: int) -> list[Path]:
        rows = self.table_model.rows
        if 0 <= row_index < len(rows):
            keeper = rows[row_index].keeper_path()
            if keeper is not None:
                return [keeper]
        return []

    def _on_table_double_clicked(self, index: QModelIndex):
        if not index.isValid():
            return
        rows = self.table_model.rows
        row_index = index.row()
        if 0 <= row_index < len(rows):
            path = rows[row_index].primary_path()
            if path is not None:
                _open_path(path)

    # ------------------------------------------------------------------
    # 状态 / 按钮
    # ------------------------------------------------------------------
    def _is_busy(self) -> bool:
        # 线程引用非 None 直到 finished 清理都算忙：QThread.isRunning() 变 False 到 finished
        # 槽执行之间有个窗口，此时按钮还没恢复，若误判为空闲会重入并覆盖引用。
        return (
            self.is_scanning
            or self.is_recycling
            or self._scan_thread is not None
            or self._recycle_thread is not None
            or self._record_thread is not None
            or self._drain_timer.isActive()
            or bool(self._process_update_queue)
        )

    def _recyclable_rows(self) -> list[CompareRow]:
        return [
            row
            for row in self.table_model.rows
            if row.checked and row.kind == KIND_DUPLICATE and row.status == "status_pending"
        ]

    def _recyclable_count(self) -> int:
        return sum(1 for row in self.table_model.rows if row.kind == KIND_DUPLICATE)

    def _update_action_states(self):
        busy = self._is_busy()
        self.btn_scan.setEnabled(not busy)
        self.btn_stop_scan.setEnabled(self.is_scanning)
        self.btn_pause.setEnabled(self.is_recycling)
        self.btn_stop_recycle.setEnabled(self.is_recycling)
        can_recycle = (
            not busy
            and self._has_scan
            and not self._scan_cancelled
            and not self._scan_stale
            and bool(self._recyclable_rows())
        )
        self.btn_recycle.setEnabled(can_recycle)
        has_rows = bool(self.table_model.rows)
        for button in (self.btn_select_all, self.btn_select_none, self.btn_select_invert):
            button.setEnabled(
                not busy and has_rows and not self._scan_cancelled and not self._scan_stale
            )
        self.btn_export_record.setEnabled(not busy and self._scan_result is not None)
        self.btn_import_record.setEnabled(not busy)
        for widget in (
            self.root_a_edit,
            self.root_b_edit,
            self.btn_root_a,
            self.btn_root_b,
            self.scope_combo,
            self.thread_count_combo,
            self.byte_verify_check,
        ):
            widget.setEnabled(not busy)

    def _on_row_check_changed(self):
        self._update_action_states()
        self._refresh_summary()

    # ------------------------------------------------------------------
    # 批量勾选
    # ------------------------------------------------------------------
    def select_all_checkable(self):
        self._apply_check_mode("all")

    def select_none(self):
        self._apply_check_mode("none")

    def invert_selection(self):
        self._apply_check_mode("invert")

    def _apply_check_mode(self, mode: str):
        """三个批量按钮和 Ctrl+A 的统一入口：只作用于合法待回收行。"""
        if self._is_busy():
            self._notify(
                self.tr("cannot_start_title"), self.tr("recycle_blocked_busy"), is_error=True
            )
            return
        if self._scan_cancelled:
            # 取消的扫描结果不允许批量勾选，避免误回收半成品结果
            self._notify(
                self.tr("cannot_start_title"), self.tr("cannot_start_cancelled"), is_error=True
            )
            return
        if self._scan_stale:
            self._notify(
                self.tr("cannot_start_title"), self.tr("cannot_start_stale"), is_error=True
            )
            return
        if self.table_model.apply_check_mode(mode):
            self._on_row_check_changed()

    def _refresh_summary(self):
        if not self._has_scan:
            self.summary.setText(self.tr("summary_empty"))
            return
        if self._record_imported and not (
            self._recycled_count or self._skipped_count or self._failed_count
        ):
            self.summary.setText(
                self.tr("summary_ready", count=self._recyclable_count(), total=len(self.table_model.rows))
                + self.tr("record_imported_badge")
            )
            return
        if self._scan_cancelled and not (
            self._recycled_count or self._skipped_count or self._failed_count
        ):
            # 取消的扫描不提供回收，汇总也不能说「可回收 N」
            self.summary.setText(self.tr("scan_cancelled"))
            return
        recyclable = sum(1 for row in self.table_model.rows if row.kind == KIND_DUPLICATE)
        total = self._scan_total or len(self.table_model.rows)
        if self._recycled_count or self._skipped_count or self._failed_count:
            self.summary.setText(
                self.tr(
                    "summary_done",
                    success=self._recycled_count,
                    skipped=self._skipped_count,
                    failed=self._failed_count,
                    mismatch=self._mismatch_count,
                    issue=self._issue_count,
                )
            )
            return
        text = self.tr("summary_ready", count=recyclable, total=total)
        if self._mismatch_count or self._issue_count:
            text = f"{text}  {self.tr('summary_detail', mismatch=self._mismatch_count, issue=self._issue_count)}"
        self.summary.setText(text)

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------
    def browse_root(self, which: str):
        if self._is_busy():
            self._notify(self.tr("cannot_start_title"), self.tr("recycle_blocked_busy"), is_error=True)
            return
        start_dir = self.root_a_edit.text().strip() if which == "a" else self.root_b_edit.text().strip()
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("choose_dir"), start_dir or str(_get_windows_pictures_dir() or Path.home())
        )
        if not folder:
            return
        if which == "a":
            self.root_a_edit.setText(folder)
        else:
            self.root_b_edit.setText(folder)
        self._save_settings()

    def start_scan(self):
        if self._is_busy():
            self._notify(self.tr("cannot_start_title"), self.tr("recycle_blocked_busy"), is_error=True)
            return
        root_a_text = self.root_a_edit.text().strip()
        root_b_text = self.root_b_edit.text().strip()
        root_a = Path(root_a_text)
        root_b = Path(root_b_text)
        try:
            validate_compare_roots(root_a, root_b)
        except ValueError as exc:
            self._show_root_error(str(exc))
            return
        except Exception as exc:
            self._show_root_error(f"{type(exc).__name__}: {exc}")
            return

        self._reset_results()
        # 扫描根/选项快照：导出记录只用这份，避免用户扫完又改目录控件。
        # 注意用绝对路径：用户可能输入相对路径，而记录格式要求绝对根。
        self._scan_snapshot = {
            "root_a": os.path.abspath(os.fspath(root_a)),
            "root_b": os.path.abspath(os.fspath(root_b)),
            "scope": self._scope(),
            "keep_strategy": "shallowest",
            "threads": self._thread_count(),
        }
        self.is_scanning = True
        self._scan_cancelled = False
        self._has_scan = False
        self.progress.setValue(0)
        self._set_status_text("scanning")
        self._update_action_states()

        self._scan_thread = QThread(self)
        self._scan_worker = CompareScanWorker(root_a, root_b, self._scope(), self._thread_count())
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.progress_update.connect(self._update_scan_progress)
        self._scan_worker.finished.connect(self._scan_finished)
        self._scan_worker.failed.connect(self._scan_failed)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.failed.connect(self._scan_thread.quit)
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread_finished)
        self._scan_thread.start()

    def _show_root_error(self, code: str):
        if code in KNOWN_ROOT_CODES:
            message = self.tr(f"invalid_root_{code}")
        else:
            message = self.tr("scan_failed", error=code)
        self._notify(self.tr("invalid_root_title"), message, is_error=True)

    def stop_scan(self):
        if self._scan_worker is not None and self.is_scanning:
            self._scan_worker.request_stop()
            self._set_status_text("status_stopping")
            self.btn_stop_scan.setEnabled(False)

    def _update_scan_progress(self, stage: str, done: int, total: int):
        percent = int(done * 100 / total) if total else 0
        self.progress.setValue(max(0, min(100, percent)))
        stage_label = self._translate_or_raw(f"stage_{stage}", stage)
        self._set_status_text("status_scanning_stage", stage=stage_label, done=done, total=total)

    def _scan_finished(self, result: object):
        if not isinstance(result, ScanResult):
            self._scan_failed(f"{type(result).__name__}")
            return
        self._apply_scan_result(result)

    def _scan_failed(self, error: str):
        self.is_scanning = False
        self._has_scan = False
        self.progress.setValue(0)
        self._show_root_error(error)
        self._set_status_text("scan_failed", error=error)
        self._update_action_states()
        self._maybe_finish_close()

    def _apply_scan_result(self, result: ScanResult):
        self.is_scanning = False
        self._has_scan = True
        self._scan_cancelled = bool(result.cancelled)
        self._scan_total = int(result.scanned_files)
        self._mismatch_count = len(result.mismatches)
        self._issue_count = len(result.issues)
        self._recycled_count = 0
        self._skipped_count = 0
        self._failed_count = 0
        # 真实重扫成功：清除导入记录标记，回收策略回到用户勾选设置
        self._scan_result = result
        self._record_imported = False
        self._imported_record = None
        self._scan_stale = False

        self.thumbnail_loader.clear()
        rows = self._build_rows(result)
        self.table.setUpdatesEnabled(False)
        try:
            self.table_model.reset_rows(rows)
            self._rebuild_path_index()
        finally:
            self.table.setUpdatesEnabled(True)
        self._refresh_preview()
        self._refresh_summary()

        duplicate_count = sum(1 for row in rows if row.kind == KIND_DUPLICATE)
        if self._scan_cancelled:
            self.progress.setValue(0)
            self._set_status_text("scan_cancelled")
        else:
            self.progress.setValue(100)
            if duplicate_count:
                self._set_status_text(
                    "scan_done", count=duplicate_count, total=max(self._scan_total, len(rows))
                )
            else:
                self._set_status_text("scan_none")
        self._update_action_states()
        self._maybe_finish_close()

    def _build_rows(self, result: ScanResult) -> list[CompareRow]:
        rows: list[CompareRow] = []
        # 取消的扫描只展示部分结果：一律不可勾选（避免误回收）
        cancelled = bool(result.cancelled)
        root_a_text = str((self._scan_snapshot or {}).get("root_a") or self.root_a_edit.text().strip())
        for group in result.groups:
            keeper = group.keeper
            for duplicate in group.duplicates:
                rows.append(
                    CompareRow(
                        kind=KIND_DUPLICATE,
                        target=duplicate,
                        keeper=keeper,
                        sha256=group.sha256,
                        size=group.size or duplicate.size,
                        mtime_ns=duplicate.mtime_ns,
                        checked=not cancelled,
                        status="status_cancelled" if cancelled else "status_pending",
                    )
                )
        for mismatch in result.mismatches:
            rows.append(
                CompareRow(
                    kind=KIND_MISMATCH,
                    target=mismatch.other,
                    keeper=mismatch.keeper,
                    sha256=mismatch.sha256,
                    size=mismatch.other.size,
                    mtime_ns=mismatch.other.mtime_ns,
                    checked=False,
                    status="status_mismatch",
                )
            )
        for issue in result.issues:
            root_a = root_a_text
            column = COL_PATH_A if root_a and _is_under(issue.path, Path(root_a)) else COL_PATH_B
            rows.append(
                CompareRow(
                    kind=KIND_ISSUE,
                    issue_path=issue.path,
                    issue_column=column,
                    checked=False,
                    status=f"status_issue|{issue.stage}|{issue.message}",
                )
            )
        return rows

    def _reset_results(self):
        self.thumbnail_loader.clear()
        self._path_cells.clear()
        self.table_model.reset_rows([])
        self.preview_panel.clear()
        self._recycled_count = 0
        self._skipped_count = 0
        self._failed_count = 0
        self._mismatch_count = 0
        self._issue_count = 0
        self._has_scan = False
        self._scan_result = None
        self._scan_snapshot = {}
        self._scan_stale = False
        self._record_imported = False
        self._imported_record = None
        self._process_update_queue.clear()
        self._pending_recycle_result = None
        self._drain_timer.stop()
        self.summary.setText(self.tr("summary_empty"))

    def _scan_thread_finished(self):
        self._scan_worker = None
        self._scan_thread = None
        self._update_action_states()
        self._maybe_finish_close()

    # ------------------------------------------------------------------
    # 扫描记录导入 / 导出
    # ------------------------------------------------------------------
    def _default_record_path(self, suffix: str) -> str:
        base = self._scan_snapshot.get("root_b") or self.root_b_edit.text().strip()
        name = Path(base).name if base else "compare"
        stamp = time.strftime("%Y%m%d-%H%M%S")
        return str(Path(base or Path.home()) / f"compare-record-{name}-{stamp}{suffix}")

    def _build_scan_record(self) -> ScanRecord:
        """用扫描快照构造记录（不读当前控件，避免导出后改根的错误数据）。"""
        if self._scan_result is None or not self._scan_snapshot:
            raise ValueError(self.tr("record_none"))
        row_states: dict[str, dict] = {}
        for row in self.table_model.rows:
            path = row.primary_path()
            if row.kind != KIND_DUPLICATE or path is None:
                continue
            row_states[str(path)] = {"checked": bool(row.checked), "status": row.status}
        return ScanRecord(
            mode=MODE_COMPARE,
            root_a=Path(self._scan_snapshot["root_a"]),
            root_b=Path(self._scan_snapshot["root_b"]),
            scope=self._scan_snapshot["scope"],
            keep_strategy=self._scan_snapshot["keep_strategy"],
            result=self._scan_result,
            row_states=row_states,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            stale=bool(self._scan_stale),
        )

    def export_record(self):
        if self._is_busy():
            self._notify(self.tr("cannot_start_title"), self.tr("record_io_busy"), is_error=True)
            return
        if self._scan_result is None:
            self._notify(self.tr("cannot_start_title"), self.tr("record_none"), is_error=True)
            return
        try:
            record = self._build_scan_record()
        except ValueError as exc:
            self._notify(self.tr("record_saved_title"), str(exc), is_error=True)
            return
        path_text, _filter = QFileDialog.getSaveFileName(
            self, self.tr("record_export_title"), self._default_record_path(".json"),
            self.tr("record_filter"),
        )
        if not path_text:
            return
        self._start_record_op(
            "save", RecordSaveWorker(Path(path_text), record), self.tr("record_saving")
        )

    def import_record(self):
        if self._is_busy():
            self._notify(self.tr("cannot_start_title"), self.tr("record_io_busy"), is_error=True)
            return
        start_dir = self.root_b_edit.text().strip() or str(Path.home())
        path_text, _filter = QFileDialog.getOpenFileName(
            self, self.tr("record_import_title"), start_dir, self.tr("record_filter")
        )
        if not path_text:
            return
        self._start_record_op(
            "load", RecordLoadWorker(Path(path_text)), self.tr("record_loading")
        )

    def _start_record_op(self, op: str, worker: QObject, status_key: str):
        """记录 I/O 进后台线程，走既有忙/关闭协议。"""
        self._record_op = op
        self._record_thread = QThread(self)
        self._record_worker = worker
        worker.moveToThread(self._record_thread)
        self._record_thread.started.connect(worker.run)
        worker.done.connect(self._on_record_op_done)
        worker.failed.connect(self._on_record_op_failed)
        worker.done.connect(self._record_thread.quit)
        worker.failed.connect(self._record_thread.quit)
        worker.done.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        self._record_thread.finished.connect(self._record_thread.deleteLater)
        self._record_thread.finished.connect(self._record_thread_finished)
        self._set_status_text(status_key)
        self._update_action_states()
        self._record_thread.start()

    def _on_record_op_done(self, payload: object):
        if self._record_op == "save":
            count = int(payload or 0)
            self._notify(self.tr("record_saved_title"), self.tr("record_export_ok", count=count))
        elif self._record_op == "load":
            if isinstance(payload, ScanRecord):
                self._apply_imported_record(payload)
            else:
                self._notify(
                    self.tr("record_import_title"), self.tr("record_export_failed", error=""),
                    is_error=True,
                )

    def _on_record_op_failed(self, error: str):
        if self._record_op == "save":
            self._notify(
                self.tr("record_saved_title"),
                self.tr("record_export_failed", error=error),
                is_error=True,
            )
        else:
            # 坏记录不能破坏现有显示：只在提示条里报错
            self._notify(
                self.tr("record_import_title"),
                self.tr("record_import_failed", error=error),
                is_error=True,
            )

    def _record_thread_finished(self):
        self._record_worker = None
        self._record_thread = None
        self._record_op = ""
        self._update_action_states()
        self._maybe_finish_close()

    def _apply_imported_record(self, record: ScanRecord):
        """只有完整解析成功的记录才会走到这里；替换显示并标记历史记录。"""
        result = record.result
        self.thumbnail_loader.clear()
        # 先把历史根/选项恢复成扫描时的快照，_build_rows 分类异常列要用记录自己的根，
        # 不能被导入前界面上残留的根影响。
        self._scan_snapshot = {
            "root_a": str(record.root_a),
            "root_b": str(record.root_b) if record.root_b is not None else "",
            "scope": record.scope,
            "keep_strategy": record.keep_strategy,
            "threads": self._thread_count(),
        }
        self._suspend_settings_save = True
        try:
            self.root_a_edit.setText(str(record.root_a))
            if record.root_b is not None:
                self.root_b_edit.setText(str(record.root_b))
            # 扫描范围恢复；选项/线程只在页面当前允许值中匹配
            for index in range(self.scope_combo.count()):
                if self.scope_combo.itemData(index) == record.scope:
                    self.scope_combo.setCurrentIndex(index)
                    break
        finally:
            self._suspend_settings_save = False

        rows = self._build_rows(result)
        cancelled_flag = bool(result.cancelled)
        stale_flag = bool(record.stale)
        recycled = skipped = failed = 0
        for row in rows:
            path = row.primary_path()
            if row.kind != KIND_DUPLICATE or path is None:
                continue
            state = record.row_states.get(str(path))
            if state is None:
                for key, value in record.row_states.items():
                    if os.path.normcase(key) == os.path.normcase(str(path)):
                        state = value
                        break
            if state is None:
                # 记录里没有该行状态时保守处理：不勾选
                row.checked = False
                continue
            status = str(state.get("status") or "status_pending")
            if cancelled_flag and status not in (
                "status_cancelled",
                "status_recycled",
                "status_skipped",
                "status_failed",
            ):
                # 取消的扫描不允许回收：未处理行一律降为“已取消”
                status = "status_cancelled"
            row.status = status
            row.checked = bool(state.get("checked")) and row.is_checkable()
            if cancelled_flag or stale_flag:
                # 取消/失效的历史结果一律不可勾选（导入时已按行状态算完计数）
                row.checked = False
            if status.startswith("status_recycled"):
                recycled += 1
            elif status.startswith("status_skipped"):
                skipped += 1
            elif status.startswith("status_failed"):
                failed += 1

        self.table.setUpdatesEnabled(False)
        try:
            self.table_model.reset_rows(rows)
            self._rebuild_path_index()
        finally:
            self.table.setUpdatesEnabled(True)

        self._scan_result = result
        self._has_scan = True
        self._scan_cancelled = cancelled_flag
        self._scan_stale = stale_flag
        self._scan_total = int(result.scanned_files)
        self._mismatch_count = len(result.mismatches)
        self._issue_count = len(result.issues)
        # 历史记录里的已回收/跳过/失败行数按行状态真实恢复，不能一律归零
        self._recycled_count = recycled
        self._skipped_count = skipped
        self._failed_count = failed
        self._record_imported = True
        self._imported_record = record

        self._refresh_preview()
        self._refresh_summary()
        self.progress.setValue(0 if self._scan_cancelled else 100)
        if self._scan_cancelled:
            self._set_status_text("scan_cancelled")
        elif self._scan_stale:
            self._set_status_text("scan_stale")
        else:
            duplicate_count = sum(1 for row in rows if row.kind == KIND_DUPLICATE)
            self._set_status_text(
                "scan_done", count=duplicate_count, total=max(self._scan_total, len(rows))
            )
        self._update_action_states()
        self._notify(
            self.tr("record_import_title"),
            self.tr(
                "record_import_ok",
                count=sum(1 for row in rows if row.is_checkable() and row.checked),
            ),
            is_error=self._scan_cancelled,
        )
        if self._scan_cancelled:
            self._notify(
                self.tr("record_import_title"), self.tr("record_import_cancelled"), is_error=True
            )


    # ------------------------------------------------------------------
    # 回收
    # ------------------------------------------------------------------
    def start_recycling(self):
        if self._is_busy():
            self._notify(self.tr("cannot_start_title"), self.tr("recycle_blocked_busy"), is_error=True)
            return
        if self._scan_cancelled:
            self._notify(
                self.tr("cannot_start_title"), self.tr("cannot_start_cancelled"), is_error=True
            )
            return
        if self._scan_stale:
            self._notify(
                self.tr("cannot_start_title"), self.tr("cannot_start_stale"), is_error=True
            )
            return
        existing = self._recyclable_rows()
        if not existing:
            self._notify(self.tr("cannot_start_title"), self.tr("cannot_start_content"), is_error=True)
            return

        items: list[tuple[int, FileEntry, FileEntry]] = []
        total_size = 0
        for row_index, row in enumerate(self.table_model.rows):
            if not row.checked or row.kind != KIND_DUPLICATE or row.status != "status_pending":
                continue
            if row.target is None or row.keeper is None:
                continue
            items.append((row_index, row.target, row.keeper))
            total_size += row.target.size
        if not items:
            self._notify(self.tr("cannot_start_title"), self.tr("cannot_start_content"), is_error=True)
            return

        # 导入的历史记录不可信：无论用户是否取消勾选，本轮一律强制逐字节重验
        bytes_required = bool(self.byte_verify_check.isChecked()) or self._record_imported

        answer = QMessageBox.question(
            self,
            self.tr("confirm_title"),
            self.tr("confirm_content", count=len(items), size=_format_size(total_size)),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.is_recycling = True
        self._recycle_paused = False
        self._recycle_stopping = False
        self.btn_pause.setText(self.tr("btn_pause"))
        self.progress.setValue(0)
        self._update_action_states()

        self._recycle_thread = QThread(self)
        self._recycle_worker = RecycleWorker(items, bytes_required)
        self._recycle_worker.moveToThread(self._recycle_thread)
        self._recycle_thread.started.connect(self._recycle_worker.run)
        self._recycle_worker.row_update_batch.connect(self._queue_recycle_updates)
        self._recycle_worker.progress_update.connect(self._update_recycle_progress)
        self._recycle_worker.finished.connect(self._recycle_finished)
        self._recycle_worker.finished.connect(self._recycle_thread.quit)
        self._recycle_worker.finished.connect(self._recycle_worker.deleteLater)
        self._recycle_thread.finished.connect(self._recycle_thread.deleteLater)
        self._recycle_thread.finished.connect(self._recycle_thread_finished)
        self._recycle_thread.start()

    def toggle_recycle_pause(self):
        if not self.is_recycling or self._recycle_worker is None:
            return
        self._recycle_paused = not self._recycle_paused
        self._recycle_worker.set_paused(self._recycle_paused)
        self.btn_pause.setText(self.tr("btn_resume") if self._recycle_paused else self.tr("btn_pause"))
        if self._recycle_paused:
            self._set_status_text("status_paused")

    def stop_recycle(self):
        if not self.is_recycling or self._recycle_worker is None:
            return
        self._recycle_worker.request_stop()
        self._recycle_paused = False
        self._recycle_stopping = True
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText(self.tr("btn_pause"))
        self.btn_stop_recycle.setEnabled(False)
        self._set_status_text("status_stopping")

    def _queue_recycle_updates(self, updates: list[tuple[int, str]]):
        self._process_update_queue.extend(updates)
        if not self._drain_timer.isActive():
            self._drain_timer.start()

    def _drain_queues(self):
        updates: list[tuple[int, str]] = []
        while self._process_update_queue and len(updates) < UI_UPDATE_DRAIN_ROWS:
            updates.append(self._process_update_queue.popleft())
        if updates:
            self._apply_recycle_updates(updates)
        if self._process_update_queue:
            return
        self._drain_timer.stop()
        if self._pending_recycle_result is not None:
            result = self._pending_recycle_result
            self._pending_recycle_result = None
            self._apply_recycle_finished(result)
        # 队列排空后再检查待处理的关闭（关闭不能丢掉最后一批状态回写）
        self._maybe_finish_close()

    def _apply_recycle_updates(self, updates: list[tuple[int, str]]):
        rows = self.table_model.rows
        self.table.setUpdatesEnabled(False)
        try:
            for row_index, status in updates:
                if 0 <= row_index < len(rows):
                    rows[row_index].status = status
                    self.table_model.update_row(row_index)
        finally:
            self.table.setUpdatesEnabled(True)
        self._refresh_summary()

    def _update_recycle_progress(self, completed: int, total: int):
        percent = int(completed * 100 / total) if total else 0
        self.progress.setValue(max(0, min(100, percent)))
        if self._recycle_stopping:
            self._set_status_text("status_stopping")
        elif self._recycle_paused:
            self._set_status_text("status_paused")
        else:
            stage_label = self.tr("stage_recycle")
            self._set_status_text(
                "status_scanning_stage", stage=stage_label, done=completed, total=total
            )

    def _recycle_finished(self, result: dict):
        self._pending_recycle_result = result
        if not self._drain_timer.isActive():
            self._drain_timer.start()

    def _apply_recycle_finished(self, result: dict):
        self.is_recycling = False
        self._recycle_paused = False
        self._recycle_stopping = False
        self._recycled_count = int(result.get("success", 0))
        self._skipped_count = int(result.get("skipped", 0))
        self._failed_count = int(result.get("failed", 0))
        total = int(result.get("total", 0))
        completed = int(result.get("completed", total))
        stopped = bool(result.get("stopped", False))
        if stopped:
            percent = int(completed * 100 / total) if total else 0
            self.progress.setValue(percent)
            self._set_status_text(
                "status_stopped",
                success=self._recycled_count,
                skipped=self._skipped_count,
                failed=self._failed_count,
            )
        else:
            self.progress.setValue(100)
            self._set_status_text(
                "recycle_done_status",
                success=self._recycled_count,
                skipped=self._skipped_count,
                failed=self._failed_count,
            )
        self._refresh_summary()
        self._update_action_states()
        self._notify(
            self.tr("recycle_done_title"),
            self.tr(
                "recycle_done_message",
                success=self._recycled_count,
                skipped=self._skipped_count,
                failed=self._failed_count,
            ),
            is_error=bool(self._failed_count),
        )
        self._maybe_finish_close()

    def _recycle_thread_finished(self):
        self._recycle_worker = None
        self._recycle_thread = None
        self._update_action_states()
        self._maybe_finish_close()

    # ------------------------------------------------------------------
    # 关闭 / 退出
    # ------------------------------------------------------------------
    def _shutdown_workers(self):
        if self._scan_worker is not None:
            self._scan_worker.request_stop()
        if self._recycle_worker is not None:
            self._recycle_worker.request_stop()

    def _stop_timers(self):
        """真正关闭前停掉定时器：否则关闭后仍会 drain（此时控件已隐藏）并可能重入 close。"""
        try:
            self._drain_timer.stop()
        except Exception:
            pass

    def _workers_running(self) -> bool:
        # 与 _is_busy 同源：引用还在（等待 finished 清理）就必须视为运行中，
        # 否则关闭会把正在收尾的 QThread 直接销毁。
        return bool(
            self._scan_thread is not None
            or self._recycle_thread is not None
            or self._record_thread is not None
        )

    def _maybe_finish_close(self):
        if not self._pending_close:
            return
        if self._workers_running():
            return
        if self._process_update_queue or self._drain_timer.isActive():
            # 还有批量回写没 drain 完，等定时器排空后再关（_drain_queues 会再调一次）
            return
        self._pending_close = False
        self._stop_timers()
        self._release_thumbnail_loader()
        self.close()

    def _release_thumbnail_loader(self):
        try:
            self.thumbnail_loader.shutdown()
        except Exception:
            pass
        try:
            self.preview_panel.shutdown()
        except Exception:
            pass

    def _on_about_to_quit(self):
        """进程退出：停定时器、停缩略图线程、请求后台 worker 停止。"""
        self._shutdown_workers()
        self._stop_timers()
        self._release_thumbnail_loader()

    def closeEvent(self, event):
        # 有后台线程时先请求停止并延后关闭，避免 QThread 在运行时被销毁
        if self._workers_running():
            self._pending_close = True
            self._shutdown_workers()
            event.ignore()
            return
        self._pending_close = False
        self._stop_timers()
        self._release_thumbnail_loader()
        super().closeEvent(event)


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