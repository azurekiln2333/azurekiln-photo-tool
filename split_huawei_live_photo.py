#!/usr/bin/env python3
"""
Split Huawei HarmonyOS Live Photo (Motion Photo) into separate JPG and MP4 files.

Huawei Live Photo Format:
- JPEG image data (SOI to EOI + padding + ctrace metadata)
- MP4 video data
- 40-byte metadata trailer at the end of the file:
  - First 20 bytes: Internal identifier (e.g., "671:503") + spaces
  - Second 20 bytes: "LIVE_XXXXXXXX" + spaces (where XXXXXXXX is MP4 size in bytes)

Usage:
    python split_huawei_live_photo.py <input.jpg> [output_dir]
    python split_huawei_live_photo.py <input_directory> [output_directory]
"""

import struct
import sys
import os
import re
from pathlib import Path


METADATA_SIZE = 40


def parse_live_metadata(data: bytes) -> tuple[int, str]:
    """Parse the LIVE metadata from near the end of the file."""
    if len(data) < 100:
        raise ValueError("文件过小")

    trailer = data[-100:]
    idx = trailer.rfind(b'LIVE_')
    if idx == -1:
        raise ValueError("未找到 LIVE_ 标记")

    live_field = trailer[idx:].decode('ascii', errors='ignore').strip()
    match = re.search(r'LIVE_(\d+)', live_field)
    if not match:
        raise ValueError(f"无效的 LIVE 元数据格式: '{live_field}'")

    mp4_size = int(match.group(1))
    return mp4_size, live_field


def validate_jpeg(data: bytes) -> bool:
    return len(data) >= 2 and data[:2] == b'\xff\xd8'


def validate_mp4(data: bytes) -> bool:
    return len(data) >= 8 and data[4:8] == b'ftyp'


def is_huawei_live_photo(file_path: Path) -> bool:
    """快速检测文件是否为鸿蒙 Live Photo（只读取尾部100字节）。"""
    try:
        with open(file_path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            if f.tell() < 100:
                return False
            f.seek(-100, os.SEEK_END)
            trailer = f.read(100)
        return b'LIVE_' in trailer
    except Exception:
        return False


def split_live_photo(input_path: str, output_dir: str) -> tuple:
    """Split a Huawei Live Photo into separate JPG and MP4 files.

    Returns:
        (jpg_output_path, mp4_output_path, jpeg_size, mp4_size)
    """
    input_path_obj = Path(input_path)
    with open(input_path, 'rb') as f:
        data = f.read()

    file_size = len(data)
    mp4_size, live_str = parse_live_metadata(data)
    jpeg_size = file_size - mp4_size - METADATA_SIZE

    mp4_data = data[jpeg_size:jpeg_size + mp4_size]
    if not validate_mp4(mp4_data):
        search_start = max(0, jpeg_size - 200)
        search_end = min(file_size, jpeg_size + 200)
        idx = data.find(b'ftyp', search_start, search_end)
        if idx != -1:
            real_mp4_start = idx - 4
            jpeg_size = real_mp4_start
            mp4_size = file_size - real_mp4_start - METADATA_SIZE
            mp4_data = data[jpeg_size:jpeg_size + mp4_size]

    if jpeg_size <= 0:
        raise ValueError(f"无效的 JPEG 大小: {jpeg_size:,} bytes")
    if mp4_size <= 0:
        raise ValueError(f"无效的 MP4 大小: {mp4_size:,} bytes")

    jpeg_data = data[:jpeg_size]

    if not validate_jpeg(jpeg_data):
        raise ValueError("提取的 JPEG 数据无效 (缺少 SOI 标记)")
    if not validate_mp4(mp4_data):
        raise ValueError("提取的 MP4 数据无效 (未在视频头部找到 ftyp 特征码)")

    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    stem = input_path_obj.stem
    jpg_output = output_dir_path / f"{stem}.jpg"
    mp4_output = output_dir_path / f"{stem}.mp4"

    with open(jpg_output, 'wb') as f:
        f.write(jpeg_data)
    with open(mp4_output, 'wb') as f:
        f.write(mp4_data)

    return str(jpg_output), str(mp4_output), jpeg_size, mp4_size


def process_directory(input_dir: str, output_dir: str = None):
    """Batch process all Huawei Live Photos in a directory."""
    input_path = Path(input_dir)
    if not input_path.is_dir():
        print(f"错误: 输入目录 '{input_dir}' 不存在！")
        return

    if output_dir is None:
        output_dir = input_path / "Split_Output"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"输入目录: {input_path}")
    print(f"输出目录: {output_dir}\n")

    jpg_files = set()
    for ext in ('*.jpg', '*.jpeg', '*.JPG', '*.JPEG'):
        jpg_files.update(input_path.glob(ext))

    out_resolved = output_dir.resolve()
    jpg_files = {f for f in jpg_files
                 if not str(f.resolve()).startswith(str(out_resolved))}
    jpg_files = sorted(jpg_files)

    if not jpg_files:
        print("未找到 JPG 文件。")
        return

    live_photos = []
    regular_photos = []
    for jpg_path in jpg_files:
        if is_huawei_live_photo(jpg_path):
            live_photos.append(jpg_path)
        else:
            regular_photos.append(jpg_path)

    print(f"发现 {len(live_photos)} 个鸿蒙 Live Photo")
    print(f"跳过 {len(regular_photos)} 个普通照片\n")

    success_count = 0
    error_count = 0
    for jpg_path in live_photos:
        try:
            jpg_out, mp4_out, jpeg_size, mp4_size = split_live_photo(str(jpg_path), str(output_dir))
            print(f"  ✓ {jpg_path.name} -> {Path(jpg_out).name} + {Path(mp4_out).name}")
            success_count += 1
        except Exception as e:
            print(f"  ✗ {jpg_path.name}: {e}")
            error_count += 1

    print(f"\n完成！成功: {success_count}, 失败: {error_count}")


def main():
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <input.jpg> [output_dir]")
        print(f"      {sys.argv[0]} <input_directory> [output_directory]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    if os.path.isfile(input_path):
        try:
            jpg_path, mp4_path, jpeg_size, mp4_size = split_live_photo(input_path, output_dir or os.path.dirname(input_path) or ".")
            print(f"分离完成！")
            print(f"  JPEG: {jpg_path} ({jpeg_size:,} bytes)")
            print(f"  MP4:  {mp4_path} ({mp4_size:,} bytes)")
        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)
    elif os.path.isdir(input_path):
        process_directory(input_path, output_dir)
    else:
        print(f"错误: '{input_path}' 不是有效的文件或目录")
        sys.exit(1)


if __name__ == '__main__':
    main()
