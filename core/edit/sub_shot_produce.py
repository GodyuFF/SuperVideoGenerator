"""子镜画面时段回填、校验与 produce_mode 映射。"""

from __future__ import annotations

from typing import Any, Literal

from core.models.entities import ProduceMode, ShotSubShot, ShotSubShotImage

VideoGenMode = Literal["still", "img2video", "text2video", "keyframes"]

_LEGACY_PRODUCE: dict[str, ProduceMode] = {
    "still_edit": "still",
    "ai_video": "img2video",
    "hybrid": "img2video",
    "keyframes": "img2video",
}

_VALID_PRODUCE: set[str] = {"still", "text2video", "img2video"}


def coerce_produce_mode(raw: Any) -> ProduceMode:
    """将历史/别名 produce_mode 规范为 still / text2video / img2video。"""
    mode = str(raw or "").strip()
    if mode in _LEGACY_PRODUCE:
        return _LEGACY_PRODUCE[mode]
    if mode in _VALID_PRODUCE:
        return mode  # type: ignore[return-value]
    return "still"


def expand_image_timing(img: ShotSubShotImage, sub: ShotSubShot) -> tuple[int, int]:
    """未显式设置（0,0）时回填所属子镜区间；已设置则原样返回。"""
    if int(img.start_ms or 0) == 0 and int(img.end_ms or 0) == 0:
        return int(sub.start_ms), int(sub.end_ms)
    return max(0, int(img.start_ms)), max(0, int(img.end_ms))


def apply_image_timing_defaults(sub: ShotSubShot) -> ShotSubShot:
    """将 images[] 未设置时段回填为子镜区间（返回新 ShotSubShot）。"""
    if not sub.images:
        return sub
    new_images: list[ShotSubShotImage] = []
    for img in sub.images:
        s, e = expand_image_timing(img, sub)
        if s != img.start_ms or e != img.end_ms:
            new_images.append(img.model_copy(update={"start_ms": s, "end_ms": e}))
        else:
            new_images.append(img)
    return sub.model_copy(update={"images": new_images})


def clamp_image_timings_to_sub(sub: ShotSubShot) -> ShotSubShot:
    """将已显式设置的画面时段钳制进子镜区间；未设置（0,0）保持不动。

    子镜被 TTS/累加归一化缩短后，设计态 images 区间可能越界；钳制失败（end<=start）
    时回退为整段子镜区间，保证结构校验可通过。
    """
    if not sub.images:
        return sub
    sub_s, sub_e = int(sub.start_ms), int(sub.end_ms)
    new_images: list[ShotSubShotImage] = []
    changed = False
    for img in sub.images:
        if int(img.start_ms or 0) == 0 and int(img.end_ms or 0) == 0:
            new_images.append(img)
            continue
        s = max(sub_s, min(int(img.start_ms or 0), sub_e))
        e = max(sub_s, min(int(img.end_ms or 0), sub_e))
        if e <= s:
            s, e = sub_s, sub_e
        if s != img.start_ms or e != img.end_ms:
            changed = True
            new_images.append(img.model_copy(update={"start_ms": s, "end_ms": e}))
        else:
            new_images.append(img)
    if not changed:
        return sub
    return sub.model_copy(update={"images": new_images})


def validate_sub_shot_image_timings(sub: ShotSubShot) -> list[str]:
    """校验每张画面时段落在子镜内且 start < end。"""
    issues: list[str] = []
    sub_s, sub_e = int(sub.start_ms), int(sub.end_ms)
    for i, img in enumerate(sub.images):
        s, e = expand_image_timing(img, sub)
        label = f"images[{i}]"
        if e <= s:
            issues.append(f"{label}: end_ms 必须大于 start_ms")
        if s < sub_s or e > sub_e:
            issues.append(f"{label}: 区间 [{s},{e}] 必须落在子镜 [{sub_s},{sub_e}] 内")
    return issues


def infer_produce_mode(sub: ShotSubShot) -> ProduceMode:
    """旧数据缺 produce_mode 时的推断：已有视频挂接 → img2video，否则静图视频。"""
    if sub.videos:
        return "img2video"
    if any(img.kind == "video" for img in sub.images):
        return "img2video"
    return "still"


def produce_mode_to_video_gen_mode(mode: ProduceMode | str) -> VideoGenMode:
    """子镜意图 → UI videoGenMode（与 produce_mode 三值对齐）。"""
    coerced = coerce_produce_mode(mode)
    if coerced == "still":
        return "still"
    if coerced == "text2video":
        return "text2video"
    return "img2video"


def video_gen_mode_to_produce_mode_hint(mode: str) -> ProduceMode:
    """单个 videoGenMode → 产出意图。"""
    return coerce_produce_mode(mode or "still")


def sync_produce_mode_from_video_gen_modes(modes: list[str]) -> ProduceMode:
    """抽屉内成片模式汇总为子镜 produce_mode（取首个非空规范值）。"""
    for m in modes:
        coerced = coerce_produce_mode(m)
        if coerced:
            return coerced
    return "still"


def finalize_sub_shot(
    sub: ShotSubShot,
    *,
    produce_mode_from_input: bool,
) -> ShotSubShot:
    """解析后定稿：回填画面时段与规范 produce_mode；未显式传入则推断。"""
    out = apply_image_timing_defaults(sub)
    mode = (
        coerce_produce_mode(out.produce_mode)
        if produce_mode_from_input
        else infer_produce_mode(out)
    )
    if mode != out.produce_mode:
        out = out.model_copy(update={"produce_mode": mode})
    return out
