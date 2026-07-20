"""SVF ↔ OpenCut Classic 项目适配器契约测试（ticks 换算与复合键）。"""

from __future__ import annotations

from core.edit.compose import compose_timeline_plan
from core.edit.transform_interp import interpolate_transform, transform_to_overlay_pixels
from core.models.entities import (
    EditClip,
    EditClipKeyframe,
    EditClipMotionDetail,
    EditClipSourceRefs,
    EditClipTransform,
    EditTimeline,
    EditVideoLayer,
    Project,
    Script,
    VideoStyleMode,
)
from core.store.memory import MemoryStore

TICKS_PER_SECOND = 120_000


def ms_to_ticks(ms: int) -> int:
    """毫秒转 Classic ticks（与前端 svfProjectAdapter 一致）。"""
    return round((ms / 1000) * TICKS_PER_SECOND)


def ticks_to_ms(ticks: int) -> int:
    """Classic ticks 转毫秒。"""
    return round((ticks / TICKS_PER_SECOND) * 1000)


def svf_project_key(project_id: str, script_id: str) -> str:
    """SVF 复合项目键。"""
    return f"{project_id}__{script_id}"


def compute_media_trim_fields(
    clip_duration_ms: int,
    source_duration_ms: int,
    *,
    pad_source_to_clip: bool = False,
) -> dict[str, int]:
    """与前端 svfTrimFields.computeMediaTrimFields 一致的 trim 契约。"""
    clip_ticks = ms_to_ticks(clip_duration_ms)
    source_ticks = ms_to_ticks(source_duration_ms)
    if clip_ticks >= source_ticks:
        effective_source = max(source_ticks, clip_ticks) if pad_source_to_clip else source_ticks
        return {"trimStart": 0, "trimEnd": 0, "sourceDuration": effective_source}
    return {
        "trimStart": 0,
        "trimEnd": source_ticks - clip_ticks,
        "sourceDuration": source_ticks,
    }


def classic_layout_matches_api(
    *,
    start_ms: int,
    end_ms: int,
    classic_start_ms: int,
    classic_dur_ms: int,
) -> bool:
    """与前端 classicLayoutMatchesApi 一致：拒绝与 API 区间严重偏离的快照。"""
    api_dur_ms = end_ms - start_ms
    start_drift = abs(classic_start_ms - start_ms)
    end_drift = abs(classic_start_ms + classic_dur_ms - end_ms)
    if start_drift > 500:
        return False
    if classic_dur_ms < api_dur_ms * 0.7:
        return False
    if end_drift > 500:
        return False
    return True


class TestSvfProjectAdapterContract:
    """验证适配层时间换算与键格式。"""

    def test_ms_ticks_roundtrip(self) -> None:
        """3 秒片段 ticks 往返误差应在 1ms 内。"""
        ms = 3000
        assert abs(ticks_to_ms(ms_to_ticks(ms)) - ms) <= 1

    def test_project_key_format(self) -> None:
        """复合键应可唯一定位 project + script。"""
        key = svf_project_key("proj_1", "scr_2")
        assert key == "proj_1__scr_2"
        parts = key.split("__", 1)
        assert parts == ["proj_1", "scr_2"]

    def test_zero_start_clip(self) -> None:
        """零起点 clip 的 ticks 应为 0。"""
        assert ms_to_ticks(0) == 0

    def test_full_length_audio_clip_trim_end_zero(self) -> None:
        """16s 源 + 16s clip → trimEnd=0、sourceDuration=全长。"""
        trim = compute_media_trim_fields(16000, 16000)
        assert trim["trimEnd"] == 0
        assert trim["sourceDuration"] == ms_to_ticks(16000)

    def test_audio_slot_longer_than_probe_pads_source(self) -> None:
        """5.33s 槽位 + 2.3s 探测源 → pad 后 sourceDuration 抬到槽位（与前端 padSourceToClip 一致）。"""
        trim = compute_media_trim_fields(5330, 2300, pad_source_to_clip=True)
        assert trim["trimEnd"] == 0
        assert trim["sourceDuration"] == ms_to_ticks(5330)

    def test_classic_layout_rejects_packed_subtitle_snapshot(self) -> None:
        """紧凑字幕快照（~1.4s 起止）不得覆盖 26s 计划中的 API 区间。"""
        assert not classic_layout_matches_api(
            start_ms=0,
            end_ms=5330,
            classic_start_ms=0,
            classic_dur_ms=1395,
        )
        assert classic_layout_matches_api(
            start_ms=5330,
            end_ms=12030,
            classic_start_ms=5330,
            classic_dur_ms=6700,
        )

    def test_partial_audio_clip_trim_end(self) -> None:
        """8s clip 取自 16s 源 → trimEnd=剩余 8s。"""
        trim = compute_media_trim_fields(8000, 16000)
        assert trim["trimEnd"] == ms_to_ticks(8000)
        assert trim["trimStart"] == 0

    def test_audio_clip_extended_to_source_has_zero_trim(self) -> None:
        """音频 clip 扩展至源全长后 trimEnd 应为 0（与前端 resolveAudioClipDurationMs 一致）。"""
        clip_ms = 5000
        source_ms = 10000
        visible_ms = source_ms if source_ms > clip_ms + 50 else clip_ms
        trim = compute_media_trim_fields(visible_ms, source_ms)
        assert trim["trimEnd"] == 0
        assert trim["sourceDuration"] == ms_to_ticks(source_ms)

    def test_timeline_metadata_patch_roundtrip(self) -> None:
        """PATCH 应支持 timeline.metadata 字段（Classic 项目快照）。"""
        from core.edit.timeline_service import patch_timeline
        from core.models.entities import EditTimeline, Project, Script
        from core.store.memory import MemoryStore

        store = MemoryStore()
        project = Project(title="p")
        store.add_project(project)
        script = Script(project_id=project.id, title="s")
        store.add_script(script)
        timeline = EditTimeline(script_id=script.id, plan_id="")
        store.set_edit_timeline(timeline)
        view = patch_timeline(
            store,
            script_id=script.id,
            project_id=project.id,
            body={"metadata": {"classic_project": {"version": 22}}},
        )
        assert view.get("metadata", {}).get("classic_project", {}).get("version") == 22

    def test_transform_pixel_mapping_matches_preview_bridge(self) -> None:
        """归一化 transform 映射到像素偏移：(x-0.5)*canvas。"""
        canvas_w, canvas_h = 1920, 1080
        x, y, width, height = 0.8, 0.2, 0.25, 0.25
        pos_x = (x - 0.5) * canvas_w
        pos_y = (y - 0.5) * canvas_h
        assert abs(pos_x - 576) < 1e-6
        assert abs(pos_y - (-324)) < 1e-6
        clip = EditClip(
            track="video",
            start_ms=0,
            end_ms=4000,
            transform=EditClipTransform(x=x, y=y, width=width, height=height),
            motion_detail=EditClipMotionDetail(scale_from=1.0, scale_to=1.2),
            motion="ken_burns_in",
        )
        mid = interpolate_transform(clip, 2000)
        assert mid.scale > 1.0
        pixels = transform_to_overlay_pixels(
            mid, canvas_width=canvas_w, canvas_height=canvas_h
        )
        assert pixels["w"] > 0
        assert pixels["h"] > 0

    def test_compose_plan_uses_shot_order_for_main_layer(self) -> None:
        """compose 主层 segment 顺序与 video_plan_shot_order 一致。"""
        store = MemoryStore()
        project = Project(title="p")
        store.add_project(project)
        script = Script(project_id=project.id, title="s")
        store.add_script(script)
        timeline = EditTimeline(
            script_id=script.id,
            plan_id="",
            video_layers=[
                EditVideoLayer(
                    id="main",
                    name="主画面",
                    z_index=0,
                    clips=[
                        EditClip(
                            id="c2",
                            track="video",
                            start_ms=4000,
                            end_ms=8000,
                            source_refs=EditClipSourceRefs(video_plan_shot_order=1),
                        ),
                        EditClip(
                            id="c1",
                            track="video",
                            start_ms=0,
                            end_ms=4000,
                            source_refs=EditClipSourceRefs(video_plan_shot_order=0),
                        ),
                    ],
                )
            ],
        )
        store.set_edit_timeline(timeline)
        plan = compose_timeline_plan(store, timeline, style_mode=VideoStyleMode.STORYBOOK)
        main_seg_ids = [
            s["clip_id"]
            for s in plan["segments"]
            if s.get("z_index") == 0
        ]
        assert main_seg_ids.index("c1") < main_seg_ids.index("c2")

    def test_keyframe_patch_roundtrip_preserves_time_ms(self) -> None:
        """PATCH 应持久化 transform.keyframes（Classic 保存回写契约）。"""
        from core.edit.timeline_service import patch_timeline

        store = MemoryStore()
        project = Project(title="p")
        store.add_project(project)
        script = Script(project_id=project.id, title="s")
        store.add_script(script)
        timeline = EditTimeline(script_id=script.id, plan_id="")
        store.set_edit_timeline(timeline)
        kf = EditClipKeyframe(time_ms=1500, opacity=0.5, x=0.6)
        clip = EditClip(
            id="clip_kf",
            track="video",
            start_ms=0,
            end_ms=4000,
            transform=EditClipTransform(
                x=0.5,
                y=0.5,
                keyframes=[kf],
            ),
            motion="static",
        )
        view = patch_timeline(
            store,
            script_id=script.id,
            project_id=project.id,
            body={
                "video_layers": [
                    {
                        "id": "main",
                        "name": "主画面",
                        "z_index": 0,
                        "clips": [
                            {
                                "id": clip.id,
                                "track": "video",
                                "start_ms": clip.start_ms,
                                "end_ms": clip.end_ms,
                                "transform": {
                                    "x": 0.5,
                                    "y": 0.5,
                                    "width": 1.0,
                                    "height": 1.0,
                                    "opacity": 1.0,
                                    "rotation": 0.0,
                                    "keyframes": [
                                        {
                                            "time_ms": 1500,
                                            "opacity": 0.5,
                                            "x": 0.6,
                                        }
                                    ],
                                },
                                "motion": "static",
                            }
                        ],
                    }
                ],
            },
        )
        saved = view["video_layers"][0]["clips"][0]["transform"]["keyframes"][0]
        assert saved["time_ms"] == 1500
        assert saved["opacity"] == 0.5
        assert saved["x"] == 0.6
