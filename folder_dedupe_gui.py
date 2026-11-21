"""目录内去重页：单个目录内跨子目录的字节级重复文件，每组保留 1 个，其余移入回收站。

准确性优先：扫描 / 哈希 / 逐字节比对 / 执行前复核 / 回收全部委托给
``duplicate_scan_core``（大小 → 完整 SHA-256 → 逐字节比对，三者缺一不可），
本文件只负责界面、线程调度与回收流程。
只提供移入回收站，不提供永久删除；保留文件绝不回收。
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
from datetime import datetime
from pathlib import Path

import file_context_menu as fcm
from duplicate_scan_core import (
    FileEntry,
    RecycleOutcome,
    ScanCancelled,
    ScanResult,
    find_internal_duplicates,
    classify_media_type,
    classify_duplicate_group,
    reselect_internal_keeper,
    recycle_duplicate,
)
from elevation_hint import attach_elevation_hint
from file_context_menu import FileContextMenu
from media_thumbnail import PreviewPanel, ThumbnailLoader
from scan_record_core import ROW_STATUS_BASES, ScanRecord, load_record, save_record
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


APP_NAME = "FolderDedupeGUI"
SETTINGS_FILENAME = "folder_dedupe_settings.json"

THUMBNAIL_SIZE = 96
ROW_HEIGHT = THUMBNAIL_SIZE + 8
PREVIEW_SIZE = 256
HASH_THREAD_OPTIONS = (1, 2, 4, 8, 16)
UI_UPDATE_DRAIN_ROWS = 200
RECYCLE_BATCH_SIZE = 20

SCOPE_ALL = "all"
SCOPE_MEDIA = "media"
SCOPES = (SCOPE_ALL, SCOPE_MEDIA)

KEEP_SHALLOWEST = "shallowest"
KEEP_OLDEST = "oldest"
KEEP_NEWEST = "newest"
KEEP_STRATEGIES = (KEEP_SHALLOWEST, KEEP_OLDEST, KEEP_NEWEST)

KIND_KEEPER = "keeper"
KIND_DUPLICATE = "duplicate"
KIND_MISMATCH = "mismatch"
KIND_ISSUE = "issue"

# 扫描记录的固定模式名（与 scan_record_core 冻结合同一致）
RECORD_MODE = "internal"
RECORD_FILTER = "JSON (*.json)"

COL_CHECK = 0
COL_GROUP = 1
COL_THUMB = 2
COL_ROLE = 3
COL_PATH = 4
COL_SIZE = 5
COL_MTIME = 6
COL_HASH = 7
COL_STATUS = 8
COLUMN_COUNT = 9

TRANSLATIONS = {
    "zh": {
        "app_title": "目录内去重",
        "header_title": "目录内去重",
        "header_subtitle": "用「大小 → 完整 SHA-256 → 逐字节比对」三重校验，"
        "找出同一目录内跨子目录的完全重复文件",
        "header_note": "每组只保留 1 个文件（可切换保留策略），其余移入回收站；"
        "保留文件绝不回收，只提供移入回收站。",
        "language": "界面语言",
        "root_dir": "扫描目录",
        "root_dir_placeholder": "选择需要去重的目录",
        "choose_dir": "选择目录",
        "scope": "扫描范围",
        "scope_all": "所有文件",
        "scope_media": "仅照片/视频",
        "keep_strategy": "保留策略",
        "keep_shallowest": "层级最浅 / 路径最短",
        "keep_oldest": "修改时间最早",
        "keep_newest": "修改时间最新",
        "keep_strategy_changed": "保留策略已变更，请重新扫描后再回收",
        "hash_threads": "Hash 线程",
        "byte_verify": "执行前再次逐字节复核",
        "btn_scan": "开始扫描",
        "btn_stop_scan": "停止扫描",
        "btn_recycle": "移入回收站",
        "btn_pause": "暂停",
        "btn_resume": "继续",
        "btn_stop_recycle": "停止回收",
        "table_check": "☐",
        "table_group": "组号",
        "table_thumb": "预览",
        "table_role": "角色",
        "table_path": "路径",
        "table_size": "大小",
        "table_mtime": "修改时间",
        "table_hash": "SHA-256",
        "table_status": "状态",
        "role_keep": "保留",
        "role_duplicate": "重复",
        "preview_selected": "选中文件",
        "preview_keeper": "本组保留文件",
        "preview_issue": "问题文件",
        "tabs_hint": "勾选要回收的重复文件；保留行不可勾选。双击行打开文件，右键查看更多操作。",
        "waiting": "等待选择目录",
        "scanning": "正在扫描",
        "status_scanning_stage": "{stage} {done}/{total}",
        "stage_enumerate": "枚举文件",
        "stage_hash": "计算哈希",
        "stage_verify": "逐字节复核",
        "stage_recycle": "回收",
        "scan_done": "扫描完成：{groups} 组重复，可回收 {count} 个文件，共 {total} 个文件",
        "scan_none": "未找到目录内的完全重复文件",
        "scan_cancelled": "扫描已取消，结果不可执行回收，请重新扫描",
        "scan_failed": "扫描失败：{error}",
        "summary_ready": "可回收 {count} 个 / 共 {total}",
        "summary_detail": "校验不一致 {mismatch}；读取问题 {issue}",
        "summary_done": "已回收 {success} / 跳过 {skipped} / 失败 {failed} / "
        "校验不一致 {mismatch} / 读取问题 {issue}",
        "summary_empty": "",
        "summary_stale": "保留策略已变更：需要重新扫描",
        "space_summary": "预计可腾出：{total}（当前勾选：{selected}）",
        "space_summary_tooltip": "按待处理副本的文件逻辑大小估算；移入回收站后，清空回收站时才会释放空间。",
        "status_pending": "待处理",
        "status_keep": "保留",
        "status_recycled": "已回收",
        "status_skipped": "已跳过：{reason}",
        "status_failed": "失败：{reason}",
        "status_mismatch": "校验不一致",
        "status_issue": "读取问题：{message}",
        "status_paused": "已暂停",
        "status_stopping": "正在停止",
        "recycle_done_status": "回收完成：已回收 {success}，跳过 {skipped}，失败 {failed}",
        "status_stopped": "已停止：已回收 {success}，跳过 {skipped}，失败 {failed}",
        "skip_target_missing": "目标文件不存在",
        "skip_keeper_missing": "保留文件不存在",
        "skip_target_changed": "目标文件已变化",
        "skip_keeper_changed": "保留文件已变化",
        "skip_same_path": "路径相同",
        "skip_content_differs": "内容已不一致",
        "skip_read_error": "读取失败",
        "fail_send2trash_unavailable": "缺少 send2trash",
        "confirm_title": "确认移入回收站",
        "confirm_content": "将把 {count} 个重复文件（共 {size}）移入回收站，每组至少保留 1 个文件，"
        "不会永久删除。\n执行前会逐个重新校验，任一校验不通过则跳过。确定继续？",
        "missing_trash_title": "缺少回收站支持",
        "missing_trash_content": "当前环境缺少 send2trash，无法移入回收站。请先安装 send2trash。",
        "cannot_start_title": "无法开始",
        "cannot_start_content": "当前没有可回收的重复文件。",
        "cannot_start_cancelled": "扫描已取消，请重新扫描后再执行回收。",
        "cannot_start_stale": "保留策略已变更，请重新扫描后再执行回收。",
        "invalid_root_title": "无法扫描",
        "invalid_root_missing": "目录不存在或不是目录",
        "invalid_root_not_dir": "选择的路径不是目录",
        "recycle_done_title": "回收完成",
        "recycle_done_message": "已回收: {success}\n跳过: {skipped}\n失败: {failed}",
        "blocked_busy": "正在处理中，请稍候。",
        "menu_open": "打开文件",
        "menu_open_folder": "打开所在目录",
        "menu_open_keeper_folder": "打开保留文件所在目录",
        "menu_copy_path": "复制路径",
        "menu_copy_files": "复制文件",
        "menu_cut_files": "剪切文件",
        "menu_system": "系统右键菜单...",
        "btn_select_all": "全选",
        "btn_select_none": "全不选",
        "btn_invert": "反选",
        "category_photo": "照片 · {groups} 组 / {files} 个文件",
        "category_video": "视频 · {groups} 组 / {files} 个文件",
        "category_other": "其他 · {groups} 组 / {files} 个文件",
        "btn_set_keeper": "设为保留",
        "keeper_changed": "已将所选文件设为本组保留项",
        "keeper_reselect_invalid": "无法切换保留项：候选文件已变化或本组已有处理结果",
        "btn_export_record": "导出记录",
        "btn_import_record": "导入记录",
        "record_action_save": "导出",
        "record_action_load": "导入",
        "record_working": "正在{action}扫描记录…",
        "record_done_title": "扫描记录",
        "record_saved": "已导出扫描记录：{path}",
        "record_imported": "已导入扫描记录：{path}；回收前会强制逐字节复核",
        "record_import_failed": "导入失败：{error}",
        "record_save_failed": "导出失败：{error}",
        "record_export_title": "导出扫描记录",
        "record_import_title": "导入扫描记录",
        "record_no_data": "当前没有可导出的扫描结果，请先扫描或导入记录",
        "record_import_cancelled": "导入的记录已被取消，不能执行回收",
        "record_import_stale": "导入的记录已失效，需要重新扫描",
        "record_force_verify": "导入记录：回收前强制逐字节复核",
    },
    "en": {
        "app_title": "Folder Dedupe",
        "header_title": "Folder Dedupe",
        "header_subtitle": "Triple-check (size → full SHA-256 → byte compare) finds byte-identical "
        "duplicates across subfolders of one folder",
        "header_note": "Each group keeps exactly one file (keep strategy selectable); the rest go to "
        "the recycle bin. The keeper is never recycled. Recycle bin only.",
        "language": "Language",
        "root_dir": "Scan folder",
        "root_dir_placeholder": "Choose the folder to dedupe",
        "choose_dir": "Choose folder",
        "scope": "Scan scope",
        "scope_all": "All files",
        "scope_media": "Photos/videos only",
        "keep_strategy": "Keep",
        "keep_shallowest": "Shallowest / shortest path",
        "keep_oldest": "Oldest modified",
        "keep_newest": "Newest modified",
        "keep_strategy_changed": "Keep strategy changed; rescan before recycling",
        "hash_threads": "Hash threads",
        "byte_verify": "Byte-verify again before recycle",
        "btn_scan": "Start scan",
        "btn_stop_scan": "Stop scan",
        "btn_recycle": "Move to recycle bin",
        "btn_pause": "Pause",
        "btn_resume": "Resume",
        "btn_stop_recycle": "Stop recycle",
        "table_check": "☐",
        "table_group": "Group",
        "table_thumb": "Preview",
        "table_role": "Role",
        "table_path": "Path",
        "table_size": "Size",
        "table_mtime": "Modified",
        "table_hash": "SHA-256",
        "table_status": "Status",
        "role_keep": "Keep",
        "role_duplicate": "Duplicate",
        "preview_selected": "Selected file",
        "preview_keeper": "Group keeper",
        "preview_issue": "Problem file",
        "tabs_hint": "Check the duplicate files to recycle; keeper rows cannot be checked. "
        "Double-click to open; right-click for more.",
        "waiting": "Waiting for a folder",
        "scanning": "Scanning",
        "status_scanning_stage": "{stage} {done}/{total}",
        "stage_enumerate": "Enumerating",
        "stage_hash": "Hashing",
        "stage_verify": "Byte verifying",
        "stage_recycle": "Recycling",
        "scan_done": "Scan complete: {groups} duplicate group(s), {count} recyclable of "
        "{total} file(s)",
        "scan_none": "No byte-identical duplicates found in this folder",
        "scan_cancelled": "Scan cancelled; results cannot be recycled. Please rescan.",
        "scan_failed": "Scan failed: {error}",
        "summary_ready": "Recyclable {count} / total {total}",
        "summary_detail": "Mismatch {mismatch}; read issues {issue}",
        "summary_done": "Recycled {success} / skipped {skipped} / failed {failed} / "
        "mismatch {mismatch} / read issues {issue}",
        "summary_empty": "",
        "summary_stale": "Keep strategy changed: rescan required",
        "space_summary": "Estimated reclaimable: {total} (selected: {selected})",
        "space_summary_tooltip": "Estimated from pending duplicates' logical file sizes; space is released only after emptying the recycle bin.",
        "status_pending": "Pending",
        "status_keep": "Keep",
        "status_recycled": "Recycled",
        "status_skipped": "Skipped: {reason}",
        "status_failed": "Failed: {reason}",
        "status_mismatch": "Verification mismatch",
        "status_issue": "Read issue: {message}",
        "status_paused": "Paused",
        "status_stopping": "Stopping",
        "recycle_done_status": "Recycle complete: {success} recycled, {skipped} skipped, "
        "{failed} failed",
        "status_stopped": "Stopped: {success} recycled, {skipped} skipped, {failed} failed",
        "skip_target_missing": "target file is missing",
        "skip_keeper_missing": "keeper file is missing",
        "skip_target_changed": "target file changed",
        "skip_keeper_changed": "keeper file changed",
        "skip_same_path": "same path",
        "skip_content_differs": "content no longer matches",
        "skip_read_error": "read error",
        "fail_send2trash_unavailable": "send2trash unavailable",
        "confirm_title": "Confirm recycle",
        "confirm_content": "Move {count} duplicate file(s) ({size}) to the recycle bin; each group "
        "keeps at least one file and nothing is permanently deleted.\nEvery file is revalidated "
        "right before recycling; any check failure skips it. Continue?",
        "missing_trash_title": "Recycle bin unavailable",
        "missing_trash_content": "send2trash is not available. Install send2trash first.",
        "cannot_start_title": "Cannot start",
        "cannot_start_content": "There is no recyclable duplicate file.",
        "cannot_start_cancelled": "The scan was cancelled. Please rescan before recycling.",
        "cannot_start_stale": "The keep strategy changed. Please rescan before recycling.",
        "invalid_root_title": "Cannot scan",
        "invalid_root_missing": "The folder does not exist or is not a folder",
        "invalid_root_not_dir": "The selected path is not a folder",
        "recycle_done_title": "Recycle complete",
        "recycle_done_message": "Recycled: {success}\nSkipped: {skipped}\nFailed: {failed}",
        "blocked_busy": "A task is running, please wait.",
        "menu_open": "Open file",
        "menu_open_folder": "Show in folder",
        "menu_open_keeper_folder": "Show group keeper in folder",
        "menu_copy_path": "Copy path",
        "menu_copy_files": "Copy files",
        "menu_cut_files": "Cut files",
        "menu_system": "System context menu...",
        "btn_select_all": "Select all",
        "btn_select_none": "Select none",
        "btn_invert": "Invert",
        "category_photo": "Photos · {groups} groups / {files} files",
        "category_video": "Videos · {groups} groups / {files} files",
        "category_other": "Other · {groups} groups / {files} files",
        "btn_set_keeper": "Set as keeper",
        "keeper_changed": "Selected file is now the group keeper",
        "keeper_reselect_invalid": "Cannot change keeper: candidate changed or this group has processed items",
        "btn_export_record": "Export record",
        "btn_import_record": "Import record",
        "record_action_save": "export",
        "record_action_load": "import",
        "record_working": "{action}ing scan record…",
        "record_done_title": "Scan record",
        "record_saved": "Scan record exported: {path}",
        "record_imported": "Scan record imported: {path}; byte-verify is enforced before recycling",
        "record_import_failed": "Import failed: {error}",
        "record_save_failed": "Export failed: {error}",
        "record_export_title": "Export scan record",
        "record_import_title": "Import scan record",
        "record_no_data": "No scan result to export yet; scan or import a record first",
        "record_import_cancelled": "The imported record was cancelled; recycling is blocked",
        "record_import_stale": "The imported record is stale; rescan required",
        "record_force_verify": "Imported record: byte-verify enforced before recycling",
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
class DedupeRow:
    """表格一行：保留文件 / 已确认重复 / 校验不一致 / 读取问题。"""

    kind: str                                    # "keeper" | "duplicate" | "mismatch" | "issue"
    group_id: int = 0                            # 0 表示不属于任何重复组
    entry: FileEntry | None = None               # 本行文件（保留行即 keeper）
    keeper: FileEntry | None = None              # 本组保留文件
    sha256: str = ""
    issue_path: Path | None = None
    issue_stage: str = ""
    checked: bool = False
    status: str = "status_pending"

    def is_checkable(self) -> bool:
        """只有扫描阶段已逐字节确认一致的重复行才能勾选回收；保留行永不可勾选。"""
        return self.kind == KIND_DUPLICATE and self.status == "status_pending"

    def primary_path(self) -> Path | None:
        if self.entry is not None:
            return self.entry.path
        return self.issue_path

    def keeper_path(self) -> Path | None:
        return self.keeper.path if self.keeper is not None else None

    def size(self) -> int:
        return self.entry.size if self.entry is not None else 0

    def mtime_ns(self) -> int:
        return self.entry.mtime_ns if self.entry is not None else 0

    def relative_path(self) -> Path | None:
        return self.entry.relative_path if self.entry is not None else None


class DedupeTableModel(QAbstractTableModel):
    def __init__(self, rows: list[DedupeRow], owner: "MainWindow"):
        super().__init__(owner)
        self.rows = rows
        self.owner = owner
        # 同组行底色按组号交替，便于区分分组
        self.group_bg_odd = QBrush(QColor("#F5F8FF"))
        self.mismatch_bg = QBrush(QColor("#FFF4E5"))
        self.issue_bg = QBrush(QColor("#FEF3F2"))
        self.mismatch_fg = QBrush(QColor("#B54708"))
        self.issue_fg = QBrush(QColor("#B42318"))
        self.done_fg = QBrush(QColor("#667085"))

    # ---- Qt 模型接口 ----
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else COLUMN_COUNT

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole):
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
        if role == Qt.ItemDataRole.DecorationRole and column == COL_THUMB:
            path = row.primary_path()
            if path is None:
                return None
            return self.owner._thumbnail_for(path)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(row, column)
        if role == Qt.ItemDataRole.FontRole and column == COL_ROLE:
            if row.kind == KIND_KEEPER:
                font = QFont()
                font.setBold(True)
                return font
            return None
        if role == Qt.ItemDataRole.BackgroundRole:
            if row.kind == KIND_MISMATCH:
                return self.mismatch_bg
            if row.kind == KIND_ISSUE:
                return self.issue_bg
            if row.group_id and row.group_id % 2 == 0:
                return self.group_bg_odd
            return None
        if role == Qt.ItemDataRole.ForegroundRole:
            if row.kind == KIND_MISMATCH:
                return self.mismatch_fg
            if row.kind == KIND_ISSUE:
                return self.issue_fg
            if row.status.startswith(("status_recycled", "status_skipped")):
                return self.done_fg
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
    def _checkable(self, row: DedupeRow) -> bool:
        if not row.is_checkable():
            return False
        # 保留策略变更后旧结果作废：扫描结果与实际保留文件不再对应，禁止回收
        if getattr(self.owner, "_scan_stale", False):
            return False
        # 取消的扫描/导入记录不能执行回收（PRD R4）
        if getattr(self.owner, "_scan_cancelled", False):
            return False
        return True

    def _display_value(self, row: DedupeRow, column: int) -> str:
        if column == COL_CHECK:
            return ""
        if column == COL_GROUP:
            return str(row.group_id) if row.group_id else "-"
        if column == COL_THUMB:
            return ""
        if column == COL_ROLE:
            if row.kind == KIND_KEEPER:
                return self.owner.tr("role_keep")
            if row.kind == KIND_DUPLICATE:
                return self.owner.tr("role_duplicate")
            return ""
        if column == COL_PATH:
            if row.kind == KIND_ISSUE:
                return str(row.issue_path) if row.issue_path is not None else ""
            relative = row.relative_path()
            return str(relative) if relative is not None else ""
        if column == COL_SIZE:
            return _format_size(row.size()) if row.size() else ""
        if column == COL_MTIME:
            return _format_mtime(row.mtime_ns()) if row.mtime_ns() else ""
        if column == COL_HASH:
            return row.sha256[:12] if row.sha256 else "-"
        if column == COL_STATUS:
            return self.owner._display_status(row.status)
        return ""

    def _tooltip(self, row: DedupeRow, column: int) -> str | None:
        if column == COL_PATH:
            path = row.primary_path()
            return str(path) if path is not None else None
        if column == COL_HASH:
            return row.sha256 or None
        if column == COL_STATUS:
            return self.owner._display_status(row.status)
        if column == COL_ROLE and row.keeper_path() is not None:
            return str(row.keeper_path())
        return None

    # ---- 批量更新 ----
    def reset_rows(self, rows: list[DedupeRow]):
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


class DedupeContextMenu(FileContextMenu):
    """在共用右键菜单基础上追加"打开保留文件所在目录"。

    复用 ``file_context_menu`` 的选中/定位/剪贴板/系统菜单能力，不另起一套。
    """

    def __init__(self, table, owner, path_provider, keeper_provider, language_provider,
                 label_provider):
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
            act_keeper_folder = menu.addAction(self._label("menu_open_keeper_folder"))
            act_keeper_folder.triggered.connect(
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


class DedupeScanWorker(QObject):
    """目录内去重扫描 worker：只调用核心模块，绝不碰 UI。"""

    progress_update = pyqtSignal(str, int, int)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, root: Path, scope: str, keep_strategy: str, threads: int):
        super().__init__()
        self._root = root
        self._scope = scope if scope in SCOPES else SCOPE_ALL
        self._keep_strategy = keep_strategy if keep_strategy in KEEP_STRATEGIES else KEEP_SHALLOWEST
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
            result = find_internal_duplicates(
                self._root,
                scope=self._scope,
                keep_strategy=self._keep_strategy,
                threads=self._threads,
                should_cancel=self._should_cancel,
                on_progress=self._on_progress,
            )
        except Exception as exc:  # 环境/权限类意外：不让异常穿透 Qt 事件循环
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(result)


class DedupeRecycleWorker(QObject):
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


class RecordSaveWorker(QObject):
    """后台导出扫描记录（文件 IO 不进主线程）。"""

    finished = pyqtSignal(str)   # 写入的路径
    failed = pyqtSignal(str)

    def __init__(self, path: Path, record: ScanRecord):
        super().__init__()
        self._path = Path(path)
        self._record = record

    def run(self):
        try:
            save_record(self._path, self._record)
        except Exception as exc:  # 包括 ValueError/OSError
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(str(self._path))

class RecordLoadWorker(QObject):
    """后台导入扫描记录：只有完整解析成功才发 finished。"""

    finished = pyqtSignal(object)  # ScanRecord
    failed = pyqtSignal(str)

    def __init__(self, path: Path):
        super().__init__()
        self._path = Path(path)

    def run(self):
        try:
            record = load_record(self._path, expected_mode=RECORD_MODE)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(record)

class MainWindow(FramelessMainWindow):
    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("Folder Dedupe")
        self._title_bar_height = 36
        if not self._embedded:
            self.resize(1360, 880)
            self._set_blue_title_bar()

        self.lang = DEFAULT_LANGUAGE
        self._last_status_key = "waiting"
        self._last_status_kwargs: dict = {}
        self._scan_cancelled = False
        self._scan_stale = False
        self._group_count = 0
        self._mismatch_count = 0
        self._issue_count = 0
        self._recycled_count = 0
        self._skipped_count = 0
        self._failed_count = 0
        self._has_scan = False
        self.is_scanning = False
        self.is_recycling = False
        self._recycle_paused = False
        self._recycle_stopping = False
        self._pending_close = False

        self._scan_thread: QThread | None = None
        self._scan_worker: DedupeScanWorker | None = None
        self._recycle_thread: QThread | None = None
        self._recycle_worker: DedupeRecycleWorker | None = None
        # 扫描记录导入导出（后台线程）；引用非 None 即视为忙，直到 finished 清理
        self._record_thread: QThread | None = None
        self._record_worker: RecordSaveWorker | RecordLoadWorker | None = None
        self._record_action = ""

        # 扫描/导入时的根与选项快照（导出只用它，不读后来修改过的控件）
        self._scan_snapshot: dict | None = None
        self._current_result: ScanResult | None = None
        self._record_imported = False

        # 每个源行固定归属一个类别；筛选仅隐藏行，绝不重排/重建 worker 的源索引
        self.active_category = "photo"
        self._row_categories: list[str] = []
        self._group_categories: dict[int, str] = {}
        self.category_buttons: dict[str, PushButton] = {}

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

        self.table_model = DedupeTableModel([], self)

        self._build_ui()
        self._load_settings()
        self._apply_language()
        self._update_action_states()

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._shutdown_workers)

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

        row_dir = QHBoxLayout()
        row_dir.setSpacing(10)
        self.root_label = BodyLabel(self.tr("root_dir"), self)
        self.root_edit = LineEdit(self)
        self.root_edit.setReadOnly(False)
        self.root_edit.setPlaceholderText(self.tr("root_dir_placeholder"))
        self.btn_root = PushButton(self.tr("choose_dir"), self)
        self.btn_root.setIcon(_pick_icon("FOLDER", "FOLDER_ADD"))
        self.btn_root.clicked.connect(lambda _checked=False: self.browse_root())
        row_dir.addWidget(self.root_label)
        row_dir.addWidget(self.root_edit, 1)
        row_dir.addWidget(self.btn_root)

        row_opts = QHBoxLayout()
        row_opts.setSpacing(12)
        self.scope_label = BodyLabel(self.tr("scope"), self)
        self.scope_combo = ComboBox(self)
        self.scope_combo.setFixedWidth(140)
        self.scope_combo.addItem(self.tr("scope_all"), userData=SCOPE_ALL)
        self.scope_combo.addItem(self.tr("scope_media"), userData=SCOPE_MEDIA)
        self.keep_strategy_label = BodyLabel(self.tr("keep_strategy"), self)
        self.keep_strategy_combo = ComboBox(self)
        self.keep_strategy_combo.setFixedWidth(190)
        self.keep_strategy_combo.addItem(self.tr("keep_shallowest"), userData=KEEP_SHALLOWEST)
        self.keep_strategy_combo.addItem(self.tr("keep_oldest"), userData=KEEP_OLDEST)
        self.keep_strategy_combo.addItem(self.tr("keep_newest"), userData=KEEP_NEWEST)
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
        row_opts.addWidget(self.keep_strategy_label)
        row_opts.addWidget(self.keep_strategy_combo)
        row_opts.addWidget(self.byte_verify_check)
        row_opts.addWidget(self.hash_thread_label)
        row_opts.addWidget(self.thread_count_combo)
        row_opts.addStretch(1)

        path_layout.addLayout(row_dir)
        path_layout.addLayout(row_opts)

        # ---- 表格 + 预览 ----
        table_card = CardWidget(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(10, 10, 10, 10)
        table_layout.setSpacing(8)
        self.tabs_hint = BodyLabel(self.tr("tabs_hint"), self)
        self.tabs_hint.setStyleSheet("color: #6b7280; padding: 4px 6px;")
        self.category_bar = QHBoxLayout()
        self.category_bar.setSpacing(8)
        self.category_buttons = {}
        self.btn_filter_photo = PushButton("", self)
        self.btn_filter_video = PushButton("", self)
        self.btn_filter_other = PushButton("", self)
        self.category_buttons.update({
            "photo": self.btn_filter_photo,
            "video": self.btn_filter_video,
            "other": self.btn_filter_other,
        })
        for category, button in self.category_buttons.items():
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked=False, value=category: self.set_active_category(value)
            )
            self.category_bar.addWidget(button)

        self.table = TableView(self)
        self.table.setModel(self.table_model)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setWordWrap(False)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_CHECK, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_GROUP, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_THUMB, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_ROLE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_PATH, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_MTIME, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_HASH, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(COL_CHECK, 34)
        self.table.setColumnWidth(COL_GROUP, 64)
        self.table.setColumnWidth(COL_THUMB, THUMBNAIL_SIZE + 12)
        self.table.setColumnWidth(COL_ROLE, 76)

        self.table_context_menu = DedupeContextMenu(
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
        table_layout.addWidget(self.tabs_hint)
        table_layout.addLayout(self.category_bar)
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

        # 批量勾选 + 扫描记录（第二行，避免 1360 宽工具栏溢出）
        row4 = QHBoxLayout()
        row4.setSpacing(8)
        self.btn_select_all = PushButton(self.tr("btn_select_all"), self)
        self.btn_select_all.clicked.connect(lambda _checked=False: self.select_all_checkable())
        self.btn_select_none = PushButton(self.tr("btn_select_none"), self)
        self.btn_select_none.clicked.connect(lambda _checked=False: self.select_none_checkable())
        self.btn_invert = PushButton(self.tr("btn_invert"), self)
        self.btn_invert.clicked.connect(lambda _checked=False: self.invert_checkable())
        row4.addWidget(self.btn_select_all)
        row4.addWidget(self.btn_select_none)
        row4.addWidget(self.btn_invert)
        self.btn_set_keeper = PrimaryPushButton(self.tr("btn_set_keeper"), self)
        self.btn_set_keeper.setIcon(_pick_icon("PIN", "FAVORITE", "SAVE"))
        self.btn_set_keeper.clicked.connect(lambda _checked=False: self.set_selected_as_keeper())
        row4.addWidget(self.btn_set_keeper)
        row4.addStretch(1)
        self.btn_export_record = PushButton(self.tr("btn_export_record"), self)
        self.btn_export_record.clicked.connect(lambda _checked=False: self.export_scan_record())
        self.btn_import_record = PushButton(self.tr("btn_import_record"), self)
        self.btn_import_record.clicked.connect(lambda _checked=False: self.import_scan_record())
        row4.addWidget(self.btn_export_record)
        row4.addWidget(self.btn_import_record)
        action_layout.addLayout(row4)

        # Ctrl+A 仅勾选合法待回收行（不改变表格行选择）
        self._select_all_shortcut = QShortcut(QKeySequence.StandardKey.SelectAll, self)
        self._select_all_shortcut.activated.connect(self.select_all_checkable)

        # ---- 底部 ----
        foot_card = CardWidget(self)
        foot_layout = QVBoxLayout(foot_card)
        foot_layout.setContentsMargins(16, 12, 16, 12)
        foot_layout.setSpacing(6)
        foot_status_layout = QHBoxLayout()
        foot_status_layout.setSpacing(10)
        self.summary = BodyLabel(self.tr("summary_empty"), self)
        self.summary.setStyleSheet("color: #475467;")
        self.progress = ProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setFixedHeight(10)
        self.progress.setMinimumWidth(240)
        self.progress.setMaximumWidth(360)
        self.status = BodyLabel(self.tr("waiting"), self)
        self.status.setStyleSheet("color: #475467;")
        foot_status_layout.addWidget(self.summary, 1)
        foot_status_layout.addWidget(
            self.progress, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        foot_status_layout.addWidget(
            self.status, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.space_summary = BodyLabel("", self)
        self.space_summary.setWordWrap(True)
        self.space_summary.setStyleSheet("color: #667085;")
        self.space_summary.setToolTip(self.tr("space_summary_tooltip"))
        foot_layout.addLayout(foot_status_layout)
        foot_layout.addWidget(self.space_summary)

        outer.addWidget(header_card)
        outer.addWidget(path_card)
        outer.addWidget(self.splitter, 1)
        outer.addWidget(action_card)
        outer.addWidget(foot_card)

        self.scope_combo.currentIndexChanged.connect(lambda _index=0: self._save_settings())
        self.thread_count_combo.currentIndexChanged.connect(lambda _index=0: self._save_settings())
        self.byte_verify_check.toggled.connect(lambda _checked=False: self._save_settings())
        self.root_edit.editingFinished.connect(lambda: self._save_settings())
        self.keep_strategy_combo.currentIndexChanged.connect(self._on_keep_strategy_changed)

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
            self.tr("table_group"),
            self.tr("table_thumb"),
            self.tr("table_role"),
            self.tr("table_path"),
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

    def _keep_strategy(self) -> str:
        value = self.keep_strategy_combo.currentData()
        return value if value in KEEP_STRATEGIES else KEEP_SHALLOWEST

    def _set_keep_strategy(self, strategy: str):
        if strategy not in KEEP_STRATEGIES:
            strategy = KEEP_SHALLOWEST
        for index in range(self.keep_strategy_combo.count()):
            if self.keep_strategy_combo.itemData(index) == strategy:
                self.keep_strategy_combo.setCurrentIndex(index)
                return

    def _refresh_combo_labels(self):
        scope_labels = {SCOPE_ALL: self.tr("scope_all"), SCOPE_MEDIA: self.tr("scope_media")}
        current_scope = self._scope()
        for index in range(self.scope_combo.count()):
            scope = self.scope_combo.itemData(index)
            if scope in scope_labels:
                self.scope_combo.setItemText(index, scope_labels[scope])
        self.scope_combo.blockSignals(True)
        try:
            for index in range(self.scope_combo.count()):
                if self.scope_combo.itemData(index) == current_scope:
                    self.scope_combo.setCurrentIndex(index)
                    break
        finally:
            self.scope_combo.blockSignals(False)

        strategy_labels = {
            KEEP_SHALLOWEST: self.tr("keep_shallowest"),
            KEEP_OLDEST: self.tr("keep_oldest"),
            KEEP_NEWEST: self.tr("keep_newest"),
        }
        current_strategy = self._keep_strategy()
        for index in range(self.keep_strategy_combo.count()):
            strategy = self.keep_strategy_combo.itemData(index)
            if strategy in strategy_labels:
                self.keep_strategy_combo.setItemText(index, strategy_labels[strategy])
        self.keep_strategy_combo.blockSignals(True)
        try:
            for index in range(self.keep_strategy_combo.count()):
                if self.keep_strategy_combo.itemData(index) == current_strategy:
                    self.keep_strategy_combo.setCurrentIndex(index)
                    break
        finally:
            self.keep_strategy_combo.blockSignals(False)

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
            "root": self.root_edit.text().strip(),
            "scope": self._scope(),
            "keep_strategy": self._keep_strategy(),
            "hash_threads": self._thread_count(),
            "byte_verify": self.byte_verify_check.isChecked(),
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
            self._set_keep_strategy(str(data.get("keep_strategy", KEEP_SHALLOWEST)))
            self._set_thread_count(int(data.get("hash_threads", _default_thread_count())))
            self.byte_verify_check.setChecked(bool(data.get("byte_verify", True)))
            root = str(data.get("root", "") or "")
            if root:
                self.root_edit.setText(root)
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

    def _on_keep_strategy_changed(self, _index: int = 0):
        self._save_settings()
        if self._suspend_settings_save or self._is_busy() or not self._has_scan:
            return
        # 保留策略变更会让已有结果的 keeper 不再匹配，要求重新扫描（最简且安全）
        self._scan_stale = True
        self._notify(self.tr("cannot_start_title"), self.tr("keep_strategy_changed"), is_error=True)
        self._set_status_text("keep_strategy_changed")
        self._refresh_summary()
        self._update_action_states()
        self._refresh_check_column()

    def _refresh_check_column(self):
        """刷勾选列（结果作废/回收后勾选态会变化）。行数为 0 时不发信号。"""
        rows = self.table_model.rows
        if not rows:
            return
        self.table_model.dataChanged.emit(
            self.table_model.index(0, COL_CHECK),
            self.table_model.index(len(rows) - 1, COL_CHECK),
            [Qt.ItemDataRole.CheckStateRole],
        )

    def _apply_language(self):
        self.setWindowTitle(self.tr("app_title"))
        self.title_label.setText(self.tr("header_title"))
        self.subtitle_label.setText(self.tr("header_subtitle"))
        self.subtitle_note_label.setText(self.tr("header_note"))
        self.elevation_hint.set_language(self.lang)
        self.language_label.setText(self.tr("language"))
        self.root_label.setText(self.tr("root_dir"))
        self.root_edit.setPlaceholderText(self.tr("root_dir_placeholder"))
        self.btn_root.setText(self.tr("choose_dir"))
        self.scope_label.setText(self.tr("scope"))
        self.keep_strategy_label.setText(self.tr("keep_strategy"))
        self._refresh_combo_labels()
        self.byte_verify_check.setText(self.tr("byte_verify"))
        self.hash_thread_label.setText(self.tr("hash_threads"))
        self.tabs_hint.setText(self.tr("tabs_hint"))
        self.btn_scan.setText(self.tr("btn_scan"))
        self.btn_stop_scan.setText(self.tr("btn_stop_scan"))
        self.btn_recycle.setText(self.tr("btn_recycle"))
        self.btn_pause.setText(
            self.tr("btn_resume") if self._recycle_paused else self.tr("btn_pause")
        )
        self.btn_stop_recycle.setText(self.tr("btn_stop_recycle"))
        self.btn_select_all.setText(self.tr("btn_select_all"))
        self.btn_select_none.setText(self.tr("btn_select_none"))
        self.btn_invert.setText(self.tr("btn_invert"))
        self.btn_export_record.setText(self.tr("btn_export_record"))
        self.btn_import_record.setText(self.tr("btn_import_record"))
        self.btn_set_keeper.setText(self.tr("btn_set_keeper"))
        self._update_category_button_labels()
        self.space_summary.setToolTip(self.tr("space_summary_tooltip"))
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
    # 类型筛选（只隐藏源行；source row 与 worker row_index 永不改变）
    # ------------------------------------------------------------------
    def _update_category_metadata(
        self,
        rows: list[DedupeRow],
        result: ScanResult,
        *,
        choose_default: bool = False,
    ) -> None:
        self._group_categories = {
            group_id: classify_duplicate_group(group)
            for group_id, group in enumerate(result.groups, start=1)
        }
        categories: list[str] = []
        for row in rows:
            if row.group_id:
                category = self._group_categories.get(row.group_id, "other")
            else:
                path = row.primary_path()
                category = classify_media_type(path) if path is not None else "other"
            categories.append(category)
        self._row_categories = categories
        if choose_default or self.active_category not in {"photo", "video", "other"}:
            self.active_category = next(
                (category for category in ("photo", "video", "other")
                 if any(item == category for item in categories)),
                "photo",
            )
        self._update_category_button_labels()
        self._apply_category_filter()
        current_row = self.table.currentIndex().row()
        if not self._row_is_visible(current_row):
            candidate_row = next(
                (index for index, item in enumerate(categories) if item == self.active_category),
                None,
            )
            if candidate_row is None:
                self.table.clearSelection()
                self.table.selectionModel().clearCurrentIndex()
                self.preview_panel.clear()
            else:
                self.table.setCurrentIndex(self.table_model.index(candidate_row, COL_PATH))

    def _update_category_button_labels(self) -> None:
        for category in ("photo", "video", "other"):
            button = self.category_buttons.get(category)
            if button is None:
                continue
            group_count = sum(1 for value in self._group_categories.values() if value == category)
            file_count = sum(1 for value in self._row_categories if value == category)
            button.setText(
                self.tr(f"category_{category}", groups=group_count, files=file_count)
            )
            button.blockSignals(True)
            try:
                button.setChecked(category == self.active_category)
            finally:
                button.blockSignals(False)

    def set_active_category(self, category: str) -> None:
        """切换分类只 setRowHidden；不重排、不重建源 rows。"""
        if category not in ("photo", "video", "other"):
            return
        self.active_category = category
        self._apply_category_filter()
        self._update_category_button_labels()
        current = self.table.currentIndex()
        if not current.isValid() or not self._row_is_visible(current.row()):
            candidate = next(
                (i for i, item in enumerate(self._row_categories) if item == category), None
            )
            if candidate is None:
                self.table.clearSelection()
                self.table.selectionModel().clearCurrentIndex()
                self.preview_panel.clear()
            else:
                self.table.setCurrentIndex(self.table_model.index(candidate, COL_PATH))
        self._refresh_preview()
        self._update_action_states()

    def _row_is_visible(self, row_index: int) -> bool:
        return (
            0 <= row_index < len(self._row_categories)
            and self._row_categories[row_index] == self.active_category
        )

    def _apply_category_filter(self) -> None:
        for row_index in range(len(self.table_model.rows)):
            self.table.setRowHidden(row_index, not self._row_is_visible(row_index))

    def _visible_checkable_rows(self) -> list[tuple[int, DedupeRow]]:
        return [
            (row_index, row)
            for row_index, row in enumerate(self.table_model.rows)
            if self._row_is_visible(row_index) and self.table_model._checkable(row)
        ]

    # ------------------------------------------------------------------
    # 缩略图 / 预览
    # ------------------------------------------------------------------
    def _thumbnail_for(self, path: Path) -> QPixmap | None:
        # 先检查路径自身类型；other 不得触发 loader（包括混合扩展名组成员）。
        if classify_media_type(path) == "other":
            return None
        try:
            return self.thumbnail_loader.request(path)
        except Exception:
            return None

    def _on_thumbnail_ready(self, path: str):
        # other 文件永远不入缩略图索引；即使旧 loader 信号晚到也不触发无意义刷新
        if classify_media_type(path) == "other":
            return
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
        for row_index, row in enumerate(self.table_model.rows):
            path = row.primary_path()
            if path is None or classify_media_type(path) == "other":
                continue
            for key in {str(path), str(_safe_resolve(path))}:
                self._path_cells.setdefault(key, []).append((row_index, COL_THUMB))

    def _refresh_preview(self):
        row_index = self.table.currentIndex().row()
        rows = self.table_model.rows
        if not (0 <= row_index < len(rows)) or not self._row_is_visible(row_index):
            self.preview_panel.clear()
            return
        row = rows[row_index]
        selected_path = row.primary_path()
        selected_title = self.tr("preview_issue" if row.kind == KIND_ISSUE else "preview_selected")
        selected_size = row.entry.size if row.entry is not None else None
        selected_mtime = row.entry.mtime_ns if row.entry is not None else None
        selected_is_other = selected_path is not None and classify_media_type(selected_path) == "other"
        if selected_is_other:
            # 当前行是非媒体时清掉上一行可能残留的两槽内容；随后仍逐槽恢复可预览的 keeper。
            self.preview_panel.clear()
        self._set_preview_slot_by_path(0, selected_title, selected_path, selected_size, selected_mtime)

        keeper_path = row.keeper.path if row.keeper is not None else None
        keeper_size = row.keeper.size if row.keeper is not None else None
        keeper_mtime = row.keeper.mtime_ns if row.keeper is not None else None
        self._set_preview_slot_by_path(
            1, self.tr("preview_keeper"), keeper_path, keeper_size, keeper_mtime
        )

    def _set_preview_slot_by_path(
        self,
        slot_index: int,
        title: str,
        path: Path | None,
        size_bytes: int | None,
        mtime_ns: int | None,
    ) -> None:
        # 每个槽独立检查路径类型。混合扩展名组中，选中项是 photo 不代表 keeper 也是媒体。
        if path is not None and classify_media_type(path) == "other":
            self.preview_panel.set_slot(slot_index, title, None, None, None)
            return
        self.preview_panel.set_slot(slot_index, title, path, size_bytes, mtime_ns)

    def _on_current_row_changed(self, _current: QModelIndex, _previous: QModelIndex):
        self._refresh_preview()
        self._refresh_keeper_action()
        self._update_action_states()

    # ------------------------------------------------------------------
    # 右键 / 双击
    # ------------------------------------------------------------------
    def _refresh_keeper_action(self) -> None:
        button = getattr(self, "btn_set_keeper", None)
        if button is None:
            return
        row_index = self.table.currentIndex().row()
        button.setEnabled(self._can_reselect_keeper(row_index))

    def _can_reselect_keeper(self, row_index: int) -> bool:
        """只做角色/快照资格检查；不读文件内容、不 hash、不做字节比较。"""
        if (
            self._is_busy()
            or not self._has_scan
            or self._current_result is None
            or self._scan_cancelled
            or self._scan_stale
            or not self._row_is_visible(row_index)
            or not (0 <= row_index < len(self.table_model.rows))
        ):
            return False
        row = self.table_model.rows[row_index]
        if row.kind != KIND_DUPLICATE or row.status != "status_pending" or row.entry is None:
            return False
        group_index = row.group_id - 1
        if not (0 <= group_index < len(self._current_result.groups)):
            return False
        group = self._current_result.groups[group_index]
        if row.group_id <= 0 or row.keeper is None:
            return False
        # 整组任何已处理/非 pending target 均不得经 keeper 切换重获回收资格。
        group_rows = [item for item in self.table_model.rows if item.group_id == row.group_id]
        if not group_rows or any(
            item.kind == KIND_DUPLICATE and item.status != "status_pending"
            for item in group_rows
        ):
            return False
        if any(item.kind not in (KIND_KEEPER, KIND_DUPLICATE) for item in group_rows):
            return False
        if row.entry.path not in {entry.path for entry in [group.keeper, *group.duplicates]}:
            return False
        try:
            stat = row.entry.path.stat()
        except OSError:
            return False
        return (
            int(stat.st_size) == int(row.entry.size)
            and int(stat.st_mtime_ns) == int(row.entry.mtime_ns)
        )

    def set_selected_as_keeper(self) -> bool:
        """将当前组的所选副本设为 keeper，原行索引和分类筛选均保持不变。"""
        row_index = self.table.currentIndex().row()
        if not self._can_reselect_keeper(row_index):
            self._notify(
                self.tr("cannot_start_title"), self.tr("keeper_reselect_invalid"), is_error=True
            )
            self._refresh_keeper_action()
            return False

        row = self.table_model.rows[row_index]
        group_index = row.group_id - 1
        old_group = self._current_result.groups[group_index]
        candidate = row.entry
        if candidate is None or candidate.path == old_group.keeper.path:
            return False

        # 纯内存 API 只重排同一内部组；stat 快照守卫已在上方通过。
        try:
            new_group = reselect_internal_keeper(old_group, candidate)
        except ValueError:
            self._notify(
                self.tr("cannot_start_title"), self.tr("keeper_reselect_invalid"), is_error=True
            )
            return False

        old_keeper_path = old_group.keeper.path
        new_keeper_path = new_group.keeper.path
        by_path = {item.entry.path: item for item in self.table_model.rows
                   if item.group_id == row.group_id and item.entry is not None}
        old_keeper_row = by_path.get(old_keeper_path)
        new_keeper_row = by_path.get(new_keeper_path)
        if old_keeper_row is None or new_keeper_row is None:
            return False

        # 原 keeper 转为可回收副本并默认勾选；新 keeper 不勾选；其它副本状态原样保留。
        old_keeper_row.kind = KIND_DUPLICATE
        old_keeper_row.keeper = new_group.keeper
        old_keeper_row.checked = True
        old_keeper_row.status = "status_pending"
        for item in new_group.duplicates:
            duplicate_row = by_path.get(item.path)
            if duplicate_row is None:
                return False
            duplicate_row.kind = KIND_DUPLICATE
            duplicate_row.keeper = new_group.keeper
        new_keeper_row.kind = KIND_KEEPER
        new_keeper_row.keeper = new_group.keeper
        new_keeper_row.checked = False
        new_keeper_row.status = "status_keep"
        new_keeper_row.sha256 = new_group.sha256
        new_keeper_row.group_id = row.group_id
        # 核心组原子替换；源 rows 不重建，所以 worker row_index 永久稳定。
        self._current_result.groups[group_index] = new_group
        self._group_count = len(self._current_result.groups)
        self._update_category_metadata(
            self.table_model.rows, self._current_result, choose_default=False
        )
        first = min(self.table_model.rows.index(item) for item in by_path.values())
        last = max(self.table_model.rows.index(item) for item in by_path.values())
        self.table_model.dataChanged.emit(
            self.table_model.index(first, 0),
            self.table_model.index(last, COLUMN_COUNT - 1),
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.CheckStateRole,
                Qt.ItemDataRole.ForegroundRole,
                Qt.ItemDataRole.FontRole,
            ],
        )
        self._refresh_preview()
        self._refresh_summary()
        self._update_action_states()
        self._notify(self.tr("record_done_title"), self.tr("keeper_changed"))
        return True

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
        return (
            self.is_scanning
            or self.is_recycling
            # 线程引用非 None 即忙：``isRunning()==False`` 到 finished 回调清理之间
            # 按钮可能已重新启用，此时再点击会覆盖唯一引用或多个任务交错。
            or self._scan_thread is not None
            or self._recycle_thread is not None
            or self._record_thread is not None
            or self._drain_timer.isActive()
            or bool(self._process_update_queue)
        )

    def _recyclable_rows(self) -> list[DedupeRow]:
        return [
            row
            for row in self.table_model.rows
            if row.checked and row.kind == KIND_DUPLICATE and row.status == "status_pending"
        ]

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
        batch_enabled = (
            (not busy) and has_rows and not self._scan_stale and not self._scan_cancelled
        )
        for button in (self.btn_select_all, self.btn_select_none, self.btn_invert):
            button.setEnabled(batch_enabled)
        self._refresh_keeper_action()
        # 导出用扫描时的快照；只要有一次完整结果就可导出（记录里保留 cancelled/stale）
        self.btn_export_record.setEnabled((not busy) and self._current_result is not None)
        self.btn_import_record.setEnabled(not busy)
        for widget in (
            self.root_edit,
            self.btn_root,
            self.scope_combo,
            self.keep_strategy_combo,
            self.thread_count_combo,
            self.byte_verify_check,
        ):
            widget.setEnabled(not busy)

    def _on_row_check_changed(self):
        self._update_action_states()
        self._refresh_summary()

    def _reclaimable_sizes(self) -> tuple[int, int]:
        """返回所有 source rows 中待处理副本的总容量和勾选容量；不访问文件系统。"""
        if (
            not self._has_scan
            or self._current_result is None
            or self._scan_cancelled
            or self._scan_stale
        ):
            return 0, 0
        total_bytes = 0
        selected_bytes = 0
        for row in self.table_model.rows:
            if not row.is_checkable() or row.entry is None or row.keeper is None:
                continue
            size = max(0, int(row.entry.size))
            total_bytes += size
            if row.checked:
                selected_bytes += size
        return total_bytes, selected_bytes

    def _refresh_space_summary(self) -> None:
        total_bytes, selected_bytes = self._reclaimable_sizes()
        self.space_summary.setText(
            self.tr(
                "space_summary",
                total=_format_size(total_bytes),
                selected=_format_size(selected_bytes),
            )
        )
        self.space_summary.setToolTip(self.tr("space_summary_tooltip"))

    def _refresh_summary(self):
        # 在任何 summary 早返回前同步刷新；容量以完整源模型为准，不受分类隐藏影响。
        self._refresh_space_summary()
        if not self._has_scan:
            self.summary.setText(self.tr("summary_empty"))
            return
        if self._scan_stale:
            self.summary.setText(self.tr("summary_stale"))
            return
        total = len(self.table_model.rows)
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
        recyclable = sum(1 for row in self.table_model.rows if row.kind == KIND_DUPLICATE)
        text = self.tr("summary_ready", count=recyclable, total=total)
        if self._mismatch_count or self._issue_count:
            text = (
                f"{text}  "
                f"{self.tr('summary_detail', mismatch=self._mismatch_count, issue=self._issue_count)}"
            )
        self.summary.setText(text)

    # ------------------------------------------------------------------
    # 批量勾选（仅合法待回收行；保留/异常/碰撞/已处理/取消/失效行一律不变）
    # ------------------------------------------------------------------
    def _selectable_rows(self) -> list[DedupeRow]:
        """当前显示分类中可回收的行；隐藏分类的勾选状态保持不变。"""
        return [row for _index, row in self._visible_checkable_rows()]

    def _apply_checked(self, targets: list[DedupeRow], checked: bool) -> int:
        changed = 0
        for row in targets:
            if row.checked != checked:
                row.checked = checked
                changed += 1
        if changed:
            self._refresh_check_column()
            self._on_row_check_changed()
        return changed

    def select_all_checkable(self) -> int:
        """全选：只勾选当前可回收行（返回变更行数，便于测试/调试）。"""
        if self._is_busy() or self._scan_stale:
            return 0
        return self._apply_checked(self._selectable_rows(), True)

    def select_none_checkable(self) -> int:
        if self._is_busy():
            return 0
        return self._apply_checked(self._selectable_rows(), False)

    def invert_checkable(self) -> int:
        if self._is_busy() or self._scan_stale:
            return 0
        changed = 0
        for row in self._selectable_rows():
            row.checked = not row.checked
            changed += 1
        if changed:
            self._refresh_check_column()
            self._on_row_check_changed()
        return changed

    # ------------------------------------------------------------------
    # 扫描记录导出/导入（后台线程，坏记录不破坏当前显示）
    # ------------------------------------------------------------------
    def _runtime_row_states(self) -> dict[str, dict]:
        states: dict[str, dict] = {}
        for row in self.table_model.rows:
            path = row.primary_path()
            if path is None:
                continue
            try:
                key = os.path.normcase(os.path.abspath(os.fspath(path)))
            except Exception:
                key = os.fspath(path)
            states[key] = {"checked": bool(row.checked), "status": str(row.status)}
        return states

    def _apply_record_row_states(self, rows: list[DedupeRow], states: dict[str, dict]) -> None:
        if not states:
            return
        for row in rows:
            path = row.primary_path()
            if path is None:
                continue
            try:
                key = os.path.normcase(os.path.abspath(os.fspath(path)))
            except Exception:
                key = os.fspath(path)
            state = states.get(key)
            if not isinstance(state, dict):
                continue
            status = state.get("status")
            checked = state.get("checked")
            # 只恢复已知的行状态键（防止脏字符串污染展示）
            if isinstance(status, str) and status:
                base = status.split("|", 1)[0]
                if base in ROW_STATUS_BASES:
                    row.status = status
            if isinstance(checked, bool):
                # 导入历史不是复核结果：只有仍属合法待回收行、且记录未失效/未取消才允许勾选
                row.checked = bool(
                    checked
                    and row.is_checkable()
                    and not self._scan_stale
                    and not self._scan_cancelled
                )

    def _build_record(self) -> ScanRecord:
        """用扫描时的根/选项快照 + 完整 ScanResult 构记录。"""
        if self._current_result is None or self._scan_snapshot is None:
            raise ValueError("no_scan_result")
        snapshot = self._scan_snapshot
        return ScanRecord(
            mode=RECORD_MODE,
            root_a=Path(snapshot["root_a"]),
            root_b=None,
            scope=str(snapshot["scope"]),
            keep_strategy=str(snapshot["keep_strategy"]),
            result=self._current_result,
            row_states=self._runtime_row_states(),
            created_at=str(snapshot.get("created_at") or ""),
            stale=bool(self._scan_stale),
        )

    def _start_record_task(self, worker, action: str, on_finished) -> bool:
        if self._is_busy():
            self._notify(self.tr("cannot_start_title"), self.tr("blocked_busy"), is_error=True)
            return False
        self._record_action = action
        self._record_thread = QThread(self)
        self._record_worker = worker
        worker.moveToThread(self._record_thread)
        self._record_thread.started.connect(worker.run)
        worker.finished.connect(on_finished)
        worker.failed.connect(self._on_record_failed)
        worker.finished.connect(self._record_thread.quit)
        worker.failed.connect(self._record_thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        self._record_thread.finished.connect(self._record_thread.deleteLater)
        self._record_thread.finished.connect(self._record_thread_finished)
        self._set_status_text(
            "record_working",
            action=self.tr("record_action_save" if action == "save" else "record_action_load"),
        )
        self._update_action_states()
        self._record_thread.start()
        return True

    def export_scan_record(self) -> bool:
        """导出扫描记录到 JSON（用户选择路径，I/O 在后台线程）。"""
        if self._is_busy():
            self._notify(self.tr("cannot_start_title"), self.tr("blocked_busy"), is_error=True)
            return False
        if self._current_result is None or self._scan_snapshot is None:
            self._notify(self.tr("record_done_title"), self.tr("record_no_data"), is_error=True)
            return False
        try:
            record = self._build_record()
        except Exception as exc:
            self._notify(self.tr("record_done_title"),
                         self.tr("record_save_failed", error=str(exc))[:160], is_error=True)
            return False
        default_name = f"folder_dedupe_record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        default_dir = self._scan_snapshot.get("root_a") or str(Path.home())
        target, _filter = QFileDialog.getSaveFileName(
            self, self.tr("record_export_title"), str(Path(default_dir) / default_name),
            RECORD_FILTER,
        )
        if not target:
            return False
        return self._start_record_task(RecordSaveWorker(Path(target), record), "save",
                                       self._on_record_saved)

    def import_scan_record(self) -> bool:
        if self._is_busy():
            self._notify(self.tr("cannot_start_title"), self.tr("blocked_busy"), is_error=True)
            return False
        source, _filter = QFileDialog.getOpenFileName(
            self, self.tr("record_import_title"), str(Path.home()), RECORD_FILTER
        )
        if not source:
            return False
        return self._start_record_task(RecordLoadWorker(Path(source)), "load",
                                       self._on_record_loaded)

    def _on_record_saved(self, path_str: str):
        self._set_status_text("record_saved", path=path_str)
        self._notify(self.tr("record_done_title"), self.tr("record_saved", path=path_str))
        self._maybe_finish_close()

    def _on_record_failed(self, error: str):
        # 坏记录/写失败：完整解析失败前不碰现有显示
        if self._record_action == "save":
            self._set_status_text("record_save_failed", error=error)
            self._notify(self.tr("record_done_title"),
                         self.tr("record_save_failed", error=error)[:200], is_error=True)
        else:
            self._set_status_text("record_import_failed", error=error)
            self._notify(self.tr("record_done_title"),
                         self.tr("record_import_failed", error=error)[:200], is_error=True)
        self._maybe_finish_close()

    def _on_record_loaded(self, record: object):
        if not isinstance(record, ScanRecord):
            self._on_record_failed(f"{type(record).__name__}")
            return
        self._apply_imported_record(record)
        self._set_status_text("record_imported", path="")
        self._notify(
            self.tr("record_done_title"), self.tr("record_force_verify"),
            is_error=bool(record.stale) or bool(record.result.cancelled),
        )
        self._maybe_finish_close()

    def _apply_imported_record(self, record: ScanRecord):
        """把完整解析成功的记录替换到当前显示（在此之前不碰任何控件）。"""
        self._suspend_settings_save = True
        try:
            self.root_edit.setText(str(record.root_a))
            for index in range(self.scope_combo.count()):
                if self.scope_combo.itemData(index) == record.scope:
                    self.scope_combo.setCurrentIndex(index)
                    break
            self._set_keep_strategy(record.keep_strategy)
        finally:
            self._suspend_settings_save = False

        result = record.result
        self._current_result = result
        # 导入记录是不可信历史：取消/失效性质由记录本身带过来，回收仍然受 guard 限制
        self._scan_snapshot = {
            "root_a": str(record.root_a),
            "root_b": None,
            "scope": record.scope,
            "keep_strategy": record.keep_strategy,
            "created_at": record.created_at,
        }
        self._record_imported = True
        self._scan_cancelled = bool(result.cancelled)
        self._scan_stale = bool(record.stale)
        self._has_scan = True
        self._group_count = len(result.groups)
        self._mismatch_count = len(result.mismatches)
        self._issue_count = len(result.issues)
        self._recycled_count = 0
        self._skipped_count = 0
        self._failed_count = 0

        self.thumbnail_loader.clear()
        rows = self._build_rows(result)
        self._apply_record_row_states(rows, record.row_states or {})
        # 已处理行的计数也按恢复的状态算（否则汇总会把历史说成 0）
        self._recycled_count = sum(
            1 for row in rows if row.status.startswith("status_recycled")
        )
        self._skipped_count = sum(1 for row in rows if row.status.startswith("status_skipped"))
        self._failed_count = sum(1 for row in rows if row.status.startswith("status_failed"))
        self.table.setUpdatesEnabled(False)
        try:
            self.table_model.reset_rows(rows)
            self._rebuild_path_index()
        finally:
            self.table.setUpdatesEnabled(True)
        self._refresh_preview()
        self._refresh_summary()
        self._update_category_metadata(rows, result, choose_default=True)
        self.progress.setValue(0)
        if self._scan_cancelled:
            self._set_status_text("record_import_cancelled")
        elif self._scan_stale:
            self._set_status_text("record_import_stale")
        else:
            self._set_status_text(
                "scan_done",
                groups=self._group_count,
                count=sum(1 for row in rows if row.kind == KIND_DUPLICATE),
                total=len(rows),
            )
        self._update_action_states()

    def _record_thread_finished(self):
        self._record_worker = None
        self._record_thread = None
        self._record_action = ""
        self._update_action_states()
        self._maybe_finish_close()

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------
    def browse_root(self):
        if self._is_busy():
            self._notify(self.tr("cannot_start_title"), self.tr("blocked_busy"), is_error=True)
            return
        start_dir = self.root_edit.text().strip() or str(
            _get_windows_pictures_dir() or Path.home()
        )
        folder = QFileDialog.getExistingDirectory(self, self.tr("choose_dir"), start_dir)
        if not folder:
            return
        self.root_edit.setText(folder)
        self._save_settings()

    def start_scan(self):
        if self._is_busy():
            self._notify(self.tr("cannot_start_title"), self.tr("blocked_busy"), is_error=True)
            return
        root_text = self.root_edit.text().strip()
        if not root_text:
            self._notify(self.tr("invalid_root_title"), self.tr("invalid_root_missing"),
                         is_error=True)
            return
        root = Path(root_text)
        if not root.exists():
            self._notify(self.tr("invalid_root_title"), self.tr("invalid_root_missing"),
                         is_error=True)
            return
        if not root.is_dir():
            self._notify(self.tr("invalid_root_title"), self.tr("invalid_root_not_dir"),
                         is_error=True)
            return

        self._reset_results()
        self.is_scanning = True
        self._scan_cancelled = False
        self._scan_stale = False
        self._has_scan = False
        self._record_imported = False  # 新扫描成功后会清除导入标记
        # 扫描时的根/选项快照（绝对路径）：导出只用它，不读后来修改过的控件
        self._scan_snapshot = {
            "root_a": os.path.abspath(os.fspath(root)),
            "root_b": None,
            "scope": self._scope(),
            "keep_strategy": self._keep_strategy(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.progress.setValue(0)
        self._set_status_text("scanning")
        self._update_action_states()

        self._scan_thread = QThread(self)
        self._scan_worker = DedupeScanWorker(
            root, self._scope(), self._keep_strategy(), self._thread_count()
        )
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
        self._notify(self.tr("invalid_root_title"), self.tr("scan_failed", error=error),
                     is_error=True)
        self._set_status_text("scan_failed", error=error)
        self._update_action_states()
        self._maybe_finish_close()

    def _apply_scan_result(self, result: ScanResult):
        self.is_scanning = False
        self._has_scan = True
        # 新扫描会重置导入标记（记录已不再对应当前结果）
        self._record_imported = False
        self._current_result = result
        if self._scan_snapshot is None:
            self._scan_snapshot = {
                "root_a": os.path.abspath(self.root_edit.text().strip() or os.getcwd()),
                "root_b": None,
                "scope": self._scope(),
                "keep_strategy": self._keep_strategy(),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        self._scan_cancelled = bool(result.cancelled)
        self._scan_stale = False
        self._group_count = len(result.groups)
        self._mismatch_count = len(result.mismatches)
        self._issue_count = len(result.issues)
        self._recycled_count = 0
        self._skipped_count = 0
        self._failed_count = 0

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
        self._update_category_metadata(rows, result, choose_default=True)

        duplicate_count = sum(1 for row in rows if row.kind == KIND_DUPLICATE)
        if self._scan_cancelled:
            self.progress.setValue(0)
            self._set_status_text("scan_cancelled")
        else:
            self.progress.setValue(100)
            if duplicate_count:
                self._set_status_text(
                    "scan_done",
                    groups=self._group_count,
                    count=duplicate_count,
                    total=len(rows),
                )
            else:
                self._set_status_text("scan_none")
        self._update_action_states()
        self._maybe_finish_close()

    def _build_rows(self, result: ScanResult) -> list[DedupeRow]:
        rows: list[DedupeRow] = []
        for group_id, group in enumerate(result.groups, start=1):
            rows.append(
                DedupeRow(
                    kind=KIND_KEEPER,
                    group_id=group_id,
                    entry=group.keeper,
                    keeper=group.keeper,
                    sha256=group.sha256,
                    checked=False,
                    status="status_keep",
                )
            )
            for duplicate in group.duplicates:
                rows.append(
                    DedupeRow(
                        kind=KIND_DUPLICATE,
                        group_id=group_id,
                        entry=duplicate,
                        keeper=group.keeper,
                        sha256=group.sha256,
                        checked=True,
                        status="status_pending",
                    )
                )
        for mismatch in result.mismatches:
            rows.append(
                DedupeRow(
                    kind=KIND_MISMATCH,
                    group_id=0,
                    entry=mismatch.other,
                    keeper=mismatch.keeper,
                    sha256=mismatch.sha256,
                    checked=False,
                    status="status_mismatch",
                )
            )
        for issue in result.issues:
            rows.append(
                DedupeRow(
                    kind=KIND_ISSUE,
                    group_id=0,
                    issue_path=issue.path,
                    issue_stage=issue.stage,
                    checked=False,
                    status=f"status_issue|{issue.stage}|{issue.message}",
                )
            )
        return rows

    def _reset_results(self):
        self.thumbnail_loader.clear()
        self._path_cells.clear()
        self._row_categories = []
        self._group_categories.clear()
        self.active_category = "photo"
        self._has_scan = False
        self.table_model.reset_rows([])
        self._update_category_button_labels()
        self._apply_category_filter()
        self.preview_panel.clear()
        self._recycled_count = 0
        self._skipped_count = 0
        self._failed_count = 0
        self._mismatch_count = 0
        self._issue_count = 0
        self._group_count = 0
        self._has_scan = False
        self._scan_stale = False
        self._current_result = None
        self._scan_snapshot = None
        self._refresh_space_summary()
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
    # 回收
    # ------------------------------------------------------------------
    def start_recycling(self):
        if self._is_busy():
            self._notify(self.tr("cannot_start_title"), self.tr("blocked_busy"), is_error=True)
            return
        if self._scan_stale:
            self._notify(self.tr("cannot_start_title"), self.tr("cannot_start_stale"),
                         is_error=True)
            return
        if self._scan_cancelled:
            self._notify(self.tr("cannot_start_title"), self.tr("cannot_start_cancelled"),
                         is_error=True)
            return
        if not self._recyclable_rows():
            self._notify(self.tr("cannot_start_title"), self.tr("cannot_start_content"),
                         is_error=True)
            return

        items: list[tuple[int, FileEntry, FileEntry]] = []
        total_size = 0
        for row_index, row in enumerate(self.table_model.rows):
            if not row.checked or row.kind != KIND_DUPLICATE or row.status != "status_pending":
                continue
            if row.entry is None or row.keeper is None:
                continue
            items.append((row_index, row.entry, row.keeper))
            total_size += row.entry.size
        if not items:
            self._notify(self.tr("cannot_start_title"), self.tr("cannot_start_content"),
                         is_error=True)
            return

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
        # 导入记录是不可信历史：强制逐字节复核，不信任用户后来的勾选/设置
        byte_verify = True if self._record_imported else self.byte_verify_check.isChecked()
        self._recycle_worker = DedupeRecycleWorker(items, byte_verify)
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
        self.btn_pause.setText(
            self.tr("btn_resume") if self._recycle_paused else self.tr("btn_pause")
        )
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

    def _workers_running(self) -> bool:
        return bool(
            (self._scan_thread is not None and self._scan_thread.isRunning())
            or (self._recycle_thread is not None and self._recycle_thread.isRunning())
        )

    def _threads_pending(self) -> bool:
        """线程引用/回调还未清理：关闭必须等它们收尾（防止覆盖唯一引用）。"""
        return bool(
            self._workers_running()
            or self._scan_thread is not None
            or self._recycle_thread is not None
            or self._record_thread is not None
        )

    def _maybe_finish_close(self):
        if self._pending_close and not self._threads_pending():
            self._pending_close = False
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

    def closeEvent(self, event):
        # 有后台线程（含尚未清理完成的记录线程）时先请求停止并延后关闭，
        # 避免 QThread 在运行时被销毁，也避免窗口先消失、回调再落到已释放控件
        if self._threads_pending() or self._is_busy():
            self._pending_close = True
            self._shutdown_workers()
            event.ignore()
            return
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