# AzureKiln Photo Tool

简体中文 | [繁體中文](docs/README.zh-TW.md) | [English](docs/README.en.md)

AzureKiln Photo Tool 是一个面向 Windows 的动态照片处理工具集。当前把三个核心功能合并到同一个 PyQt6 / Fluent 风格 GUI 中，并使用左侧 Windows 风格边栏切换功能页：

- **LivePhoto 合并**：将同名照片与视频批量合成为 Google / Microsoft Photos 可识别的 Motion Photo。
- **华为 LivePhoto 分离**：将华为相机或系统合并得到的单个 LivePhoto JPG 批量拆分为 `JPG + MP4`。
- **Flyme LivePhoto 修复**：修复 Flyme 12.6 以下版本系统相机拍摄的历史 LivePhoto 元数据兼容性问题。

左上角菜单按钮可展开或收起边栏。旧的三个独立 GUI 入口仍保留，方便单独运行或回归测试。

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
exiftool/exiftool.exe
bin/exiftool.exe
系统 PATH
```

## 使用说明

1. 启动统一 GUI：`python unified_gui.py` 或运行便携版 `AzureKilnPhotoTool.exe`。
2. 通过左侧边栏选择功能页：`LivePhoto 合并`、`华为 LivePhoto 分离`、`Flyme LivePhoto 修复`。
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

- `unified_gui.py`：三功能合一的侧栏 GUI 入口。
- `merge_live_photo_gui.py`：LivePhoto 合并页面和独立入口。
- `merge_live_photo.py`：命令行批量合并脚本。
- `split_huawei_live_photo_gui.py`：华为 LivePhoto 分离页面和独立入口。
- `split_huawei_live_photo.py`：命令行分离脚本。
- `main_gui.py`：Flyme LivePhoto 修复页面和独立入口。
- `main_gui_logic.py`：Flyme 文件扫描、分类、输出和修复流程。
- `flyme_livephoto_fix_core.py`：基于 ExifTool 的识别与修复引擎。
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
