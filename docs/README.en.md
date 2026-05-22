# AzureKiln Photo Tool

[简体中文](../README.md) | [繁體中文](README.zh-TW.md) | English

AzureKiln Photo Tool is a Windows-focused motion photo toolkit. It combines three core workflows into one PyQt6 / Fluent-style GUI with a Windows-style sidebar:

- **LivePhoto Merge**: batch merge same-name image and video pairs into Motion Photos recognized by Google Photos and Microsoft Photos.
- **Huawei LivePhoto Split**: batch split single Huawei LivePhoto JPG files into `JPG + MP4`.
- **Flyme LivePhoto Fix**: repair metadata compatibility for legacy Live Photos captured by Flyme system cameras before Flyme 12.6.

The top-left menu button expands or collapses the sidebar. The three older standalone GUI entry points are still available for isolated use and regression testing.

## Features

### LivePhoto Merge

- Scans `JPG/JPEG/HEIC/HEIF` images and matches `MP4/MOV` videos by basename.
- Exports Google Photos / Microsoft Photos-compatible Motion Photos.
- Preserves EXIF, capture time, and file timestamps whenever possible.
- Can organize still images without matching videos into `Static_Photos`.
- Supports optional summary output to `All_Processed_Summary`.
- Optional HEIC/HEIF support is available through `pillow-heif`.

### Huawei LivePhoto Split

- Scans the selected folder or all subfolders.
- Detects embedded Huawei LivePhoto JPG files, ordinary still photos, and existing same-name `JPG + MP4` pairs.
- Splits embedded LivePhoto files into matching `.jpg` and `.mp4` files.
- Preserves the source directory structure and lets you choose separate conflict rules for photos and videos.

### Flyme LivePhoto Fix

- Classifies pending Flyme live photos, already compatible live photos, static photos, other phone photos, and unrelated files.
- Uses ExifTool to patch metadata so legacy Flyme Live Photos can be recognized by Microsoft Photos, Google Photos, and similar apps.
- Supports drag-and-drop import, asynchronous scanning, drag selection, sorting, context menus, copy/move, and fix/export workflows.
- Saves output directory, language, category filters, and processing options locally.

## Tested Devices

| Platform | Device | System version | Covered workflow |
| --- | --- | --- | --- |
| HarmonyOS | HUAWEI Mate 20 | HarmonyOS 4.0.0.121 | Huawei LivePhoto Split |
| HarmonyOS | HUAWEI nova 5z | HarmonyOS 2.0.0.165 | Huawei LivePhoto Split |
| HarmonyOS NEXT | HUAWEI nova 14 Ultra | HarmonyOS 5 / 6 | Huawei Split, LivePhoto Merge |
| iOS | iPhone 6s Plus | iOS 15.8.7 | LivePhoto Merge |
| iOS | iPhone 7 Plus | iOS 14.8.1 | LivePhoto Merge |
| Flyme | Meizu 21 / 21 Note | Earlier than Flyme 12.6 | Flyme LivePhoto Fix |

## Quick Start

### Windows Portable Build

- Operating system: Windows 10 / 11 x64
- Runtime: no Python installation required

Download the release zip and SHA256 file, extract the package, and run:

```text
AzureKilnPhotoTool.exe
```

Checksum example:

```powershell
Get-FileHash .\AzureKilnPhotoTool-1.0.0-20260523-windows-x64-portable.zip -Algorithm SHA256
Get-Content .\AzureKilnPhotoTool-1.0.0-20260523-windows-x64-portable.sha256.txt
```

### Run from Source

Requirements:

- Python 3.10+
- `PyQt6`
- `PyQt6-Fluent-Widgets`
- `PyQt6-Frameless-Window` or `qframelesswindow`
- `Pillow`
- Optional: `pillow-heif` for HEIC/HEIF support
- Optional: `send2trash` for recycle-bin cleanup
- Flyme repair requires `ExifTool`

```powershell
python -m venv .venv
.\.venv\Scripts\activate

pip install PyQt6 PyQt6-Fluent-Widgets PyQt6-Frameless-Window Pillow pillow-heif send2trash pywin32

python unified_gui.py
```

ExifTool lookup order:

```text
vendor/exiftool/exiftool.exe
exiftool/exiftool.exe
bin/exiftool.exe
system PATH
```

## Usage

1. Start the unified GUI with `python unified_gui.py` or run `AzureKilnPhotoTool.exe`.
2. Choose a workflow from the sidebar: `LivePhoto Merge`, `Huawei LivePhoto Split`, or `Flyme LivePhoto Fix`.
3. Use the top-left menu button to collapse or expand the sidebar.
4. Configure source folder, output folder, scan rules, and conflict behavior in the selected page.
5. Start the current page's merge, split, or repair workflow.

The old standalone entry points remain available:

```powershell
python merge_live_photo_gui.py
python split_huawei_live_photo_gui.py
python main_gui.py
```

## Command Line Tools

LivePhoto merge:

```powershell
python merge_live_photo.py .\input_dir .\output_dir
```

Huawei LivePhoto split:

```powershell
python split_huawei_live_photo.py .\sample\HarmonyOS4\Source\IMG_20260515_230101.jpg .\sample\HarmonyOS4\SplitOutput
python split_huawei_live_photo.py .\sample\HarmonyOS4\Source .\sample\HarmonyOS4\SplitOutput
```

The Flyme repair batch workflow is primarily exposed through the GUI. Its core implementation lives in `flyme_livephoto_fix_core.py` and `main_gui_logic.py`.

## Packaging

The unified GUI is best packaged as a portable directory build so ExifTool can be bundled:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name AzureKilnPhotoTool `
  --collect-all qfluentwidgets `
  --collect-all qframelesswindow `
  --hidden-import pillow_heif `
  --hidden-import send2trash `
  --add-data "vendor/exiftool;exiftool" `
  .\unified_gui.py
```

You can use `--onefile` if you only need a single executable, but Flyme repair still requires `exiftool.exe` to be discoverable.

## Project Structure

- `unified_gui.py`: unified sidebar GUI entry point.
- `merge_live_photo_gui.py`: LivePhoto merge page and standalone entry point.
- `merge_live_photo.py`: command-line batch merge script.
- `split_huawei_live_photo_gui.py`: Huawei LivePhoto split page and standalone entry point.
- `split_huawei_live_photo.py`: command-line split script.
- `main_gui.py`: Flyme LivePhoto repair page and standalone entry point.
- `main_gui_logic.py`: Flyme scanning, classification, output, and repair workflow.
- `flyme_livephoto_fix_core.py`: ExifTool-based detection and repair engine.
- `*_translations.py`: GUI localization text.
- `sample/`: test samples.

Local settings:

```text
%APPDATA%\MergeLivePhotoGUI\settings.json
%APPDATA%\SplitHuaweiLivePhotoGUI\settings.json
%APPDATA%\FlymeLivePhotoFix\settings.json
```

## License

This project is released under the license in `LICENSE`.
