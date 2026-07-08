"""绿幕抠图单元测试。"""

import struct
import zlib
from pathlib import Path

import pytest

from core.assets.chroma_key import apply_chroma_key_to_png
from core.tts.ffmpeg_util import is_ffmpeg_available, resolve_ffmpeg_binary


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def _write_green_with_red_square(path: Path, size: int = 32) -> None:
    width = height = size
    raw_rows: list[bytes] = []
    for y in range(height):
        row = bytearray([0])  # filter type None
        for x in range(width):
            cx, cy = width // 2, height // 2
            if abs(x - cx) < 6 and abs(y - cy) < 6:
                row.extend((255, 0, 0, 255))
            else:
                row.extend((0, 255, 0, 255))
        raw_rows.append(bytes(row))
    compressed = zlib.compress(b"".join(raw_rows), 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


@pytest.mark.skipif(
    not is_ffmpeg_available(),
    reason="FFmpeg 不可用，跳过 chroma key 集成测试",
)
def test_apply_chroma_key_to_png(tmp_path: Path):
    src = tmp_path / "green_red.png"
    _write_green_with_red_square(src)
    out = apply_chroma_key_to_png(src, ffmpeg=resolve_ffmpeg_binary())
    assert out.is_file()
    assert out.suffix.lower() == ".png"
    assert out.stat().st_size > 0
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
