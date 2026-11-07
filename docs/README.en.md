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

Download one of the following from [GitHub Releases](https://github.com/azurekiln2333/azurekiln-photo-tool/releases):

- Installer `AzureKilnPhotoTool-<version>-<date>-windows-x64-setup.exe`: choose "current user only (no admin)" or "all users (admin)" during setup; creates a Start menu shortcut (desktop shortcut optional) and can be uninstalled from Settings → Apps.
- Portable `AzureKilnPhotoTool-<version>-<date>-windows-x64-portable.zip` plus the matching SHA256 file. Extract and run:

```text
AzureKilnPhotoTool.exe
```

The SHA256 file records the hash of `AzureKilnPhotoTool.exe`. Checksum example:

```powershell
Get-FileHash .\AzureKilnPhotoTool.exe -Algorithm SHA256
Get-Content .\AzureKilnPhotoTool-1.1.0-20261108-windows-x64-portable.sha256.txt
```

The binaries are not code-signed, so Windows SmartScreen may show an "unknown publisher" warning on first launch.

### Run from Source

Requirements:

- Python 3.10+
- `PyQt6`
- `PyQt6-Fluent-Widgets`
- `PyQt6-Frameless-Window` or `qframelesswindow`
- `Pillow`
- Optional: `pillow-heif` for HEIC/HEIF support
- Optional: `send2trash` for recycle-bin cleanup
- `pywin32` for the system context menu
- Flyme repair requires `ExifTool`

Pinned versions (the ones used for release builds, Python 3.14 recommended) are listed in `requirements.txt`:

```powershell
python -m venv .venv
.\.venv\Scripts\activate

pip install -r requirements.txt

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

### CI Build and Release (GitHub Actions)

`.github/workflows/build.yml` does all packaging on a Windows runner:

- **Push to any branch**: installs `requirements-build.txt`, downloads a pinned ExifTool (13.58, SHA256-verified), builds the onefile exe from `AzureKilnPhotoTool_onefile.spec`, verifies the bundle contains `pillow_heif` and ExifTool, then produces the portable zip, SHA256 file, and Inno Setup installer as workflow artifacts (no Release).
- **Push a `vX.Y.Z` tag**: runs the same build and creates a GitHub Release with the portable zip, `.sha256.txt`, and installer.

The single source of the version is `APP_VERSION` in `unified_gui.py`. The tag must match it, otherwise the build fails and nothing is published:

```powershell
# 1. Set APP_VERSION = "1.1.0" in unified_gui.py, commit and push
# 2. Tag and push the tag
git tag v1.1.0
git push github v1.1.0
```

### Local Build

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt

# ExifTool folder (exiftool.exe + exiftool_files/), default D:\ProgramFiles\exiftool
$env:EXIFTOOL_DIR = "D:\ProgramFiles\exiftool"
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm AzureKilnPhotoTool_onefile.spec

# Optional: verify the bundle and create portable zip + SHA256 (written to release/)
.\.venv\Scripts\python.exe scripts\ci\verify_bundle.py
.\.venv\Scripts\python.exe scripts\ci\package_portable.py --version (.\.venv\Scripts\python.exe scripts\ci\get_version.py)

# Optional: installer (requires Inno Setup 6)
iscc /DAppVersion=1.1.0 installer\AzureKilnPhotoTool.iss
```

Do not pass `--clean`, and always build from a `.venv` with all dependencies installed; otherwise HEIC and recycle-bin support are silently dropped.

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
- `requirements.txt` / `requirements-build.txt`: pinned runtime / build dependencies.
- `AzureKilnPhotoTool_onefile.spec`: onefile PyInstaller spec (bundles ExifTool).
- `installer/AzureKilnPhotoTool.iss`: Inno Setup installer script.
- `scripts/ci/`: version, bundle-check, and portable-packaging scripts (shared by CI and local builds).
- `.github/workflows/build.yml`: CI build and release workflow.
- `sample/`: test samples.

Local settings:

```text
%APPDATA%\MergeLivePhotoGUI\settings.json
%APPDATA%\SplitHuaweiLivePhotoGUI\settings.json
%APPDATA%\FlymeLivePhotoFix\settings.json
```

## License

This project is released under the license in `LICENSE`.
