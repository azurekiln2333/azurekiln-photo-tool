# 项目结构约定

> 记录项目**实际的**文件放置方式，不是理想架构。

---

## 顶层模块职责

| 文件 / 目录 | 职责 | 关键点 |
|------|------|------|
| `unified_gui.py` | 统一入口：左侧边栏承载 6 个功能页 | 把各功能页 `MainWindow` 以 `embedded=True` 方式嵌入，用 `takeCentralWidget()` 搬移内容 |
| `merge_live_photo_gui.py` | LivePhoto 合并页 + 独立入口 | 拖拽导入、异步扫描、合并批处理 |
| `split_huawei_live_photo_gui.py` | 华为 LivePhoto 分离页 + 独立入口 | — |
| `main_gui.py` | Flyme LivePhoto 修复页 + 独立入口 | 注意：文件名是 `main_gui`，但**不是**全项目主入口 |
| `main_gui_logic.py` | Flyme 扫描/分类/输出/修复流程 | — |
| `flyme_livephoto_fix_core.py` | Flyme 修复引擎（基于 ExifTool） | 通过 `exiftool_resolver` 定位 ExifTool |
| `timestamp_fix_gui.py` | 时间戳修复页 + **共用时间/元数据读取层** | 见下方「共用层」警告 |
| `rename_photo_gui.py` | 照片/视频重命名页 + 独立入口 | 表格行号与 `file_list` 严格一一对应 |
| `dedupe_media_gui.py` | 图片视频去重页 + 独立入口 | — |
| `exiftool_resolver.py` | ExifTool 定位与调用解析 | 处理 PyInstaller onefile 的 stub 自定位失效 |
| `elevation_hint.py` | 管理员权限检测 + Fluent 内嵌提示条 | 被 7 个入口共用 |
| `file_context_menu.py` | 各页共用的表格右键菜单 | 用 `win32gui` / `win32com.shell` 调系统菜单 |
| `*_translations.py` | 各功能页的 zh/en 文案 | `merge_live_photo_translations.py`、`split_huawei_live_photo_translations.py`、`ui_translations.py` |
| `merge_live_photo.py` / `split_huawei_live_photo.py` | 命令行批量脚本 | 无 GUI，可直接跑 |
| `sample/` | 测试样例 | HarmonyOS2/4/6 的 Source / SplitOutput / ByHwExpandToHMOSToSplit |

---

## 共用层警告（改前必读）

`timestamp_fix_gui.py` **同时是共用的时间/元数据读取层**，导出：

- `detect_timestamp` / `detect_rename_timestamp`
- `_timestamp_from_exif` / `_timestamp_from_media_created` / `_timestamp_from_filename`
- `_format_timestamp`
- `apply_file_times_only`
- `IMAGE_SUFFIXES` / `VIDEO_SUFFIXES`

被以下页面 import 使用：

- `rename_photo_gui.py`
- `dedupe_media_gui.py`
- `merge_live_photo_gui.py`

**改这些函数会同时影响多个页面。** 修改前先搜索引用：

```bash
grep -rn "detect_timestamp\|IMAGE_SUFFIXES\|VIDEO_SUFFIXES" --include=*.py .
```

---

## 命名与放置习惯（观察自现有代码）

- GUI 页面文件：`<功能>_gui.py`；对应命令行：`<功能>.py`；核心引擎：`<功能>_core.py`。
- 翻译文件：`<功能>_translations.py`，导出 `DEFAULT_LANGUAGE` / `SUPPORTED_LANGUAGES` / `TRANSLATIONS`。
- 共用工具类模块直接放仓库根目录（本项目是**扁平结构**，没有 `src/` / `packages/` 分层）。
- 不要新增子包目录，除非有明确的多模块边界需求。

---

## 不要做的事

- ❌ 不要把 GUI 代码写进 `*_core.py` / `exiftool_resolver.py`（这些必须保持无 PyQt 依赖，
  便于命令行与打包复用）。
- ❌ 不要为「看起来更整洁」而重构目录结构；扁平结构是现状，改动会波及所有入口与 spec。
- ❌ 不要在 `main_gui.py` 之外再造一个「主入口」；全项目入口是 `unified_gui.py`。
