"""媒体统计与目录说明编辑页（PyQt6 + Fluent，独立与内嵌两用）。

职责：
- 递归目录树展示每个目录的图片数、视频数、总项数（口径由 media_statistics_core 计算）。
- 选中目录后加载其直接包含的 readme.txt，在下方编辑后自动保存，缺失时按需创建
  （读写安全性由 media_readme_core 保证）。

关键约定（见任务 refinement.md / design.md）：
- 媒体扩展名唯一来源是 timestamp_fix_gui 的 IMAGE_SUFFIXES / VIDEO_SUFFIXES，
  本页导入后传给核心扫描器，不在此复制格式集。
- 扫描与说明读写全部在后台 QThread 中执行；本页只在主线程操作控件。
- 扫描结果先入队，再由 10 ms 定时器每轮最多处理 UI_ROW_DRAIN_COUNT 行，
  避免大量行同步插入导致界面冻结。
- 说明读写只有一个活跃 worker，快速切换时只保留最新待读请求，
  用单调递增的 request_id 丢弃过期结果，防止串读串写。
- 编辑停止 800 ms 或焦点离开时自动保存；离开目录前先写完最新草稿。
- 仅保存失败显示重试/放弃/取消，关闭失败后继续编辑会撤销关闭意图。
- request_close(on_ready) -> bool 是唯一的关闭协调入口：
  返回 True 表示现在可以安全退出；否则在清理完成后调用 on_ready，
  且绝不阻塞主线程等待后台线程。
"""

from __future__ import annotations

import json
import os
import sys
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from qframelesswindow import FramelessMainWindow, StandardTitleBar

from PyQt6.QtCore import QEvent, QModelIndex, QObject, QSize, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QFontMetrics, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from elevation_hint import attach_elevation_hint
from media_readme_core import (
    MAX_README_BYTES,
    STATUS_CONFLICT,
    STATUS_ERROR,
    STATUS_MISSING,
    STATUS_READY,
    STATUS_SAVED,
    STATUS_TOO_LARGE,
    ReadmeDocument,
    load_readme,
    save_readme,
)
from media_statistics_core import FolderSnapshot, ScanOutcome, scan_folders
# 媒体格式集唯一来源：不在本页复制常量
from timestamp_fix_gui import IMAGE_SUFFIXES, VIDEO_SUFFIXES


try:
    from qfluentwidgets import (
        BodyLabel,
        CardWidget,
        ComboBox,
        FluentIcon,
        IndeterminateProgressBar,
        InfoBar,
        InfoBarPosition,
        LineEdit,
        PlainTextEdit,
        PrimaryPushButton,
        PushButton,
        SubtitleLabel,
        TreeView,
        setTheme,
        setThemeColor,
        Theme,
    )
except ImportError as _exc:  # pragma: no cover - 环境缺失时明确报错
    raise ImportError(
        "qfluentwidgets is not installed. 请安装 PyQt6-Fluent-Widgets 后再运行媒体统计页。"
    ) from _exc


APP_NAME = "MediaStatisticsGUI"
SUPPORTED_LANGUAGES = ("zh", "en")
DEFAULT_LANGUAGE = "zh"
#: 与其它页一致的批量刷新上限（每轮 drain 最多处理的行数）
UI_ROW_DRAIN_COUNT = 120
#: 树列定义：文件夹 / 图片 / 视频 / 总项数
TREE_COLUMNS = 4


TRANSLATIONS = {
    "zh": {
        "app_title": "媒体统计",
        "header_title": "媒体统计",
        "header_subtitle": "统计文件夹内图片、视频数量",
        "language": "界面语言",
        "root_dir": "根目录",
        "root_placeholder": "选择、粘贴或拖入相册根目录",
        "choose_root": "选择根目录",
        "tree_title": "目录统计",
        "drop_hint": "拖入文件夹即可统计该目录",
        "table_folder": "文件夹",
        "table_image": "图片",
        "table_video": "视频",
        "table_total": "总项数",
        "expand_all": "展开全部",
        "collapse_all": "折叠全部",
        "rescan": "重新扫描",
        "stop_scan": "停止扫描",
        "summary": "根目录合计 {total} 项（图片 {image}，视频 {video}）",
        "summary_none": "尚未选择根目录",
        "readme_title": "目录说明 readme.txt",
        "readme_path_none": "未选择目录",
        "status_waiting_root": "等待选择根目录",
        "status_scanning": "正在扫描目录…",
        "status_scan_done": "扫描完成：共 {folders} 个目录，{total} 项媒体",
        "status_scan_partial": "扫描不完整：共 {folders} 个目录，{total} 项媒体（{errors} 个目录无法访问或扫描被中止）",
        "status_scan_stopped": "扫描已停止，结果不完整（已发现 {folders} 个目录）",
        "status_stopping": "正在停止扫描…",
        "status_invalid_root": "根目录不存在或不可访问",
        "status_readme_too_large": "说明文件超过 {size} MiB 上限，无法编辑",
        "status_readme_error": "读取说明失败：{error}",
        "status_readme_conflict_plain": "保存已中止，未覆盖磁盘内容：{error}",
        "status_readme_save_failed": "保存失败：{error}",
        "status_scan_busy": "扫描进行中，请先停止或等待完成",
        "draft_prompt": "自动保存失败，请处理当前修改后再{action}。",
        "draft_save_prompt": "自动保存失败，修改仍保留在编辑框中。",
        "draft_save": "重试",
        "draft_discard": "放弃修改",
        "draft_cancel": "取消",
        "action_switch_folder": "切换目录",
        "action_set_root": "更换根目录",
        "action_scan": "重新扫描",
        "action_close": "关闭窗口",
        "notice_invalid_root": "目录不可用",
        "notice_readme_failed": "说明读写失败",
        "notice_stopped": "已请求停止扫描",
        "incomplete_mark": "不完整",
        "incomplete_tip": "该目录包含无法访问的子目录，计数可能不完整",
    },
    "en": {
        "app_title": "Media Statistics",
        "header_title": "Media Statistics",
        "header_subtitle": "Count images and videos in folders",
        "language": "Language",
        "root_dir": "Root folder",
        "root_placeholder": "Choose, paste or drop an album root folder",
        "choose_root": "Choose folder",
        "tree_title": "Folder statistics",
        "drop_hint": "Drop a folder here to count it",
        "table_folder": "Folder",
        "table_image": "Images",
        "table_video": "Videos",
        "table_total": "Total",
        "expand_all": "Expand all",
        "collapse_all": "Collapse all",
        "rescan": "Rescan",
        "stop_scan": "Stop scan",
        "summary": "Root total {total} items (images {image}, videos {video})",
        "summary_none": "No root folder selected",
        "readme_title": "Folder readme.txt",
        "readme_path_none": "No folder selected",
        "status_waiting_root": "Waiting for a root folder",
        "status_scanning": "Scanning folders…",
        "status_scan_done": "Scan finished: {folders} folders, {total} media items",
        "status_scan_partial": "Incomplete scan: {folders} folders, {total} media items ({errors} folders unreadable or scan aborted)",
        "status_scan_stopped": "Scan stopped, results are incomplete ({folders} folders found)",
        "status_stopping": "Stopping scan…",
        "status_invalid_root": "Root folder is missing or inaccessible",
        "status_readme_too_large": "readme.txt exceeds the {size} MiB limit and cannot be edited",
        "status_readme_error": "Failed to load readme.txt: {error}",
        "status_readme_conflict_plain": "Save aborted; disk content was not overwritten: {error}",
        "status_readme_save_failed": "Save failed: {error}",
        "status_scan_busy": "A scan is running; stop it or wait for it to finish",
        "draft_prompt": "Autosave failed. Resolve the draft before {action}.",
        "draft_save_prompt": "Autosave failed. Your changes remain in the editor.",
        "draft_save": "Retry",
        "draft_discard": "Discard",
        "draft_cancel": "Cancel",
        "action_switch_folder": "switching folder",
        "action_set_root": "changing root folder",
        "action_scan": "rescanning",
        "action_close": "closing the window",
        "notice_invalid_root": "Folder unavailable",
        "notice_readme_failed": "Readme operation failed",
        "notice_stopped": "Stop requested",
        "incomplete_mark": "Incomplete",
        "incomplete_tip": "This folder contains unavailable subfolders; counts may be incomplete",
    },
}


def _pick_icon(*names: str):
    """按顺序取第一个可用的 Fluent 图标（不硬编码图标路径）。"""
    for name in names:
        icon = getattr(FluentIcon, name, None)
        if icon is not None:
            return icon
    return FluentIcon.APPLICATION


def _get_settings_path() -> Path:
    """独立页的设置路径（与统一 GUI 分离，测试时隔离 APPDATA）。"""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME / "settings.json"
    return Path.home() / ".config" / APP_NAME / "settings.json"


def _thread_is_running(thread: QThread | None) -> bool:
    try:
        return thread is not None and thread.isRunning()
    except RuntimeError:
        return False


class _ElidedLabel(BodyLabel):
    """单行省略标签：不因长文本撐宽页面，完整内容放 tooltip。

    BodyLabel 默认根据文本宽度给出 sizeHint/minimumSizeHint，长路径会把整个窗口撐大；
    这里把水平尺寸策略设为 Ignored，并在绘制时做省略号处理。
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        text: str = "",
        mode: Qt.TextElideMode = Qt.TextElideMode.ElideMiddle,
    ):
        super().__init__(parent)
        self._full_text = text or ""
        self._elide_mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setWordWrap(False)
        BodyLabel.setText(self, self._full_text)
        self.setToolTip(self._full_text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt 命名
        """保存完整文本用于省略绘制与 tooltip；控件文本仍为完整值（便于测试断言）。"""
        self._full_text = text or ""
        super().setText(self._full_text)
        self.setToolTip(self._full_text)
        self.updateGeometry()

    def full_text(self) -> str:
        return self._full_text

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt 命名
        hint = super().minimumSizeHint()
        return QSize(0, hint.height())

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt 命名
        # 宽度不参与布局计算；高度沿用字体度量
        return QSize(0, super().sizeHint().height())

    def paintEvent(self, event):  # noqa: N802 - Qt 命名
        # 不在此处修改控件状态（会触发重布局/重绘递归），只负责绘制省略后的文本
        from PyQt6.QtGui import QPainter

        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        rect = self.contentsRect()
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(self._full_text, self._elide_mode, max(0, rect.width() - 4))
        painter.drawText(rect, int(self.alignment()), elided)
        painter.end()


# ---------------------------------------------------------------------------
# 后台 worker
# ---------------------------------------------------------------------------


class ScanWorker(QObject):
    """目录统计 worker：分批发快照，最后发一次完成结果。"""

    batch_ready = pyqtSignal(int, object)
    finished = pyqtSignal(int, object)
    #: 兜底信号：即使扫描内部出现未预期异常，也必须发出完成信号以释放线程
    failed = pyqtSignal(int, str)

    def __init__(self, scan_id: int, root: Path, stop_event: threading.Event | None = None):
        super().__init__()
        self.scan_id = scan_id
        self.root = root
        self.stop_event = stop_event or threading.Event()

    def run(self):
        try:
            outcome = scan_folders(
                self.root,
                IMAGE_SUFFIXES,
                VIDEO_SUFFIXES,
                stop_event=self.stop_event,
                on_batch=lambda batch: self.batch_ready.emit(self.scan_id, batch),
            )
        except Exception as exc:  # 不让异常穿透 Qt 事件循环
            self.failed.emit(self.scan_id, str(exc))
            return
        self.finished.emit(self.scan_id, outcome)


class ReadmeLoadWorker(QObject):
    """说明文件读取 worker：每次只读一个目录，结果带回 request_id。"""

    finished = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, request_id: int, directory: Path):
        super().__init__()
        self.request_id = request_id
        self.directory = directory

    def run(self):
        try:
            result = load_readme(self.directory)
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))
            return
        self.finished.emit(self.request_id, result)


class ReadmeSaveWorker(QObject):
    """说明文件保存 worker：冻结 document + 文本，避免写错目录。"""

    finished = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, request_id: int, document: ReadmeDocument, text: str):
        super().__init__()
        self.request_id = request_id
        self.document = document
        self.text = text

    def run(self):
        try:
            result = save_readme(self.document, self.text)
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))
            return
        self.finished.emit(self.request_id, result)


# ---------------------------------------------------------------------------
# 树节点数据
# ---------------------------------------------------------------------------


@dataclass
class _FolderNode:
    """树中一个目录行的对应数据（行 ↔ 数据严格一一对应）。"""

    path: Path
    item: QStandardItem | None
    snapshot: FolderSnapshot | None


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------


class MainWindow(FramelessMainWindow):
    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("Media Statistics")
        self._title_bar_height = 36
        if not self._embedded:
            self.resize(1280, 860)
            self._set_blue_title_bar()

        self.lang = DEFAULT_LANGUAGE
        self._last_status_key = "status_waiting_root"
        self._last_status_kwargs: dict = {}

        # ---- 扫描状态 ----
        self.root_dir: Path | None = None
        self._scan_id = 0
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        #: 已请求停止但尚未 finished 的旧扫描线程（保留引用 + 标识，避免被新扫描覆盖）
        self._retired_scan_jobs: list[tuple[QThread, ScanWorker]] = []
        self._scan_stop_event: threading.Event | None = None
        self._scan_stop_requested = False
        self._last_outcome: ScanOutcome | None = None
        #: 替换根目录/重扫的待办动作：等旧扫描线程退出后再启动
        self._pending_scan_restart = False
        # 队列：批次快照 + 一次待应用的完成结果（等队列清空后再应用）
        self._scan_batch_queue: deque[list[FolderSnapshot]] = deque()
        self._pending_final_snapshots: deque[FolderSnapshot] = deque()
        self._pending_scan_result: ScanOutcome | None = None
        self._pending_scan_error: str | None = None
        #: 最终快照仍在排队时，收尾动作（展开根/选根）要等队列清空
        self._scan_final_outcome_pending = False
        self._folders: dict[Path, _FolderNode] = {}
        self._ui_drain_timer = QTimer(self)
        self._ui_drain_timer.setInterval(10)
        self._ui_drain_timer.timeout.connect(self._drain_ui_queues)

        # ---- 说明文件状态 ----
        self.readme_document: ReadmeDocument | None = None
        self._readme_directory: Path | None = None
        self._readme_dirty = False
        self._readme_busy = False  # 读或写正在进行
        self._readme_request_id = 0  # 单调递增，丢弃过期结果
        self._readme_pending_load: tuple[int, Path] | None = None
        self._readme_thread: QThread | None = None
        self._readme_worker: QObject | None = None
        #: 已发起但尚未 finished 的说明 IO 线程（保留引用，避免被新线程覆盖）
        self._retired_readme_jobs: list[tuple[QThread, QObject]] = []
        self._suspend_editor_signal = False
        self._readme_status_key = ""
        self._readme_status_kwargs: dict = {}
        self._autosave_failed = False
        self._autosave_requested = False
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(800)
        self._autosave_timer.timeout.connect(self._flush_readme)

        # ---- 草稿守卫生成/关闭状态 ----
        self._pending_action: tuple[str, object, str] | None = None
        #: 关闭意图：需要草稿解决且后台清理完成后才能回调关闭
        self._close_intent = False
        self._close_callbacks: list = []
        self._closing = False

        self._settings_path = _get_settings_path()
        self._suspend_settings_save = False

        self._build_ui()
        self._load_settings()
        self._apply_language()
        self._connect_settings_signals()

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QWidget(self)
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, (0 if self._embedded else self._title_bar_height) + 8, 20, 12)
        outer.setSpacing(8)

        # ---- 标题区 ----
        header_card = QWidget(self)
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(4, 0, 4, 2)
        header_layout.setSpacing(4)

        self.title_label = SubtitleLabel(self.tr("header_title"), self)
        title_font = QFont("Microsoft YaHei", 15)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.subtitle_label = BodyLabel(self.tr("header_subtitle"), self)
        self.subtitle_label.setStyleSheet("color: #667085;")
        self.subtitle_label.setWordWrap(True)

        self.language_label = BodyLabel(self.tr("language"), self)
        self.language_combo = ComboBox(self)
        self.language_combo.addItem("中文", userData="zh")
        self.language_combo.addItem("English", userData="en")
        self.language_combo.setFixedWidth(128)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        title_row = QHBoxLayout()
        title_row.addWidget(self.title_label)
        title_row.addStretch(1)
        if not self._embedded:
            title_row.addWidget(self.language_label)
            title_row.addWidget(self.language_combo)
        else:
            self.language_label.hide()
            self.language_combo.hide()
        header_layout.addLayout(title_row)
        header_layout.addWidget(self.subtitle_label)
        # 管理员权限拖拽提示：内嵌在标题下方，非 elevated 时零占位
        self.elevation_hint = attach_elevation_hint(header_layout, self, lang=self.lang)

        # ---- 根目录选择 ----
        path_card = CardWidget(self)
        path_layout = QHBoxLayout(path_card)
        path_layout.setContentsMargins(14, 8, 14, 8)
        path_layout.setSpacing(10)
        self.root_label = BodyLabel(self.tr("root_dir"), self)
        self.root_edit = LineEdit(self)
        self.root_edit.setPlaceholderText(self.tr("root_placeholder"))
        self.root_edit.returnPressed.connect(self._on_root_edit_committed)
        self.btn_root = PushButton(self.tr("choose_root"), self)
        self.btn_root.setIcon(_pick_icon("FOLDER", "FOLDER_ADD"))
        self.btn_root.clicked.connect(self.browse_root)
        path_layout.addWidget(self.root_label)
        path_layout.addWidget(self.root_edit, 1)
        path_layout.addWidget(self.btn_root)

        # ---- 内容区：上下可拖动分割 ----
        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(8)

        tree_card = CardWidget(self)
        tree_layout = QVBoxLayout(tree_card)
        tree_layout.setContentsMargins(10, 10, 10, 10)
        tree_layout.setSpacing(6)

        tree_header_row = QHBoxLayout()
        tree_header_row.setSpacing(8)
        self.tree_title_label = BodyLabel(self.tr("tree_title"), tree_card)
        self.tree_title_label.setStyleSheet("font-weight: 600;")
        self.drop_hint = BodyLabel(self.tr("drop_hint"), tree_card)
        self.drop_hint.setStyleSheet("color: #6b7280; padding: 4px 6px;")
        self.summary_label = _ElidedLabel(tree_card, text=self.tr("summary_none"))
        self.summary_label.setStyleSheet("color: #667085;")
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tree_header_row.addWidget(self.tree_title_label)
        tree_header_row.addWidget(self.drop_hint)
        tree_header_row.addWidget(self.summary_label, 1)

        tree_button_row = QHBoxLayout()
        tree_button_row.setSpacing(8)
        self.btn_expand = PushButton(self.tr("expand_all"), tree_card)
        self.btn_expand.setIcon(_pick_icon("CHEVRON_DOWN", "DOWNLOAD"))
        self.btn_expand.clicked.connect(self.expand_all)
        self.btn_collapse = PushButton(self.tr("collapse_all"), tree_card)
        self.btn_collapse.setIcon(_pick_icon("CHEVRON_UP", "UP"))
        self.btn_collapse.clicked.connect(self.collapse_all)
        self.btn_scan = PushButton(self.tr("rescan"), tree_card)
        self.btn_scan.setIcon(_pick_icon("SYNC", "UPDATE"))
        self.btn_scan.clicked.connect(self.scan_files)
        self.btn_stop = PushButton(self.tr("stop_scan"), tree_card)
        self.btn_stop.setIcon(_pick_icon("CANCEL", "CLOSE"))
        self.btn_stop.clicked.connect(self.stop_scan)
        self.btn_stop.setEnabled(False)
        self.scan_progress = IndeterminateProgressBar(tree_card)
        self.scan_progress.setVisible(False)
        self.scan_progress.setFixedWidth(120)
        tree_button_row.addWidget(self.btn_expand)
        tree_button_row.addWidget(self.btn_collapse)
        tree_button_row.addWidget(self.scan_progress)
        tree_button_row.addStretch(1)
        tree_button_row.addWidget(self.btn_scan)
        tree_button_row.addWidget(self.btn_stop)

        self.tree = TreeView(self)
        self.tree.setObjectName("mediaStatisticsTree")
        self.tree_model = QStandardItemModel(0, TREE_COLUMNS, self)
        self.tree_model.setHorizontalHeaderLabels(self._tree_headers())
        self.tree.setModel(self.tree_model)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setFrameShape(QFrame.Shape.NoFrame)
        self.tree.setAcceptDrops(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.tree.viewport().setAcceptDrops(True)
        self.tree.viewport().installEventFilter(self)
        tree_header = self.tree.header()
        # stretchLastSection 默认开启会把「总项数」拉得极大而计数列被压成极窄，这里关闭
        tree_header.setStretchLastSection(False)
        tree_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            tree_header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        # 数值列给一个下限，避免「图片/视频/总项数」被挤成只显示省略号
        tree_header.setMinimumSectionSize(72)
        self.tree.selectionModel().currentChanged.connect(self._on_tree_current_changed)

        tree_layout.addLayout(tree_header_row)
        tree_layout.addLayout(tree_button_row)
        tree_layout.addWidget(self.tree, 1)

        # ---- 说明编辑区 ----
        readme_card = CardWidget(self)
        readme_layout = QVBoxLayout(readme_card)
        readme_layout.setContentsMargins(14, 8, 14, 8)
        readme_layout.setSpacing(6)

        readme_header_row = QHBoxLayout()
        readme_header_row.setSpacing(8)
        self.readme_title_label = BodyLabel(self.tr("readme_title"), readme_card)
        self.readme_title_label.setStyleSheet("font-weight: 600;")
        self.readme_path_label = _ElidedLabel(readme_card, text=self.tr("readme_path_none"))
        self.readme_path_label.setStyleSheet("color: #667085;")
        self.readme_path_label.setToolTip(self.tr("readme_path_none"))
        readme_header_row.addWidget(self.readme_title_label)
        readme_header_row.addWidget(self.readme_path_label, 1)

        self.readme_status_label = BodyLabel("", readme_card)
        self.readme_status_label.setStyleSheet("color: #475467;")
        self.readme_status_label.setWordWrap(True)
        self.readme_status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.readme_status_label.setMinimumWidth(0)
        self.readme_status_label.hide()

        # 仅保存失败时显示重试 / 放弃 / 取消，不占正常编辑高度
        self.draft_bar = CardWidget(readme_card)
        draft_layout = QHBoxLayout(self.draft_bar)
        draft_layout.setContentsMargins(12, 8, 12, 8)
        draft_layout.setSpacing(8)
        self.draft_label = BodyLabel("", self.draft_bar)
        self.draft_label.setStyleSheet("color: #B54708;")
        self.draft_label.setWordWrap(True)
        self.draft_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.draft_label.setMinimumWidth(0)
        self.btn_draft_save = PrimaryPushButton(self.tr("draft_save"), self.draft_bar)
        self.btn_draft_save.clicked.connect(lambda: self._resolve_draft("save"))
        self.btn_draft_discard = PushButton(self.tr("draft_discard"), self.draft_bar)
        self.btn_draft_discard.clicked.connect(lambda: self._resolve_draft("discard"))
        self.btn_draft_cancel = PushButton(self.tr("draft_cancel"), self.draft_bar)
        self.btn_draft_cancel.clicked.connect(lambda: self._resolve_draft("cancel"))
        draft_layout.addWidget(self.draft_label, 1)
        draft_layout.addWidget(self.btn_draft_save)
        draft_layout.addWidget(self.btn_draft_discard)
        draft_layout.addWidget(self.btn_draft_cancel)
        self.draft_bar.setVisible(False)

        self.readme_edit = PlainTextEdit(readme_card)
        self.readme_edit.setReadOnly(True)
        self.readme_edit.setMinimumHeight(72)
        self.readme_edit.installEventFilter(self)
        self.readme_edit.textChanged.connect(self._on_editor_text_changed)

        readme_layout.addLayout(readme_header_row)
        readme_layout.addWidget(self.readme_edit, 1)
        readme_layout.addWidget(self.readme_status_label)
        readme_layout.addWidget(self.draft_bar)

        self.splitter.addWidget(tree_card)
        self.splitter.addWidget(readme_card)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([600, 124])

        outer.addWidget(header_card)
        outer.addWidget(path_card)
        outer.addWidget(self.splitter, 1)

        # 最小尺寸按实际内容估算（避免固定像素导致 680 高被抬到 715 而溢出屏）
        self.setMinimumHeight(560)
        self.setMinimumWidth(720)

    def _set_blue_title_bar(self):
        """独立运行时使用与其它页一致的自绘标题栏。"""
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
    # 文案与语言
    # ------------------------------------------------------------------

    def tr(self, key: str, **kwargs) -> str:
        text = TRANSLATIONS.get(self.lang, TRANSLATIONS["zh"]).get(key, key)
        return text.format(**kwargs) if kwargs else text

    def _tree_headers(self) -> list[str]:
        return [
            self.tr("table_folder"),
            self.tr("table_image"),
            self.tr("table_video"),
            self.tr("table_total"),
        ]

    def _set_status_text(self, key: str, **kwargs):
        self._last_status_key = key
        self._last_status_kwargs = kwargs
        self._refresh_summary()

    def _set_readme_status(self, key: str, **kwargs):
        self._readme_status_key = key
        self._readme_status_kwargs = kwargs
        self.readme_status_label.setText(self.tr(key, **kwargs) if key else "")
        self.readme_status_label.setVisible(bool(key))

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
        self.elevation_hint.set_language(self.lang)
        self.language_label.setText(self.tr("language"))
        self.root_label.setText(self.tr("root_dir"))
        self.root_edit.setPlaceholderText(self.tr("root_placeholder"))
        self.btn_root.setText(self.tr("choose_root"))
        self.tree_title_label.setText(self.tr("tree_title"))
        self.drop_hint.setText(self.tr("drop_hint"))
        self.tree_model.setHorizontalHeaderLabels(self._tree_headers())
        self.btn_expand.setText(self.tr("expand_all"))
        self.btn_collapse.setText(self.tr("collapse_all"))
        self.btn_scan.setText(self.tr("rescan"))
        self.btn_stop.setText(self.tr("stop_scan"))
        self.readme_title_label.setText(self.tr("readme_title"))
        self.btn_draft_save.setText(self.tr("draft_save"))
        self.btn_draft_discard.setText(self.tr("draft_discard"))
        self.btn_draft_cancel.setText(self.tr("draft_cancel"))

        # 动态状态与数值刷新
        self._set_status_text(self._last_status_key, **self._last_status_kwargs)
        readme_key = getattr(self, "_readme_status_key", "")
        if readme_key:
            self.readme_status_label.setText(
                self.tr(readme_key, **getattr(self, "_readme_status_kwargs", {}))
            )
        if self._readme_directory is None:
            self.readme_path_label.setText(self.tr("readme_path_none"))
        elif self.readme_document is not None:
            self.readme_path_label.setText(str(self.readme_document.path))
        self._refresh_summary()
        self._refresh_node_labels()
        self._refresh_draft_bar()

    def _refresh_node_labels(self):
        """语言切换后刷新“不完整”标记与提示。"""
        for node in self._folders.values():
            if node.item is None:
                continue
            self._update_node_item(node)

    def _refresh_summary(self):
        outcome = self._last_outcome
        summary = self.tr("summary_none")
        if outcome is not None and outcome.folders:
            root_snapshot = outcome.folders[0]
            summary = self.tr(
                "summary",
                total=root_snapshot.total,
                image=root_snapshot.image_count,
                video=root_snapshot.video_count,
            )
        key = self._last_status_key
        status = self.tr(key, **self._last_status_kwargs)
        if key in ("status_scan_partial", "status_scan_stopped"):
            summary = f"{summary} · {self.tr('incomplete_mark')}" if outcome else status
        elif key not in ("status_waiting_root", "status_scan_done"):
            summary = status
        self.summary_label.setText(summary)
        self.summary_label.setToolTip(f"{summary}\n{status}" if summary != status else summary)

    def _refresh_draft_bar(self):
        if (
            self._pending_action is None
            or self._pending_action[2] != "draft"
            or self._is_io_busy()
        ):
            self.draft_bar.setVisible(False)
            return
        action_key, _action, _kind = self._pending_action
        text = self.tr("draft_save_prompt") if action_key == "action_save" else self.tr(
            "draft_prompt", action=self.tr(action_key)
        )
        self.draft_label.setText(text)
        self.draft_bar.setVisible(True)

    # ------------------------------------------------------------------
    # 设置持久化
    # ------------------------------------------------------------------

    def _settings_payload(self) -> dict:
        return {
            "language": self.lang,
            "root_dir": self.root_edit.text().strip(),
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
        self.root_edit.editingFinished.connect(self._save_settings)

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
            root_dir = str(data.get("root_dir", "")).strip()
            if root_dir:
                # 只恢复输入框内容，不自动扫描（避免启动即触发后台 IO）
                self.root_edit.setText(root_dir)
        finally:
            self._suspend_settings_save = False

    # ------------------------------------------------------------------
    # 提示
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # 拖拽：只接受一个文件夹
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj is getattr(self, "readme_edit", None) and event.type() == QEvent.Type.FocusOut:
            self._flush_readme()
        if obj is self.tree.viewport():
            if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                    return True
            if event.type() == QEvent.Type.Drop:
                paths = [
                    Path(url.toLocalFile())
                    for url in event.mimeData().urls()
                    if url.isLocalFile()
                ]
                if not paths:
                    return False
                # 拖入文件夹则用该目录，拖入文件则用其父目录；真实类型由扫描 worker 校验
                first = paths[0]
                folder = first if first.suffix == "" else first.parent
                if folder is not None:
                    self.set_root_folder(folder)
                    event.acceptProposedAction()
                    return True
                return False
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # 根目录
    # ------------------------------------------------------------------

    def browse_root(self):
        start_dir = str(self.root_dir) if self.root_dir is not None else ""
        folder = QFileDialog.getExistingDirectory(self, self.tr("choose_root"), start_dir)
        if not folder:
            return
        self.set_root_folder(folder)

    def _on_root_edit_committed(self):
        text = self.root_edit.text().strip()
        if not text:
            return
        self.set_root_folder(text)

    def set_root_folder(self, path: str | Path):
        """设置根目录并开始扫描（先经过草稿守卫）。

        不在主线程做 is_dir 校验（云占位/网络路径可能阻塞界面），
        目录是否存在由后台扫描 worker 枚举时判定，失败会显示为不完整结果。
        """
        text = str(path).strip().strip('"')
        if not text:
            self._set_status_text("status_invalid_root")
            return
        target = Path(text)

        def apply():
            self._apply_root_folder(target)

        self._run_with_draft_guard("action_set_root", apply)

    def _apply_root_folder(self, target: Path):
        """真正替换根目录：停止旧扫描、使旧请求失效、清空树并开始新扫描。"""
        self.root_dir = target
        self.root_edit.setText(str(target))
        self._save_settings()
        self._reset_readme_state()
        self._start_scan()

    def _reset_readme_state(self):
        """根目录变化时清空说明区（旧文档与草稿由守护流程处理）。"""
        self._readme_request_id += 1
        self._readme_pending_load = None
        self._readme_directory = None
        self.readme_document = None
        self._readme_dirty = False
        self._readme_busy = False
        self._autosave_timer.stop()
        self._autosave_requested = False
        self._autosave_failed = False
        self._set_editor_text("")
        self.readme_edit.setReadOnly(True)
        self.readme_path_label.setText(self.tr("readme_path_none"))
        self._set_readme_status("")

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------

    def scan_files(self):
        """重新扫描当前根目录（经草稿守卫）。"""
        if _thread_is_running(self._scan_thread):
            self._notify(self.tr("notice_stopped"), self.tr("status_scan_busy"), is_error=True)
            return
        if self.root_dir is None:
            text = self.root_edit.text().strip()
            if not text:
                self._set_status_text("status_waiting_root")
                return
            self.set_root_folder(text)
            return
        self._run_with_draft_guard("action_scan", self._start_scan)

    def _start_scan(self):
        if self.root_dir is None:
            return
        # 旧扫描仍在退出中：只记下重启请求，等 finished 后再启动（不覆盖线程引用）
        if self._scan_thread is not None:
            self._pending_scan_restart = True
            self._stop_scan_thread()
            self._set_status_text("status_stopping")
            return
        self._pending_scan_restart = False
        self._scan_id += 1
        scan_id = self._scan_id
        self._scan_stop_event = threading.Event()
        self._scan_stop_requested = False
        self._scan_batch_queue.clear()
        self._pending_final_snapshots.clear()
        self._pending_scan_result = None
        self._pending_scan_error = None
        self._scan_final_outcome_pending = False
        self._last_outcome = None
        self._ui_drain_timer.stop()
        self._clear_tree()
        self.summary_label.setText(self.tr("summary_none"))
        self._set_status_text("status_scanning")
        self.scan_progress.setVisible(True)
        self.btn_stop.setEnabled(True)
        self.btn_scan.setEnabled(False)

        thread = QThread(self)
        worker = ScanWorker(scan_id, self.root_dir, self._scan_stop_event)
        self._scan_thread = thread
        self._scan_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.batch_ready.connect(self._queue_scan_batch)
        worker.finished.connect(self._scan_finished)
        worker.failed.connect(self._scan_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        # 以 lambda 绑定具体线程身份，防止旧线程的 finished 清除新引用
        thread.finished.connect(lambda t=thread, w=worker: self._on_scan_thread_finished(t, w))
        thread.start()

    def _on_scan_thread_finished(self, thread: QThread | None = None, worker: ScanWorker | None = None):
        """某个扫描线程退出：只清理它自己的引用，不影响当前活跃的新扫描。"""
        del worker
        if thread is not None and thread is not self._scan_thread:
            # 已退役的旧线程（极端情况）：仅移除残留引用
            self._retired_scan_jobs = [(t, w) for (t, w) in self._retired_scan_jobs if t is not thread]
            self._maybe_finish_close()
            return

        self._scan_thread = None
        self._scan_worker = None
        self._retired_scan_jobs = [
            (t, w) for (t, w) in self._retired_scan_jobs if _thread_is_running(t)
        ]
        if not self._maybe_start_pending_scan_restart():
            self._maybe_finish_close()

    def _maybe_start_pending_scan_restart(self) -> bool:
        """旧扫描全部退出后，启动被暂缓的重扫/换根。"""
        if not self._pending_scan_restart:
            return False
        if self._scan_thread is not None:
            return False
        if any(_thread_is_running(t) for (t, _w) in self._retired_scan_jobs):
            return False
        self._pending_scan_restart = False
        self._start_scan()
        return True

    def stop_scan(self):
        """请求停止扫描（协作式；不阻塞主线程等待）。"""
        if not _thread_is_running(self._scan_thread):
            self.btn_stop.setEnabled(False)
            return
        if self._scan_stop_event is not None:
            self._scan_stop_event.set()
        self._scan_stop_requested = True
        self._set_status_text("status_stopping")
        self.btn_stop.setEnabled(False)
        self._notify(self.tr("notice_stopped"), self.tr("status_stopping"))

    def _stop_scan_thread(self):
        """使旧扫描失效并请求停止；不等待线程（线程自行退出）。"""
        if self._scan_stop_event is not None:
            self._scan_stop_event.set()
        self._scan_stop_requested = False
        # 旧 worker 的完成结果按 scan_id 丢弃；线程强引用保留到 finished 再释放

    def _clear_tree(self):
        self.tree_model.removeRows(0, self.tree_model.rowCount())
        self._folders.clear()

    def _queue_scan_batch(self, scan_id: int, batch: object):
        if scan_id != self._scan_id:
            return  # 过期扫描
        if not batch:
            return
        self._scan_batch_queue.append(list(batch))
        self._ensure_ui_drain_timer()

    def _scan_finished(self, scan_id: int, outcome: object):
        if scan_id != self._scan_id:
            return
        self._pending_scan_result = outcome if isinstance(outcome, ScanOutcome) else None
        self._ensure_ui_drain_timer()

    def _scan_failed(self, scan_id: int, message: str):
        if scan_id != self._scan_id:
            return
        self._pending_scan_error = message
        self._ensure_ui_drain_timer()

    def _ensure_ui_drain_timer(self):
        if not self._ui_drain_timer.isActive():
            self._ui_drain_timer.start()

    def _drain_ui_queues(self):
        """每轮最多处理 UI_ROW_DRAIN_COUNT 个目录，队列清空后才应用完成结果。"""
        processed = 0
        self.tree.setUpdatesEnabled(False)
        try:
            while self._scan_batch_queue and processed < UI_ROW_DRAIN_COUNT:
                batch = self._scan_batch_queue[0]
                # 同一批次可能被拆到多轮，剩下的部分必须保留在队首
                while batch and processed < UI_ROW_DRAIN_COUNT:
                    self._apply_snapshot(batch.pop(0))
                    processed += 1
                if not batch:
                    self._scan_batch_queue.popleft()
            # 扫描完成后的补全快照同样按限次处理
            while self._pending_final_snapshots and processed < UI_ROW_DRAIN_COUNT:
                self._apply_snapshot(self._pending_final_snapshots.popleft())
                processed += 1
        finally:
            self.tree.setUpdatesEnabled(True)

        final_pending = bool(self._pending_final_snapshots)
        if final_pending:
            # 还有最终快照未插完：保持定时器，等下一轮
            self._ensure_ui_drain_timer()
            return
        if self._scan_batch_queue:
            return
        if self._pending_scan_result is None and self._pending_scan_error is None:
            self._ui_drain_timer.stop()
            if self._scan_final_outcome_pending:
                self._scan_final_outcome_pending = False
                self._finish_scan_ui(self._last_outcome)
            if not _thread_is_running(self._scan_thread):
                self._maybe_finish_close()
            return

        self._ui_drain_timer.stop()
        outcome = self._pending_scan_result
        error = self._pending_scan_error
        self._pending_scan_result = None
        self._pending_scan_error = None
        if error is not None:
            self._apply_scan_failed(error)
            return
        # 最终快照不在此同步全量重放：只把尚未插入的目录入队，走同一限次 drain
        queued = self._queue_missing_final_snapshots(outcome)
        if queued:
            self._last_outcome = outcome
            self._scan_final_outcome_pending = True
            self._set_scan_status_summary(outcome)
            self.scan_progress.setVisible(False)
            self.btn_stop.setEnabled(False)
            self.btn_scan.setEnabled(True)
            return
        self._finish_scan_ui(outcome)

    def _queue_missing_final_snapshots(self, outcome: ScanOutcome | None) -> int:
        """把最终结果中尚未插入树的目录加入待处理队列（限批 drain 消费）。"""
        if outcome is None:
            return 0
        pending = [snap for snap in outcome.folders if snap.path not in self._folders]
        if not pending:
            return 0
        # 先入队，剩余部分每轮最多 UI_ROW_DRAIN_COUNT 个
        self._pending_final_snapshots.extend(pending)
        self._ensure_ui_drain_timer()
        return len(pending)

    def _drain_final_snapshots(self) -> bool:
        """限次消费待插入的最终快照；全部插完后返回 True（供外部/测试调用）。"""
        processed = 0
        while self._pending_final_snapshots and processed < UI_ROW_DRAIN_COUNT:
            snapshot = self._pending_final_snapshots.popleft()
            self._apply_snapshot(snapshot)
            processed += 1
        return not self._pending_final_snapshots

    def _set_scan_status_summary(self, outcome: ScanOutcome | None):
        """扫描完成的状态文案（不涉及树结构操作）。"""
        self._last_outcome = outcome
        self._refresh_summary()
        if outcome is None:
            return
        total = outcome.total
        folder_count = len(outcome.folders)
        if outcome.cancelled or self._scan_stop_requested:
            self._set_status_text("status_scan_stopped", folders=folder_count)
            self._scan_stop_requested = False
        elif not outcome.complete:
            self._set_status_text(
                "status_scan_partial",
                folders=folder_count,
                total=total,
                errors=len(outcome.errors),
            )
        else:
            self._set_status_text("status_scan_done", folders=folder_count, total=total)

    def _finish_scan_ui(self, outcome: ScanOutcome | None):
        """扫描收尾：恢复按钮、刷新汇总与状态，并在不影响草稿的前提下展开根。"""
        self.scan_progress.setVisible(False)
        self.btn_stop.setEnabled(False)
        self.btn_scan.setEnabled(True)
        if outcome is not None:
            self._set_scan_status_summary(outcome)
            self._expand_root_only()
        # 线程可能先于最后一批 UI 更新退出；重扫恢复原选择时不会再触发
        # README 读取，因此必须在队列排空后再检查关闭，不能依赖其他信号。
        self._maybe_finish_close()

    def _apply_scan_failed(self, message: str):
        self.scan_progress.setVisible(False)
        self.btn_stop.setEnabled(False)
        self.btn_scan.setEnabled(True)
        if not self._folders:
            # 根目录根本不可枚举：明确报根目录无效，而不是“部分结果”
            self.summary_label.setText(self.tr("summary_none"))
            self._set_status_text("status_invalid_root")
            self._notify(self.tr("notice_invalid_root"), message, is_error=True)
            self._maybe_finish_close()
            return
        self._set_status_text("status_scan_partial", folders=len(self._folders), total=0, errors=1)
        self._notify(self.tr("notice_readme_failed"), message, is_error=True)
        self._maybe_finish_close()

    # ------------------------------------------------------------------
    # 树更新
    # ------------------------------------------------------------------

    def _apply_snapshot(self, snapshot: FolderSnapshot):
        """按路径更新/插入一个目录行（同一目录的后续通知覆盖计数，不累加）。"""
        path = snapshot.path
        node = self._folders.get(path)
        if node is None:
            node = self._insert_node(snapshot)
            if node is None:
                return
        node.snapshot = snapshot
        self._update_node_item(node)

    def _insert_node(self, snapshot: FolderSnapshot) -> _FolderNode | None:
        parent_item = None
        if snapshot.parent_path is not None:
            parent_node = self._folders.get(snapshot.parent_path)
            if parent_node is not None:
                parent_item = parent_node.item
        if parent_item is None and snapshot.parent_path is not None:
            # 父节点尚未到达：跳过（最终结果会补全），避免产生游离行
            return None

        item = QStandardItem(snapshot.name)
        item.setEditable(False)
        item.setData(str(snapshot.path), Qt.ItemDataRole.UserRole)
        count_items = []
        for _ in range(TREE_COLUMNS - 1):
            count_item = QStandardItem("0")
            count_item.setEditable(False)
            count_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            count_items.append(count_item)

        if parent_item is None:
            self.tree_model.appendRow([item, *count_items])
        else:
            parent_item.appendRow([item, *count_items])

        node = _FolderNode(path=snapshot.path, item=item, snapshot=snapshot)
        self._folders[snapshot.path] = node
        return node

    def _update_node_item(self, node: _FolderNode):
        item = node.item
        snapshot = node.snapshot
        if item is None or snapshot is None:
            return
        label = snapshot.name
        if not snapshot.complete:
            label = f"{label} ({self.tr('incomplete_mark')})"
        item.setText(label)
        item.setToolTip(self.tr("incomplete_tip") if not snapshot.complete else str(snapshot.path))
        parent_item = item.parent()
        model = parent_item.child if parent_item is not None else self.tree_model.item
        row = item.row()
        model(row, 1).setText(f"{snapshot.image_count:,}")
        model(row, 2).setText(f"{snapshot.video_count:,}")
        model(row, 3).setText(f"{snapshot.total:,}")

    def _expand_root_only(self):
        """扫描完成后展开根节点，并尽量恢复当前目录的选择。

        重建树会让当前索引失效；若已有选中的说明目录（或草稿），
        重建后把它重新选中，而不是把选择/草稿强行切回根目录。
        """
        if self.tree_model.rowCount() == 0:
            return
        root_index = self.tree_model.index(0, 0)
        self.tree.expand(root_index)

        folder = self._readme_directory
        if folder is not None:
            node = self._folders.get(folder)
            if node is not None and node.item is not None:
                # 重建后的新索引：阻断信号，避免重复触发选择/加载
                self._set_tree_current_index_silently(node.item.index())
                self.tree.scrollTo(node.item.index())
                return

        if self.tree.currentIndex().isValid():
            return
        self._set_tree_current_index_silently(root_index)
        self.tree.scrollToTop()
        # 信号被阻断，手动触发一次根目录说明加载
        self._on_tree_current_changed(root_index, QModelIndex())

    def expand_all(self):
        self.tree.expandAll()

    def collapse_all(self):
        self.tree.collapseAll()
        if self.tree_model.rowCount() > 0:
            # 折叠全部后至少保留根可见
            self.tree.expand(self.tree_model.index(0, 0))

    def _on_tree_current_changed(self, current: QModelIndex, _previous: QModelIndex):
        if not current.isValid():
            return
        path_text = current.sibling(current.row(), 0).data(Qt.ItemDataRole.UserRole)
        if not path_text:
            return
        folder = Path(str(path_text))
        if folder == self._readme_directory:
            return
        self._run_with_draft_guard(
            "action_switch_folder",
            lambda: self._select_folder(folder),
        )

    def _select_folder(self, folder: Path):
        """切换说明区到指定目录（旧结果按 request_id 丢弃）。"""
        self._autosave_timer.stop()
        self._autosave_requested = False
        self._autosave_failed = False
        self._readme_directory = folder
        self.readme_document = None
        self._readme_dirty = False
        self._set_editor_text("")
        self.readme_edit.setReadOnly(True)
        self._restore_tree_selection()
        self.readme_path_label.setText(str(folder / "readme.txt"))
        self._set_readme_status("")
        self._request_readme_load(folder)

    # ------------------------------------------------------------------
    # 说明文件：读取
    # ------------------------------------------------------------------

    def _request_readme_load(self, folder: Path):
        self._readme_request_id += 1
        request_id = self._readme_request_id
        if self._readme_thread is not None:
            # 只保留最新待读请求，避免堆积下载与线程
            self._readme_pending_load = (request_id, folder)
            return
        self._start_readme_load(request_id, folder)

    def _start_readme_load(self, request_id: int, folder: Path):
        self._readme_busy = True
        thread = QThread(self)
        worker = ReadmeLoadWorker(request_id, folder)
        self._readme_thread = thread
        self._readme_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_readme_loaded)
        worker.failed.connect(self._on_readme_load_failed)
        for signal in (worker.finished, worker.failed):
            signal.connect(thread.quit)
            signal.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        # 以 lambda 绑定身份，旧线程的 finished 不得清除新线程引用
        thread.finished.connect(lambda t=thread, w=worker: self._on_readme_thread_finished(t, w))
        thread.start()

    def _on_readme_thread_finished(self, thread: QThread | None = None, worker: QObject | None = None):
        """某个说明 IO 线程退出：只清理它自己的引用，然后才继续后续工作。"""
        del worker
        if thread is not None and thread is not self._readme_thread:
            self._retired_readme_jobs = [
                (t, w) for (t, w) in self._retired_readme_jobs if t is not thread
            ]
            self._maybe_finish_close()
            return

        self._readme_thread = None
        self._readme_worker = None
        self._retired_readme_jobs = [
            (t, w) for (t, w) in self._retired_readme_jobs if _thread_is_running(t)
        ]
        self._readme_busy = False
        # 注意：只有旧线程已退出，才允许发起新的 IO
        pending = self._readme_pending_load
        if pending is not None:
            self._readme_pending_load = None
            request_id, folder = pending
            if request_id == self._readme_request_id:
                self._start_readme_load(request_id, folder)
                return
        self._maybe_continue_pending_action()
        self._maybe_finish_close()

    def _on_readme_loaded(self, request_id: int, result):
        if request_id != self._readme_request_id:
            return  # 过期结果，丢弃
        status = getattr(result, "status", STATUS_ERROR)
        error = getattr(result, "error", "") or ""
        if status in (STATUS_READY, STATUS_MISSING) and getattr(result, "document", None) is not None:
            document = result.document
            self.readme_document = document
            self._readme_dirty = False
            self._set_editor_text(document.text)
            self.readme_edit.setReadOnly(False)
            self.readme_path_label.setText(str(document.path))
            self._set_readme_status("")
        else:
            # 只有核心确认的真正缺失才可编辑；读取失败不能当作新空白
            self.readme_document = None
            self._readme_dirty = False
            self._set_editor_text("")
            self.readme_edit.setReadOnly(True)
            if status == STATUS_TOO_LARGE:
                self._set_readme_status(
                    "status_readme_too_large", size=MAX_README_BYTES // (1024 * 1024)
                )
            else:
                self._set_readme_status("status_readme_error", error=error)
                self._notify(self.tr("notice_readme_failed"), error, is_error=True)
            self.readme_path_label.setText(
                str(getattr(result, "path", None) or (self._readme_directory or Path("")) / "readme.txt")
            )
        self._maybe_continue_pending_action()

    def _on_readme_load_failed(self, request_id: int, message: str):
        if request_id != self._readme_request_id:
            return
        self.readme_document = None
        self._readme_dirty = False
        self._set_editor_text("")
        self.readme_edit.setReadOnly(True)
        self._set_readme_status("status_readme_error", error=message)
        self._notify(self.tr("notice_readme_failed"), message, is_error=True)
        self._maybe_continue_pending_action()

    # ------------------------------------------------------------------
    # 说明文件：保存
    # ------------------------------------------------------------------

    def _on_editor_text_changed(self):
        if self._suspend_editor_signal:
            return
        if self.readme_document is None:
            return
        self._readme_dirty = self.readme_edit.toPlainText() != self.readme_document.text
        if (
            self._autosave_failed
            and self._pending_action is not None
            and self._pending_action[0] == "action_close"
        ):
            # 关闭失败后继续编辑表示留在窗口；只有显式重试/放弃才续关
            self._pending_action = None
            self._cancel_close_intent()
            self._refresh_draft_bar()
        self._autosave_failed = False
        self._set_readme_status("")
        if self._pending_action is not None:
            action_key, action, _kind = self._pending_action
            self._pending_action = (action_key, action, "io")
            self._refresh_draft_bar()
            # 已请求离开目录时，必须继续写完最新草稿再执行动作
            if action_key != "action_save":
                self._flush_readme()
                return
        # 保存进行中即使撤回旧基线，也要在新基线返回后重新比较
        if self._readme_dirty or self._is_io_busy():
            self._autosave_timer.start()
        else:
            self._autosave_timer.stop()
            self._maybe_continue_pending_action()

    def _set_editor_text(self, text: str):
        self._suspend_editor_signal = True
        try:
            self.readme_edit.setPlainText(text)
        finally:
            self._suspend_editor_signal = False

    def _flush_readme(self):
        """停止防抖并请求写入；IO 未清理时仅记下待办，失败后等编辑或重试。"""
        self._autosave_timer.stop()
        if self._autosave_failed or self.readme_document is None:
            return
        self._autosave_requested = True
        self._maybe_continue_pending_action()

    def save_readme(self) -> bool:
        """冻结路径/基线/文本启动一次保存，始终保持编辑器可输入。"""
        if self._is_io_busy() or self.readme_document is None or not self._readme_dirty:
            return False
        text = self.readme_edit.toPlainText()
        document = self.readme_document
        self._autosave_requested = False
        self._readme_busy = True
        self._readme_request_id += 1
        request_id = self._readme_request_id
        self._refresh_draft_bar()

        thread = QThread(self)
        worker = ReadmeSaveWorker(request_id, document, text)
        self._readme_thread = thread
        self._readme_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_readme_saved)
        worker.failed.connect(self._on_readme_save_failed)
        for signal in (worker.finished, worker.failed):
            signal.connect(thread.quit)
            signal.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._on_readme_thread_finished(t, w))
        thread.start()
        return True

    def _on_readme_saved(self, request_id: int, result):
        if request_id != self._readme_request_id:
            return
        status = getattr(result, "status", STATUS_ERROR)
        error = getattr(result, "error", "") or ""
        if status == STATUS_SAVED and getattr(result, "document", None) is not None:
            self.readme_document = result.document
            # 只更新保存基线；当前文本可能比 worker 的快照更新，绝不覆盖它
            self._readme_dirty = self.readme_edit.toPlainText() != result.document.text
            self._autosave_failed = False
            self._set_readme_status("")
            if self._readme_dirty and not self._autosave_timer.isActive():
                self._autosave_requested = True
            return
        key = "status_readme_conflict_plain" if status == STATUS_CONFLICT else "status_readme_save_failed"
        self._mark_readme_save_failed(key, error)

    def _on_readme_save_failed(self, request_id: int, message: str):
        if request_id != self._readme_request_id:
            return
        self._mark_readme_save_failed("status_readme_save_failed", message)

    def _mark_readme_save_failed(self, key: str, message: str):
        """失败不改变草稿和目录，也不自动循环重试或继续关闭。"""
        self._autosave_timer.stop()
        self._autosave_requested = False
        self._autosave_failed = True
        self._readme_dirty = self.readme_edit.toPlainText() != self.readme_document.text
        self._set_readme_status(key, error=message)
        if self._pending_action is None:
            self._pending_action = ("action_save", self._noop_action, "draft")
        else:
            action_key, action, _kind = self._pending_action
            self._pending_action = (action_key, action, "draft")
        self._restore_tree_selection()

    # ------------------------------------------------------------------
    # 草稿守卫：自动保存，失败时重试 / 放弃 / 取消
    # ------------------------------------------------------------------

    def _run_with_draft_guard(self, action_key: str, action):
        """离开当前目录前自动写完最新草稿，仅失败才显示异常决策。"""
        if self._close_intent and action_key != "action_close":
            self._cancel_close_intent()
        self._pending_action = (action_key, action, "io")
        self._autosave_timer.stop()
        self._autosave_requested = True
        self._restore_tree_selection()
        self._maybe_continue_pending_action()

    def _is_io_busy(self) -> bool:
        """说明读写是否仍在进行（线程引用未清即视为未完成）。"""
        return self._readme_busy or self._readme_thread is not None

    def _resolve_draft(self, choice: str):
        pending = self._pending_action
        if pending is None:
            return
        action_key, action, _kind = pending
        # IO 进行中不允许决策（保存/读取未返回时放弃会把草稿写错）
        if self._is_io_busy():
            return
        if choice == "cancel":
            self._pending_action = None
            self._cancel_close_intent()
            self._refresh_draft_bar()
            # 取消：恢复树选择到当前说明目录
            self._restore_tree_selection()
            return

        if choice == "discard":
            self._pending_action = None
            self._autosave_timer.stop()
            self._autosave_requested = False
            self._autosave_failed = False
            self._refresh_draft_bar()
            self._set_editor_text(self.readme_document.text if self.readme_document else "")
            self._readme_dirty = False
            self._set_readme_status("")
            if action_key in ("action_save", "action_scan") and self._readme_directory is not None:
                # 留在当前目录（含重扫）时重新读取，避免继续用外部变更前的基线
                self._select_folder(self._readme_directory)
            if action_key != "action_save":
                action()
            # 关闭流程：草稿已放弃，继续等待后台清理并回调 on_ready
            self._maybe_finish_close()
            return

        # 重试继续保持原动作，直到所有较新的文本也已成功保存
        self._autosave_failed = False
        self._pending_action = (action_key, action, "io")
        self._autosave_requested = True
        self._set_readme_status("")
        self._refresh_draft_bar()
        self._maybe_continue_pending_action()

    def _restore_tree_selection(self):
        """把树选择恢复到当前说明目录，避免选择与编辑区不一致。"""
        folder = self._readme_directory
        if folder is None:
            return
        node = self._folders.get(folder)
        if node is None or node.item is None:
            return
        index = node.item.index()
        self._set_tree_current_index_silently(index)

    def _set_tree_current_index_silently(self, index: QModelIndex):
        """阻断选择信号设置当前行（不触发草稿守卫/加载）。"""
        self.tree.blockSignals(True)
        selection_model = self.tree.selectionModel()
        if selection_model is not None:
            selection_model.blockSignals(True)
        try:
            self.tree.setCurrentIndex(index)
        finally:
            if selection_model is not None:
                selection_model.blockSignals(False)
            self.tree.blockSignals(False)

    def _current_tree_folder(self) -> Path | None:
        index = self.tree.currentIndex()
        if not index.isValid():
            return None
        text = index.sibling(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        return Path(str(text)) if text else None

    def _maybe_continue_pending_action(self):
        """只在旧线程清理后启动下一次保存或执行待办动作。"""
        pending = self._pending_action
        if self._is_io_busy():
            return
        # 失败与 dirty 独立：旧快照失败时用户可能已撤回基线，仍须明确处理
        if self._autosave_failed:
            if pending is not None:
                self._pending_action = (pending[0], pending[1], "draft")
            self._refresh_draft_bar()
            return
        if self._readme_dirty and self.readme_document is not None:
            if self._autosave_requested or (pending is not None and pending[0] != "action_save"):
                self.save_readme()
            return
        self._autosave_requested = False
        if pending is None:
            return
        _action_key, action, _kind = pending
        self._pending_action = None
        self._refresh_draft_bar()
        action()
        self._maybe_finish_close()

    # ------------------------------------------------------------------
    # 关闭协调（独立窗口与统一窗口共用）
    # ------------------------------------------------------------------

    def _has_background_work(self) -> bool:
        return (
            self._scan_thread is not None
            or self._readme_thread is not None
            or bool(self._retired_scan_jobs)
            or bool(self._retired_readme_jobs)
            or self._ui_drain_timer.isActive()
            or bool(self._scan_batch_queue)
            or bool(self._pending_final_snapshots)
            or self._readme_busy
            or self._pending_scan_restart
        )

    def request_close(self, on_ready) -> bool:
        """关闭协调接口（幂等）。

        返回 True：当前可以安全退出，调用方直接接受关闭。
        返回 False：已接管关闭流程，最终会调用 on_ready（可能延迟到后台清理完成）。
        """
        self._autosave_timer.stop()
        if not self._readme_dirty and not self._has_background_work() and not self._autosave_failed:
            self._pending_action = None
            self._cancel_close_intent()
            return True

        if on_ready is not None and on_ready not in self._close_callbacks:
            self._close_callbacks.append(on_ready)
        self._closing = True
        self._close_intent = True
        if self._scan_stop_event is not None:
            self._scan_stop_event.set()
        self._pending_scan_restart = False
        self._readme_pending_load = None
        self._pending_action = ("action_close", self._noop_action, "io")
        self._autosave_requested = True
        self._maybe_continue_pending_action()
        return False

    def _noop_action(self):
        """关闭流程的占位动作：决策后由 _maybe_finish_close 统一回调。"""
        return None

    def _cancel_close_intent(self):
        """用户取消离开当前目录时撤销关闭意图和回调。"""
        self._close_intent = False
        self._closing = False
        self._close_callbacks.clear()

    def _maybe_finish_close(self):
        """后台清理结束（或草稿已解决）后，若仍有等待的关闭回调则执行。"""
        if not self._close_callbacks:
            return
        # 关闭意图必须仍然有效，且失败的草稿决策已经明确解决
        if not self._close_intent:
            return
        if self._autosave_failed:
            return
        if self._readme_dirty and self.readme_document is not None:
            return
        if self._pending_action is not None:
            return
        if self._has_background_work():
            return
        self._closing = False
        self._close_intent = False
        callbacks = list(self._close_callbacks)
        self._close_callbacks.clear()
        for callback in callbacks:
            try:
                callback()
            except Exception:
                pass

    def closeEvent(self, event):
        """独立运行时的关闭：非阻塞协调，必要时 ignore 后延迟重新关闭。"""

        def on_ready():
            # 清理完成后关闭窗口（推迟到事件循环，避免在信号回调里重入）
            self.hide()
            QTimer.singleShot(0, self.close)

        if self.request_close(on_ready):
            # 直接关闭：停掉可能残留的协作式扫描
            if self._scan_stop_event is not None:
                self._scan_stop_event.set()
            event.accept()
            return
        event.ignore()


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
