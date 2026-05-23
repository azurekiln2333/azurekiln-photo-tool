# Merge LivePhoto Tool (Google Motion Photo 批量合成工具)

简体中文 | [繁體中文](docs/README.zh-TW.md) | [English](docs/README.en.md)

该项目用于将分离保存的照片与同名动态视频批量合成为 Google Photos/ Microsoft Photos 可识别的 Motion Photo 文件。

目前HarmonyOS NEXT(包括 HarmonyOS 5/6)、iOS、OriginOS拍摄动态照片会拆成 `JPG/HEIC` 静态图与 `MP4/MOV` 视频两个文件进行保存。

这个项目的诞生就是为了能够批量把两个文件合并成一个 Motion Photos 标准的动态照片文件，支持文件名自动匹配静态照片与对应视频，合并处理后能够在 Windows Photos、Google Photos 等平台中正常播放动态效果。

在合并过程中，项目会尽可能保留原始 EXIF 信息以及拍摄时间等元数据。

同时，项目基于 `PyQt6` 设计了 Windows 11 风格的 GUI，并提供静态照片分离、HEIC 转 JPG、汇总输出与回收站清理等功能，以提升批量整理体验。

##  核心特性

**智能匹配与合成**
- **自动配对**：自动扫描 `JPG/JPEG/HEIC/HEIF` 图片，并按同名规则匹配 `MP4/MOV` 视频。
- **批量合成**：一键将图片与视频合成为 Google Photos 可识别的 Motion Photo。
- **时间保留**：输出文件优先使用照片 EXIF 拍摄时间，缺失时回退沿用原文件时间。
- **防冲突机制**：目标目录存在同名文件时，可自由选择“跳过”或“覆盖”。

**灵活整理与导出**
- **静态照片分离**：没有匹配视频的普通照片可自动复制到 `Static_Photos` 目录。
- **HEIC 处理**：支持读取 HEIC/HEIF；静态 HEIC 可按需转换为 JPG，并保留 EXIF/时间戳。
- **汇总输出**：处理完成后可汇总到 `All_Processed_Summary`，便于一次性检查或导入。
- **配置记忆**：自动保存输出目录、界面语言、扫描规则、冲突策略等个人偏好设置。

## 已测试设备

| 平台 | 设备 | 系统版本 |
| --- | --- | --- |
| HarmonyOS | nova 14 Ultra | HarmonyOS 5 / 6 |
| iOS | iPhone 6s Plus | iOS 15.8.7 |
| iOS | iPhone 7 Plus | iOS 14.8.1 |

---

## 快速开始

### 1. 运行环境
- 操作系统：Windows 10 / 11
- 运行依赖：Python 3.10+
- 核心组件：`PyQt6`、`PyQt6-Fluent-Widgets`、`Pillow`

> **关于 HEIC 和回收站功能的说明**：
> 如需处理 HEIC/HEIF，请安装 `pillow-heif`。
> 如需启用“汇总后移入回收站”，请安装 `send2trash`。

### 2. 源码运行 (开发者)

克隆仓库后，安装依赖并启动：

```powershell
# 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\activate

# 安装依赖
pip install PyQt6 PyQt6-Fluent-Widgets qframelesswindow Pillow pillow-heif send2trash

# 启动程序
python merge_live_photo_gui.py
```

---

## 使用指南

1. **选择目录**：启动程序后，选择包含图片与同名视频的源目录，并确认输出目录。
2. **扫描文件**：按需勾选“扫描所有子目录”，程序会自动查找图片并匹配同名 `MP4/MOV`。
3. **设置处理规则**：选择动态照片、静态照片遇到同名文件时的处理策略（跳过/覆盖），并按需启用静态照片分离、HEIC 转 JPG、汇总输出等选项。
4. **一键合成/整理**：
   - 点击 **“开始批量合成”** 按钮。
   - 有匹配视频的图片会输出为 Google Motion Photo。
   - *说明：没有匹配视频的图片可按设置分离到 `Static_Photos`，处理结果可汇总到 `All_Processed_Summary`。*

> **提示**：输出文件会优先读取原图的 EXIF 拍摄时间并写入文件时间；如果原图没有拍摄时间，则沿用原文件时间。

---

##  打包构建

如果需要将 GUI 打包成一个单文件免安装 `exe` 程序，请执行以下命令：

```powershell
pip install pyinstaller

pyinstaller --noconfirm --clean --onefile --windowed --name MergeLivePhotoTool `
  --collect-all qfluentwidgets `
  --collect-all qframelesswindow `
  --hidden-import pillow_heif `
  --hidden-import send2trash `
  --exclude-module PyQt6.QtNetwork `
  --exclude-module PyQt6.QtOpenGL `
  --exclude-module PyQt6.QtQml `
  --exclude-module PyQt6.QtQuick `
  --exclude-module PyQt6.QtSql `
  --exclude-module PyQt6.QtTest `
  --exclude-module PyQt6.QtWebEngineCore `
  --exclude-module PyQt6.QtWebEngineWidgets `
  .\merge_live_photo_gui.py
```
*构建产物将输出至 `dist/MergeLivePhotoTool.exe`。如已安装 UPX 并加入 `PATH`，PyInstaller 会自动尝试进一步压缩可执行文件。*

---

## 项目结构与配置

- **本地配置**：用户设置会自动保存在 `%APPDATA%\MergeLivePhotoGUI\settings.json`。
- `merge_live_photo_gui.py`：主界面、扫描、合成、静态照片分离与汇总处理逻辑。
- `merge_live_photo.py`：命令行批量合成脚本。
- `merge_live_photo_translations.py`：GUI 多语言文本。

## 开源协议
本项目基于仓库中的 `LICENSE` 文件发布。
