# Huawei LivePhoto Batch Split Tool

[简体中文](../README.md) | [繁體中文](README.zh-TW.md) | English

This project batch-splits single Huawei camera or system-merged LivePhoto JPG files into standalone static photos and motion videos. The split `JPG + MP4` files can later be merged into the Motion Photo standard for playback in Windows Photos, Google Photos, and similar gallery applications.

The GUI is built with `PyQt6` and `PyQt6-Fluent-Widgets`, following a Windows 11 style and staying visually consistent with `merge_live_photo_gui.py` in this repository.

## Features

- **Batch scanning**: Scan the selected folder or all subfolders.
- **Automatic detection**: Detect Huawei LivePhoto JPG files, ordinary static photos, and existing matching JPG/MP4 files.
- **Batch splitting**: Split embedded LivePhoto JPG files into matching `.jpg` and `.mp4` files.
- **File organization**: Copy existing matching JPG/MP4 files into one output folder while preserving folder structure.
- **Conflict handling**: Choose skip or overwrite separately for existing photo and video targets.
- **Chinese / English UI**: GUI strings are separated into `split_huawei_live_photo_translations.py`.
- **Persistent settings**: Language, input/output folders, scan mode, and conflict rules are saved locally.

## Tested Devices

| Platform | Device | Code name | System version | Source |
| --- | --- | --- | --- | --- |
| HarmonyOS | HUAWEI Mate 20 | HMA-AL00 | HarmonyOS 4.0.0.121 | Native LivePhoto JPG file |
| HarmonyOS | HUAWEI nova 5z | SPN-AL00 | HarmonyOS 2.0.0.165 | Native LivePhoto JPG file |
| HarmonyOS NEXT | HUAWEI nova 14 Ultra | MRT-AL10 | HarmonyOS 5 / 6 | Single merged LivePhoto JPG file |

> HarmonyOS 5 / 6 captures are supported when they become a single LivePhoto JPG file through Huawei Cloud, system APIs, file manager copy, or sharing to HarmonyOS 4 and earlier devices.

## Quick Start

### 1. Run the Windows Portable Build Directly

- Operating system: Windows 10 / 11
- Runtime: no Python installation required

Download both release assets:

```text
SplitHuaweiLivePhotoTool-1.0.0-20260523-windows-x64-portable.zip
SplitHuaweiLivePhotoTool-1.0.0-20260523-windows-x64-portable.sha256.txt
```

Optional: verify SHA256 before extracting:

```powershell
Get-FileHash .\SplitHuaweiLivePhotoTool-1.0.0-20260523-windows-x64-portable.zip -Algorithm SHA256
Get-Content .\SplitHuaweiLivePhotoTool-1.0.0-20260523-windows-x64-portable.sha256.txt
```

Extract the portable package and run:

```text
SplitHuaweiLivePhotoTool.exe
```

The portable package includes:

- Windows x64 GUI application
- Simplified Chinese, Traditional Chinese, and English documentation

### 2. Run from Source

- Runtime dependency: Python 3.10+
- Core packages: `PyQt6`, `PyQt6-Fluent-Widgets`, `PyQt6-Frameless-Window`, `Pillow`

```powershell
python -m venv .venv
.\.venv\Scripts\activate

pip install PyQt6 PyQt6-Fluent-Widgets PyQt6-Frameless-Window Pillow

python split_huawei_live_photo_gui.py
```

Split a single file or a folder from the command line:

```powershell
python split_huawei_live_photo.py .\sample\HarmonyOS4\Source\IMG_20260515_230101.jpg .\sample\HarmonyOS4\SplitOutput
python split_huawei_live_photo.py .\sample\HarmonyOS4\Source .\sample\HarmonyOS4\SplitOutput
```

## Usage

1. Start `SplitHuaweiLivePhotoTool.exe` or run `python split_huawei_live_photo_gui.py`.
2. Choose the source folder. It can contain single Huawei LivePhoto JPG files captured by the camera or produced through Huawei Cloud, system APIs, file manager copy, or cross-device sharing.
3. Confirm the output folder and choose whether to scan subfolders.
4. Set conflict rules for existing target files.
5. Click **Start batch split**.

Output files are written into the output folder while preserving the source folder structure. Ordinary static photos are marked as skipped and are not copied.

## Build

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

Build output:

```text
dist\SplitHuaweiLivePhotoTool.exe
```

## Project Structure

- `split_huawei_live_photo.py`: command-line and core splitting logic.
- `split_huawei_live_photo_gui.py`: PyQt6 / Fluent GUI.
- `split_huawei_live_photo_translations.py`: Chinese and English GUI strings.
- `merge_live_photo_gui.py`: merge-tool GUI used as the visual reference.
- `merge_live_photo_translations.py`: merge-tool GUI strings.
- `sample/`: test samples.

Local settings path:

```text
%APPDATA%\SplitHuaweiLivePhotoGUI\settings.json
```

## License

This project is released under the license in `LICENSE`.
