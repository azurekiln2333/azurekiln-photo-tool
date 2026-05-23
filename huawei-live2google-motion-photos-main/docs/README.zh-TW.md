# Merge LivePhoto Tool（Google Motion Photo 批次合成工具）

[简体中文](../README.md) | 繁體中文 | [English](README.en.md)

這個專案用於將分離儲存的照片與同名動態影片批次合成為 Google Photos / Microsoft Photos 可識別的 Motion Photo 檔案。

目前 HarmonyOS NEXT（包含 HarmonyOS 5/6）、iOS、OriginOS 拍攝動態照片時，會拆成 `JPG/HEIC` 靜態圖與 `MP4/MOV` 影片兩個檔案儲存。

這個專案的誕生，是為了能夠批次將這兩個檔案合併成符合 Motion Photo 標準的動態照片檔案。它支援依檔名自動匹配靜態照片與對應影片，合併處理後可在 Windows Photos、Google Photos 等平台中正常播放動態效果。

在合併過程中，專案會盡可能保留原始 EXIF 資訊、拍攝時間等中繼資料。

同時，專案基於 `PyQt6` 設計了 Windows 11 風格的 GUI，並提供靜態照片分離、HEIC 轉 JPG、彙總輸出與回收站清理等功能，以提升批次整理體驗。

## 核心特性

**智慧匹配與合成**
- **自動配對**：自動掃描 `JPG/JPEG/HEIC/HEIF` 圖片，並依同名規則匹配 `MP4/MOV` 影片。
- **批次合成**：一鍵將圖片與影片合成為 Google Photos 可識別的 Motion Photo。
- **時間保留**：輸出檔案優先使用照片 EXIF 拍攝時間，缺失時回退沿用原檔案時間。
- **防衝突機制**：當目標目錄已有同名檔案時，可自由選擇「跳過」或「覆蓋」。

**彈性整理與匯出**
- **靜態照片分離**：沒有匹配影片的一般照片可自動複製到 `Static_Photos` 目錄。
- **HEIC 處理**：支援讀取 HEIC/HEIF；靜態 HEIC 可依需求轉換為 JPG，並保留 EXIF/時間戳。
- **彙總輸出**：處理完成後可彙總到 `All_Processed_Summary`，方便一次性檢查或匯入。
- **設定記憶**：自動儲存輸出目錄、介面語言、掃描規則、衝突策略等個人偏好設定。

## 已測試裝置

| 平台 | 裝置 | 系統版本 |
| --- | --- | --- |
| HarmonyOS | nova 14 Ultra | HarmonyOS 5 / 6 |
| iOS | iPhone 6s Plus | iOS 15.8.7 |
| iOS | iPhone 7 Plus | iOS 14.8.1 |

---

## 快速開始

### 1. 執行環境
- 作業系統：Windows 10 / 11
- 執行相依：Python 3.10+
- 核心元件：`PyQt6`、`PyQt6-Fluent-Widgets`、`Pillow`

> **關於 HEIC 與回收站功能的說明**：
> 如需處理 HEIC/HEIF，請安裝 `pillow-heif`。
> 如需啟用「彙總後移入回收站」，請安裝 `send2trash`。

### 2. 由原始碼執行（開發者）

複製倉庫後，安裝相依套件並啟動：

```powershell
# 建立並啟用虛擬環境
python -m venv .venv
.\.venv\Scripts\activate

# 安裝相依套件
pip install PyQt6 PyQt6-Fluent-Widgets qframelesswindow Pillow pillow-heif send2trash

# 啟動程式
python merge_live_photo_gui.py
```

---

## 使用指南

1. **選擇目錄**：啟動程式後，選擇包含圖片與同名影片的來源目錄，並確認輸出目錄。
2. **掃描檔案**：依需求勾選「掃描所有子目錄」，程式會自動尋找圖片並匹配同名 `MP4/MOV`。
3. **設定處理規則**：選擇動態照片、靜態照片遇到同名檔案時的處理策略（跳過或覆蓋），並依需求啟用靜態照片分離、HEIC 轉 JPG、彙總輸出等選項。
4. **一鍵合成／整理**：
   - 點擊 **「開始批次合成」** 按鈕。
   - 有匹配影片的圖片會輸出為 Google Motion Photo。
   - *說明：沒有匹配影片的圖片可依設定分離到 `Static_Photos`，處理結果可彙總到 `All_Processed_Summary`。*

> **提示**：輸出檔案會優先讀取原圖的 EXIF 拍攝時間並寫入檔案時間；如果原圖沒有拍攝時間，則沿用原檔案時間。

---

## 打包構建

若需要將 GUI 打包成單檔免安裝 `exe` 程式，請執行以下命令：

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
*構建產物將輸出至 `dist/MergeLivePhotoTool.exe`。若已安裝 UPX 並加入 `PATH`，PyInstaller 會自動嘗試進一步壓縮可執行檔。*

---

## 專案結構與設定

- **本機設定**：使用者設定會自動儲存到 `%APPDATA%\MergeLivePhotoGUI\settings.json`。
- `merge_live_photo_gui.py`：主介面、掃描、合成、靜態照片分離與彙總處理邏輯。
- `merge_live_photo.py`：命令列批次合成腳本。
- `merge_live_photo_translations.py`：GUI 多語言文字。

## 開源授權
本專案依照倉庫中的 `LICENSE` 檔案發布。
