#!/usr/bin/env python3
from __future__ import annotations

import ctypes
import importlib
import io
import json
import os
import shutil
import struct
import sys
from datetime import datetime
from pathlib import Path

from PIL import ExifTags, Image
from qframelesswindow import FramelessMainWindow, StandardTitleBar

from merge_live_photo_translations import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, TRANSLATIONS

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

# Optional HEIC support
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HAS_HEIC = True
except ImportError:
    HAS_HEIC = False

# Optional recycle-bin support
try:
    from send2trash import send2trash

    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False

APP_NAME = "MergeLivePhotoGUI"
XMP_IDENTIFIER = b"http://ns.adobe.com/xap/1.0/\x00"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".heic", ".heif")
VIDEO_SUFFIXES = (".mp4", ".mov")
EXIF_TIMESTAMP_TAGS = ("DateTimeOriginal", "DateTimeDigitized", "DateTime")


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


def _capture_timestamp_from_image(img_path: Path) -> float | None:
    try:
        with Image.open(img_path) as img:
            exif = img.getexif()
            if not exif:
                return None

            for tag_name in EXIF_TIMESTAMP_TAGS:
                tag_id = next((key for key, name in ExifTags.TAGS.items() if name == tag_name), None)
                if tag_id is None:
                    continue
                raw_value = exif.get(tag_id)
                if not raw_value:
                    continue
                if isinstance(raw_value, bytes):
                    raw_value = raw_value.decode("utf-8", "ignore")
                try:
                    return datetime.strptime(str(raw_value), "%Y:%m:%d %H:%M:%S").timestamp()
                except ValueError:
                    continue
    except Exception:
        return None
    return None


def _apply_output_timestamp(output_path: Path, source_path: Path):
    ts = _capture_timestamp_from_image(source_path)
    if ts is None:
        try:
            stat = os.stat(source_path)
            ts = stat.st_mtime
        except Exception:
            return

    try:
        os.utime(output_path, (ts, ts))
    except Exception:
        pass


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
            "Install it with: pip install PyQt6-Fluent-Widgets\n"
            "If you need Pro, install the Pro package documented by the project."
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
IS_PRO = FW["is_pro"]


def _pick_icon(*names: str):
    for name in names:
        icon = getattr(FluentIcon, name, None)
        if icon is not None:
            return icon
    return FluentIcon.APPLICATION


def find_jpeg_end(data: bytes) -> int:
    if data[:2] != b"\xff\xd8":
        raise ValueError("不是有效的 JPEG 文件")
    eoi_positions = []
    pos = 0
    while True:
        pos = data.find(b"\xff\xd9", pos)
        if pos == -1:
            break
        eoi_positions.append(pos)
        pos += 2
    if not eoi_positions:
        raise ValueError("鏈壘鍒?JPEG EOI 鏍囪")
    for eoi in reversed(eoi_positions):
        try:
            img = Image.open(io.BytesIO(data[: eoi + 2]))
            img.verify()
            return eoi + 2
        except Exception:
            continue
    return eoi_positions[-1] + 2


def strip_existing_xmp(jpeg_data: bytes) -> bytes:
    if jpeg_data[:2] != b"\xff\xd8":
        raise ValueError("不是有效的 JPEG 文件")
    result = bytearray(jpeg_data[:2])
    pos = 2
    while pos < len(jpeg_data):
        if jpeg_data[pos] != 0xFF:
            result += jpeg_data[pos:]
            break
        marker = jpeg_data[pos : pos + 2]
        if len(marker) < 2:
            result += jpeg_data[pos:]
            break
        marker_code = struct.unpack(">H", marker)[0]
        if marker_code in (0xFFD8, 0xFFD9):
            result += marker
            pos += 2
            continue
        if marker_code == 0xFFDA:
            result += jpeg_data[pos:]
            break
        seg_len = struct.unpack(">H", jpeg_data[pos + 2 : pos + 4])[0]
        seg_data = jpeg_data[pos + 4 : pos + 2 + seg_len]
        if marker_code == 0xFFE1 and seg_data.startswith(XMP_IDENTIFIER):
            pos += 2 + seg_len
            continue
        result += marker + jpeg_data[pos + 2 : pos + 2 + seg_len]
        pos += 2 + seg_len
    return bytes(result)


def _is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


def _find_matching_video(img_path: Path) -> Path | None:
    for suffix in VIDEO_SUFFIXES:
        for candidate_suffix in (suffix, suffix.upper()):
            video_path = img_path.with_suffix(candidate_suffix)
            if video_path.exists():
                return video_path
    return None


def _make_task(img_path: Path, base_dir: Path | None = None) -> dict:
    video_path = _find_matching_video(img_path)
    is_heic = img_path.suffix.lower() in (".heic", ".heif")
    if is_heic and not HAS_HEIC:
        status = "status_missing_heif"
    else:
        status = "status_pending"

    if base_dir is not None:
        try:
            rel_path = img_path.relative_to(base_dir)
        except ValueError:
            rel_path = Path(img_path.name)
    else:
        rel_path = Path(img_path.name)

    return {
        "img_path": img_path,
        "mp4_path": video_path,
        "rel_path": rel_path,
        "is_heic": is_heic,
        "is_heic_error": is_heic and not HAS_HEIC,
        "has_mp4_text": "yes" if video_path is not None else "no",
        "status": status,
    }


def build_xmp_app1(mp4_size: int) -> bytes:
    xmp_content = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 5.1.0-jc003">\n'
        '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '    <rdf:Description rdf:about=""\n'
        '        xmlns:GCamera="http://ns.google.com/photos/1.0/camera/"\n'
        '        xmlns:Container="http://ns.google.com/photos/1.0/container/"\n'
        '        xmlns:Item="http://ns.google.com/photos/1.0/container/item/"\n'
        '      GCamera:MotionPhoto="1"\n'
        '      GCamera:MotionPhotoVersion="1"\n'
        '      GCamera:MotionPhotoPresentationTimestampUs="-1">\n'
        '      <Container:Directory>\n'
        '        <rdf:Seq>\n'
        '          <rdf:li rdf:parseType="Resource">\n'
        '            <Container:Item\n'
        '              Item:Mime="image/jpeg"\n'
        '              Item:Semantic="Primary"\n'
        '              Item:Length="0"\n'
        '              Item:Padding="0"/>\n'
        '          </rdf:li>\n'
        '          <rdf:li rdf:parseType="Resource">\n'
        '            <Container:Item\n'
        '              Item:Mime="video/mp4"\n'
        '              Item:Semantic="MotionPhoto"\n'
        f'              Item:Length="{mp4_size}"\n'
        '              Item:Padding="0"/>\n'
        '          </rdf:li>\n'
        '        </rdf:Seq>\n'
        '      </Container:Directory>\n'
        '    </rdf:Description>\n'
        '  </rdf:RDF>\n'
        '</x:xmpmeta>'
    )
    payload = XMP_IDENTIFIER + xmp_content.encode("utf-8")
    length = len(payload) + 2
    return b"\xff\xe1" + struct.pack(">H", length) + payload


def make_live_photo(img_path: str, mp4_path: str, output_path: str):
    img_path_lower = img_path.lower()
    if img_path_lower.endswith(".heic") or img_path_lower.endswith(".heif"):
        if not HAS_HEIC:
            raise ImportError("鏈畨瑁?pillow-heif")
        img = Image.open(img_path)
        exif = img.info.get("exif", b"")
        if img.mode != "RGB":
            img = img.convert("RGB")
        out_io = io.BytesIO()
        img.save(out_io, format="JPEG", quality=95, exif=exif)
        jpg_data = out_io.getvalue()
    else:
        with open(img_path, "rb") as f:
            jpg_data = f.read()

    with open(mp4_path, "rb") as f:
        mp4_data = f.read()

    jpeg_end = find_jpeg_end(jpg_data)
    clean_jpeg = jpg_data[:jpeg_end]
    stripped_jpeg = strip_existing_xmp(clean_jpeg)

    mp4_size = len(mp4_data)
    xmp_segment = build_xmp_app1(mp4_size)

    result = bytearray()
    result += stripped_jpeg[:2]
    result += xmp_segment
    result += stripped_jpeg[2:]
    result += mp4_data

    with open(output_path, "wb") as f:
        f.write(bytes(result))

    _apply_output_timestamp(Path(output_path), Path(img_path))


class ScanWorker(QObject):
    row_ready = pyqtSignal(dict)
    finished = pyqtSignal(int)

    def __init__(self, input_dir: Path, recursive: bool):
        super().__init__()
        self.input_dir = input_dir
        self.recursive = recursive

    def run(self):
        img_files_set: set[Path] = set()
        iterator = self.input_dir.rglob("*") if self.recursive else self.input_dir.glob("*")
        img_files_set.update(path for path in iterator if _is_image_file(path))

        img_files = sorted(img_files_set)
        for img_path in img_files:
            video_path = _find_matching_video(img_path)
            mp4_path = img_path.with_suffix(".mp4")
            if not mp4_path.exists():
                mp4_path = img_path.with_suffix(".MP4")
            if video_path is not None:
                mp4_path = video_path

            is_heic = img_path.suffix.lower() in (".heic", ".heif")
            if is_heic and not HAS_HEIC:
                status = "status_missing_heif"
            else:
                status = "status_pending"

            try:
                rel_path = img_path.relative_to(self.input_dir)
            except ValueError:
                rel_path = Path(img_path.name)

            self.row_ready.emit(
                {
                    "img_path": img_path,
                    "mp4_path": mp4_path if mp4_path.exists() else None,
                    "rel_path": rel_path,
                    "is_heic": is_heic,
                    "is_heic_error": is_heic and not HAS_HEIC,
                    "has_mp4_text": "yes" if mp4_path.exists() else "no",
                    "status": status,
                }
            )

        self.finished.emit(len(img_files))


class ProcessWorker(QObject):
    row_update = pyqtSignal(int, str)
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, tasks: list[dict], options: dict):
        super().__init__()
        self.tasks = tasks
        self.options = options

    def run(self):
        out_path = Path(self.options["output_dir"])
        out_path.mkdir(parents=True, exist_ok=True)

        if out_path.parent == out_path:
            static_out_path = out_path / "Static_Photos"
            summary_out_path = out_path / "All_Processed_Summary"
        else:
            static_out_path = out_path.parent / "Static_Photos"
            summary_out_path = out_path.parent / "All_Processed_Summary"

        if self.options["copy_static"]:
            static_out_path.mkdir(parents=True, exist_ok=True)

        total = len(self.tasks)
        success_count = 0
        live_exist_skip_count = 0
        static_copy_count = 0
        static_exist_skip_count = 0
        fail_count = 0
        error_skip_count = 0
        summary_success = 0
        summary_failed = 0
        files_to_summarize: list[tuple[Path, Path]] = []

        for index, task in enumerate(self.tasks):
            img_path = task["img_path"]
            mp4_path = task["mp4_path"]
            rel_path = task["rel_path"]
            is_heic = task["is_heic"]
            is_heic_error = task["is_heic_error"]

            progress_percent = int(((index + 1) / total) * 100) if total else 0

            if is_heic_error:
                error_skip_count += 1
                self.row_update.emit(index, "status_skip_missing_heif")
                self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")
                continue

            if mp4_path is None:
                if self.options["copy_static"]:
                    try:
                        convert_to_jpg = is_heic and self.options["convert_static_heic"]
                        final_rel_path = rel_path.with_suffix(".jpg") if convert_to_jpg else rel_path
                        target_static_file = static_out_path / final_rel_path
                        target_static_file.parent.mkdir(parents=True, exist_ok=True)

                        if target_static_file.exists() and self.options["static_exist_action"] == "skip":
                            static_exist_skip_count += 1
                            self.row_update.emit(index, "status_static_exists")
                            files_to_summarize.append((target_static_file, final_rel_path))
                        else:
                            if convert_to_jpg:
                                img = Image.open(img_path)
                                exif = img.info.get("exif", b"")
                                if img.mode != "RGB":
                                    img = img.convert("RGB")
                                img.save(target_static_file, format="JPEG", quality=95, exif=exif)
                                _apply_output_timestamp(target_static_file, img_path)
                                status_text = "status_static_converted"
                            else:
                                shutil.copy2(img_path, target_static_file)
                                _apply_output_timestamp(target_static_file, img_path)
                                status_text = "status_static_copied"

                            static_copy_count += 1
                            self.row_update.emit(index, status_text)
                            files_to_summarize.append((target_static_file, final_rel_path))
                    except Exception as exc:
                        fail_count += 1
                        self.row_update.emit(index, f"status_static_failed|{str(exc)[:28]}")
                else:
                    self.row_update.emit(index, "status_skip_no_video")
            else:
                output_file = out_path / rel_path.with_suffix(".jpg")
                output_file.parent.mkdir(parents=True, exist_ok=True)

                if output_file.exists() and self.options["live_exist_action"] == "skip":
                    live_exist_skip_count += 1
                    self.row_update.emit(index, "status_live_exists")
                    files_to_summarize.append((output_file, rel_path.with_suffix(".jpg")))
                else:
                    self.row_update.emit(index, "status_merging")
                    try:
                        make_live_photo(str(img_path), str(mp4_path), str(output_file))
                        _apply_output_timestamp(output_file, img_path)

                        success_count += 1
                        self.row_update.emit(index, "status_merge_success")
                        files_to_summarize.append((output_file, rel_path.with_suffix(".jpg")))
                    except Exception as exc:
                        fail_count += 1
                        self.row_update.emit(index, f"status_merge_failed|{str(exc)[:28]}")

            self.progress_update.emit(progress_percent, f"progress|{index + 1}|{total}")

        if self.options["do_summary"] and files_to_summarize:
            self.progress_update.emit(100, "status_summarizing")
            for processed_file, rel_p in files_to_summarize:
                try:
                    dest_file = summary_out_path / rel_p
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(processed_file, dest_file)
                    summary_success += 1
                    if self.options["summary_trash"]:
                        send2trash(str(processed_file))
                except Exception:
                    summary_failed += 1

        self.finished.emit(
            {
                "success_count": success_count,
                "live_exist_skip_count": live_exist_skip_count,
                "static_copy_count": static_copy_count,
                "static_exist_skip_count": static_exist_skip_count,
                "fail_count": fail_count,
                "error_skip_count": error_skip_count,
                "summary_success": summary_success,
                "summary_failed": summary_failed,
                "out_path": str(out_path),
                "static_out_path": str(static_out_path),
                "summary_out_path": str(summary_out_path),
                "did_summary": self.options["do_summary"],
                "copy_static": self.options["copy_static"],
                "summary_trash": self.options["summary_trash"],
            }
        )


class MainWindow(FramelessMainWindow):
    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("Merge Live Photo")
        self._title_bar_height = 36
        if not self._embedded:
            self.resize(1280, 860)
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
        header_layout.addLayout(language_row)

        path_card = CardWidget(self)
        path_layout = QVBoxLayout(path_card)
        path_layout.setContentsMargins(16, 14, 16, 14)
        path_layout.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.input_label = BodyLabel(self.tr("source_dir"), self)
        self.input_edit = LineEdit(self)
        self.input_edit.setReadOnly(True)
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
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText(self.tr("output_placeholder"))
        self.btn_output = PushButton(self.tr("choose_output"), self)
        self.btn_output.setIcon(_pick_icon("SAVE", "DOWNLOAD"))
        self.btn_output.clicked.connect(self.browse_output)
        row2.addWidget(self.output_label)
        row2.addWidget(self.output_edit, 1)
        row2.addWidget(self.btn_output)

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

        output_card = CardWidget(self)
        output_layout = QVBoxLayout(output_card)
        output_layout.setContentsMargins(16, 14, 16, 14)
        output_layout.setSpacing(10)

        self.output_settings_label = BodyLabel(self.tr("processing_options"), self)
        self.output_settings_label.setStyleSheet("font-weight: 600;")
        output_layout.addWidget(self.output_settings_label)

        live_row = QHBoxLayout()
        live_row.setSpacing(12)
        self.live_exists_label = BodyLabel(self.tr("live_exists"), self)
        live_row.addWidget(self.live_exists_label)
        self.live_skip_radio = RadioButton(self.tr("skip"), self)
        self.live_overwrite_radio = RadioButton(self.tr("overwrite"), self)
        self.live_skip_radio.setChecked(True)
        live_row.addWidget(self.live_skip_radio)
        live_row.addWidget(self.live_overwrite_radio)
        live_row.addStretch(1)
        output_layout.addLayout(live_row)

        static_row = QHBoxLayout()
        static_row.setSpacing(12)
        self.copy_static_check = CheckBox(self.tr("copy_static"), self)
        self.copy_static_check.setChecked(True)
        self.copy_static_check.toggled.connect(self.toggle_static_options)
        static_row.addWidget(self.copy_static_check)
        self.static_exists_label = BodyLabel(self.tr("static_exists"), self)
        static_row.addWidget(self.static_exists_label)
        self.static_skip_radio = RadioButton(self.tr("skip"), self)
        self.static_overwrite_radio = RadioButton(self.tr("overwrite"), self)
        self.static_skip_radio.setChecked(True)
        static_row.addWidget(self.static_skip_radio)
        static_row.addWidget(self.static_overwrite_radio)
        static_row.addStretch(1)
        output_layout.addLayout(static_row)

        heic_row = QHBoxLayout()
        heic_row.setSpacing(12)
        self.convert_static_heic_check = CheckBox(self.tr("convert_static_heic"), self)
        self.convert_static_heic_check.setChecked(True)
        heic_row.addWidget(self.convert_static_heic_check)
        heic_row.addStretch(1)
        output_layout.addLayout(heic_row)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(12)
        self.do_summary_check = CheckBox(self.tr("do_summary"), self)
        self.do_summary_check.toggled.connect(self.toggle_summary_options)
        self.summary_trash_check = CheckBox(self.tr("summary_trash"), self)
        self.summary_trash_check.setEnabled(False)
        summary_row.addWidget(self.do_summary_check)
        summary_row.addWidget(self.summary_trash_check)
        summary_row.addStretch(1)
        output_layout.addLayout(summary_row)

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
        self.table.setColumnCount(3)
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
        self.btn_start = PrimaryPushButton(self.tr("start_merge"), self)
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
        outer.addWidget(option_card)
        outer.addWidget(output_card)
        outer.addWidget(table_card, 1)
        outer.addWidget(action_card)
        outer.addWidget(foot_card)

        self._init_default_output_dir()
        self._load_settings()
        self.toggle_static_options()
        self.toggle_summary_options()
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
        return [self.tr("table_image"), self.tr("table_video"), self.tr("table_status")]

    def _display_status(self, status: str) -> str:
        if status.startswith("status_static_failed|"):
            return self.tr("status_static_failed", error=status.split("|", 1)[1])
        if status.startswith("status_merge_failed|"):
            return self.tr("status_merge_failed", error=status.split("|", 1)[1])
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
        self.live_exists_label.setText(self.tr("live_exists"))
        self.live_skip_radio.setText(self.tr("skip"))
        self.live_overwrite_radio.setText(self.tr("overwrite"))
        self.copy_static_check.setText(self.tr("copy_static"))
        self.static_exists_label.setText(self.tr("static_exists"))
        self.static_skip_radio.setText(self.tr("skip"))
        self.static_overwrite_radio.setText(self.tr("overwrite"))
        self.convert_static_heic_check.setText(self.tr("convert_static_heic"))
        self.do_summary_check.setText(self.tr("do_summary"))
        self.summary_trash_check.setText(self.tr("summary_trash"))
        self.drop_hint.setText(self.tr("drop_hint"))
        self.table.setHorizontalHeaderLabels(self._table_headers())
        self.btn_scan.setText(self.tr("rescan"))
        self.btn_clear.setText(self.tr("clear_list"))
        self.btn_start.setText(self.tr("start_merge"))
        self._set_status_text(self._last_status_key, **self._last_status_kwargs)
        self._refresh_table_language()

    def _refresh_table_language(self):
        for row, task in enumerate(self.file_list):
            video_item = self.table.item(row, 1)
            status_item = self.table.item(row, 2)
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
        if is_error:
            InfoBar.error(
                title=title,
                content=content,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2600,
                parent=self,
            )
            return

        InfoBar.success(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=1800,
            parent=self,
        )

    def _init_default_output_dir(self):
        pics_dir = _get_windows_pictures_dir() or (Path.home() / "Pictures")
        base = pics_dir / "MergeLivePhoto_output"
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
            "live_exist_action": "skip" if self.live_skip_radio.isChecked() else "overwrite",
            "copy_static": self.copy_static_check.isChecked(),
            "static_exist_action": "skip" if self.static_skip_radio.isChecked() else "overwrite",
            "convert_static_heic": self.convert_static_heic_check.isChecked(),
            "do_summary": self.do_summary_check.isChecked(),
            "summary_trash": self.summary_trash_check.isChecked(),
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
            self.live_skip_radio.setChecked(data.get("live_exist_action", "skip") != "overwrite")
            self.live_overwrite_radio.setChecked(data.get("live_exist_action", "skip") == "overwrite")
            self.copy_static_check.setChecked(bool(data.get("copy_static", True)))
            self.static_skip_radio.setChecked(data.get("static_exist_action", "skip") != "overwrite")
            self.static_overwrite_radio.setChecked(data.get("static_exist_action", "skip") == "overwrite")
            self.convert_static_heic_check.setChecked(bool(data.get("convert_static_heic", True)))
            self.do_summary_check.setChecked(bool(data.get("do_summary", False)))
            self.summary_trash_check.setChecked(bool(data.get("summary_trash", False)))
        finally:
            self._suspend_settings_save = False

    def browse_input(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("dialog_choose_source"))
        if not folder:
            return
        self.input_edit.setText(folder)
        if not self.output_edit.text().strip():
            self.output_edit.setText(str(Path(folder) / "LivePhotos_Output"))
        else:
            self.output_edit.setText(str(Path(folder) / "LivePhotos_Output"))
        self._save_settings()
        self.scan_files()

    def browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("dialog_choose_output"))
        if not folder:
            return
        Path(folder).mkdir(parents=True, exist_ok=True)
        self.output_edit.setText(folder)
        self._save_settings()

    def toggle_static_options(self):
        state = self.copy_static_check.isChecked()
        self.static_skip_radio.setEnabled(state)
        self.static_overwrite_radio.setEnabled(state)
        self.convert_static_heic_check.setEnabled(state)
        self._save_settings()

    def toggle_summary_options(self):
        state = self.do_summary_check.isChecked()
        self.summary_trash_check.setEnabled(state)
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
                    self.output_edit.setText(str(first_dir / "LivePhotos_Output"))
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
        self._scan_worker = ScanWorker(input_dir, self.include_subdirs_check.isChecked())
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
        self.table.setItem(row, 1, QTableWidgetItem(self.tr(task["has_mp4_text"])))
        self.table.setItem(row, 2, QTableWidgetItem(self._display_status(task["status"])))
        self.file_list.append(task)

    def _scan_finished(self, count: int):
        if count == 0:
            self._set_status_text("scan_none_status")
            self._notify(self.tr("scan_complete_title"), self.tr("scan_none_content"), is_error=True)
            return
        self._set_status_text("scan_done_status", count=count)
        self._notify(self.tr("scan_complete_title"), self.tr("scan_done_content", count=count))

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

        if self.do_summary_check.isChecked() and self.summary_trash_check.isChecked() and not HAS_SEND2TRASH:
            self._notify(
                self.tr("missing_dependency_title"),
                self.tr("missing_send2trash"),
                is_error=True,
            )
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
            "live_exist_action": "skip" if self.live_skip_radio.isChecked() else "overwrite",
            "copy_static": self.copy_static_check.isChecked(),
            "static_exist_action": "skip" if self.static_skip_radio.isChecked() else "overwrite",
            "convert_static_heic": self.convert_static_heic_check.isChecked(),
            "do_summary": self.do_summary_check.isChecked(),
            "summary_trash": self.summary_trash_check.isChecked(),
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
            self.table.setItem(row, 2, QTableWidgetItem(self._display_status(status_text)))
            self.table.scrollToItem(self.table.item(row, 2))

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
            live=result["success_count"],
            static=result["static_copy_count"],
        )

        msg = self.tr(
            "task_done_message",
            success=result["success_count"],
            live_skip=result["live_exist_skip_count"],
            static_copy=result["static_copy_count"],
            static_skip=result["static_exist_skip_count"],
            failed=result["fail_count"] + result["error_skip_count"],
        )

        if result["did_summary"]:
            msg += self.tr(
                "summary_result",
                success=result["summary_success"],
                failed=result["summary_failed"],
                path=result["summary_out_path"],
            )
            if result["summary_trash"]:
                msg += self.tr("summary_trash_done")
        else:
            msg += self.tr("output_result", path=result["out_path"])
            if result["copy_static"]:
                msg += self.tr("static_output_result", path=result["static_out_path"])

        QMessageBox.information(self, self.tr("task_done_title"), msg)
        self._notify(self.tr("task_done_title"), self.tr("process_done_notice", count=result["success_count"]))


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
