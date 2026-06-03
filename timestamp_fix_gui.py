from __future__ import annotations

import ctypes
import importlib
import json
import os
import re
import subprocess
import sys
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import ExifTags, Image
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
    QLabel,
    QMessageBox,
    QTableView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass


APP_NAME = "TimestampFixGUI"
SUPPORTED_LANGUAGES = ("zh", "en")
DEFAULT_LANGUAGE = "zh"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".heic", ".heif", ".png", ".tif", ".tiff", ".webp")
VIDEO_SUFFIXES = (".mp4", ".mov", ".m4v", ".3gp")
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES + VIDEO_SUFFIXES
EXIFTOOL_TIMEOUT_SECONDS = 60
EXIF_DATETIME_TAGS = ("DateTimeOriginal", "DateTimeDigitized", "DateTime")
EXIF_SUBSEC_TAGS = ("SubSecTimeOriginal", "SubSecTimeDigitized", "SubSecTime")
WINDOWS_MEDIA_DATE_PROPERTY_IDS = (12, 208, 182, 183, 191)
UI_ROW_DRAIN_COUNT = 120
FILENAME_TIME_PATTERNS = (
    re.compile(r"(20\d{2}|19\d{2})([01]\d)([0-3]\d)[_\- ]?([0-2]\d)([0-5]\d)([0-5]\d)"),
    re.compile(r"(20\d{2}|19\d{2})[-_.]([01]\d)[-_.]([0-3]\d)[_ -]([0-2]\d)[-.]([0-5]\d)[-.]([0-5]\d)"),
)
TRANSLATIONS = {
    "zh": {
        "app_title": "照片时间戳修复",
        "header_title": "照片时间戳修复",
        "header_subtitle": "从拍摄时间恢复文件创建、修改和访问时间",
        "header_note": "拖入文件或文件夹，优先读取 EXIF 拍摄时间；没有拍摄时间时使用该文件现有的最早时间。",
        "language": "界面语言",
        "source_dir": "源目录",
        "source_placeholder": "选择或拖入需要修复时间戳的照片目录",
        "choose_source": "选择源目录",
        "scan_subdirs": "扫描子目录",
        "table_file": "文件相对路径",
        "table_shot_time": "采用时间",
        "table_source": "来源",
        "table_status": "状态",
        "drop_hint": "可拖入照片、视频或文件夹，处理会直接修改原文件时间戳",
        "rescan": "重新扫描",
        "clear_list": "清空列表",
        "start_fix": "开始修复时间戳",
        "waiting_source": "等待选择或拖入文件",
        "scanning": "正在扫描文件",
        "scan_none_status": "未找到可处理文件",
        "scan_done_status": "共扫描到 {count} 个文件，准备就绪",
        "drop_added": "已拖拽添加 {added} 个文件，当前共 {count} 项",
        "drop_no_new": "未添加新的文件",
        "list_cleared": "列表已清空",
        "preparing": "准备修复",
        "progress": "正在处理 {i}/{total}",
        "task_done_status": "修复完成：成功 {success}，失败 {failed}，跳过 {skipped}",
        "status_pending": "待处理",
        "status_fixing": "正在写入时间戳",
        "status_fixed": "已修复",
        "status_fixed_file_only": "已修复文件时间，媒体元数据未写入",
        "status_skipped": "已跳过",
        "status_failed": "失败：{error}",
        "source_exif": "EXIF 拍摄时间",
        "source_filename": "文件名时间",
        "source_earliest": "文件现有最早时间",
        "source_unknown": "未知",
        "yes": "是",
        "no": "否",
        "invalid_folder_title": "目录无效",
        "invalid_folder_content": "请选择有效的源目录。",
        "cannot_start_title": "无法开始",
        "cannot_start_content": "请先添加需要修复的文件。",
        "task_done_title": "处理完成",
        "task_done_message": "时间戳修复完成。\n\n成功: {success}\n失败: {failed}\n跳过: {skipped}",
        "process_done_notice": "已完成 {count} 个文件",
    },
    "en": {
        "app_title": "Timestamp Fix",
        "header_title": "Photo Timestamp Fix",
        "header_subtitle": "Restore file created, modified, and accessed timestamps from capture time",
        "header_note": "Drop files or folders. EXIF capture time is preferred; otherwise the file's earliest existing timestamp is used.",
        "language": "Language",
        "source_dir": "Source folder",
        "source_placeholder": "Choose or drop a folder containing photos to fix",
        "choose_source": "Choose source",
        "scan_subdirs": "Scan subfolders",
        "table_file": "Relative file path",
        "table_shot_time": "Applied time",
        "table_source": "Source",
        "table_status": "Status",
        "drop_hint": "Drop photos, videos, or folders. Processing modifies original file timestamps in place.",
        "rescan": "Rescan",
        "clear_list": "Clear list",
        "start_fix": "Fix timestamps",
        "waiting_source": "Waiting for files",
        "scanning": "Scanning files",
        "scan_none_status": "No processable files found",
        "scan_done_status": "Scanned {count} file(s), ready",
        "drop_added": "Dropped {added} file(s), total {count}",
        "drop_no_new": "No new files were added",
        "list_cleared": "List cleared",
        "preparing": "Preparing",
        "progress": "Processing {i}/{total}",
        "task_done_status": "Done: {success} fixed, {failed} failed, {skipped} skipped",
        "status_pending": "Pending",
        "status_fixing": "Writing timestamps",
        "status_fixed": "Fixed",
        "status_fixed_file_only": "File timestamps fixed; media metadata was not written",
        "status_skipped": "Skipped",
        "status_failed": "Failed: {error}",
        "source_exif": "EXIF capture time",
        "source_filename": "Filename time",
        "source_earliest": "Earliest existing file time",
        "source_unknown": "Unknown",
        "yes": "Yes",
        "no": "No",
        "invalid_folder_title": "Invalid folder",
        "invalid_folder_content": "Choose a valid source folder.",
        "cannot_start_title": "Cannot start",
        "cannot_start_content": "Add files to fix first.",
        "task_done_title": "Task complete",
        "task_done_message": "Timestamp repair complete.\n\nFixed: {success}\nFailed: {failed}\nSkipped: {skipped}",
        "process_done_notice": "Processed {count} file(s)",
    },
}


@dataclass
class TimestampItem:
    path: Path
    source_root: Path | None
    rel_path: Path
    timestamp: float | None
    source: str
    status: str = "status_pending"


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
        raise ImportError("qfluentwidgets is not installed.") from last_exc

    return {
        "theme": module.Theme,
        "set_theme": module.setTheme,
        "PrimaryPushButton": module.PrimaryPushButton,
        "PushButton": module.PushButton,
        "LineEdit": module.LineEdit,
        "TableView": getattr(module, "TableView", QTableView),
        "TableWidget": module.TableWidget,
        "ProgressBar": module.ProgressBar,
        "CheckBox": module.CheckBox,
        "ComboBox": module.ComboBox,
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
TableView = FW["TableView"]
TableWidget = FW["TableWidget"]
ProgressBar = FW["ProgressBar"]
CheckBox = FW["CheckBox"]
ComboBox = FW["ComboBox"]
CardWidget = FW["CardWidget"]
SubtitleLabel = FW["SubtitleLabel"]
BodyLabel = FW["BodyLabel"]
InfoBar = FW["InfoBar"]
InfoBarPosition = FW["InfoBarPosition"]
FluentIcon = FW["FluentIcon"]
setThemeColor = FW["set_theme_color"]
IS_PRO = FW["is_pro"]


def _pick_icon(*names: str):
    for name in names:
        icon = getattr(FluentIcon, name, None)
        if icon is not None:
            return icon
    return FluentIcon.APPLICATION


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except Exception:
        return path


def _is_supported_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES


def _iter_paths(paths: list[Path], recursive: bool) -> list[tuple[Path, Path | None]]:
    files: list[tuple[Path, Path | None]] = []
    for path in paths:
        if path.is_file():
            if _is_supported_file(path):
                files.append((path, path.parent))
            continue
        if not path.is_dir():
            continue
        iterator = path.rglob("*") if recursive else path.glob("*")
        files.extend((candidate, path) for candidate in iterator if _is_supported_file(candidate))
    return files


def _parse_exif_datetime(value: object, subsec: object = None) -> float | None:
    if not value:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    text = str(value).strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt)
            if subsec:
                subsec_text = str(subsec.decode("utf-8", "ignore") if isinstance(subsec, bytes) else subsec)
                digits = "".join(ch for ch in subsec_text if ch.isdigit())[:6]
                if digits:
                    dt = dt.replace(microsecond=int(digits.ljust(6, "0")))
            return dt.timestamp()
        except ValueError:
            continue
    return None


def _parse_shell_datetime(value: object) -> float | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None

    text = text.replace("\u200e", "").replace("\u200f", "")
    text = re.sub(r"[\u202a-\u202e]", "", text)
    text = text.replace("上午", "AM").replace("下午", "PM")

    formats = (
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %I:%M:%S %p",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            continue

    match = re.search(
        r"(20\d{2}|19\d{2})\D+([01]?\d)\D+([0-3]?\d)\D+([0-2]?\d)\D+([0-5]\d)(?:\D+([0-5]\d))?",
        text,
    )
    if match:
        try:
            year, month, day, hour, minute, second = match.groups(default="0")
            return datetime(
                int(year),
                int(month),
                int(day),
                int(hour),
                int(minute),
                int(second),
            ).timestamp()
        except ValueError:
            return None

    return None


def _timestamp_from_windows_shell(path: Path) -> float | None:
    if sys.platform != "win32":
        return None
    try:
        import win32com.client  # type: ignore

        shell = win32com.client.Dispatch("Shell.Application")
        folder = shell.NameSpace(str(path.parent))
        if folder is None:
            return None
        item = folder.ParseName(path.name)
        if item is None:
            return None
        for prop_id in WINDOWS_MEDIA_DATE_PROPERTY_IDS:
            value = folder.GetDetailsOf(item, prop_id)
            ts = _parse_shell_datetime(value)
            if ts is not None:
                return ts
    except Exception:
        return None
    return None


def _timestamp_from_exif(path: Path) -> float | None:
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        return None
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None

            tag_lookup = {name: key for key, name in ExifTags.TAGS.items()}
            for tag_name in EXIF_DATETIME_TAGS:
                tag_id = tag_lookup.get(tag_name)
                if tag_id is None:
                    continue
                value = exif.get(tag_id)
                subsec = None
                for subsec_name in EXIF_SUBSEC_TAGS:
                    subsec_id = tag_lookup.get(subsec_name)
                    if subsec_id is not None:
                        subsec = exif.get(subsec_id)
                        if subsec:
                            break
                ts = _parse_exif_datetime(value, subsec)
                if ts is not None:
                    return ts
    except Exception:
        return None
    return None


def _timestamp_from_filename(path: Path) -> float | None:
    for pattern in FILENAME_TIME_PATTERNS:
        match = pattern.search(path.stem)
        if not match:
            continue
        try:
            year, month, day, hour, minute, second = (int(part) for part in match.groups())
            return datetime(year, month, day, hour, minute, second).timestamp()
        except ValueError:
            continue
    return None


def _earliest_file_timestamp(path: Path) -> float | None:
    try:
        stat = path.stat()
    except OSError:
        return None

    candidates = [stat.st_mtime, stat.st_atime]
    ctime = getattr(stat, "st_ctime", None)
    if ctime:
        candidates.append(ctime)
    birthtime = getattr(stat, "st_birthtime", None)
    if birthtime:
        candidates.append(birthtime)
    return min(candidates) if candidates else None


def detect_timestamp(path: Path) -> tuple[float | None, str]:
    ts = _timestamp_from_windows_shell(path)
    if ts is not None:
        return ts, "source_exif"
    ts = _timestamp_from_exif(path)
    if ts is not None:
        return ts, "source_exif"
    ts = _timestamp_from_filename(path)
    if ts is not None:
        return ts, "source_filename"
    ts = _earliest_file_timestamp(path)
    if ts is not None:
        return ts, "source_earliest"
    return None, "source_unknown"


def _format_timestamp(ts: float | None) -> str:
    if ts is None:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _unix_time_to_filetime(timestamp: float) -> int:
    return int((timestamp + 11644473600) * 10_000_000)


def _set_windows_file_times(path: Path, timestamp: float) -> None:
    if sys.platform != "win32":
        return

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p

    set_file_time = kernel32.SetFileTime
    set_file_time.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    set_file_time.restype = ctypes.c_int

    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]

    generic_write = 0x40000000
    file_share_read = 0x00000001
    file_share_write = 0x00000002
    file_share_delete = 0x00000004
    open_existing = 3
    file_attribute_normal = 0x00000080
    invalid_handle_value = ctypes.c_void_p(-1).value

    handle = create_file(
        str(path),
        generic_write,
        file_share_read | file_share_write | file_share_delete,
        None,
        open_existing,
        file_attribute_normal,
        None,
    )
    if handle == invalid_handle_value:
        raise ctypes.WinError(ctypes.get_last_error())

    value = _unix_time_to_filetime(timestamp)
    low = value & 0xFFFFFFFF
    high = value >> 32

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

    filetime = FILETIME(low, high)
    try:
        ok = set_file_time(handle, ctypes.byref(filetime), ctypes.byref(filetime), ctypes.byref(filetime))
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        close_handle(handle)


def _startupinfo():
    if os.name != "nt":
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return startupinfo


def _exiftool_candidates() -> list[str]:
    env_path = os.environ.get("EXIFTOOL_PATH")
    base_dir = Path(__file__).resolve().parent
    candidates: list[str] = []
    if env_path:
        candidates.append(env_path)
    candidates.extend(
        [
            str(base_dir / "vendor" / "exiftool" / "exiftool.exe"),
            str(base_dir / "vendor" / "exiftool" / "exiftool"),
            str(base_dir / "exiftool" / "exiftool.exe"),
            str(base_dir / "exiftool" / "exiftool"),
            str(base_dir / "bin" / "exiftool.exe"),
            str(base_dir / "bin" / "exiftool"),
            "exiftool",
        ]
    )
    return candidates


@lru_cache(maxsize=1)
def _find_exiftool() -> str | None:
    for candidate in _exiftool_candidates():
        if candidate != "exiftool" and not Path(candidate).exists():
            continue
        try:
            result = subprocess.run(
                [candidate, "-ver"],
                capture_output=True,
                timeout=EXIFTOOL_TIMEOUT_SECONDS,
                startupinfo=_startupinfo(),
            )
            if result.returncode == 0:
                return candidate
        except Exception:
            continue
    return None


def _batch_exiftool_supported_exts() -> tuple[str, ...]:
    return tuple(sorted({suffix.lstrip(".") for suffix in SUPPORTED_SUFFIXES}))


def _apply_batch_exiftool(source_root: Path) -> bool:
    exiftool = _find_exiftool()
    if exiftool is None:
        return False

    root = _safe_resolve(source_root)
    if not root.is_dir():
        return False

    args = [
        exiftool,
        "-api",
        "QuickTimeUTC=1",
        "-AllDates<FileModifyDate",
        "-FileCreateDate<FileModifyDate",
        "-AllDates<FileCreateDate",
        "-FileModifyDate<FileCreateDate",
        "-AllDates<TrackCreateDate",
        "-FileCreateDate<TrackCreateDate",
        "-FileModifyDate<TrackCreateDate",
        "-AllDates<MediaCreateDate",
        "-FileCreateDate<MediaCreateDate",
        "-FileModifyDate<MediaCreateDate",
        "-AllDates<CreateDate",
        "-FileCreateDate<CreateDate",
        "-FileModifyDate<CreateDate",
        "-AllDates<DateTimeOriginal",
        "-FileCreateDate<DateTimeOriginal",
        "-FileModifyDate<DateTimeOriginal",
        "-overwrite_original",
    ]
    for ext in _batch_exiftool_supported_exts():
        args.extend(["-ext", ext])
    args.extend(["-r", "."])

    result = subprocess.run(
        args,
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=EXIFTOOL_TIMEOUT_SECONDS,
        startupinfo=_startupinfo(),
    )
    return result.returncode == 0


def apply_file_times_only(path: Path, timestamp: float) -> None:
    os.utime(path, (timestamp, timestamp))
    _set_windows_file_times(path, timestamp)


def _make_item(file_path: Path, source_root: Path | None) -> TimestampItem:
    if source_root is not None:
        try:
            rel_path = file_path.relative_to(source_root)
        except ValueError:
            rel_path = Path(file_path.name)
    else:
        rel_path = Path(file_path.name)

    timestamp, source = detect_timestamp(file_path)
    return TimestampItem(
        path=file_path,
        source_root=source_root,
        rel_path=rel_path,
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
        items: list[TimestampItem] = []
        for file_path, source_root in _iter_paths(self.paths, self.recursive):
            resolved = _safe_resolve(file_path)
            if resolved in seen:
                continue
            seen.add(resolved)
            items.append(_make_item(file_path, source_root))

        for item in sorted(items, key=lambda value: str(value.rel_path)):
            self.row_ready.emit(item)

        self.finished.emit(len(items))


class DropScanWorker(QObject):
    row_ready = pyqtSignal(object)
    finished = pyqtSignal(int)

    def __init__(self, paths: list[Path], recursive: bool, existing: set[Path]):
        super().__init__()
        self.paths = paths
        self.recursive = recursive
        self.existing = existing

    def run(self):
        seen: set[Path] = set(self.existing)
        items: list[TimestampItem] = []
        for file_path, source_root in _iter_paths(self.paths, self.recursive):
            resolved = _safe_resolve(file_path)
            if resolved in seen:
                continue
            seen.add(resolved)
            items.append(_make_item(file_path, source_root))

        for item in sorted(items, key=lambda value: str(value.rel_path)):
            self.row_ready.emit(item)

        self.finished.emit(len(items))


class ProcessWorker(QObject):
    row_update = pyqtSignal(int, str)
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, items: list[TimestampItem]):
        super().__init__()
        self.items = items

    def run(self):
        success = 0
        failed = 0
        skipped = 0
        total = len(self.items)
        source_roots: set[Path] = set()
        for item in self.items:
            if item.source_root is not None:
                source_roots.add(item.source_root)

        for index, item in enumerate(self.items):
            progress_percent = int(((index + 1) / total) * 100) if total else 0
            if item.timestamp is None:
                skipped += 1
                self.row_update.emit(index, "status_skipped")
                self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")
                continue

            self.row_update.emit(index, "status_fixing")
            try:
                apply_file_times_only(item.path, item.timestamp)
                success += 1
                self.row_update.emit(index, "status_fixed_file_only")
            except Exception as exc:
                failed += 1
                self.row_update.emit(index, f"status_failed|{str(exc)[:36]}")

            self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")

        media_written = False
        for source_root in sorted(source_roots, key=lambda path: str(path)):
            media_written = _apply_batch_exiftool(source_root) or media_written

        if media_written:
            for index, item in enumerate(self.items):
                if item.status == "status_fixed_file_only":
                    item.status = "status_fixed"
                    self.row_update.emit(index, "status_fixed")

        self.finished.emit({"success": success, "failed": failed, "skipped": skipped})


class MainWindow(FramelessMainWindow):
    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("Timestamp Fix")
        self._title_bar_height = 36
        if not self._embedded:
            self.resize(1280, 820)
            self._set_blue_title_bar()

        self.lang = DEFAULT_LANGUAGE
        self._last_status_key = "waiting_source"
        self._last_status_kwargs: dict = {}
        self.file_list: list[TimestampItem] = []
        self._scan_row_queue: deque[TimestampItem] = deque()
        self._process_update_queue: deque[tuple[int, str]] = deque()
        self._pending_scan_result: int | None = None
        self._pending_drop_result: int | None = None
        self._pending_process_result: dict | None = None
        self._ui_drain_timer = QTimer(self)
        self._ui_drain_timer.setInterval(10)
        self._ui_drain_timer.timeout.connect(self._drain_ui_queues)
        self.is_processing = False
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._drop_thread: QThread | None = None
        self._drop_worker: DropScanWorker | None = None
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
        self.table_context_menu = install_file_context_menu(self.table, self, self._context_file_paths, lambda: self.lang)
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
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        self.btn_scan = PushButton(self.tr("rescan"), self)
        self.btn_scan.setIcon(_pick_icon("SYNC", "UPDATE"))
        self.btn_scan.clicked.connect(self.scan_files)
        self.btn_clear = PushButton(self.tr("clear_list"), self)
        self.btn_clear.setIcon(_pick_icon("DELETE", "REMOVE"))
        self.btn_clear.clicked.connect(self.clear_list)
        self.btn_start = PrimaryPushButton(self.tr("start_fix"), self)
        self.btn_start.setIcon(_pick_icon("PLAY", "SEND"))
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

    def _thread_is_running(self, thread: QThread | None) -> bool:
        try:
            return thread is not None and thread.isRunning()
        except RuntimeError:
            return False

    def _is_busy(self) -> bool:
        return (
            self.is_processing
            or self._thread_is_running(self._scan_thread)
            or self._thread_is_running(self._drop_thread)
            or self._thread_is_running(self._process_thread)
            or self._ui_drain_timer.isActive()
            or bool(self._scan_row_queue)
            or bool(self._process_update_queue)
        )

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
        self.btn_start.setText(self.tr("start_fix"))
        self._set_status_text(self._last_status_key, **self._last_status_kwargs)
        self._refresh_table_language()

    def _refresh_table_language(self):
        for row, item in enumerate(self.file_list):
            source_item = self.table.item(row, 2)
            status_item = self.table.item(row, 3)
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

    def _context_file_paths(self, _row: int, selected_rows: list[int]) -> list[Path]:
        return [
            self.file_list[row].path
            for row in selected_rows
            if 0 <= row < len(self.file_list)
        ]

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
        if self._is_busy():
            return
        self.file_list.clear()
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self._set_status_text("list_cleared")

    def add_dropped_paths(self, paths: list[Path]):
        if self._is_busy():
            return
        first_dir = next((p for p in paths if p.is_dir()), None)
        if first_dir is None:
            first_file = next((p for p in paths if p.is_file()), None)
            first_dir = first_file.parent if first_file is not None else None
        if first_dir is not None:
            self.input_edit.setText(str(first_dir))
            self._save_settings()

        existing = {_safe_resolve(item.path) for item in self.file_list}
        self.progress.setValue(0)
        self._set_status_text("scanning")

        self._drop_thread = QThread(self)
        self._drop_worker = DropScanWorker(paths, self.include_subdirs_check.isChecked(), existing)
        self._drop_worker.moveToThread(self._drop_thread)
        self._drop_thread.started.connect(self._drop_worker.run)
        self._drop_worker.row_ready.connect(self._queue_scan_row)
        self._drop_worker.finished.connect(self._drop_finished)
        self._drop_worker.finished.connect(self._drop_thread.quit)
        self._drop_worker.finished.connect(self._drop_worker.deleteLater)
        self._drop_thread.finished.connect(self._drop_thread.deleteLater)
        self._drop_thread.finished.connect(self._drop_thread_finished)
        self._drop_thread.start()

    def scan_files(self):
        if self._is_busy():
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
        self._scan_row_queue.clear()
        self._process_update_queue.clear()
        self._pending_scan_result = None
        self._pending_drop_result = None
        self._pending_process_result = None
        self._ui_drain_timer.stop()
        self.progress.setValue(0)
        self._set_status_text("scanning")
        self._save_settings()

        self._scan_thread = QThread(self)
        self._scan_worker = ScanWorker([input_dir], self.include_subdirs_check.isChecked())
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.row_ready.connect(self._queue_scan_row)
        self._scan_worker.finished.connect(self._scan_finished)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.start()

    def _append_scan_row(self, item: TimestampItem):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(item.rel_path)))
        self.table.setItem(row, 1, QTableWidgetItem(_format_timestamp(item.timestamp)))
        self.table.setItem(row, 2, QTableWidgetItem(self.tr(item.source)))
        self.table.setItem(row, 3, QTableWidgetItem(self._display_status(item.status)))
        self.file_list.append(item)

    def _queue_scan_row(self, item: TimestampItem):
        self._scan_row_queue.append(item)
        self._ensure_ui_drain_timer()

    def _queue_process_update(self, row: int, status_text: str):
        self._process_update_queue.append((row, status_text))
        self._ensure_ui_drain_timer()

    def _ensure_ui_drain_timer(self):
        if not self._ui_drain_timer.isActive():
            self._ui_drain_timer.start()

    def _drain_ui_queues(self):
        scan_items: list[TimestampItem] = []
        while self._scan_row_queue and len(scan_items) < UI_ROW_DRAIN_COUNT:
            scan_items.append(self._scan_row_queue.popleft())
        if scan_items:
            self.table.setUpdatesEnabled(False)
            try:
                for item in scan_items:
                    self._append_scan_row(item)
            finally:
                self.table.setUpdatesEnabled(True)

        process_updates: list[tuple[int, str]] = []
        while self._process_update_queue and len(process_updates) < UI_ROW_DRAIN_COUNT:
            process_updates.append(self._process_update_queue.popleft())
        if process_updates:
            self.table.setUpdatesEnabled(False)
            try:
                for row, status_text in process_updates:
                    self._update_row_status(row, status_text)
            finally:
                self.table.setUpdatesEnabled(True)
                self.table.viewport().update()

        if self._scan_row_queue or self._process_update_queue:
            return

        self._ui_drain_timer.stop()
        if self._pending_drop_result is not None:
            result = self._pending_drop_result
            self._pending_drop_result = None
            self._apply_drop_finished(result)
        if self._pending_scan_result is not None:
            result = self._pending_scan_result
            self._pending_scan_result = None
            self._apply_scan_finished(result)
        if self._pending_process_result is not None:
            result = self._pending_process_result
            self._pending_process_result = None
            self._apply_processing_finished(result)

    def _drop_finished(self, added: int):
        self._pending_drop_result = added
        self._ensure_ui_drain_timer()

    def _apply_drop_finished(self, added: int):
        if added:
            self.progress.setValue(0)
            self._set_status_text("drop_added", added=added, count=len(self.file_list))
        else:
            self._set_status_text("drop_no_new")

    def _drop_thread_finished(self):
        self._drop_worker = None
        self._drop_thread = None

    def _scan_finished(self, count: int):
        self._pending_scan_result = count
        self._ensure_ui_drain_timer()

    def _apply_scan_finished(self, count: int):
        if count == 0:
            self._set_status_text("scan_none_status")
            self._notify(self.tr("invalid_folder_title"), self.tr("scan_none_status"), is_error=True)
            return
        self._set_status_text("scan_done_status", count=count)

    def start_processing(self):
        if self._is_busy():
            return
        if not self.file_list:
            self._notify(self.tr("cannot_start_title"), self.tr("cannot_start_content"), is_error=True)
            return

        self.is_processing = True
        self._process_update_queue.clear()
        self._pending_process_result = None
        self._ui_drain_timer.stop()
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
        self._process_worker.row_update.connect(self._queue_process_update)
        self._process_worker.progress_update.connect(self._update_progress)
        self._process_worker.finished.connect(self._processing_finished)
        self._process_worker.finished.connect(self._process_thread.quit)
        self._process_worker.finished.connect(self._process_worker.deleteLater)
        self._process_thread.finished.connect(self._process_thread.deleteLater)
        self._process_thread.start()

    def _update_row_status(self, row: int, status_text: str):
        if 0 <= row < self.table.rowCount():
            if 0 <= row < len(self.file_list):
                self.file_list[row].status = status_text
            self.table.setItem(row, 3, QTableWidgetItem(self._display_status(status_text)))
            self.table.scrollToItem(self.table.item(row, 3))

    def _update_progress(self, percent: int, text: str):
        self.progress.setValue(percent)
        self.status.setText(self._display_progress_text(text))
        self.progress.repaint()
        self.status.repaint()

    def _processing_finished(self, result: dict):
        self._pending_process_result = result
        self._ensure_ui_drain_timer()

    def _apply_processing_finished(self, result: dict):
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
