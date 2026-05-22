#!/usr/bin/env python3
"""
Combine separate JPG + MP4 into a Google Photos-recognizable Live Photo (Motion Photo).
Supports batch processing of a directory.

Usage:
    python3 batch_make_live_photo.py <input_directory> <output_directory>
"""

import struct
import sys
import os
import io
from PIL import Image
from pathlib import Path

XMP_IDENTIFIER = b'http://ns.adobe.com/xap/1.0/\x00'


def find_jpeg_end(data: bytes) -> int:
    """Find the end of the actual JPEG image data (after the last valid EOI)."""
    if data[:2] != b'\xff\xd8':
        raise ValueError("Not a JPEG file")

    eoi_positions = []
    pos = 0
    while True:
        pos = data.find(b'\xff\xd9', pos)
        if pos == -1:
            break
        eoi_positions.append(pos)
        pos += 2

    if not eoi_positions:
        raise ValueError("No JPEG EOI marker found")

    for eoi in reversed(eoi_positions):
        try:
            img = Image.open(io.BytesIO(data[:eoi + 2]))
            img.verify()
            return eoi + 2
        except Exception:
            continue

    return eoi_positions[-1] + 2


def strip_existing_xmp(jpeg_data: bytes) -> bytes:
    """Remove any existing XMP APP1 segments to avoid duplicate XMP conflicts."""
    if jpeg_data[:2] != b'\xff\xd8':
        raise ValueError("Not a JPEG file")

    result = bytearray(jpeg_data[:2])
    pos = 2
    while pos < len(jpeg_data):
        if jpeg_data[pos] != 0xFF:
            result += jpeg_data[pos:]
            break
        marker = jpeg_data[pos:pos + 2]
        if len(marker) < 2:
            result += jpeg_data[pos:]
            break
        marker_code = struct.unpack('>H', marker)[0]
        if marker_code in (0xFFD8, 0xFFD9):
            result += marker
            pos += 2
            continue
        if marker_code == 0xFFDA:
            result += jpeg_data[pos:]
            break
        seg_len = struct.unpack('>H', jpeg_data[pos + 2:pos + 4])[0]
        seg_data = jpeg_data[pos + 4:pos + 2 + seg_len]
        if marker_code == 0xFFE1 and seg_data.startswith(XMP_IDENTIFIER):
            pos += 2 + seg_len
            continue
        result += marker + jpeg_data[pos + 2:pos + 2 + seg_len]
        pos += 2 + seg_len

    return bytes(result)


def build_xmp_app1(mp4_size: int) -> bytes:
    """Build an XMP APP1 segment for Motion Photo metadata."""
    xmp_content = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 5.1.0-jc003">\n'
        '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '    <rdf:Description rdf:about=""\n'
        '        xmlns:GCamera="http://ns.google.com/photos/1.0/camera/"\n'
        '        xmlns:Container="http://ns.google.com/photos/1.0/container/"\n'
        '        xmlns:Item="http://ns.google.com/photos/1.0/container/item/"\n'
        '      GCamera:MotionPhoto="1"\n'
        '      GCamera:MotionPhotoVersion="1"\n'
        '      GCamera:MotionPhotoPresentationTimestampUs="-1">\n'
        '      <Container:Directory>\n'
        '        <rdf:Seq>\n'
        '          <rdf:li rdf:parseType="Resource">\n'
        '            <Container:Item\n'
        '              Item:Mime="image/jpeg"\n'
        '              Item:Semantic="Primary"\n'
        '              Item:Length="0"\n'
        '              Item:Padding="0"/>\n'
        '          </rdf:li>\n'
        '          <rdf:li rdf:parseType="Resource">\n'
        '            <Container:Item\n'
        '              Item:Mime="video/mp4"\n'
        '              Item:Semantic="MotionPhoto"\n'
        f'              Item:Length="{mp4_size}"\n'
        '              Item:Padding="0"/>\n'
        '          </rdf:li>\n'
        '        </rdf:Seq>\n'
        '      </Container:Directory>\n'
        '    </rdf:Description>\n'
        '  </rdf:RDF>\n'
        '</x:xmpmeta>'
    )

    payload = XMP_IDENTIFIER + xmp_content.encode('utf-8')
    length = len(payload) + 2
    return b'\xff\xe1' + struct.pack('>H', length) + payload


def make_live_photo(jpg_path: str, mp4_path: str, output_path: str):
    """Combine JPG + MP4 into a Motion Photo."""
    with open(jpg_path, 'rb') as f:
        jpg_data = f.read()
    with open(mp4_path, 'rb') as f:
        mp4_data = f.read()

    jpeg_end = find_jpeg_end(jpg_data)
    clean_jpeg = jpg_data[:jpeg_end]
    stripped_jpeg = strip_existing_xmp(clean_jpeg)

    mp4_size = len(mp4_data)
    xmp_segment = build_xmp_app1(mp4_size)

    result = bytearray()
    result += stripped_jpeg[:2]
    result += xmp_segment
    result += stripped_jpeg[2:]
    result += mp4_data

    with open(output_path, 'wb') as f:
        f.write(bytes(result))


def process_directory(input_dir: str, output_dir: str):
    """Process all JPG+MP4 pairs in a directory."""
    in_path = Path(input_dir)
    out_path = Path(output_dir)

    if not in_path.is_dir():
        print(f"错误: 输入目录 '{input_dir}' 不存在！")
        return

    # 创建输出目录（如果不存在的话）
    out_path.mkdir(parents=True, exist_ok=True)
    print(f"扫描目录: {in_path}")
    print(f"输出目录: {out_path}\n")

    # 获取所有图片文件 (支持大小写后缀)
    jpg_files = []
    for ext in ('*.jpg', '*.jpeg', '*.JPG', '*.JPEG'):
        jpg_files.extend(in_path.glob(ext))

    if not jpg_files:
        print("输入目录中没有找到 JPG 文件。")
        return

    processed_count = 0
    skipped_count = 0

    for jpg_path in jpg_files:
        # 尝试寻找同名的 mp4 文件 (支持大小写)
        mp4_path = jpg_path.with_suffix('.mp4')
        if not mp4_path.exists():
            mp4_path = jpg_path.with_suffix('.MP4')

        # 如果同名 MP4 存在，进行合并
        if mp4_path.exists():
            output_path = out_path / jpg_path.name
            print(f"合并中: {jpg_path.name} + {mp4_path.name} -> {output_path.name}")
            try:
                make_live_photo(str(jpg_path), str(mp4_path), str(output_path))
                processed_count += 1
            except Exception as e:
                print(f"  [失败] 处理 {jpg_path.name} 时发生错误: {e}")
        else:
            # 如果没有 MP4，跳过该文件（静态照片）
            print(f"跳过: {jpg_path.name} (未找到同名 MP4 视频)")
            skipped_count += 1

    print("\n" + "=" * 40)
    print("处理完成！")
    print(f"成功合成的实况照片数: {processed_count}")
    print(f"跳过的普通静态照片数: {skipped_count}")
    print("=" * 40)


def main():
    if len(sys.argv) != 3:
        print(f"用法: python3 {sys.argv[0]} <输入文件夹路径> <输出文件夹路径>")
        print(f"示例: python3 {sys.argv[0]} ./my_photos ./output_live_photos")
        sys.exit(1)

    input_dir = sys.argv[1]
    output_dir = sys.argv[2]

    process_directory(input_dir, output_dir)


if __name__ == '__main__':
    main()