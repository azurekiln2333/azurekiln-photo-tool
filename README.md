# AzureKiln Photo Tool

简体中文 | [繁體中文](docs/README.zh-TW.md) | [English](docs/README.en.md)

AzureKiln Photo Tool 是一个面向 Windows 的动态照片处理工具集。当前把六个功能页合并到同一个 PyQt6 / Fluent 风格 GUI 中，并使用左侧 Windows 风格边栏切换功能页：

- **LivePhoto 合并**：将同名照片与视频批量合成为 Google / Microsoft Photos 可识别的 Motion Photo。
- **华为 LivePhoto 分离**：将华为相机或系统合并得到的单个 LivePhoto JPG 批量拆分为 `JPG + MP4`。
- **Flyme LivePhoto 修复**：修复 Flyme 12.6 以下版本系统相机拍摄的历史 LivePhoto 元数据兼容性问题。
- **照片时间戳修复**：从拍摄时间恢复文件的创建、修改和访问时间。
- **照片/视频重命名**：按读取到的时间把照片与视频批量重命名为 `IMG_年月日_时分秒` / `VID_年月日_时分秒`。
- **图片视频去重**：按内容哈希查找并清理重复的图片与视频。

左上角菜单按钮可展开或收起边栏。旧的独立 GUI 入口仍保留，方便单独运行或回归测试。

## 核心特性

### LivePhoto 合并

- 自动扫描 `JPG/JPEG/HEIC/HEIF` 图片，并按同名规则匹配 `MP4/MOV` 视频。
- 批量合成为 Google Photos / Microsoft Photos 可识别的 Motion Photo。
- 尽量保留原始 EXIF、拍摄时间和文件时间。
- 可把无匹配视频的静态照片整理到 `Static_Photos`，并支持汇总输出到 `All_Processed_Summary`。
- 可选 HEIC/HEIF 读取与静态 HEIC 转 JPG。

### 华为 LivePhoto 分离

- 支持扫描当前目录或所有子目录。
- 自动识别华为内嵌 LivePhoto JPG、普通静态照片，以及同名 `JPG + MP4` 文件。
- 将内嵌 LivePhoto 拆分为同名 `.jpg` 与 `.mp4`。
- 输出时保留源目录层级，并可分别设置照片和视频冲突策略。

### Flyme LivePhoto 修复

- 自动区分待修复 Flyme 动态照片、已兼容动态照片、静态照片、其他照片和无关文件。
- 基于 ExifTool 修补元数据，让历史 Flyme LivePhoto 能被 Microsoft Photos、Google Photos 等识别。
- 支持拖拽导入、异步扫描、框选、排序、右键菜单、复制/移动/修复并输出。
- 支持按类别控制导出范围，并记忆输出目录、语言和处理选项。

### 照片时间戳修复

- 从 EXIF 拍摄时间或视频容器创建时间恢复文件时间戳。
- 读取范围覆盖 IFD0、Exif SubIFD 的 `DateTimeOriginal` / `DateTimeDigitized` 以及 XMP，并跳过相机「未设置时钟」写入的占位时间（如 `2001:01:01 00:00:00`）。
- 视频支持 MP4 / MOV / M4V / 3GP / AVI / WMV / MKV：优先 ffprobe 的 `creation_time` 与 AVI（RIFF）的 `date`，其次 ExifTool 的 `DateCreated` / `CreateDate` 等标签。
- 可拖拽导入、异步扫描，并可选批量写回媒体元数据。

### 照片/视频重命名

- 左侧读取原始文件时间，右侧按匹配到的文件时间批量重命名待处理文件。
- 时间来源优先级为「拍摄/容器元数据 → 文件名时间 → 文件现有最早时间」，避免被 `IMG_20010101_000000` 这类占位文件名覆盖真实拍摄时间。
- 原始文件匹配优先使用相对路径，其次使用文件名；可自定义照片/视频前缀（默认 `IMG` / `VID`）。
- 支持 JPG/JPEG/HEIC/HEIF/PNG/TIF/TIFF/WebP 与 MP4/MOV/M4V/3GP/AVI/WMV/MKV。
- **隐藏已符合规则的文件**：文件名已符合命名规则、且与读取到的时间一致时，可选择从列表中隐藏，只留下真正需要处理的文件。

### 图片视频去重

- 按内容哈希查找重复的图片与视频，并支持保留策略与回收站清理。

## 已测试设备

| 平台 | 设备 | 系统版本 | 覆盖功能 |
| --- | --- | --- | --- |
| HarmonyOS | HUAWEI Mate 20 | HarmonyOS 4.0.0.121 | 华为 LivePhoto 分离 |
| HarmonyOS | HUAWEI nova 5z | HarmonyOS 2.0.0.165 | 华为 LivePhoto 分离 |
| HarmonyOS NEXT | HUAWEI nova 14 Ultra | HarmonyOS 5 / 6 | 华为分离、LivePhoto 合并 |
| iOS | iPhone 6s Plus | iOS 15.8.7 | LivePhoto 合并 |
| iOS | iPhone 7 Plus | iOS 14.8.1 | LivePhoto 合并 |
| Flyme | Meizu 21 / 21 Note | Flyme 12.6 以下 | Flyme LivePhoto 修复 |

> HarmonyOS 5 / 6 拍摄后，通过华为云下载、系统接口调用、文件管理复制，或分享给 HarmonyOS 4 及以下设备等方式得到的单个 LivePhoto JPG，也支持分离为 JPG 和 MP4。

## 快速开始

### Windows 便携版

- 操作系统：Windows 10 / 11 x64
- 运行环境：无需安装 Python

下载 release 中的便携包和 SHA256 文件，解压后运行：

```text
AzureKilnPhotoTool.exe
```

校验示例：

```powershell
Get-FileHash .\AzureKilnPhotoTool-1.0.0-20260523-windows-x64-portable.zip -Algorithm SHA256
Get-Content .\AzureKilnPhotoTool-1.0.0-20260523-windows-x64-portable.sha256.txt
```

### 源码运行

运行依赖：

- Python 3.10+
- `PyQt6`
- `PyQt6-Fluent-Widgets`
- `PyQt6-Frameless-Window` 或 `qframelesswindow`
- `Pillow`
- 可选：`pillow-heif`，用于 HEIC/HEIF 支持
- 可选：`send2trash`，用于汇总后移入回收站
- Flyme 修复需要 `ExifTool`

```powershell
python -m venv .venv
.\.venv\Scripts\activate

pip install PyQt6 PyQt6-Fluent-Widgets PyQt6-Frameless-Window Pillow pillow-heif send2trash pywin32

python unified_gui.py
```

ExifTool 查找顺序：

```text
vendor/exiftool/exiftool.exe
vendor/exiftool/exiftool
exiftool/exiftool.exe
exiftool/exiftool
bin/exiftool.exe
bin/exiftool
EXIFTOOL_PATH
系统 PATH 中的 exiftool
```

## 使用说明

1. 启动统一 GUI：`python unified_gui.py` 或运行便携版 `AzureKilnPhotoTool.exe`。
2. 通过左侧边栏选择功能页：`LivePhoto 合并`、`华为 LivePhoto 分离`、`Flyme LivePhoto 修复`、`照片时间戳修复`、`照片/视频重命名`、`图片视频去重`。
3. 点击左上角菜单按钮可收起或展开边栏。
4. 在对应功能页选择源目录、输出目录、扫描规则和冲突策略。
5. 点击当前页面的开始、分离或修复按钮执行批处理。

三个旧入口仍可单独运行：

```powershell
python merge_live_photo_gui.py
python split_huawei_live_photo_gui.py
python main_gui.py
```

## 命令行工具

LivePhoto 合并：

```powershell
python merge_live_photo.py .\input_dir .\output_dir
```

华为 LivePhoto 分离：

```powershell
python split_huawei_live_photo.py .\sample\HarmonyOS4\Source\IMG_20260515_230101.jpg .\sample\HarmonyOS4\SplitOutput
python split_huawei_live_photo.py .\sample\HarmonyOS4\Source .\sample\HarmonyOS4\SplitOutput
```

Flyme 修复的批量工作流主要通过 GUI 提供，核心逻辑位于 `flyme_livephoto_fix_core.py` 与 `main_gui_logic.py`。

## 打包构建

统一 GUI 推荐打包为便携目录包，便于携带 ExifTool：

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name AzureKilnPhotoTool `
  --collect-all qfluentwidgets `
  --collect-all qframelesswindow `
  --hidden-import pillow_heif `
  --hidden-import send2trash `
  --add-data "vendor/exiftool;exiftool" `
  .\unified_gui.py
```

如果只需要单文件，也可以使用 `--onefile`；但 Flyme 修复功能仍需要确保 `exiftool.exe` 可被程序找到。

## 项目结构

- `unified_gui.py`：六个功能页合一的侧栏 GUI 入口。
- `merge_live_photo_gui.py`：LivePhoto 合并页面和独立入口。
- `merge_live_photo.py`：命令行批量合并脚本。
- `split_huawei_live_photo_gui.py`：华为 LivePhoto 分离页面和独立入口。
- `split_huawei_live_photo.py`：命令行分离脚本。
- `main_gui.py`：Flyme LivePhoto 修复页面和独立入口。
- `main_gui_logic.py`：Flyme 文件扫描、分类、输出和修复流程。
- `flyme_livephoto_fix_core.py`：基于 ExifTool 的识别与修复引擎。
- `timestamp_fix_gui.py`：照片时间戳修复页面，并提供各页面共用的时间/元数据读取函数。
- `rename_photo_gui.py`：照片/视频重命名页面和独立入口。
- `dedupe_media_gui.py`：图片视频去重页面和独立入口。
- `exiftool_resolver.py`：ExifTool 定位与调用解析（含 PyInstaller onefile 兼容处理）。
- `*_translations.py`：各功能 GUI 的多语言文本。
- `sample/`：测试样例。

本地配置保存位置：

```text
%APPDATA%\MergeLivePhotoGUI\settings.json
%APPDATA%\SplitHuaweiLivePhotoGUI\settings.json
%APPDATA%\FlymeLivePhotoFix\settings.json
```

## 开源协议

本项目基于仓库中的 `LICENSE` 文件发布。
