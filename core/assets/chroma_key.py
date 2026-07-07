"""绿幕抠图：FFmpeg colorkey → 透明 PNG。"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from core.tts.ffmpeg_util import ffmpeg_missing_message, is_ffmpeg_available, resolve_ffmpeg_binary

logger = logging.getLogger("core.assets.chroma_key")

DEFAULT_KEY_HEX = "0x00FF00"
DEFAULT_SIMILARITY = 0.25
DEFAULT_BLEND = 0.08


class ChromaKeyError(RuntimeError):
    """绿幕抠图失败。"""


def apply_chroma_key_to_png(
    input_path: Path,
    *,
    key_hex: str = DEFAULT_KEY_HEX,
    similarity: float = DEFAULT_SIMILARITY,
    blend: float = DEFAULT_BLEND,
    ffmpeg: str | None = None,
) -> Path:
    """
    使用 FFmpeg colorkey 将绿幕背景转为透明 PNG。
    输出路径与输入同目录，扩展名为 .png。
    """
    src = Path(input_path)
    if not src.is_file():
        raise ChromaKeyError(f"输入文件不存在：{src}")

    exe = (ffmpeg or "").strip() or resolve_ffmpeg_binary()
    if not is_ffmpeg_available(exe):
        raise ChromaKeyError(ffmpeg_missing_message(exe))

    out = src.with_suffix(".png")
    if out == src:
        out = src.parent / f"{src.stem}_cutout.png"

    vf = f"colorkey={key_hex}:{similarity}:{blend},format=rgba"
    cmd = [
        exe,
        "-y",
        "-i",
        str(src),
        "-vf",
        vf,
        "-frames:v",
        "1",
        str(out),
    ]
    logger.debug("chroma_key %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise ChromaKeyError(f"FFmpeg colorkey 失败：{err or proc.returncode}")

    if not out.is_file() or out.stat().st_size == 0:
        raise ChromaKeyError("FFmpeg 未产出有效 PNG")

    if src != out and src.suffix.lower() in (".jpg", ".jpeg", ".webp"):
        src.unlink(missing_ok=True)

    return out
