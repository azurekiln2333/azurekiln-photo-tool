# Merge LivePhoto Tool (Google Motion Photo Batch Merge Tool)

[简体中文](../README.md) | [繁體中文](README.zh-TW.md) | English

This project batch merges separately stored photos and same-name motion videos into Motion Photo files recognized by Google Photos / Microsoft Photos.

Currently, motion photos captured on HarmonyOS NEXT (including HarmonyOS 5/6), iOS, and OriginOS are saved as two separate files: a `JPG/HEIC` still image and an `MP4/MOV` video.

This project was created to batch merge those two files into a single Motion Photo-standard live photo file. It automatically matches still photos with corresponding videos by filename, and the merged results can play motion effects normally in Windows Photos, Google Photos, and other platforms.

During merging, the project preserves original EXIF information, capture time, and other metadata whenever possible.

The project also provides a Windows 11-style GUI built with `PyQt6`, along with static photo separation, HEIC-to-JPG conversion, summary output, and recycle-bin cleanup features to improve batch organization workflows.

## Core Features

**Smart Matching and Merging**
- **Automatic pairing**: Scans `JPG/JPEG/HEIC/HEIF` images and matches `MP4/MOV` videos by basename.
- **Batch merge**: Merges each image and video pair into a Google Photos-compatible Motion Photo.
- **Timestamp preservation**: Output files prefer the photo EXIF capture time and fall back to the source file timestamp when capture time is missing.
- **Conflict prevention**: When a file with the same name already exists in the target directory, you can choose to skip it or overwrite it.

**Flexible Organization and Export**
- **Static photo separation**: Regular photos without matching videos can be copied automatically to `Static_Photos`.
- **HEIC handling**: Supports reading HEIC/HEIF; static HEIC files can be converted to JPG while preserving EXIF metadata and timestamps.
- **Summary output**: Processed files can be collected into `All_Processed_Summary` for easier review or import.
- **Preference persistence**: Automatically saves personal settings such as output directory, UI language, scan rules, and conflict behavior.

## Tested Devices

| Platform | Device | System version |
| --- | --- | --- |
| HarmonyOS | nova 14 Ultra | HarmonyOS 5 / 6 |
| iOS | iPhone 6s Plus | iOS 15.8.7 |
| iOS | iPhone 7 Plus | iOS 14.8.1 |

---

## Quick Start

### 1. Requirements
- Operating system: Windows 10 / 11
- Runtime dependency: Python 3.10+
- Core components: `PyQt6`, `PyQt6-Fluent-Widgets`, `Pillow`

> **About HEIC and recycle-bin features**:
> Install `pillow-heif` if you need HEIC/HEIF support.
> Install `send2trash` if you want to move processed categorized files to the recycle bin after summary output.

### 2. Run from Source (Developers)

After cloning the repository, install the dependencies and start the app:

```powershell
# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install dependencies
pip install PyQt6 PyQt6-Fluent-Widgets qframelesswindow Pillow pillow-heif send2trash

# Launch the application
python merge_live_photo_gui.py
```

---

## Usage Guide

1. **Choose folders**: After starting the application, choose the source folder containing images and matching videos, then confirm the output folder.
2. **Scan files**: Enable `Scan subfolders` if needed. The app will find images and match same-name `MP4/MOV` files automatically.
3. **Set processing rules**: Choose how duplicate live-photo and static-photo outputs should be handled: skip or overwrite. Enable static photo separation, HEIC-to-JPG conversion, summary output, and other options as needed.
4. **One-click merge/organize**:
   - Click the **`Start batch merge`** button.
   - Images with matching videos will be exported as Google Motion Photo files.
   - *Note: Images without matching videos can be separated into `Static_Photos`, and processed results can be collected into `All_Processed_Summary`.*

> **Tip**: Output files first read the source image EXIF capture time and write it as the file timestamp. If no capture time is available, the source file timestamp is used instead.

---

## Packaging Build

If you want to package the GUI into a standalone one-file portable `exe`, run:

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
*The build output will be written to `dist/MergeLivePhotoTool.exe`. If UPX is installed and available in `PATH`, PyInstaller will automatically try to compress the executable further.*

---

## Project Structure and Configuration

- **Local configuration**: User settings are automatically saved to `%APPDATA%\MergeLivePhotoGUI\settings.json`.
- `merge_live_photo_gui.py`: Main UI, scanning, merging, static photo separation, and summary processing logic.
- `merge_live_photo.py`: Command-line batch merge script.
- `merge_live_photo_translations.py`: GUI localization text.

## License
This project is distributed under the `LICENSE` file in the repository.
