from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

from qframelesswindow import FramelessMainWindow

from PyQt6.QtCore import QParallelAnimationGroup, QPoint, QEasingCurve, QPropertyAnimation, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from main_gui import MainWindow as FlymeFixWindow
from merge_live_photo_gui import MainWindow as MergeLivePhotoWindow
from split_huawei_live_photo_gui import MainWindow as SplitHuaweiWindow


APP_TITLE = "AzureKiln Photo Tool"
APP_NAME = "AzureKilnPhotoTool"
APP_VERSION = "1.0.0"
GITHUB_URL = "https://github.com/azurekiln2333/azurekiln-photo-tool"
SUPPORTED_LANGUAGES = ("zh", "en")
TRANSLATIONS = {
    "zh": {
        "merge": "LivePhoto 合并",
        "split": "华为 LivePhoto 分离",
        "flyme": "Flyme LivePhoto 修复",
        "settings": "设置",
        "settings_title": "设置",
        "settings_subtitle": "统一管理语言、低频选项和应用信息",
        "language": "界面语言",
        "merge_settings": "LivePhoto 合并设置",
        "split_settings": "华为 LivePhoto 分离设置",
        "flyme_settings": "Flyme LivePhoto 修复设置",
        "scan_settings": "扫描",
        "exist_settings": "同名文件处理",
        "output_settings": "输出内容",
        "intermediate_settings": "中间产物",
        "about": "关于",
        "version": "版本",
        "github": "GitHub",
    },
    "en": {
        "merge": "Merge LivePhoto",
        "split": "Split Huawei LivePhoto",
        "flyme": "Fix Flyme LivePhoto",
        "settings": "Settings",
        "settings_title": "Settings",
        "settings_subtitle": "Manage language, low-frequency options, and app information",
        "language": "Language",
        "merge_settings": "Merge LivePhoto Settings",
        "split_settings": "Huawei LivePhoto Split Settings",
        "flyme_settings": "Flyme LivePhoto Fix Settings",
        "scan_settings": "Scan",
        "exist_settings": "Existing files",
        "output_settings": "Output content",
        "intermediate_settings": "Intermediate artifacts",
        "about": "About",
        "version": "Version",
        "github": "GitHub",
    },
}


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
            "qfluentwidgets is not installed. Install PyQt6-Fluent-Widgets; "
            "if you need Pro, install the Pro package documented by the project."
        ) from last_exc

    return {
        "BodyLabel": module.BodyLabel,
        "CardWidget": module.CardWidget,
        "ComboBox": module.ComboBox,
        "FluentIcon": module.FluentIcon,
        "FluentWindow": module.FluentWindow,
        "NavigationItemPosition": module.NavigationItemPosition,
        "SubtitleLabel": module.SubtitleLabel,
        "Theme": module.Theme,
        "setTheme": module.setTheme,
        "setThemeColor": module.setThemeColor,
        "is_pro": is_pro,
    }


FW = _import_fluent()
BodyLabel = FW["BodyLabel"]
CardWidget = FW["CardWidget"]
ComboBox = FW["ComboBox"]
FluentIcon = FW["FluentIcon"]
FluentWindow = FW["FluentWindow"]
NavigationItemPosition = FW["NavigationItemPosition"]
SubtitleLabel = FW["SubtitleLabel"]
Theme = FW["Theme"]
setTheme = FW["setTheme"]
setThemeColor = FW["setThemeColor"]
IS_PRO = FW["is_pro"]


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


class EmbeddedPage(QWidget):
    """Display only the content widget from an existing feature window."""

    def __init__(self, object_name: str, feature_window: FramelessMainWindow, parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.feature_window = feature_window

        content = feature_window.takeCentralWidget()
        if content is None:
            raise RuntimeError(f"{type(feature_window).__name__} has no central widget")

        feature_window.hide()
        feature_window.setParent(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(content)


class SettingsPage(QWidget):
    def __init__(self, feature_windows: list[FramelessMainWindow], parent=None):
        super().__init__(parent)
        self.setObjectName("settings")
        self.feature_windows = feature_windows
        self._button_groups: list[QButtonGroup] = []
        self._labels: dict[str, list[BodyLabel]] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.viewport().setStyleSheet("background: transparent;")

        content = QWidget(self.scroll_area)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 28, 28, 28)
        content_layout.setSpacing(16)

        self.title_label = SubtitleLabel(self)
        title_font = QFont("Microsoft YaHei", 16)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.subtitle_label = BodyLabel(self)
        self.subtitle_label.setStyleSheet("color: #667085;")

        self.language_card = CardWidget(self)
        card_layout = QHBoxLayout(self.language_card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(12)

        self.language_label = BodyLabel(self.language_card)
        self.language_combo = ComboBox(self.language_card)
        self.language_combo.addItem("中文", userData="zh")
        self.language_combo.addItem("English", userData="en")
        self.language_combo.setFixedWidth(180)

        card_layout.addWidget(self.language_label)
        card_layout.addStretch(1)
        card_layout.addWidget(self.language_combo)

        content_layout.addWidget(self.title_label)
        content_layout.addWidget(self.subtitle_label)
        content_layout.addWidget(self.language_card)
        self._build_feature_settings(content_layout)
        self._build_about_card(content_layout)
        content_layout.addStretch(1)

        self.scroll_area.setWidget(content)
        layout.addWidget(self.scroll_area)

    def _new_card(self, key: str, parent_layout: QVBoxLayout) -> QVBoxLayout:
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)

        title = BodyLabel(card)
        title.setStyleSheet("font-weight: 600;")
        self._labels.setdefault(key, []).append(title)
        card_layout.addWidget(title)
        parent_layout.addWidget(card)
        return card_layout

    def _section(self, layout: QVBoxLayout, key: str):
        label = BodyLabel(self)
        label.setStyleSheet("color: #667085; margin-top: 4px;")
        self._labels.setdefault(key, []).append(label)
        layout.addWidget(label)

    def _row(self, layout: QVBoxLayout, *widgets: QWidget):
        row = QHBoxLayout()
        row.setSpacing(12)
        for widget in widgets:
            row.addWidget(widget)
            widget.show()
        row.addStretch(1)
        layout.addLayout(row)

    def _group_radios(self, *buttons: QWidget):
        group = QButtonGroup(self)
        group.setExclusive(True)
        for button in buttons:
            if hasattr(button, "setAutoExclusive"):
                button.setAutoExclusive(False)
            group.addButton(button)
        self._button_groups.append(group)

    def _build_feature_settings(self, layout: QVBoxLayout):
        merge, split, flyme = self.feature_windows

        merge_layout = self._new_card("merge_settings", layout)
        self._section(merge_layout, "scan_settings")
        self._row(merge_layout, merge.include_subdirs_check)
        self._section(merge_layout, "exist_settings")
        self._group_radios(merge.live_skip_radio, merge.live_overwrite_radio)
        self._row(merge_layout, merge.live_exists_label, merge.live_skip_radio, merge.live_overwrite_radio)
        self._group_radios(merge.static_skip_radio, merge.static_overwrite_radio)
        self._row(merge_layout, merge.static_exists_label, merge.static_skip_radio, merge.static_overwrite_radio)
        self._row(merge_layout, merge.convert_static_heic_check)
        self._section(merge_layout, "intermediate_settings")
        self._row(merge_layout, merge.summary_trash_check)

        split_layout = self._new_card("split_settings", layout)
        self._section(split_layout, "scan_settings")
        self._row(split_layout, split.include_subdirs_check)
        self._section(split_layout, "exist_settings")
        self._group_radios(split.photo_skip_radio, split.photo_overwrite_radio)
        self._row(split_layout, split.photo_exists_label, split.photo_skip_radio, split.photo_overwrite_radio)
        self._group_radios(split.video_skip_radio, split.video_overwrite_radio)
        self._row(split_layout, split.video_exists_label, split.video_skip_radio, split.video_overwrite_radio)

        flyme_layout = self._new_card("flyme_settings", layout)
        self._section(flyme_layout, "scan_settings")
        self._row(flyme_layout, flyme.scan_subdirs_check)
        self._section(flyme_layout, "exist_settings")
        self._group_radios(flyme.skip_radio, flyme.overwrite_radio)
        self._row(flyme_layout, flyme.skip_radio, flyme.overwrite_radio)
        self._section(flyme_layout, "output_settings")
        self._row(
            flyme_layout,
            flyme.output_fixed_live_check,
            flyme.output_static_check,
            flyme.output_other_photo_check,
            flyme.output_other_file_check,
        )
        flyme_layout.addWidget(flyme.output_settings_note)
        flyme.output_settings_note.show()

    def _build_about_card(self, layout: QVBoxLayout):
        about_layout = self._new_card("about", layout)

        version_row = QHBoxLayout()
        version_row.setSpacing(12)
        self.version_label = BodyLabel(self)
        self.version_value = BodyLabel(APP_VERSION, self)
        version_row.addWidget(self.version_label)
        version_row.addStretch(1)
        version_row.addWidget(self.version_value)
        about_layout.addLayout(version_row)

        github_row = QHBoxLayout()
        github_row.setSpacing(12)
        self.github_label = BodyLabel(self)
        self.github_value = BodyLabel(GITHUB_URL, self)
        self.github_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        github_row.addWidget(self.github_label)
        github_row.addStretch(1)
        github_row.addWidget(self.github_value)
        about_layout.addLayout(github_row)

    def set_language(self, lang: str):
        text = TRANSLATIONS[lang]
        self.title_label.setText(text["settings_title"])
        self.subtitle_label.setText(text["settings_subtitle"])
        self.language_label.setText(text["language"])
        self.version_label.setText(text["version"])
        self.github_label.setText(text["github"])
        for key, labels in self._labels.items():
            for label in labels:
                label.setText(text[key])

        self.language_combo.blockSignals(True)
        try:
            for idx in range(self.language_combo.count()):
                if self.language_combo.itemData(idx) == lang:
                    self.language_combo.setCurrentIndex(idx)
                    break
        finally:
            self.language_combo.blockSignals(False)


class UnifiedMainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1440, 900)
        self.setMinimumSize(980, 680)
        self._fade_label: QLabel | None = None
        self._transition_group: QParallelAnimationGroup | None = None
        self._incoming_effect: QGraphicsOpacityEffect | None = None
        self._incoming_page: QWidget | None = None
        self._incoming_origin = QPoint()
        self._settings_path = _get_settings_path()
        self.lang = self._load_global_language()

        self._feature_windows = [
            MergeLivePhotoWindow(self, embedded=True),
            SplitHuaweiWindow(self, embedded=True),
            FlymeFixWindow(self, embedded=True),
        ]
        self.pages = [
            EmbeddedPage("merge", self._feature_windows[0], self),
            EmbeddedPage("split", self._feature_windows[1], self),
            EmbeddedPage("flyme", self._feature_windows[2], self),
        ]
        self.settings_page = SettingsPage(self._feature_windows, self)

        self.merge_item = self.addSubInterface(
            self.pages[0],
            _pick_icon("ADD_TO", "SAVE_COPY", "LINK"),
            TRANSLATIONS[self.lang]["merge"],
            NavigationItemPosition.TOP,
        )
        self.split_item = self.addSubInterface(
            self.pages[1],
            _pick_icon("CUT", "IMAGE_EXPORT", "FOLDER"),
            TRANSLATIONS[self.lang]["split"],
            NavigationItemPosition.TOP,
        )
        self.flyme_item = self.addSubInterface(
            self.pages[2],
            _pick_icon("DEVELOPER_TOOLS", "SYNC", "UPDATE"),
            TRANSLATIONS[self.lang]["flyme"],
            NavigationItemPosition.TOP,
        )
        self.settings_item = self.addSubInterface(
            self.settings_page,
            _pick_icon("SETTING", "DEVELOPER_TOOLS"),
            TRANSLATIONS[self.lang]["settings"],
            NavigationItemPosition.BOTTOM,
        )
        self.settings_page.language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.apply_language(self.lang, save=False)
        self._tune_animations()

    def switchTo(self, interface: QWidget):
        if interface is self.stackedWidget.currentWidget():
            return

        self._clear_transition()

        old_page_pixmap = self.stackedWidget.grab()
        self.stackedWidget.setCurrentWidget(interface, popOut=False)

        if old_page_pixmap.isNull():
            return

        offset = 22
        duration = 220
        curve = QEasingCurve.Type.OutCubic
        self._incoming_page = interface
        self._incoming_origin = interface.pos()

        self._fade_label = QLabel(self.stackedWidget)
        self._fade_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._fade_label.setGeometry(self.stackedWidget.rect())
        self._fade_label.setPixmap(old_page_pixmap)
        self._fade_label.setScaledContents(True)
        self._fade_label.show()
        self._fade_label.raise_()

        effect = QGraphicsOpacityEffect(self._fade_label)
        effect.setOpacity(1.0)
        self._fade_label.setGraphicsEffect(effect)

        self._incoming_effect = QGraphicsOpacityEffect(interface)
        self._incoming_effect.setOpacity(0.0)
        interface.setGraphicsEffect(self._incoming_effect)
        interface.move(self._incoming_origin + QPoint(offset, 0))

        old_fade = QPropertyAnimation(effect, b"opacity", self)
        old_fade.setDuration(duration)
        old_fade.setStartValue(1.0)
        old_fade.setEndValue(0.0)
        old_fade.setEasingCurve(curve)

        old_slide = QPropertyAnimation(self._fade_label, b"pos", self)
        old_slide.setDuration(duration)
        old_slide.setStartValue(self._fade_label.pos())
        old_slide.setEndValue(self._fade_label.pos() + QPoint(-10, 0))
        old_slide.setEasingCurve(curve)

        new_fade = QPropertyAnimation(self._incoming_effect, b"opacity", self)
        new_fade.setDuration(duration)
        new_fade.setStartValue(0.0)
        new_fade.setEndValue(1.0)
        new_fade.setEasingCurve(curve)

        new_slide = QPropertyAnimation(interface, b"pos", self)
        new_slide.setDuration(duration)
        new_slide.setStartValue(self._incoming_origin + QPoint(offset, 0))
        new_slide.setEndValue(self._incoming_origin)
        new_slide.setEasingCurve(curve)

        self._transition_group = QParallelAnimationGroup(self)
        for animation in (old_fade, old_slide, new_fade, new_slide):
            self._transition_group.addAnimation(animation)
        self._transition_group.finished.connect(self._clear_transition)
        self._transition_group.start()

    def _tune_animations(self):
        self.navigationInterface.panel.setIndicatorAnimationEnabled(False)
        self.stackedWidget.setAnimationEnabled(False)

    def _load_global_language(self) -> str:
        if not self._settings_path.exists():
            return "zh"
        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except Exception:
            return "zh"
        lang = data.get("language")
        return lang if lang in SUPPORTED_LANGUAGES else "zh"

    def _save_global_settings(self):
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            self._settings_path.write_text(
                json.dumps({"language": self.lang}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _on_language_changed(self, _index: int):
        lang = self.settings_page.language_combo.currentData()
        if lang in SUPPORTED_LANGUAGES:
            self.apply_language(lang)

    def apply_language(self, lang: str, save: bool = True):
        if lang not in SUPPORTED_LANGUAGES:
            return

        self.lang = lang
        text = TRANSLATIONS[lang]
        self.merge_item.setText(text["merge"])
        self.merge_item.setToolTip(text["merge"])
        self.split_item.setText(text["split"])
        self.split_item.setToolTip(text["split"])
        self.flyme_item.setText(text["flyme"])
        self.flyme_item.setToolTip(text["flyme"])
        self.settings_item.setText(text["settings"])
        self.settings_item.setToolTip(text["settings"])
        self.settings_page.set_language(lang)

        for feature_window in self._feature_windows:
            self._apply_feature_language(feature_window, lang)

        if save:
            self._save_global_settings()

    def _apply_feature_language(self, feature_window: FramelessMainWindow, lang: str):
        if hasattr(feature_window, "lang"):
            feature_window.lang = lang
        combo = getattr(feature_window, "language_combo", None)
        if combo is not None:
            combo.blockSignals(True)
            try:
                for idx in range(combo.count()):
                    if combo.itemData(idx) == lang:
                        combo.setCurrentIndex(idx)
                        break
            finally:
                combo.blockSignals(False)

        apply_language = getattr(feature_window, "_apply_language", None)
        if callable(apply_language):
            apply_language()

    def _clear_transition(self):
        if self._transition_group is not None:
            self._transition_group.stop()
            self._transition_group.deleteLater()
            self._transition_group = None

        if self._fade_label is not None:
            self._fade_label.deleteLater()
            self._fade_label = None

        if self._incoming_page is not None:
            self._incoming_page.move(self._incoming_origin)
            self._incoming_page.setGraphicsEffect(None)
            self._incoming_page = None
            self._incoming_effect = None


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 10))
    setThemeColor("#1677FF")
    setTheme(Theme.LIGHT)

    win = UnifiedMainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
