# AzureKiln Photo Tool Web

This is a local browser version of the unified desktop tool. It lives in its own `web/` directory and reuses the existing Python core modules from the project root.

## Start

Run from the project root:

```powershell
python .\web\server.py
```

Open:

```text
http://127.0.0.1:8765
```

Use another port when needed:

```powershell
$env:AZUREKILN_WEB_PORT=9000
python .\web\server.py
```

## Workflow

The desktop GUI can read and write selected local folders directly. A browser cannot safely do that, so the web version uses this flow:

1. Upload files in the browser.
2. The local Python server processes them.
3. Download the generated ZIP.

## Features

- Merge LivePhoto: upload same-stem `JPG/JPEG` and `MP4/MOV` files, download Motion Photo JPG output.
- Split Huawei LivePhoto: upload embedded Huawei LivePhoto `JPG/JPEG` files, download extracted `JPG + MP4`.
- Fix Flyme LivePhoto: upload Flyme LivePhoto `JPG/JPEG` files, download metadata-fixed JPG output.

Flyme fixing still depends on ExifTool being discoverable by the existing `flyme_livephoto_fix_core.py` lookup order.

## Linux server notes

ExifTool is available on Linux as the `exiftool` command. The `.exe` file is only the Windows launcher.

Install it on common Linux distributions:

```bash
# Debian / Ubuntu
sudo apt update
sudo apt install -y libimage-exiftool-perl

# Fedora / RHEL family
sudo dnf install -y perl-Image-ExifTool

# Arch Linux
sudo pacman -S perl-image-exiftool
```

Verify:

```bash
exiftool -ver
```

If ExifTool is installed outside `PATH`, point the app to it:

```bash
export EXIFTOOL_PATH=/opt/exiftool/exiftool
python web/server.py
```

Merge and Huawei split do not need ExifTool. Only Flyme repair needs it.
