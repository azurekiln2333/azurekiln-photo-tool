from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QEvent, QObject, QItemSelectionModel, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QAbstractItemView, QMenu, QWidget

if sys.platform == "win32":
    try:
        import win32con  # type: ignore
        import win32gui  # type: ignore
        from win32com.shell import shell, shellcon  # type: ignore

        HAS_SHELL_CONTEXT = True
    except Exception:
        HAS_SHELL_CONTEXT = False
else:
    HAS_SHELL_CONTEXT = False


LABELS = {
    "zh": {
        "open": "打开",
        "open_folder": "打开所在目录",
        "copy_files": "复制文件",
        "cut_files": "剪切文件",
        "copy_path": "复制路径",
        "system_context_menu": "系统右键菜单...",
    },
    "en": {
        "open": "Open",
        "open_folder": "Show in folder",
        "copy_files": "Copy files",
        "cut_files": "Cut files",
        "copy_path": "Copy path",
        "system_context_menu": "System context menu...",
    },
}


PathProvider = Callable[[int, list[int]], list[Path]]
LanguageProvider = Callable[[], str]


def _label(lang: str, key: str) -> str:
    return LABELS.get(lang, LABELS["zh"]).get(key, key)


def _selected_rows(table) -> list[int]:
    model = table.selectionModel()
    if model is None:
        return []
    return sorted({index.row() for index in model.selectedRows()})


def _row_at(table, pos) -> int:
    if hasattr(table, "rowAt"):
        return int(table.rowAt(pos.y()))
    index = table.indexAt(pos)
    return index.row() if index.isValid() else -1


def _select_row(table, row: int):
    table.clearSelection()
    model = table.model()
    if model is None:
        return
    index = model.index(row, 0)
    if not index.isValid():
        return
    flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    table.selectionModel().select(index, flags)
    if hasattr(table, "setCurrentCell"):
        table.setCurrentCell(row, 0)
    else:
        table.setCurrentIndex(index)


def _copy_paths_text(paths: list[Path]):
    QApplication.clipboard().setText("\n".join(str(path) for path in paths))


def _set_file_clipboard(owner: QWidget, paths: list[Path], cut: bool = False) -> bool:
    if not paths:
        return False
    if sys.platform != "win32":
        _copy_paths_text(paths)
        return True

    class _Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class _DropFiles(ctypes.Structure):
        _fields_ = [
            ("pFiles", ctypes.c_uint32),
            ("pt", _Point),
            ("fNC", ctypes.c_int),
            ("fWide", ctypes.c_int),
        ]

    def _alloc_block(raw: bytes):
        kernel32 = ctypes.windll.kernel32
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
        handle = kernel32.GlobalAlloc(0x0042, len(raw))
        if not handle:
            raise MemoryError("GlobalAlloc failed")
        locked = kernel32.GlobalLock(handle)
        if not locked:
            kernel32.GlobalFree(handle)
            raise MemoryError("GlobalLock failed")
        try:
            ctypes.memmove(locked, raw, len(raw))
        finally:
            kernel32.GlobalUnlock(handle)
        return handle

    try:
        abs_paths = [str(path.resolve()) for path in paths]
    except Exception:
        abs_paths = [str(path) for path in paths]
    file_list = ("\0".join(abs_paths) + "\0\0").encode("utf-16le")
    header = _DropFiles(pFiles=ctypes.sizeof(_DropFiles), pt=_Point(0, 0), fNC=0, fWide=1)
    payload = ctypes.string_at(ctypes.byref(header), ctypes.sizeof(header)) + file_list
    effect = (2 if cut else 1).to_bytes(4, "little")
    text = ("\r\n".join(abs_paths) + "\0").encode("utf-16le")

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    cf_hdrop = 15
    cf_unicode_text = 13
    preferred_effect = user32.RegisterClipboardFormatW("Preferred DropEffect")
    drop_handle = _alloc_block(payload)
    effect_handle = _alloc_block(effect)
    text_handle = _alloc_block(text)
    try:
        if not user32.OpenClipboard(int(owner.winId())):
            return False
        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(cf_hdrop, drop_handle):
                return False
            drop_handle = None
            if preferred_effect and user32.SetClipboardData(preferred_effect, effect_handle):
                effect_handle = None
            if user32.SetClipboardData(cf_unicode_text, text_handle):
                text_handle = None
            return True
        finally:
            user32.CloseClipboard()
    finally:
        if drop_handle:
            kernel32.GlobalFree(drop_handle)
        if effect_handle:
            kernel32.GlobalFree(effect_handle)
        if text_handle:
            kernel32.GlobalFree(text_handle)


def _show_explorer_context_menu(owner: QWidget, file_paths: list[Path], global_pos) -> bool:
    if not HAS_SHELL_CONTEXT or not file_paths:
        return False
    try:
        owner_hwnd = int(owner.window().winId())
        folder = shell.SHGetDesktopFolder()
        abs_paths = [str(path.resolve()) for path in file_paths]
        parent_dirs = {str(Path(path).parent) for path in abs_paths}
        if len(parent_dirs) != 1:
            return False
        parent_dir = str(Path(abs_paths[0]).parent)

        parent_pidl = shell.SHParseDisplayName(parent_dir, 0)[0]
        parent_folder = folder.BindToObject(parent_pidl, None, shell.IID_IShellFolder)
        child_pidls = [
            parent_folder.ParseDisplayName(0, None, Path(path).name)[1]
            for path in abs_paths
        ]
        _inout, cm = parent_folder.GetUIObjectOf(
            owner_hwnd,
            child_pidls,
            shell.IID_IContextMenu,
            0,
            shell.IID_IContextMenu,
        )

        hmenu = win32gui.CreatePopupMenu()
        try:
            id_cmd_first = 1
            cm.QueryContextMenu(hmenu, 0, id_cmd_first, 0x7FFF, shellcon.CMF_NORMAL)
            win32gui.SetForegroundWindow(owner_hwnd)
            cmd = win32gui.TrackPopupMenu(
                hmenu,
                win32con.TPM_LEFTALIGN | win32con.TPM_RETURNCMD | win32con.TPM_RIGHTBUTTON,
                global_pos.x(),
                global_pos.y(),
                0,
                owner_hwnd,
                None,
            )
        finally:
            win32gui.DestroyMenu(hmenu)
        if cmd:
            cm.InvokeCommand((0, owner_hwnd, cmd - id_cmd_first, None, parent_dir, 0, 0, 0))
        else:
            win32gui.PostMessage(owner_hwnd, win32con.WM_NULL, 0, 0)
        return True
    except Exception:
        return False


class FileContextMenu(QObject):
    def __init__(
        self,
        table,
        owner: QWidget,
        path_provider: PathProvider,
        language_provider: LanguageProvider | None = None,
    ):
        super().__init__(owner)
        self.table = table
        self.owner = owner
        self.path_provider = path_provider
        self.language_provider = language_provider or (lambda: "zh")
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.table.viewport() and event.type() == QEvent.Type.ContextMenu:
            self.show(event.pos())
            return True
        return super().eventFilter(obj, event)

    def show(self, pos):
        row = _row_at(self.table, pos)
        if row < 0:
            return
        selected = _selected_rows(self.table)
        if row not in selected:
            selected = [row]
            _select_row(self.table, row)
        paths = [path for path in self.path_provider(row, selected) if path is not None]
        if not paths:
            return

        lang = self.language_provider()
        global_pos = self.table.viewport().mapToGlobal(pos)
        menu = QMenu(self.owner)
        same_parent = len({str(path.parent) for path in paths}) == 1

        act_copy_files = menu.addAction(_label(lang, "copy_files"))
        act_copy_files.triggered.connect(lambda: _set_file_clipboard(self.owner, paths, cut=False))
        act_cut_files = menu.addAction(_label(lang, "cut_files"))
        act_cut_files.triggered.connect(lambda: _set_file_clipboard(self.owner, paths, cut=True))
        menu.addSeparator()

        if len(paths) == 1:
            first_path = paths[0]
            act_open = menu.addAction(_label(lang, "open"))
            act_open.triggered.connect(
                lambda: subprocess.run(["cmd", "/c", "start", "", str(first_path)], check=False)
            )

        first_path = paths[0]
        act_reveal = menu.addAction(_label(lang, "open_folder"))
        act_reveal.triggered.connect(lambda: subprocess.run(["explorer", "/select,", str(first_path)], check=False))

        act_copy_path = menu.addAction(_label(lang, "copy_path"))
        act_copy_path.triggered.connect(lambda: _copy_paths_text(paths))

        if sys.platform == "win32":
            menu.addSeparator()
            act_shell = menu.addAction(_label(lang, "system_context_menu"))
            act_shell.setEnabled(HAS_SHELL_CONTEXT and same_parent)
            act_shell.triggered.connect(
                lambda: QTimer.singleShot(0, lambda: _show_explorer_context_menu(self.owner, paths, QCursor.pos()))
            )

        menu.exec(global_pos)


def install_file_context_menu(
    table,
    owner: QWidget,
    path_provider: PathProvider,
    language_provider: LanguageProvider | None = None,
) -> FileContextMenu:
    helper = FileContextMenu(table, owner, path_provider, language_provider)
    setattr(table, "_file_context_menu_helper", helper)
    return helper
