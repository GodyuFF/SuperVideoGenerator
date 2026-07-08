"""subtitle_align 与 TTS cue 持久化测试。"""

from core.edit.subtitle_align import enrich_subtitles_from_audio
from core.edit.timeline import compile_timeline_from_shots, normalize_tracks
from core.models.entities import (
    AssetScope,
    EditClip,
    EditTimeline,
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    TextAsset,
    TextAssetType,
    VideoPlan,
    VideoPlanShot,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from core.tts.subtitle import populate_legacy_submaker_with_full_text, subtitle_cues_from_submaker
from edge_tts import SubMaker
from tests.support.frame_fixtures import ensure_shot_frame_image


def _store_with_audio_cues() -> MemoryStore:
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1", duration_sec=60)
    store.add_script(script)
    char = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="虎",
        content={"summary": "虎"},
    )
    store.add_text_asset(char)
    media = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.IMAGE,
        name="图",
        url="https://images.test/t.png",
        source_asset_id=char.id,
    )
    store.add_media_asset(media)
    char.primary_media_id = media.id
    store.update_text_asset(char)

    shot = VideoPlanShot(
        order=0,
        duration_ms=6000,
        narration_text="第一句。第二句！",
        camera_motion="ken_burns_in",
        asset_refs={"character": [char.id]},
    )
    ensure_shot_frame_image(
        store,
        project_id=project.id,
        script_id=script.id,
        shot=shot,
        image_url="https://images.test/t.png",
    )
    plan = VideoPlan(script_id=script.id, mode=VideoStyleMode.DYNAMIC_IMAGE, shots=[shot])
    store.set_video_plan(plan)

    sub_maker = populate_legacy_submaker_with_full_text(SubMaker(), shot.narration_text, 6.0)
    cues = subtitle_cues_from_submaker(sub_maker)
    audio = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.AUDIO,
        name="配音",
        url="https://audio.test/a.mp3",
        metadata={
            "shot_id": shot.id,
            "duration_ms": 6000,
            "narration_text": shot.narration_text,
            "subtitle_cues": cues,
        },
    )
    store.add_media_asset(audio)
    store._test_script_id = script.id  # type: ignore[attr-defined]
    store._test_shot_id = shot.id  # type: ignore[attr-defined]
    store._test_audio_id = audio.id  # type: ignore[attr-defined]
    store._test_media_id = media.id  # type: ignore[attr-defined]
    return store


def test_subtitle_cues_from_punctuation_split():
    sub_maker = populate_legacy_submaker_with_full_text(
        SubMaker(), "你好，世界！再见。", 3.0
    )
    cues = subtitle_cues_from_submaker(sub_maker)
    assert len(cues) >= 2
    assert cues[0]["end_ms"] > cues[0]["start_ms"]


def test_enrich_subtitles_from_audio_splits_by_cues():
    store = _store_with_audio_cues()
    script_id = store._test_script_id  # type: ignore[attr-defined]
    media_id = store._test_media_id  # type: ignore[attr-defined]
    audio_id = store._test_audio_id  # type: ignore[attr-defined]
    plan = store.get_video_plan_for_script(script_id)
    assert plan

    timeline = EditTimeline(
        script_id=script_id,
        duration_ms=6000,
        tracks=normalize_tracks(
            {
                "video": [
                    {
                        "track": "video",
                        "start_ms": 0,
                        "end_ms": 6000,
                        "asset_ref": media_id,
                    }
                ],
                "audio": [
                    {
                        "track": "audio",
                        "start_ms": 0,
                        "end_ms": 6000,
                        "asset_ref": audio_id,
                        "metadata": {"shot_id": plan.shots[0].id},
                    }
                ],
                "subtitle": [],
            }
        ),
    )
    enriched = enrich_subtitles_from_audio(store, timeline, plan)
    subs = enriched.tracks.get("subtitle", [])
    assert len(subs) >= 2
    assert all(isinstance(s.label, str) and s.label for s in subs)


def test_compile_timeline_finalize_includes_split_subtitles():
    store = _store_with_audio_cues()
    script_id = store._test_script_id  # type: ignore[attr-defined]
    audio_id = store._test_audio_id  # type: ignore[attr-defined]
    plan = store.get_video_plan_for_script(script_id)
    assert plan
    from core.edit.timeline import finalize_merged_timeline

    timeline = compile_timeline_from_shots(
        store,
        script_id=script_id,
        plan=plan,
        tts_by_shot={plan.shots[0].id: audio_id},
    )
    finalized = finalize_merged_timeline(store, timeline, plan)
    subs = finalized.tracks.get("subtitle", [])
    assert len(subs) >= 2
