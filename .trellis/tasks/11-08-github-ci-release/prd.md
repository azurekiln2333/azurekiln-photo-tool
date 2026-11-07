# GitHub Actions CI/CD: onefile exe + installer, release on tag

## Goal

把目前"本机 .venv + 手动 PyInstaller + 手动打 zip/sha256"的发布流程搬到 GitHub Actions：
平时 push 自动云构建（验证可打包、产物可下载），推 `v*` 标签时自动发布 GitHub Release，
附带单文件便携版 zip 与 Windows 安装包。顺带根治"打包环境缺 pillow-heif 导致 HEIC 丢失"这类问题。
本次同时把版本升到 1.1.0 作为首个云端发布版本。

## Background / Confirmed Facts

- 远程：`github` → `https://github.com/azurekiln2333/azurekiln-photo-tool.git`；当前无任何 git tag；无 `.github/`。
- `.gitignore:9` 忽略 `*.spec` → 云端拿不到 `AzureKilnPhotoTool_onefile.spec`。
- 无 `requirements.txt` / `pyproject.toml`。本地 `.venv`（Python 3.14.0）关键依赖：
  PyQt6 6.11.0、PyQt6-Fluent-Widgets 1.11.2、PyQt6-Frameless-Window 0.8.1、pillow 12.2.0、
  pillow_heif 1.3.0、Send2Trash 2.1.0、pywin32 311、pyinstaller 6.20.0。
- `AzureKilnPhotoTool_onefile.spec:30-42` 从 `EXIFTOOL_DIR`（默认 `D:\ProgramFiles\exiftool`）打包
  `exiftool.exe` + 整个 `exiftool_files/`；缺失时只打印警告继续。本地 ExifTool 版本 13.58。
- 版本号硬编码在 `unified_gui.py:37` `APP_VERSION = "1.0.0"`。
- 现有发布命名规范（`.trellis/spec/python/packaging.md`）：
  `AzureKilnPhotoTool-<版本>-<YYYYMMDD>-windows-x64-portable.zip` + 同名 `.sha256.txt`，
  zip 内含 exe + sha256.txt；sha256 文件格式 `<hash>  AzureKilnPhotoTool.exe`。

## Requirements

- R1 依赖清单：新增固定版本依赖清单（与本地 `.venv` 版本一致，含 pillow-heif、pyinstaller），CI 与本地共用。
- R2 spec 入库：`AzureKilnPhotoTool_onefile.spec` 纳入版本库（调整 `.gitignore`），其他 spec 保持忽略。
- R3 ExifTool：CI 下载固定版本 ExifTool 13.58（校验 SHA256）并通过 `EXIFTOOL_DIR` 注入；
  在 CI 环境中缺失 ExifTool 必须构建失败（本地行为不变）。
- R4 push 构建：push 到任意分支触发 Windows 构建，产出单文件 exe 便携 zip + 安装包，作为 workflow artifact 上传，不发布 Release。
- R5 Release：推 `v*` 标签时构建并创建 GitHub Release，上传 portable zip、`.sha256.txt`、安装包。
- R6 构建自检：CI 中验证打包产物内含 `pillow_heif` 与 ExifTool（`exiftool_files/perl.exe`、`exiftool.pl`），缺失即失败。
- R7 安装包：Inno Setup 安装程序，安装时由用户选择"仅当前用户（免管理员，`%LOCALAPPDATA%\Programs`）/ 所有用户（需 UAC，`Program Files`）"；
  开始菜单快捷方式、可选桌面快捷方式、可在"应用和功能"卸载。
- R8 单文件便携版：与安装包同一次构建产出、一起发布，沿用现有命名规范。
- R9 版本号：以 `unified_gui.py` 的 `APP_VERSION` 为唯一来源；标签构建时 `vX.Y.Z` 必须等于 `APP_VERSION`，否则失败、不发布。
  分支构建用 `APP_VERSION` 命名产物。
- R10 升版：`APP_VERSION` 升到 `1.1.0`。
- R11 文档：README（三语）打包章节与 `.trellis/spec/python/packaging.md` 更新为 CI 发布流程。

## Acceptance Criteria

- [ ] push 到分支后 Actions 构建成功，可下载 portable zip 与安装包 artifact。（R1–R4, R6, R8）
- [ ] 标签与 `APP_VERSION` 不一致时，标签构建失败且不创建 Release。（R9）
- [ ] 推 `v1.1.0` 后自动出现 GitHub Release，含 portable zip、`.sha256.txt`、安装包，命名符合规范，哈希一致。（R5, R8, R10）
- [ ] Release 中的 exe 能打开 iPhone HEIC，不再提示缺 pillow-heif；ExifTool 相关功能正常；关于页显示 1.1.0。（R3, R6, R10）
- [ ] 安装包可选两种安装范围、生成快捷方式、可从"应用和功能"卸载。（R7）
- [ ] 文档与打包规范反映新流程。（R11）

## Out of Scope

- 代码签名（无证书；Windows SmartScreen 可能提示"未知发布者"）。
- macOS / Linux 构建。
- 目录版（`AzureKilnPhotoTool.spec`）与 `SplitHuaweiLivePhotoTool.spec` 产物。
- 自动更新检查。
