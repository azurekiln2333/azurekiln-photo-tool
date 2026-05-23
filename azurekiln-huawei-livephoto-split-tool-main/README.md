# 华为LivePhoto批量分离工具

简体中文 | [繁體中文](docs/README.zh-TW.md) | [English](docs/README.en.md)

该项目用于将华为相机拍摄或由系统合并得到的 LivePhoto 单个 JPG 文件批量分离为静态照片与动态视频文件。分离后的 `JPG + MP4` 可用于后续重新合成为 Motion Photo 标准格式，以便在 Windows Photos、Google Photos 等相册应用中正常播放动态照片。

项目基于 `PyQt6` 与 `PyQt6-Fluent-Widgets` 构建 Windows 11 风格 GUI，界面风格尽量与同仓库的 `merge_live_photo_gui.py` 保持一致。

## 核心特性

- **批量扫描**：支持扫描当前目录或所有子目录。
- **自动识别**：自动区分华为 LivePhoto JPG、普通静态照片，以及已存在的同名 JPG/MP4 文件。
- **批量分离**：内嵌 LivePhoto 会被拆分为同名 `.jpg` 与 `.mp4`。
- **文件整理**：已存在的同名 JPG/MP4 文件可复制到统一输出目录并保留目录层级。
- **冲突策略**：照片和视频目标已存在时可分别选择跳过或覆盖。
- **中英文切换**：GUI 文案已分离到 `split_huawei_live_photo_translations.py`。
- **配置记忆**：语言、输入输出目录、扫描规则、冲突策略会保存到本地配置。

## 已测试设备

| 平台 | 设备 | 代号 | 系统版本 | 来源 |
| --- | --- | --- | --- | --- |
| HarmonyOS | HUAWEI Mate 20 | HMA-AL00 | HarmonyOS 4.0.0.121 | 本机 LivePhoto JPG 文件 |
| HarmonyOS | HUAWEI nova 5z | SPN-AL00 | HarmonyOS 2.0.0.165 | 本机 LivePhoto JPG 文件 |
| HarmonyOS NEXT | HUAWEI nova 14 Ultra | MRT-AL10 | HarmonyOS 5 / 6 | 合并后的单个 LivePhoto JPG 文件 |

> HarmonyOS 5 / 6 拍摄后，通过华为云下载、系统接口调用、文件管理复制，或分享给 HarmonyOS 4 及以下设备等方式得到的单个 LivePhoto JPG 文件，也支持分离为 JPG 和 MP4。

## 快速开始

### 1. Windows 便携版直接运行
- 操作系统：Windows 10 / 11
- 运行环境：无需安装 Python

从 release 下载以下两个文件：

```text
SplitHuaweiLivePhotoTool-1.0.0-20260523-windows-x64-portable.zip
SplitHuaweiLivePhotoTool-1.0.0-20260523-windows-x64-portable.sha256.txt
```

可选：解压前校验 SHA256：

```powershell
Get-FileHash .\SplitHuaweiLivePhotoTool-1.0.0-20260523-windows-x64-portable.zip -Algorithm SHA256
Get-Content .\SplitHuaweiLivePhotoTool-1.0.0-20260523-windows-x64-portable.sha256.txt
```

解压便携包后运行：

```text
SplitHuaweiLivePhotoTool.exe
```

便携包内包含：

- Windows x64 GUI 程序
- 简体中文、繁體中文、English 文档

### 2. 源码运行
- 运行依赖：Python 3.10+
- 核心组件：`PyQt6`、`PyQt6-Fluent-Widgets`、`PyQt6-Frameless-Window`、`Pillow`

```powershell
python -m venv .venv
.\.venv\Scripts\activate

pip install PyQt6 PyQt6-Fluent-Widgets PyQt6-Frameless-Window Pillow

python split_huawei_live_photo_gui.py
```

命令行分离单个文件或目录：

```powershell
python split_huawei_live_photo.py .\sample\HarmonyOS4\Source\IMG_20260515_230101.jpg .\sample\HarmonyOS4\SplitOutput
python split_huawei_live_photo.py .\sample\HarmonyOS4\Source .\sample\HarmonyOS4\SplitOutput
```

## 使用说明

1. 启动 `SplitHuaweiLivePhotoTool.exe` 或运行 `python split_huawei_live_photo_gui.py`。
2. 选择源文件夹。源文件夹可以包含华为相机拍摄，或通过华为云、系统接口、文件管理复制、跨设备分享等方式得到的单个 LivePhoto JPG 文件。
3. 确认输出目录，按需选择是否扫描子目录。
4. 设置目标文件已存在时的处理策略。
5. 点击 **开始批量分离**。

输出文件会按源目录层级写入输出目录。普通静态照片只会标记为跳过，不会复制到输出目录。

## 打包构建

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name SplitHuaweiLivePhotoTool `
  --collect-all qfluentwidgets `
  --collect-all qframelesswindow `
  --exclude-module PyQt6.QtNetwork `
  --exclude-module PyQt6.QtOpenGL `
  --exclude-module PyQt6.QtQml `
  --exclude-module PyQt6.QtQuick `
  --exclude-module PyQt6.QtSql `
  --exclude-module PyQt6.QtTest `
  --exclude-module PyQt6.QtWebEngineCore `
  --exclude-module PyQt6.QtWebEngineWidgets `
  .\split_huawei_live_photo_gui.py
```

构建产物：

```text
dist\SplitHuaweiLivePhotoTool.exe
```

## 项目结构与配置

- `split_huawei_live_photo.py`：命令行与核心分离逻辑。
- `split_huawei_live_photo_gui.py`：PyQt6 / Fluent GUI。
- `split_huawei_live_photo_translations.py`：拆分工具中英文 UI 文案。
- `merge_live_photo_gui.py`：合成工具 GUI，可作为界面风格参考。
- `merge_live_photo_translations.py`：合成工具中英文 UI 文案。
- `sample/`：测试样例。

本地配置保存位置：

```text
%APPDATA%\SplitHuaweiLivePhotoGUI\settings.json
```

## 开源协议

本项目基于仓库中的 `LICENSE` 文件发布。
