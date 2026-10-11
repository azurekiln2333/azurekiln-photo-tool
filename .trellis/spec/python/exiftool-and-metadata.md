# ExifTool 与元数据约定

> 本项目最核心、最容易踩坑的部分。改元数据相关代码前必读。

---

## ExifTool 调用：统一走 `exiftool_resolver`

**不要**自己拼 ExifTool 路径。统一使用 `exiftool_resolver`：

```python
from exiftool_resolver import resolve_exiftool

self._exiftool = resolve_exiftool()          # -> ExifToolCommand | None
if self._exiftool is None:
    raise FileNotFoundError("未找到 exiftool！...")

# 注意：args 传「不含 exiftool 本体」的参数
self._exiftool.command(["-ver"])             # -> 完整命令行
self._exiftool.cwd                           # -> 正确的工作目录
```

`ExifToolCommand` 提供：
- `.command(args)` — 返回可直接喂给 `subprocess.run` 的完整 argv（含 perl 前置参数）
- `.cwd` — 运行目录
- `.describe()` — 人类可读的定位说明

调用方**必须传绝对路径**给 ExifTool，因为 perl 模式下 cwd 是 `exiftool_files` 目录。

### 为什么不能自己找

Windows 版 ExifTool = `exiftool.exe`（~58KB stub）+ `exiftool_files/`（真正 Perl 运行时）。
stub 依赖「相对自身位置」推导 `exiftool_files`。PyInstaller onefile 下文件被解压到
`%TEMP%/_MEIxxxxxx`，stub 自定位失效（表现为 Perl `@INC` 为空）。

`exiftool_resolver._candidate_dirs()` 按顺序探测，打包布局必须与它对齐：

```
_MEIPASS/exiftool_files/{perl.exe,exiftool.pl,lib}   -> perl 直调模式（onefile 下唯一可靠）
_MEIPASS/exiftool.exe                                -> stub 直调模式（回退）
```

perl.exe 依赖的 DLL 必须与 perl.exe 同目录，所以 `exiftool_files/` 必须**整目录原样打包**，不能裁剪。

---

## 时间来源优先级（硬性规则）

读取拍摄时间时，优先级**必须**是：

```
拍摄/容器元数据  →  文件名  →  文件最早时间
```

**不能**让文件名优先。原因：华为等设备会写入占位文件名 `IMG_20010101_000000`，
真实时间在 EXIF `DateTimeOriginal`。旧实现先读文件名，导致被占位值覆盖。

**回归用例**：项目根 `IMG_20010101_000000.jpg`
- 占位文件名：`2001-01-01 00:00:00`
- 正确时间（EXIF `DateTimeOriginal`）：`2006-05-30`

### 占位时间过滤

`PLACEHOLDER_EXIF_TIMES`（`timestamp_fix_gui.py`）列出相机「未设置时钟」写入的占位时间：
1970 / 1980 / 2000 / `2001-01-01 00:00:00` 等。命中后**继续找更可信的来源**，不能直接采用。

---

## EXIF 读取：必须读 SubIFD

```python
# ❌ 错误：Image.getexif() 只返回 IFD0
exif = img.getexif()

# ✅ 正确：遍历 IFD0 + Exif SubIFD(0x8769 / 0xA005) + XMP
```

`DateTimeOriginal` 位于 **Exif SubIFD (0x8769)**，不在 IFD0。
只读 IFD0 只能拿到 `ModifyDate`（可能是占位值）。

实现参考 `timestamp_fix_gui.py` 的 `_timestamp_from_exif()` / `_timestamp_from_xmp()`。

---

## 视频时间

- 优先 `ffprobe` 的 `creation_time`（按 UTC 解析）与 AVI(RIFF) 的 `date`（IDIT，按本地时间）。
- 其次 ExifTool `DateCreated` / `CreateDate` / `MediaCreateDate` / `TrackCreateDate` / `DateTimeOriginal`。
- **ExifTool 读 QuickTime 时间需加 `-api QuickTimeUTC=1`** 才会转成本地时间。
- AVI 没有 `creation_time`，日期在 RIFF INFO 的 `date`(IDIT) / ExifTool 的 `DateCreated`。

支持后缀：`mp4/mov/m4v/3gp/avi/wmv/mkv`（见 `VIDEO_SUFFIXES`）。

---

## 媒体后缀常量

统一使用 `timestamp_fix_gui.py` 导出的常量，不要在别处另定义：

- `IMAGE_SUFFIXES`：`.jpg/.jpeg/.heic/.heif/.png/.tif/.tiff/.webp`
- `VIDEO_SUFFIXES`：`.mp4/.mov/.m4v/.3gp/.avi/.wmv/.mkv`

`rename_photo_gui.py` 直接复用；`dedupe_media_gui.py` 也自动受益。

---

## 禁止事项

- ❌ 不要绕过 `exiftool_resolver` 自己找 exiftool 路径。
- ❌ 不要用 `Image.getexif()` 只读 IFD0 就当作拿到了拍摄时间。
- ❌ 不要把文件名时间置于元数据时间之前。
- ❌ 不要在 QuickTime 时间读取时漏掉 `-api QuickTimeUTC=1`。
