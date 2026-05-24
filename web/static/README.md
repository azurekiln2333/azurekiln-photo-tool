# AzureKiln Photo Tool Web

这是桌面版 `unified_gui.py` 的本地 Web 入口。它不会直接操作浏览器所在电脑的任意目录，而是使用“上传文件 -> 后端处理 -> 下载 ZIP”的流程。

## 启动

在项目根目录运行：

```powershell
python .\web\server.py
```

然后打开：

```text
http://127.0.0.1:8765
```

可选端口：

```powershell
$env:AZUREKILN_WEB_PORT=9000
python .\web\server.py
```

## 功能对应

- LivePhoto 合并：上传同名 `JPG/JPEG` 与 `MP4/MOV` 文件，输出 Motion Photo JPG。
- 华为 LivePhoto 拆分：上传华为内嵌 LivePhoto `JPG/JPEG`，输出拆分后的 `JPG + MP4`。
- Flyme LivePhoto 修复：上传 Flyme LivePhoto `JPG/JPEG`，调用现有 ExifTool 修复逻辑输出兼容照片。

Flyme 修复仍需要 ExifTool 能被项目现有逻辑找到。Windows 通常是 `exiftool.exe`，Linux/macOS 通常是 `exiftool` 命令。

## Linux 服务器

ExifTool 有 Linux 用法，`.exe` 只是 Windows 启动器。常见安装方式：

```bash
# Debian / Ubuntu
sudo apt update
sudo apt install -y libimage-exiftool-perl

# Fedora / RHEL
sudo dnf install -y perl-Image-ExifTool

# Arch Linux
sudo pacman -S perl-image-exiftool
```

验证：

```bash
exiftool -ver
```

如果安装在非 PATH 路径，可以指定：

```bash
export EXIFTOOL_PATH=/opt/exiftool/exiftool
python web/server.py
```

合并和华为拆分不依赖 ExifTool，只有 Flyme 修复依赖它。
