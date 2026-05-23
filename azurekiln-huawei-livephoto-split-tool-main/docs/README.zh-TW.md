# 華為LivePhoto批量分離工具

[简体中文](../README.md) | 繁體中文 | [English](README.en.md)

該專案用於將華為相機拍攝或由系統合併得到的 LivePhoto 單個 JPG 檔案批量分離為靜態照片與動態影片檔案。分離後的 `JPG + MP4` 可用於後續重新合成為 Motion Photo 標準格式，以便在 Windows Photos、Google Photos 等相簿應用中正常播放動態照片。

專案基於 `PyQt6` 與 `PyQt6-Fluent-Widgets` 建構 Windows 11 風格 GUI，介面風格盡量與同倉庫的 `merge_live_photo_gui.py` 保持一致。

## 核心特性

- **批量掃描**：支援掃描目前目錄或所有子目錄。
- **自動識別**：自動區分華為 LivePhoto JPG、普通靜態照片，以及已存在的同名 JPG/MP4 檔案。
- **批量分離**：內嵌 LivePhoto 會被拆分為同名 `.jpg` 與 `.mp4`。
- **檔案整理**：已存在的同名 JPG/MP4 檔案可複製到統一輸出目錄並保留目錄層級。
- **衝突策略**：照片和影片目標已存在時可分別選擇跳過或覆蓋。
- **中英文切換**：GUI 文案已分離到 `split_huawei_live_photo_translations.py`。
- **設定記憶**：語言、輸入輸出目錄、掃描規則、衝突策略會儲存到本機設定。

## 已測試裝置

| 平台 | 裝置 | 代號 | 系統版本 | 來源 |
| --- | --- | --- | --- | --- |
| HarmonyOS | HUAWEI Mate 20 | HMA-AL00 | HarmonyOS 4.0.0.121 | 本機 LivePhoto JPG 檔案 |
| HarmonyOS | HUAWEI nova 5z | SPN-AL00 | HarmonyOS 2.0.0.165 | 本機 LivePhoto JPG 檔案 |
| HarmonyOS NEXT | HUAWEI nova 14 Ultra | MRT-AL10 | HarmonyOS 5 / 6 | 合併後的單個 LivePhoto JPG 檔案 |

> HarmonyOS 5 / 6 拍攝後，透過華為雲下載、系統介面呼叫、檔案管理複製，或分享給 HarmonyOS 4 及以下裝置等方式得到的單個 LivePhoto JPG 檔案，也支援分離為 JPG 和 MP4。

## 快速開始

### 1. Windows 便攜版直接執行

- 作業系統：Windows 10 / 11
- 執行環境：無需安裝 Python

從 release 下載以下兩個檔案：

```text
SplitHuaweiLivePhotoTool-1.0.0-20260523-windows-x64-portable.zip
SplitHuaweiLivePhotoTool-1.0.0-20260523-windows-x64-portable.sha256.txt
```

可選：解壓前校驗 SHA256：

```powershell
Get-FileHash .\SplitHuaweiLivePhotoTool-1.0.0-20260523-windows-x64-portable.zip -Algorithm SHA256
Get-Content .\SplitHuaweiLivePhotoTool-1.0.0-20260523-windows-x64-portable.sha256.txt
```

解壓便攜包後執行：

```text
SplitHuaweiLivePhotoTool.exe
```

便攜包內包含：

- Windows x64 GUI 程式
- 简体中文、繁體中文、English 文件說明

### 2. 原始碼執行

- 執行依賴：Python 3.10+
- 核心元件：`PyQt6`、`PyQt6-Fluent-Widgets`、`PyQt6-Frameless-Window`、`Pillow`

```powershell
python -m venv .venv
.\.venv\Scripts\activate

pip install PyQt6 PyQt6-Fluent-Widgets PyQt6-Frameless-Window Pillow

python split_huawei_live_photo_gui.py
```

命令列分離單個檔案或目錄：

```powershell
python split_huawei_live_photo.py .\sample\HarmonyOS4\Source\IMG_20260515_230101.jpg .\sample\HarmonyOS4\SplitOutput
python split_huawei_live_photo.py .\sample\HarmonyOS4\Source .\sample\HarmonyOS4\SplitOutput
```

## 使用說明

1. 啟動 `SplitHuaweiLivePhotoTool.exe` 或執行 `python split_huawei_live_photo_gui.py`。
2. 選擇來源資料夾。來源資料夾可以包含華為相機拍攝，或透過華為雲、系統介面、檔案管理複製、跨裝置分享等方式得到的單個 LivePhoto JPG 檔案。
3. 確認輸出目錄，按需選擇是否掃描子目錄。
4. 設定目標檔案已存在時的處理策略。
5. 點選 **開始批量分離**。

輸出檔案會按來源目錄層級寫入輸出目錄。普通靜態照片只會標記為跳過，不會複製到輸出目錄。

## 打包建置

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

建置產物：

```text
dist\SplitHuaweiLivePhotoTool.exe
```

## 專案結構

- `split_huawei_live_photo.py`：命令列與核心分離邏輯。
- `split_huawei_live_photo_gui.py`：PyQt6 / Fluent GUI。
- `split_huawei_live_photo_translations.py`：拆分工具中英文 UI 文案。
- `merge_live_photo_gui.py`：合成工具 GUI，可作為介面風格參考。
- `merge_live_photo_translations.py`：合成工具中英文 UI 文案。
- `sample/`：測試樣例。

本機設定儲存位置：

```text
%APPDATA%\SplitHuaweiLivePhotoGUI\settings.json
```

## 開源協議

本專案基於倉庫中的 `LICENSE` 檔案發布。
