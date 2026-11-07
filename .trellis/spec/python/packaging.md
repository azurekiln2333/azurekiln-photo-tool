# 打包约定（PyInstaller）

> 本项目实际使用的打包方式与踩过的坑。

---

## 必须用 `.venv`

```powershell
# ✅ 正确
.venv/Scripts/python.exe -m PyInstaller --noconfirm AzureKilnPhotoTool_onefile.spec

# ❌ 错误：系统 Python 3.13 缺 pillow_heif / send2trash
python -m PyInstaller ...
```

- `.venv` = Python 3.14.0 + PyInstaller 6.20.0，含 `pillow_heif` / `send2trash` / `win32com`。
- 系统 Python 3.13 缺依赖，用它打包会**静默丢掉 HEIC 与回收站功能**。
- 依赖清单：`requirements.txt`（运行，固定版本）、`requirements-build.txt`（`-r requirements.txt` + PyInstaller）。
  CI 与本地共用；升级依赖时**同时**改 `.venv` 与清单，保持一致。

---

## 不要加 `--clean`

```
❌ --clean 会批量删除 %LOCALAPPDATA%\pyinstaller\bincache*（190 项），
   被沙箱安全删除策略拦截，导致构建中止。
```

---

## 两种产物

| 目标 | 命令 | 产物 |
|------|------|------|
| 单文件 | `PyInstaller --noconfirm AzureKilnPhotoTool_onefile.spec` | `dist/AzureKilnPhotoTool.exe`（~76.9MB） |
| 目录版 | `AzureKilnPhotoTool.spec` | `dist/AzureKilnPhotoTool/` |

onefile 每次启动都要解压 Qt + 508 个 perl 文件，**冷启动明显慢**；目录版更快，用于日常测试。

---

## ExifTool 打包布局（关键）

必须与 `exiftool_resolver._candidate_dirs()` 对齐：

```
_MEIPASS/exiftool.exe                                (stub 直调，回退)
_MEIPASS/exiftool_files/{perl.exe, exiftool.pl, lib} (perl 直调，唯一可靠)
```

spec 里通过 `EXIFTOOL_DIR` 环境变量覆盖源目录，默认 `D:\ProgramFiles\exiftool`。
`exiftool_files/` 必须**整目录原样打包**（含 perl 依赖 DLL，必须与 perl.exe 同目录），不能裁剪。

验证方式：启动 exe → 等 `%TEMP%\_MEIxxxx` 解压 → 确认 `exiftool.exe` / `exiftool_files/perl.exe`
/ `exiftool.pl` / `lib` 都在 → 用解压出的 perl 跑 `-ver`（应返回 13.58）。

CI 下（环境变量 `CI` 存在）spec 发现 `exiftool.exe` / `exiftool_files/{perl.exe,exiftool.pl,lib}`
缺失会 `raise SystemExit`；本地缺失仍只打印警告继续。

---

## 发布流程（GitHub Actions，`.github/workflows/build.yml`）

| 触发 | 行为 |
|------|------|
| push 任意分支 / 手动 | 构建 → 自检 → portable zip + sha256 + 安装包，上传为 workflow artifact |
| push `v*` 标签 | 同上 + `softprops/action-gh-release` 创建 Release 并上传三类文件 |

- **版本唯一来源**：`unified_gui.py` 的 `APP_VERSION`。`scripts/ci/get_version.py --tag vX.Y.Z` 校验，
  标签 ≠ `v` + `APP_VERSION` 时构建失败，不发布。发版 = 改 `APP_VERSION` → 提交 → `git tag vX.Y.Z` → push 标签。
- **ExifTool**：CI 从 SourceForge 版本归档下载 `exiftool-13.58_64.zip`，校验 workflow 中固定的 SHA256，
  `exiftool(-k).exe` 改名为 `exiftool.exe`，`exiftool_files/` 原样，通过 `EXIFTOOL_DIR` 注入。
  升级 ExifTool 必须同时改 `EXIFTOOL_VERSION` 与 `EXIFTOOL_SHA256`。
- **自检**：`scripts/ci/verify_bundle.py` 用 PyInstaller `CArchiveReader` 读 exe 目录表，断言含
  `pillow_heif`（PYZ 模块 + `_pillow_heif*.pyd` + `libheif*.dll`）、`send2trash`、
  `exiftool.exe`、`exiftool_files/{perl.exe,exiftool.pl,lib/}`。
- **便携包**：`scripts/ci/package_portable.py --version <ver> [--date YYYYMMDD]`，日期默认 UTC 当天，
  输出到 `release/`，并自检三方哈希。
- **安装包**：`installer/AzureKilnPhotoTool.iss`（Inno Setup 6），安装单文件 exe；
  `PrivilegesRequired=lowest` + `PrivilegesRequiredOverridesAllowed=dialog` 让用户选「仅当前用户 / 所有用户」。
  **`AppId` GUID 永不修改**（否则无法覆盖升级）。runner 无 `iscc` 时 `choco install innosetup`。
- CI 无 UPX，exe 会比本地 UPX 压缩版略大，不影响功能。不做代码签名。

---

## 发布产物命名规则（`release/`）

```
AzureKilnPhotoTool-<版本>-<YYYYMMDD>-windows-x64-portable.zip
AzureKilnPhotoTool-<版本>-<YYYYMMDD>-windows-x64-portable.sha256.txt
AzureKilnPhotoTool-<版本>-<YYYYMMDD>-windows-x64-setup.exe
```

- zip 内含 `exe + sha256.txt`。
- sha256 文件格式：`<64位hash>  AzureKilnPhotoTool.exe`（两个空格 + CRLF 换行，共 90 字节）。
- 发布前验证 zip 完整性、zip 内 exe 与 sha256.txt **三方哈希一致**。

---

## 打包相关禁止事项

- ❌ 不用系统 Python 打包。
- ❌ 不加 `--clean`。
- ❌ 不裁剪 `exiftool_files/` 内容。
- ❌ 不把 `dist/`、`build/`、`release/` 提交进版本库（已在 `.gitignore`）。
- ❌ `*.spec` 中**只有** `AzureKilnPhotoTool_onefile.spec` 入库（CI 依赖它，`.gitignore` 已放行）；其他 spec 保持忽略。
- ❌ 不在 Release 标签与 `APP_VERSION` 不一致时强行发布。
