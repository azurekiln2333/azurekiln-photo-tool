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

---

## 发布产物命名规则（`release/`）

```
AzureKilnPhotoTool-<版本>-<YYYYMMDD>-windows-x64-portable.zip
AzureKilnPhotoTool-<版本>-<YYYYMMDD>-windows-x64-portable.sha256.txt
```

- zip 内含 `exe + sha256.txt`。
- sha256 文件格式：`<64位hash>  AzureKilnPhotoTool.exe`（两个空格 + 换行，共 90 字节）。
- 发布前验证 zip 完整性、zip 内 exe 与 sha256.txt **三方哈希一致**。

---

## 打包相关禁止事项

- ❌ 不用系统 Python 打包。
- ❌ 不加 `--clean`。
- ❌ 不裁剪 `exiftool_files/` 内容。
- ❌ 不把 `dist/`、`build/`、`release/`、`*.spec` 提交进版本库（已在 `.gitignore`）。
