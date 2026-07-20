"""VideoPlan 用户编辑服务单元测试（新模型：镜内多轨 Shot）。"""

import pytest

from core.edit.video_plan_service import (
    VideoPlanNotFoundError,
    VideoPlanRevisionError,
    apply_video_plan_ops,
    patch_shot_plan_fields,
)
from core.models.entities import (
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    ScriptStatus,
    Shot,
    VideoPlan,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from tests.support.shot_fixtures import make_shot


def _sample_shot() -> Shot:
    """合法镜内多轨单镜。"""
    return make_shot(order=0, duration_ms=5000, text="原始旁白")


@pytest.fixture
def vp_store() -> MemoryStore:
    """含合法镜内结构的视频计划稿存储。"""
    store = MemoryStore()
    project = Project(title="vp-test")
    store.add_project(project)
    script = Script(project_id=project.id, title="S1", status=ScriptStatus.DRAFT)
    store.add_script(script)
    shot = _sample_shot()
    plan = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.STORYBOOK,
        shots=[shot],
        detail_revision=1,
    )
    store.set_video_plan(plan)
    audio = MediaAsset(
        project_id=project.id,
        script_id=script.id,
        type=MediaAssetType.AUDIO,
        name="tts",
        url="https://cdn.example.com/a.mp3",
        metadata={"shot_id": shot.id, "script_id": script.id},
    )
    store.add_media_asset(audio)
    return store


def test_patch_shot_audio_invalidates_tts(vp_store: MemoryStore):
    """修改镜内音频轨应标记 TTS superseded。"""
    script_id = list(vp_store.scripts.keys())[0]
    shot = vp_store.get_video_plan_for_script(script_id).shots[0]
    result = patch_shot_plan_fields(
        vp_store,
        script_id,
        shot.id,
        {
            "audio_tracks": [
                {
                    "kind": "voice",
                    "name": "角色音",
                    "clips": [
                        {
                            "start_ms": 0,
                            "end_ms": 5000,
                            "text": "新旁白文本",
                        }
                    ],
                }
            ],
            "subtitles": [
                {"text": "新旁白", "start_ms": 500, "end_ms": 2500},
                {"text": "文本", "start_ms": 2500, "end_ms": 4500},
            ],
        },
        expected_revision=1,
    )
    assert result["detail_revision"] == 2
    assert result["side_effects"]["tts_stale"] is True
    assert shot.id in result["side_effects"]["tts_stale_shot_ids"]
    for media in vp_store.media_assets.values():
        if media.metadata.get("shot_id") == shot.id:
            assert media.metadata.get("superseded") is True


def test_patch_shot_revision_conflict(vp_store: MemoryStore):
    """revision 冲突应抛 VideoPlanRevisionError。"""
    script_id = list(vp_store.scripts.keys())[0]
    shot = vp_store.get_video_plan_for_script(script_id).shots[0]
    with pytest.raises(VideoPlanRevisionError):
        patch_shot_plan_fields(
            vp_store,
            script_id,
            shot.id,
            {"duration_ms": 9999},
            expected_revision=99,
        )


def test_patch_shot_invalid_structure_fails(vp_store: MemoryStore):
    """非法镜内结构应返回校验错误。"""
    script_id = list(vp_store.scripts.keys())[0]
    shot = vp_store.get_video_plan_for_script(script_id).shots[0]
    with pytest.raises(ValueError, match="结构校验失败"):
        patch_shot_plan_fields(
            vp_store,
            script_id,
            shot.id,
            {
                "video_tracks": [
                    {
                        "z_index": 0,
                        "clips": [{"start_ms": 100, "end_ms": 50}],
                    }
                ],
            },
            expected_revision=1,
        )


def test_reorder_ops(vp_store: MemoryStore):
    """reorder op 应正确重排镜头 order。"""
    script_id = list(vp_store.scripts.keys())[0]
    shot2 = make_shot(order=1, duration_ms=2000, text="第二镜")
    plan = vp_store.get_video_plan_for_script(script_id)
    shots = list(plan.shots) + [shot2]
    vp_store.set_video_plan(plan.model_copy(update={"shots": shots, "detail_revision": 2}))
    ids = [s.id for s in shots]
    result = apply_video_plan_ops(
        vp_store,
        script_id,
        [{"op": "reorder", "ordered_shot_ids": list(reversed(ids))}],
        expected_revision=2,
    )
    reordered = result["shots"]
    assert reordered[0]["id"] == ids[1]
    assert reordered[1]["id"] == ids[0]


def test_get_video_plan_not_found_raises():
    """无计划稿时 patch 应抛 VideoPlanNotFoundError。"""
    store = MemoryStore()
    project = Project(title="empty")
    store.add_project(project)
    script = Script(project_id=project.id, title="S")
    store.add_script(script)
    with pytest.raises(VideoPlanNotFoundError):
        patch_shot_plan_fields(store, script.id, "shot_x", {"duration_ms": 1000})
