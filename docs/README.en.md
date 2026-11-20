# AzureKiln Photo Tool

[简体中文](../README.md) | [繁體中文](README.zh-TW.md) | English

AzureKiln Photo Tool is a Windows-focused motion photo toolkit. It combines nine feature pages into one PyQt6 / Fluent-style GUI with a Windows-style sidebar:

- **LivePhoto Merge**: batch merge same-name image and video pairs into Motion Photos recognized by Google Photos and Microsoft Photos.
- **Huawei LivePhoto Split**: batch split single Huawei LivePhoto JPG files into `JPG + MP4`.
- **Flyme LivePhoto Fix**: repair metadata compatibility for legacy Live Photos captured by Flyme system cameras before Flyme 12.6.
- **Fix Photo Timestamps**: restore file creation, modification, and access times from capture time.
- **Rename Photos/Videos**: batch rename photos and videos to `IMG_YYYYMMDD_HHMMSS` / `VID_YYYYMMDD_HHMMSS` based on the read timestamp.
- **Dedupe Media**: find and clean up duplicate images and videos by content hash.
- **Media Statistics**: browse per-folder image, video, and total media counts in a directory tree, and edit and automatically save `readme.txt` in the selected folder.
- **Folder Compare**: pick the files in a messy folder B that are byte-identical to files in a keep-only library A, re-verify them, and move only those to the Recycle Bin. A is never modified.
- **Folder Dedupe**: find byte-identical duplicate copies across subfolders of a single folder, keep one per group, and move the rest to the Recycle Bin.

The top-left menu button expands or collapses the sidebar. Every feature page also keeps its own standalone GUI entry point for isolated use and regression testing.

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

### Folder Compare

- Pick folder A (the keep-only library — **read-only, never modified or deleted**) and folder B (to clean up); both are scanned recursively in the background.
- Lists every copy in B that is **byte-identical** to some file in A; "identical" requires all three checks: **same size → same full-file SHA-256 → byte-by-byte equality**. Files that only duplicate each other inside B, with no counterpart in A, are not handled here.
- A file whose SHA-256 matches but whose bytes differ is reported as "hash mismatch"; unreadable files, permission errors, and files that vanish mid-scan are reported as "read issues". Neither kind is ever recycled.
- **Select all / Select none / Invert selection** only act on currently valid recycle candidates; keeper rows, hash mismatches, read issues, processed, and cancelled rows are protected.
- Both preview slots stay the same width and the splitter between table and preview can be dragged to any useful ratio; long paths wrap at any character and never stretch the preview area.
- Video previews do not depend on the Windows thumbnail cache: when the system thumbnail is unavailable, the first frame is decoded by the bundled Qt Multimedia FFmpeg backend with a timeout. Failures show a reason and are retried a limited number of times; **Retry preview** forces a fresh decode, so a file that finished downloading appears correctly.
- The scan can be exported as a versioned JSON record (mode, scan roots, options, file fingerprints, groups, issues, statistics, and check/processing state) and imported later to continue reviewing. Imported records are treated as untrusted history: out-of-root paths, wrong mode, duplicate targets, or records intersecting the keeper are rejected.
- Recycling from an imported record re-reads every current file and forces a byte-by-byte verification, so changed or deleted files are skipped; cancelled or stale records cannot recycle anything.
- Before each recycle, the pair (target, reference) is re-validated: both still exist, size and modification time still match the scan, and by default the bytes are compared once more (can be turned off for speed). Any failure skips that item with an explicit reason.
- Identical / nested A and B roots (checked on real paths) are rejected with a message. Symbolic links and directory junctions are never followed, and zero-byte files are skipped.
- Each row shows the B and A thumbnails with relative paths, size, modified time, SHA-256 prefix, and status.
- Cleanup is **Recycle Bin only** (`send2trash`); there is no permanent delete.

### Folder Dedupe

- Pick one folder, scan all subfolders recursively, group files by content (byte-identical), keep exactly one file per group, and list the rest for recycling.
- Keep strategies: shallowest / shortest path (default), oldest modified time, newest modified time. Ties fall back to path order, so results are deterministic and repeatable.
- Shares the same scan and verification core as Folder Compare (size → full SHA-256 → byte comparison), including pre-execution re-validation and hash-mismatch protection.
- Also supports **select all / select none / invert selection** (valid candidates only, keepers protected), the equal-width draggable preview, the video first-frame fallback with retry, and versioned JSON record export / import with mandatory byte verification after import.
- Rows of the same group are tinted alternately; keeper rows cannot be checked. The side preview panel shows the selected file next to its group keeper.
- Recycle Bin only, as well.

### Media Statistics

- Drag in, paste, or pick a root folder; it is scanned recursively in the background and shown as a tree of the real directory levels (root / year / month / any nested folder), with empty folders preserved.
- Columns are `Folder / Images / Videos / Total`; the total equals images plus videos, and non-media files such as `readme.txt` are not counted.
- Each row includes the folder's direct media plus media in all its subfolders; every file is counted once by path, with no content deduplication.
- Extension matching reuses the existing format set: images `JPG/JPEG/HEIC/HEIF/PNG/TIF/TIFF/WebP`, videos `MP4/MOV/M4V/3GP/AVI/WMV/MKV`, case-insensitive.
- Counting only enumerates directory entry names and types: no media data is opened, no EXIF is read, no thumbnails are generated, and no hashes are computed.
- OneDrive "online-only" placeholders are included (cloud attributes are never treated as links to skip); real symbolic links and directory junctions are skipped to avoid cycles.
- Supports expand all, collapse all, rescan, and stop; inaccessible folders or a stopped scan keep the partial result and are clearly marked incomplete.
- Selecting any folder node loads the `readme.txt` **directly inside that folder** below the tree for editing (case-insensitive name, parent readme is never inherited).
- The compact editor leaves more height for the folder tree. Changes save automatically after about 0.8 seconds of inactivity or when focus leaves the editor; no save button is needed.
- If no readme exists, start typing to create `readme.txt` in that folder using UTF-8. Viewing an empty editor creates nothing. Both loading and saving have a 2 MiB limit.
- Recognized encodings (UTF-8 / UTF-8 BOM / UTF-16 BOM / GB18030) and common newline styles are preserved; saving writes a temporary file and replaces the original, so a failed write leaves the original untouched.
- Switching folders, rescanning, or quitting first saves the latest draft. Failed saves keep the text and offer retry / discard / cancel. External modification, deletion, or creation of a competing readme is reported as a conflict and never silently overwritten.
- Online-only readme caveat: a `readme.txt` is only read on demand when its folder is selected, and OneDrive may download that text at that point; being offline or a read failure only affects the readme area with a visible message, never the statistics themselves, and never triggers other media downloads. Directory enumeration itself may make the cloud client fetch directory metadata, so the scan is not promised to be entirely network-free.

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
- Video first frames use the Qt Multimedia FFmpeg backend bundled in the PyQt6 wheel; no separate FFmpeg install is needed, and the release bundle self-check requires that backend

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
2. Choose a feature page from the sidebar: `LivePhoto Merge`, `Huawei LivePhoto Split`, `Flyme LivePhoto Fix`, `Fix Photo Timestamps`, `Rename Photos/Videos`, `Dedupe Media`, `Media Statistics`, `Folder Compare`, `Folder Dedupe`.
3. Use the top-left menu button to collapse or expand the sidebar.
4. Configure source folder, output folder, scan rules, and conflict behavior in the selected page.
5. Start the current page's merge, split, or repair workflow.

Each feature page keeps its own standalone entry point as well:

```powershell
python merge_live_photo_gui.py
python split_huawei_live_photo_gui.py
python main_gui.py
python timestamp_fix_gui.py
python rename_photo_gui.py
python dedupe_media_gui.py
python media_statistics_gui.py
python dir_compare_gui.py
python folder_dedupe_gui.py
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

- **Push to any branch**: installs `requirements-build.txt`, runs the standard-library unittest suite under `tests/` with offscreen Qt (`QT_QPA_PLATFORM=offscreen`) and an isolated `APPDATA`, then builds the onefile exe from `AzureKilnPhotoTool_onefile.spec` (ExifTool 13.58 injected after SHA256 verification). The bundle self-check requires `pillow_heif`, ExifTool, the Qt Multimedia FFmpeg video first-frame backend, and the page modules before producing the portable zip, SHA256 file, and Inno Setup installer as workflow artifacts (no Release).
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

- `unified_gui.py`: unified sidebar GUI entry point hosting nine feature pages.
- `merge_live_photo_gui.py`: LivePhoto merge page and standalone entry point.
- `merge_live_photo.py`: command-line batch merge script.
- `split_huawei_live_photo_gui.py`: Huawei LivePhoto split page and standalone entry point.
- `split_huawei_live_photo.py`: command-line split script.
- `main_gui.py`: Flyme LivePhoto repair page and standalone entry point.
- `main_gui_logic.py`: Flyme scanning, classification, output, and repair workflow.
- `flyme_livephoto_fix_core.py`: ExifTool-based detection and repair engine.
- `media_statistics_gui.py`: media statistics and folder `readme.txt` editor page and standalone entry point.
- `media_statistics_core.py`: standard-library-only recursive folder scan and image/video counting core (no PyQt).
- `media_readme_core.py`: standard-library-only `readme.txt` encoding detection, loading, safe creation, and atomic saving core (no PyQt).
- `duplicate_scan_core.py`: standard-library-only scan and verification core (no PyQt) for folder compare / folder dedupe: enumeration, hashing, byte comparison, pre-execution re-validation, recycling.
- `scan_record_core.py`: standard-library-only scan-record JSON format, save/load, and untrusted-history validation (no PyQt).
- `media_thumbnail.py`: async thumbnail loader and side preview panel shared by the Folder Compare and Folder Dedupe pages.
- `dir_compare_gui.py`: Folder Compare page and standalone entry point.
- `folder_dedupe_gui.py`: Folder Dedupe page and standalone entry point.
- `tests/`: standard-library `unittest` regressions (scan core, record format, thumbnail/video fallback, page bulk selection and record entry points), no third-party test framework.
- `*_translations.py`: GUI localization text.
- `requirements.txt` / `requirements-build.txt`: pinned runtime / build dependencies.
- `AzureKilnPhotoTool_onefile.spec`: onefile PyInstaller spec (bundles ExifTool and the Qt Multimedia video backend).
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
