"""绿幕抠图：FFmpeg colorkey → 透明 PNG。"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.models.entities import MediaAssetType, TextAssetType
from core.tts.ffmpeg_util import ffmpeg_missing_message, is_ffmpeg_available, resolve_ffmpeg_binary

if TYPE_CHECKING:
    from core.models.entities import MediaAsset
    from core.store.memory import MemoryStore

logger = logging.getLogger("core.assets.chroma_key")

DEFAULT_KEY_HEX = "0x00FF00"
DEFAULT_SIMILARITY = 0.32
DEFAULT_BLEND = 0.06


class ChromaKeyError(RuntimeError):
    """绿幕抠图失败。"""


def apply_chroma_key_to_png(
    input_path: Path,
    *,
    output_path: Path | None = None,
    key_hex: str = DEFAULT_KEY_HEX,
    similarity: float = DEFAULT_SIMILARITY,
    blend: float = DEFAULT_BLEND,
    ffmpeg: str | None = None,
) -> Path:
    """
    使用 FFmpeg colorkey 将绿幕背景转为透明 PNG。
    默认输出到 output_path；未指定时对非 PNG 输入使用同 stem 的 .png。
    """
    src = Path(input_path)
    if not src.is_file():
        raise ChromaKeyError(f"输入文件不存在：{src}")

    exe = (ffmpeg or "").strip() or resolve_ffmpeg_binary()
    if not is_ffmpeg_available(exe):
        raise ChromaKeyError(ffmpeg_missing_message(exe))

    out = Path(output_path) if output_path is not None else src.with_suffix(".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.parent / f".{out.stem}.chroma_work.png"

    vf = f"format=rgba,colorkey={key_hex}:{similarity}:{blend},format=rgba"
    cmd = [
        exe,
        "-y",
        "-i",
        str(src),
        "-vf",
        vf,
        "-frames:v",
        "1",
        str(work),
    ]
    logger.debug("chroma_key %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        work.unlink(missing_ok=True)
        err = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise ChromaKeyError(f"FFmpeg colorkey 失败：{err or proc.returncode}")

    if not work.is_file() or work.stat().st_size == 0:
        work.unlink(missing_ok=True)
        raise ChromaKeyError("FFmpeg 未产出有效 PNG")

    if work.resolve() != out.resolve():
        out.unlink(missing_ok=True)
        work.replace(out)

    if src.resolve() != out.resolve() and src.suffix.lower() in (".jpg", ".jpeg", ".webp"):
        src.unlink(missing_ok=True)

    # 清理历史 _cutout 旁路文件
    legacy = src.parent / f"{src.stem}_cutout.png"
    if legacy.is_file() and legacy.resolve() != out.resolve():
        legacy.unlink(missing_ok=True)

    return out


def is_chroma_eligible_text_type(asset_type: Any) -> bool:
    type_val = asset_type.value if hasattr(asset_type, "value") else str(asset_type)
    return type_val in (TextAssetType.CHARACTER.value, TextAssetType.PROP.value)


def apply_chroma_key_to_media(
    media: MediaAsset,
    *,
    project_id: str,
    script_id: str,
    asset_type: Any,
) -> bool:
    """
    对 character/prop 媒体执行绿幕抠图，更新 media.url 与 metadata。
    返回是否成功应用透明 PNG。
    """
    if not is_chroma_eligible_text_type(asset_type):
        return False

    from core.store.media_storage import absolute_media_path
    from core.store.project_paths import relative_media_path, script_media_dir

    local = absolute_media_path(media.url)
    if local is None or not local.is_file():
        media.metadata["chroma_key_applied"] = False
        media.metadata["chroma_key_error"] = "本地媒体文件不可用"
        return False

    target = script_media_dir(project_id, script_id) / f"{media.id}.png"
    old_paths: set[Path] = {local.resolve()}
    cutout = local.parent / f"{local.stem}_cutout.png"
    if cutout.is_file():
        old_paths.add(cutout.resolve())

    try:
        out = apply_chroma_key_to_png(local, output_path=target)
        media.url = relative_media_path(project_id, script_id, out.name)
        media.metadata["chroma_key_applied"] = True
        media.metadata["background"] = "transparent"
        media.metadata.pop("chroma_key_error", None)
        for old in old_paths:
            if old.resolve() != out.resolve():
                old.unlink(missing_ok=True)
        return True
    except ChromaKeyError as e:
        media.metadata["chroma_key_applied"] = False
        media.metadata["chroma_key_error"] = str(e)
        logger.warning("chroma_key failed media=%s: %s", media.id, e)
        return False


def reapply_chroma_for_script(
    store: MemoryStore,
    *,
    project_id: str,
    script_id: str,
    force: bool = False,
) -> dict[str, Any]:
    """对剧本下 character/prop 关联图片重新抠图（修复历史绿幕原图）。"""
    applied: list[str] = []
    skipped: list[str] = []
    failed: list[dict[str, str]] = []

    for media in store.list_media_for_script(script_id, MediaAssetType.IMAGE):
        if not media.source_asset_id:
            skipped.append(media.id)
            continue
        text = store.get_text_asset(media.source_asset_id)
        if text is None or not is_chroma_eligible_text_type(text.type):
            skipped.append(media.id)
            continue
        if (
            not force
            and media.metadata.get("chroma_key_applied") is True
            and str(media.url or "").lower().endswith(".png")
        ):
            skipped.append(media.id)
            continue
        ok = apply_chroma_key_to_media(
            media,
            project_id=project_id,
            script_id=script_id,
            asset_type=text.type,
        )
        if ok:
            applied.append(media.id)
        else:
            failed.append(
                {
                    "media_id": media.id,
                    "error": str(media.metadata.get("chroma_key_error", "unknown")),
                }
            )

    return {
        "applied": applied,
        "skipped": skipped,
        "failed": failed,
        "applied_count": len(applied),
        "failed_count": len(failed),
    }
