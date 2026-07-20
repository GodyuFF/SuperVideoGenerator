"""镜内多轨结构校验：保证「可剪辑标准视频」不变量，无降级。

对应产品原则：以剪辑可控为核心、标准视频为唯一产物形态、缺素材显式报错不降级。

- validate_shot_structure：单镜结构自洽（时长为正、片段合法、同轨不重叠、片段在镜内）。
- validate_shots_editable：批量结构校验，返回每镜问题列表。
- validate_shots_render_ready：渲染/导出前的「无降级」就绪校验——每个视频/音频
  片段必须已绑定 media，缺素材显式列出，交由上层回补，绝不用占位素材静默出片。
"""

from __future__ import annotations

from core.edit.sub_shot_produce import validate_sub_shot_image_timings
from core.models.entities import Shot
from core.store.memory import MemoryStore


def shot_voice_text(shot: Shot) -> str:
    """拼接镜内 voice 音频 clip 文案。"""
    return "".join(
        c.text.strip()
        for t in shot.audio_tracks
        if t.kind == "voice"
        for c in t.clips
        if c.text.strip()
    )


def validate_shot_voice_content(shot: Shot, *, require_voice: bool = True) -> list[str]:
    """校验单镜 voice 配音幕是否满足图文管线要求。"""
    if not require_voice:
        return []
    issues: list[str] = []
    label = shot.id or f"镜{shot.order}"
    if not shot.sub_shots:
        return issues
    voice_tracks = [t for t in shot.audio_tracks if t.kind == "voice"]
    if not voice_tracks:
        issues.append(f"{label}: 缺少 kind=voice 的 audio_tracks（配音幕必填）")
        return issues
    has_text = any(c.text.strip() for t in voice_tracks for c in t.clips)
    if not has_text:
        issues.append(f"{label}: voice clip 缺少非空 text（TTS 与看板配音幕唯一输入）")
    return issues


def validate_shots_voice_content(
    shots: list[Shot],
    *,
    require_voice: bool = True,
) -> dict[str, list[str]]:
    """批量校验镜内 voice 配音幕，返回 {shot_id: [问题...]}。"""
    result: dict[str, list[str]] = {}
    for shot in shots:
        issues = validate_shot_voice_content(shot, require_voice=require_voice)
        if issues:
            result[shot.id] = issues
    return result


def validate_shots_voice_speakers(
    shots: list[Shot],
    store: MemoryStore,
    script_id: str,
) -> dict[str, list[str]]:
    """批量校验配音幕说话人（旁白 vs 角色对白），返回 {shot_id: [问题...]}。"""
    from core.edit.voice_speaker import validate_shots_voice_speakers as _validate

    return _validate(shots, store, script_id)


def validate_shot_structure(shot: Shot) -> list[str]:
    """校验单个分镜的镜内结构是否自洽可剪辑，返回问题描述列表（空表示通过）。"""
    issues: list[str] = []
    duration = int(shot.duration_ms or 0)
    label = shot.id or f"镜{shot.order}"

    if duration <= 0:
        issues.append(f"{label}: 分镜时长必须为正（当前 {duration}ms）")

    has_visual = bool(shot.sub_shots)
    has_video_clip = any(t.clips for t in shot.video_tracks)
    if not has_visual and not has_video_clip:
        issues.append(f"{label}: 分镜至少需要一个画面(visual)或一个视频片段")

    # 视频轨：片段合法 + 同轨不重叠 + 在镜内
    for track in shot.video_tracks:
        prev_end = -1
        for clip in sorted(track.clips, key=lambda c: c.start_ms):
            start = int(clip.start_ms or 0)
            end = int(clip.end_ms or 0)
            if end <= start:
                issues.append(f"{label}/视频轨{track.z_index}: 片段 {clip.id} 时长非法")
            if start < 0 or (duration > 0 and end > duration):
                issues.append(
                    f"{label}/视频轨{track.z_index}: 片段 {clip.id} 超出镜内 [0,{duration}]"
                )
            if start < prev_end:
                issues.append(
                    f"{label}/视频轨{track.z_index}: 片段 {clip.id} 与同轨片段重叠"
                )
            prev_end = max(prev_end, end)

    # 音频轨：片段合法 + 同轨不重叠 + 在镜内
    for track in shot.audio_tracks:
        prev_end = -1
        for clip in sorted(track.clips, key=lambda c: c.start_ms):
            start = int(clip.start_ms or 0)
            end = int(clip.end_ms or 0)
            if end <= start:
                issues.append(f"{label}/音频轨({track.kind}): 片段 {clip.id} 时长非法")
            if start < 0 or (duration > 0 and end > duration):
                issues.append(
                    f"{label}/音频轨({track.kind}): 片段 {clip.id} 超出镜内 [0,{duration}]"
                )
            if start < prev_end:
                issues.append(
                    f"{label}/音频轨({track.kind}): 片段 {clip.id} 与同轨片段重叠"
                )
            prev_end = max(prev_end, end)

    # 字幕：合法 + 在镜内 + 同镜不重叠（同一时刻仅一条）
    prev_sub_end = -1
    for sub in sorted(shot.subtitles, key=lambda s: (int(s.start_ms or 0), int(s.end_ms or 0))):
        start = int(sub.start_ms or 0)
        end = int(sub.end_ms or 0)
        if end <= start:
            issues.append(f"{label}/字幕: 片段 {sub.id} 时长非法")
        if start < 0 or (duration > 0 and end > duration):
            issues.append(f"{label}/字幕: 片段 {sub.id} 超出镜内 [0,{duration}]")
        if start < prev_sub_end:
            issues.append(f"{label}/字幕: 片段 {sub.id} 与同镜字幕时间重叠")
        prev_sub_end = max(prev_sub_end, end)

    # 子镜画面时段：落在子镜内且 start < end
    for sub in shot.sub_shots:
        sub_label = f"{label}/子镜{sub.id or sub.start_ms}"
        for issue in validate_sub_shot_image_timings(sub):
            issues.append(f"{sub_label}: {issue}")

    return issues


def validate_shots_editable(shots: list[Shot]) -> dict[str, list[str]]:
    """批量校验分镜结构自洽，返回 {shot_id: [问题...]}，仅含有问题的分镜。"""
    result: dict[str, list[str]] = {}
    for shot in shots:
        issues = validate_shot_structure(shot)
        if issues:
            result[shot.id] = issues
    return result


def validate_shots_render_ready(shots: list[Shot]) -> list[str]:
    """渲染/导出前的无降级就绪校验：每个视频/音频片段必须已绑定 media_id。

    返回缺素材的问题列表（空表示可直接渲染）。字幕不含 media，仅要求文本非空。
    """
    issues: list[str] = []
    for shot in shots:
        label = shot.id or f"镜{shot.order}"
        for track in shot.video_tracks:
            for clip in track.clips:
                if not clip.media_id:
                    issues.append(
                        f"{label}/视频轨{track.z_index}: 片段 {clip.id} 缺少 media（需回补生图/生视频）"
                    )
        for track in shot.audio_tracks:
            for clip in track.clips:
                if not clip.media_id:
                    kind_hint = "配音" if track.kind == "voice" else "背景音"
                    issues.append(
                        f"{label}/音频轨({track.kind}): 片段 {clip.id} 缺少 media（需回补{kind_hint}）"
                    )
    return issues
