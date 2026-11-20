# AzureKiln Photo Tool

[简体中文](../README.md) | 繁體中文 | [English](README.en.md)

AzureKiln Photo Tool 是面向 Windows 的動態照片處理工具集。現在已將九個功能頁整合到同一個 PyQt6 / Fluent 風格 GUI，並使用 Windows 風格左側邊欄切換功能頁：

- **LivePhoto 合併**：將同名照片與影片批次合成為 Google / Microsoft Photos 可識別的 Motion Photo。
- **華為 LivePhoto 分離**：將華為相機或系統合併得到的單一 LivePhoto JPG 批次拆分為 `JPG + MP4`。
- **Flyme LivePhoto 修復**：修復 Flyme 12.6 以下版本系統相機拍攝的舊 LivePhoto 中繼資料相容性問題。
- **照片時間戳記修復**：從拍攝時間還原檔案的建立、修改與存取時間。
- **照片/影片重新命名**：依讀取到的時間將照片與影片批次重新命名為 `IMG_年月日_時分秒` / `VID_年月日_時分秒`。
- **圖片影片去重**：依內容雜湊尋找並清理重複的圖片與影片。
- **媒體統計**：依資料夾層級樹檢視圖片、影片與媒體總項數，並編輯、自動儲存所選目錄的 `readme.txt`。
- **目錄比對**：從「待清理目錄 B」挑出與「保留目錄 A」逐位元組一致的檔案，先複核再移入回收站，A 唯讀不動。
- **目錄內去重**：在單一目錄內跨子目錄找出逐位元組一致的重複副本，每組只留一個，其餘移入回收站。

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

### 目錄比對

- 選擇目錄 A（保留庫，**唯讀，絕不修改或刪除其中任何檔案**）與目錄 B（待清理），於背景遞迴掃描兩者的全部子目錄。
- 列出 B 中所有與 A 中某個檔案**逐位元組一致**的副本；判定只採用三重複核：**大小相同 → 完整檔案 SHA-256 相同 → 逐位元組比對完全相同**。只在 B 內部重複、A 中不存在的檔案本頁不處理。
- SHA-256 相同但逐位元組不同的檔案（雜湊碰撞或異常改名）標記為「複核不一致」，讀取失敗、權限不足、掃描中消失的檔案標記為「讀取問題」，兩類都**絕不回收**。
- 掃描結束後仍可繼續操作：**全選 / 全不選 / 反選**只作用於目前合法的待回收副本；保留項、複核異常、讀取問題、已處理、已取消的列不會被批次選中。
- 兩側預覽槽始終等寬，拖曳表格與預覽之間的分隔條即可調整寬度；長路徑依任意字元換行，不會把預覽區擠開。
- 影片預覽不依賴 Windows 縮圖快取：系統縮圖取不到時由內建 Qt Multimedia FFmpeg 後端解碼首幀（帶逾時），失敗會顯示原因並自動有限重試；可點擊「重試預覽」強制重新解碼，已下載完成的檔案會隨之正常顯示。
- 可將本次掃描匯出為帶版本的 JSON 記錄（模式、掃描根、選項、檔案指紋、分組、異常、統計與勾選/處理狀態），之後重新匯入繼續複核。匯入的記錄視為不可信的歷史資料：越界路徑、錯誤模式、重複目標或與保留項相交的記錄會被拒絕。
- 從匯入記錄執行回收時，會對每一對檔案重新讀取目前檔案並強制逐位元組複核，已刪除或已修改的檔案會被跳過；已取消或失效的記錄不能回收。
- 執行回收前對每一對（目標, 參照檔案）重新複核：兩者都存在、大小與修改時間與掃描時一致；預設還會再逐位元組複核一次（可關閉以提速）。任一不滿足就跳過並給出原因。
- A 與 B 相同、A 在 B 內、B 在 A 內（解析真實路徑後判斷）→ 拒絕掃描並提示。不跟隨符號連結 / 目錄聯結，預設跳過 0 位元組檔案。
- 每列顯示 B 與 A 的縮圖及相對路徑、大小、修改時間、SHA-256 前綴與狀態。
- **只移入回收站**（`send2trash`），不提供永久刪除。

### 目錄內去重

- 選擇一個目錄，遞迴掃描全部子目錄，依內容（逐位元組一致）分組，每組保留 1 個檔案，其餘列為回收對象。
- 保留策略可選：層級最淺 / 路徑最短（預設）、修改時間最早、修改時間最新；平手時依路徑排序，結果確定可重現。
- 與「目錄比對」共用同一套掃描與複核核心（大小 → 完整 SHA-256 → 逐位元組比對），同樣帶執行前複核與「複核不一致」保護。
- 同樣支援**全選 / 全不選 / 反選**（僅作用於合法副本，保留列受保護）、等寬可拖曳預覽、影片首幀解碼回退與重試，以及帶版本 JSON 記錄匯出 / 匯入與匯入後強制逐位元組複核。
- 表格中同組列以交替底色區分，保留列不可勾選；右側預覽面板顯示所選檔案與本組保留檔案。
- 同樣只移入回收站。

### 媒體統計

- 拖曳、貼上或選擇一個根目錄，於背景遞迴掃描後依實際目錄層級（根目錄 / 年份 / 月份 / 任意巢狀子目錄）顯示樹狀結構，空目錄保留。
- 欄位為「資料夾 / 圖片 / 影片 / 總項數」；總項數等於圖片數加影片數，`readme.txt` 等非媒體檔案不計入。
- 每一列包含該目錄的直屬媒體及其所有子目錄中的媒體；每個檔案依路徑計一次，不做內容去重。
- 副檔名沿用本工具既有格式集：圖片 `JPG/JPEG/HEIC/HEIF/PNG/TIF/TIFF/WebP`，影片 `MP4/MOV/M4V/3GP/AVI/WMV/MKV`，不分大小寫。
- 統計僅列舉目錄項名稱與類型，不開啟媒體資料、不讀取 EXIF、不產生縮圖、不計算雜湊。
- 支援 OneDrive「僅線上」預留項目（雲端屬性不會被當成連結跳過）；跳過符號連結與目錄聯結以避免循環。
- 支援展開全部、收合全部、重新掃描與停止掃描；無法存取或中途停止時保留已掃描結果並標示為不完整。
- 選取任一目錄節點後，於樹狀結構下方載入並編輯該目錄**直接包含**的 `readme.txt`（名稱不分大小寫，不繼承上層說明）。
- 說明區保持精簡，視窗高度優先留給目錄表；停止輸入約 0.8 秒或離開編輯框時自動儲存，無須點擊按鈕。
- 沒有說明檔案時可直接輸入，自動建立目前目錄的 `readme.txt`（UTF-8）；僅查看空白不會建立檔案。讀取與儲存上限均為 2 MiB。
- 保留可辨識的原編碼（UTF-8 / UTF-8 BOM / UTF-16 BOM / GB18030）與原換行風格；儲存時採臨時檔加置換，寫入失敗時原檔案不受損。
- 切換目錄、重新掃描或退出前自動儲存最新草稿；儲存失敗會保留文字並提供重試 / 放棄 / 取消。外部修改、刪除或搶先建立說明檔案時提示衝突，不靜默覆蓋。
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
- 影片首幀預覽使用 PyQt6 內建的 Qt Multimedia FFmpeg 後端，無需另外安裝 FFmpeg；發布包會自檢該後端是否齊全

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
2. 透過左側邊欄選擇功能頁：`LivePhoto 合併`、`華為 LivePhoto 分離`、`Flyme LivePhoto 修復`、`照片時間戳記修復`、`照片/影片重新命名`、`圖片影片去重`、`媒體統計`、`目錄比對`、`目錄內去重`。
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
python dir_compare_gui.py
python folder_dedupe_gui.py
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

- **push 到任意分支**：安裝 `requirements-build.txt`，先以離屏 Qt（`QT_QPA_PLATFORM=offscreen`）與隔離 `APPDATA` 執行 `tests/` 下的標準庫 unittest，再以 `AzureKilnPhotoTool_onefile.spec` 打包單一執行檔（ExifTool 13.58 校驗 SHA256 後注入），自檢產物含 `pillow_heif`、ExifTool、Qt Multimedia FFmpeg 影片首幀後端與頁面模組，產生可攜 zip、SHA256 檔案與 Inno Setup 安裝程式，作為 workflow artifact 上傳（不發布 Release）。
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

- `unified_gui.py`：九個功能頁合一的側欄 GUI 入口。
- `merge_live_photo_gui.py`：LivePhoto 合併頁面和獨立入口。
- `merge_live_photo.py`：命令列批次合併腳本。
- `split_huawei_live_photo_gui.py`：華為 LivePhoto 分離頁面和獨立入口。
- `split_huawei_live_photo.py`：命令列分離腳本。
- `main_gui.py`：Flyme LivePhoto 修復頁面和獨立入口。
- `main_gui_logic.py`：Flyme 檔案掃描、分類、輸出和修復流程。
- `flyme_livephoto_fix_core.py`：基於 ExifTool 的識別與修復引擎。
- `media_statistics_gui.py`：媒體統計與目錄 `readme.txt` 編輯頁面和獨立入口。
- `media_statistics_core.py`：純標準庫的目錄遞迴掃描與圖片/影片計數核心（不依賴 PyQt）。
- `media_readme_core.py`：純標準庫的 `readme.txt` 編碼辨識、讀取、安全建立與原子儲存核心（不依賴 PyQt）。
- `duplicate_scan_core.py`：純標準庫的目錄比對 / 目錄內去重掃描與複核核心（不依賴 PyQt）：列舉、雜湊、逐位元組比對、執行前複核、回收。
- `scan_record_core.py`：純標準庫的掃描記錄 JSON 格式、儲存/讀取與不可信歷史複核（不依賴 PyQt）。
- `media_thumbnail.py`：目錄比對與目錄內去重頁共用的非同步縮圖載入器與側邊預覽面板。
- `dir_compare_gui.py`：目錄比對頁面和獨立入口。
- `folder_dedupe_gui.py`：目錄內去重頁面和獨立入口。
- `tests/`：標準庫 `unittest` 回歸（掃描核心、記錄格式、縮圖/影片回退、頁面批次勾選與記錄入口），無第三方測試框架。
- `*_translations.py`：各功能 GUI 的多語言文字。
- `requirements.txt` / `requirements-build.txt`：固定版本的執行 / 打包依賴。
- `AzureKilnPhotoTool_onefile.spec`：單一執行檔打包設定（含 ExifTool 與 Qt Multimedia 影片後端）。
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
