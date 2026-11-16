# AzureKiln Photo Tool

[简体中文](../README.md) | 繁體中文 | [English](README.en.md)

AzureKiln Photo Tool 是面向 Windows 的動態照片處理工具集。現在已將七個功能頁整合到同一個 PyQt6 / Fluent 風格 GUI，並使用 Windows 風格左側邊欄切換功能頁：

- **LivePhoto 合併**：將同名照片與影片批次合成為 Google / Microsoft Photos 可識別的 Motion Photo。
- **華為 LivePhoto 分離**：將華為相機或系統合併得到的單一 LivePhoto JPG 批次拆分為 `JPG + MP4`。
- **Flyme LivePhoto 修復**：修復 Flyme 12.6 以下版本系統相機拍攝的舊 LivePhoto 中繼資料相容性問題。
- **照片時間戳記修復**：從拍攝時間還原檔案的建立、修改與存取時間。
- **照片/影片重新命名**：依讀取到的時間將照片與影片批次重新命名為 `IMG_年月日_時分秒` / `VID_年月日_時分秒`。
- **圖片影片去重**：依內容雜湊尋找並清理重複的圖片與影片。
- **媒體統計**：依資料夾層級樹檢視圖片、影片與媒體總項數，並編輯所選目錄既有的 `readme.txt`。

左上角選單按鈕可展開或收合邊欄。每個功能頁也都保留各自的獨立 GUI 入口，方便單獨執行或回歸測試。

## 核心功能

### LivePhoto 合併

- 自動掃描 `JPG/JPEG/HEIC/HEIF` 圖片，並依同名規則匹配 `MP4/MOV` 影片。
- 批次合成為 Google Photos / Microsoft Photos 可識別的 Motion Photo。
- 盡量保留原始 EXIF、拍攝時間與檔案時間。
- 可將沒有匹配影片的靜態照片整理到 `Static_Photos`。
- 支援彙總輸出到 `All_Processed_Summary`。
- 可透過 `pillow-heif` 啟用 HEIC/HEIF 支援。

### 華為 LivePhoto 分離

- 支援掃描目前資料夾或所有子資料夾。
- 自動識別華為內嵌 LivePhoto JPG、普通靜態照片，以及同名 `JPG + MP4` 檔案。
- 將內嵌 LivePhoto 拆分為同名 `.jpg` 與 `.mp4`。
- 輸出時保留來源目錄層級，並可分別設定照片與影片衝突策略。

### Flyme LivePhoto 修復

- 自動區分待修復 Flyme 動態照片、已相容動態照片、靜態照片、其他手機照片和無關檔案。
- 基於 ExifTool 修補中繼資料，讓舊 Flyme LivePhoto 能被 Microsoft Photos、Google Photos 等平台識別。
- 支援拖曳匯入、非同步掃描、框選、排序、右鍵選單、複製/移動/修復並輸出。
- 可依類別控制匯出範圍，並記憶輸出目錄、語言和處理選項。

### 媒體統計

- 拖曳、貼上或選擇一個根目錄，於背景遞迴掃描後依實際目錄層級（根目錄 / 年份 / 月份 / 任意巢狀子目錄）顯示樹狀結構，空目錄保留。
- 欄位為「資料夾 / 圖片 / 影片 / 總項數」；總項數等於圖片數加影片數，`readme.txt` 等非媒體檔案不計入。
- 每一列包含該目錄的直屬媒體及其所有子目錄中的媒體；每個檔案依路徑計一次，不做內容去重。
- 副檔名沿用本工具既有格式集：圖片 `JPG/JPEG/HEIC/HEIF/PNG/TIF/TIFF/WebP`，影片 `MP4/MOV/M4V/3GP/AVI/WMV/MKV`，不分大小寫。
- 統計僅列舉目錄項名稱與類型，不開啟媒體資料、不讀取 EXIF、不產生縮圖、不計算雜湊。
- 支援 OneDrive「僅線上」預留項目（雲端屬性不會被當成連結跳過）；跳過符號連結與目錄聯結以避免循環。
- 支援展開全部、收合全部、重新掃描與停止掃描；無法存取或中途停止時保留已掃描結果並標示為不完整。
- 選取任一目錄節點後，於樹狀結構下方載入並編輯該目錄**直接包含**的 `readme.txt`（名稱不分大小寫，不繼承上層說明）。
- 僅編輯既有的說明檔案，不建立新檔案；最高載入 2 MiB，超過上限時禁止編輯。
- 保留可辨識的原編碼（UTF-8 / UTF-8 BOM / UTF-16 BOM / GB18030）與原換行風格；儲存時採臨時檔加置換，寫入失敗時原檔案不受損。
- 有未儲存修改時，切換目錄、重新掃描或退出會提供儲存 / 放棄 / 取消；外部修改或刪除說明檔案時提示衝突，不靜默覆蓋。
- 僅線上說明檔案的邊界：選取目錄時才按需讀取 `readme.txt`，OneDrive 可能因此下載該文字；離線或讀取失敗只影響說明區塊並給出提示，不影響統計，也不觸發其他媒體內容下載。目錄列舉本身可能讓雲端客戶端取回目錄中繼資料，因此不保證統計過程完全不產生網路存取。

## 已測試設備

| 平台 | 設備 | 系統版本 | 覆蓋功能 |
| --- | --- | --- | --- |
| HarmonyOS | HUAWEI Mate 20 | HarmonyOS 4.0.0.121 | 華為 LivePhoto 分離 |
| HarmonyOS | HUAWEI nova 5z | HarmonyOS 2.0.0.165 | 華為 LivePhoto 分離 |
| HarmonyOS NEXT | HUAWEI nova 14 Ultra | HarmonyOS 5 / 6 | 華為分離、LivePhoto 合併 |
| iOS | iPhone 6s Plus | iOS 15.8.7 | LivePhoto 合併 |
| iOS | iPhone 7 Plus | iOS 14.8.1 | LivePhoto 合併 |
| Flyme | Meizu 21 / 21 Note | Flyme 12.6 以下 | Flyme LivePhoto 修復 |

## 快速開始

### Windows 可攜版

- 作業系統：Windows 10 / 11 x64
- 執行環境：不需要安裝 Python

在 [GitHub Releases](https://github.com/azurekiln2333/azurekiln-photo-tool/releases) 下載以下任一形式：

- 安裝程式 `AzureKilnPhotoTool-<版本>-<日期>-windows-x64-setup.exe`：安裝時可選「僅目前使用者（免管理員）」或「所有使用者（需管理員）」，建立開始功能表捷徑（可選桌面捷徑），可在「設定 → 應用程式」中解除安裝。
- 可攜包 `AzureKilnPhotoTool-<版本>-<日期>-windows-x64-portable.zip` 與同名 SHA256 檔案，解壓縮後執行：

```text
AzureKilnPhotoTool.exe
```

SHA256 檔案記錄的是 `AzureKilnPhotoTool.exe` 的雜湊，校驗範例：

```powershell
Get-FileHash .\AzureKilnPhotoTool.exe -Algorithm SHA256
Get-Content .\AzureKilnPhotoTool-1.1.0-20261108-windows-x64-portable.sha256.txt
```

程式未做程式碼簽章，首次執行時 Windows SmartScreen 可能提示「未知的發行者」。

### 從原始碼執行

執行依賴：

- Python 3.10+
- `PyQt6`
- `PyQt6-Fluent-Widgets`
- `PyQt6-Frameless-Window` 或 `qframelesswindow`
- `Pillow`
- 可選：`pillow-heif`，用於 HEIC/HEIF 支援
- 可選：`send2trash`，用於移入回收站
- `pywin32`：系統右鍵選單
- Flyme 修復需要 `ExifTool`

上述依賴的固定版本見 `requirements.txt`（發布構建所用版本，建議 Python 3.14）：

```powershell
python -m venv .venv
.\.venv\Scripts\activate

pip install -r requirements.txt

python unified_gui.py
```

ExifTool 查找順序：

```text
vendor/exiftool/exiftool.exe
exiftool/exiftool.exe
bin/exiftool.exe
系統 PATH
```

## 使用說明

1. 啟動統一 GUI：`python unified_gui.py` 或執行可攜版 `AzureKilnPhotoTool.exe`。
2. 透過左側邊欄選擇功能頁：`LivePhoto 合併`、`華為 LivePhoto 分離`、`Flyme LivePhoto 修復`、`照片時間戳記修復`、`照片/影片重新命名`、`圖片影片去重`、`媒體統計`。
3. 點擊左上角選單按鈕可收合或展開邊欄。
4. 在對應功能頁設定來源資料夾、輸出資料夾、掃描規則和衝突策略。
5. 點擊目前頁面的開始、分離或修復按鈕執行批次處理。

各功能頁也保留獨立執行入口：

```powershell
python merge_live_photo_gui.py
python split_huawei_live_photo_gui.py
python main_gui.py
python timestamp_fix_gui.py
python rename_photo_gui.py
python dedupe_media_gui.py
python media_statistics_gui.py
```

## 命令列工具

LivePhoto 合併：

```powershell
python merge_live_photo.py .\input_dir .\output_dir
```

華為 LivePhoto 分離：

```powershell
python split_huawei_live_photo.py .\sample\HarmonyOS4\Source\IMG_20260515_230101.jpg .\sample\HarmonyOS4\SplitOutput
python split_huawei_live_photo.py .\sample\HarmonyOS4\Source .\sample\HarmonyOS4\SplitOutput
```

Flyme 修復的批次流程主要透過 GUI 提供，核心邏輯位於 `flyme_livephoto_fix_core.py` 與 `main_gui_logic.py`。

## 打包構建

### 雲端構建與發布（GitHub Actions）

`.github/workflows/build.yml` 在 Windows runner 上完成全部打包：

- **push 到任意分支**：安裝 `requirements-build.txt`，下載固定版本 ExifTool（13.58，校驗 SHA256），以 `AzureKilnPhotoTool_onefile.spec` 打包單一執行檔，自檢產物含 `pillow_heif` 與 ExifTool，產生可攜 zip、SHA256 檔案與 Inno Setup 安裝程式，作為 workflow artifact 上傳（不發布 Release）。
- **推送 `vX.Y.Z` 標籤**：執行同樣的構建，並自動建立 GitHub Release，上傳可攜 zip、`.sha256.txt` 與安裝程式。

版本號唯一來源是 `unified_gui.py` 中的 `APP_VERSION`，標籤必須與之一致，否則構建失敗、不發布：

```powershell
# 1. 修改 unified_gui.py 中 APP_VERSION = "1.1.0" 並提交、推送
# 2. 建立標籤並推送
git tag v1.1.0
git push github v1.1.0
```

### 本機構建

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt

# ExifTool 目錄（含 exiftool.exe 與 exiftool_files/），預設 D:\ProgramFiles\exiftool
$env:EXIFTOOL_DIR = "D:\ProgramFiles\exiftool"
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm AzureKilnPhotoTool_onefile.spec

# 可選：自檢並產生可攜 zip + SHA256（輸出到 release/）
.\.venv\Scripts\python.exe scripts\ci\verify_bundle.py
.\.venv\Scripts\python.exe scripts\ci\package_portable.py --version (.\.venv\Scripts\python.exe scripts\ci\get_version.py)

# 可選：安裝程式（需安裝 Inno Setup 6）
iscc /DAppVersion=1.1.0 installer\AzureKilnPhotoTool.iss
```

注意：不要加 `--clean`；必須使用裝齊依賴的 `.venv`，否則會靜默遺失 HEIC 與回收站功能。

## 專案結構

- `unified_gui.py`：七個功能頁合一的側欄 GUI 入口。
- `merge_live_photo_gui.py`：LivePhoto 合併頁面和獨立入口。
- `merge_live_photo.py`：命令列批次合併腳本。
- `split_huawei_live_photo_gui.py`：華為 LivePhoto 分離頁面和獨立入口。
- `split_huawei_live_photo.py`：命令列分離腳本。
- `main_gui.py`：Flyme LivePhoto 修復頁面和獨立入口。
- `main_gui_logic.py`：Flyme 檔案掃描、分類、輸出和修復流程。
- `flyme_livephoto_fix_core.py`：基於 ExifTool 的識別與修復引擎。
- `media_statistics_gui.py`：媒體統計與目錄 `readme.txt` 編輯頁面和獨立入口。
- `media_statistics_core.py`：純標準庫的目錄遞迴掃描與圖片/影片計數核心（不依賴 PyQt）。
- `media_readme_core.py`：純標準庫的 `readme.txt` 編碼辨識、讀取與原子儲存核心（不依賴 PyQt）。
- `*_translations.py`：各功能 GUI 的多語言文字。
- `requirements.txt` / `requirements-build.txt`：固定版本的執行 / 打包依賴。
- `AzureKilnPhotoTool_onefile.spec`：單一執行檔打包設定（含 ExifTool）。
- `installer/AzureKilnPhotoTool.iss`：Inno Setup 安裝程式腳本。
- `scripts/ci/`：版本讀取、產物自檢、可攜包產生腳本（CI 與本機共用）。
- `.github/workflows/build.yml`：雲端構建與發布流程。
- `sample/`：測試樣例。

本機設定保存位置：

```text
%APPDATA%\MergeLivePhotoGUI\settings.json
%APPDATA%\SplitHuaweiLivePhotoGUI\settings.json
%APPDATA%\FlymeLivePhotoFix\settings.json
```

## 開源協議

本專案基於倉庫中的 `LICENSE` 文件發布。
