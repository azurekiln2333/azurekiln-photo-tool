# Design: GitHub Actions CI/CD

## Files

| 文件 | 变更 |
|------|------|
| `requirements.txt` | 新增：运行依赖固定版本 |
| `requirements-build.txt` | 新增：`-r requirements.txt` + `pyinstaller==6.20.0` + `pyinstaller-hooks-contrib` |
| `.gitignore` | `*.spec` 后追加 `!AzureKilnPhotoTool_onefile.spec` |
| `AzureKilnPhotoTool_onefile.spec` | 入库；`CI` 环境变量存在且 ExifTool 缺失时 `raise SystemExit` |
| `installer/AzureKilnPhotoTool.iss` | 新增：Inno Setup 脚本 |
| `scripts/ci/` | 新增：版本读取/校验、产物自检、打包 zip+sha256 的小脚本（Python，便于本地复现） |
| `.github/workflows/build.yml` | 新增：唯一 workflow |
| `unified_gui.py:37` | `APP_VERSION = "1.1.0"` |
| README ×3、`.trellis/spec/python/packaging.md` | 文档更新 |

## Workflow (`build.yml`)

触发：`push`（branches: `**`，tags: `v*`）+ `workflow_dispatch`。
单 job，`runs-on: windows-latest`，`permissions: contents: write`（仅创建 Release 需要）。

1. checkout
2. `actions/setup-python` → Python 3.14（与本地 `.venv` 一致），pip 缓存键 = `requirements*.txt`
3. `pip install -r requirements-build.txt`
4. 读取版本：解析 `unified_gui.py` 的 `APP_VERSION`（正则，不 import GUI）。
   若 `github.ref_type == tag`：`ref_name` 去掉 `v` 必须等于 `APP_VERSION`，否则 fail。
5. ExifTool：下载 `exiftool-13.58_64.zip`（SourceForge 版本归档 URL，exiftool.org 只保留最新版），
   校验固定 SHA256，解压后 `exiftool(-k).exe` → `exiftool.exe`，`exiftool_files/` 原样；`EXIFTOOL_DIR` 指向它。
   用 `actions/cache` 以版本号为键缓存。
6. `python -m PyInstaller --noconfirm AzureKilnPhotoTool_onefile.spec`（不加 `--clean`）
7. 自检：`pyi-archive_viewer`（PyInstaller 自带的 archive 读取 API）列出 `dist/AzureKilnPhotoTool.exe` 内容，
   断言含 `pillow_heif`、`exiftool_files/perl.exe`、`exiftool_files/exiftool.pl`。
8. Portable：生成 `AzureKilnPhotoTool-<ver>-<YYYYMMDD>-windows-x64-portable.zip`（exe + sha256.txt）
   与同名 `.sha256.txt`，格式沿用规范（`<hash>  AzureKilnPhotoTool.exe\n`）。日期用 UTC 构建日期。
9. Installer：确保 `iscc` 可用（runner 未预装时 `choco install innosetup -y`），
   `iscc /DAppVersion=<ver> /DSourceExe=dist\AzureKilnPhotoTool.exe installer\AzureKilnPhotoTool.iss`
   → `AzureKilnPhotoTool-<ver>-<YYYYMMDD>-windows-x64-setup.exe`。
10. `actions/upload-artifact`：zip、sha256、setup.exe（所有构建都上传）。
11. 仅标签：`softprops/action-gh-release`（固定版本）创建 Release，上传同三类文件，自动生成 release notes。

## Installer (`.iss`)

- 固定 `AppId`（新生成 GUID，之后永不更改，保证升级覆盖安装）。
- `PrivilegesRequired=lowest` + `PrivilegesRequiredOverridesAllowed=dialog` → 安装时弹窗选"仅我/所有用户"。
- `DefaultDirName={autopf}\AzureKilnPhotoTool`（`autopf` 随所选范围落到 `%LOCALAPPDATA%\Programs` 或 `Program Files`）。
- `ArchitecturesAllowed=x64compatible`、`ArchitecturesInstallIn64BitMode=x64compatible`。
- 开始菜单快捷方式 + `[Tasks]` 可选桌面快捷方式；安装结束可选"立即运行"。
- 只安装单文件 exe（与 portable 同一个 exe），卸载器由 Inno 自动注册到"应用和功能"。
- 语言：简体中文 + 英文（Inno 6 自带 `ChineseSimplified.isl` 为非官方翻译，若 runner 缺失则仅英文——实现时确认）。

## Trade-offs / Notes

- 安装包装单文件 exe 而非目录版：只需构建一次，与 portable 完全一致；代价是安装版也有 onefile 冷启动解压开销。后续如需提速可另开任务改装目录版。
- CI 无 UPX → exe 体积可能比本地略大，不影响功能。
- 不签名 → SmartScreen 警告，已列 Out of Scope。
- 回滚：删除 `.github/workflows/build.yml` 即停用 CI；已发布的 Release 可在 GitHub 上删除，tag 用 `git push github :refs/tags/vX.Y.Z` 删除。
