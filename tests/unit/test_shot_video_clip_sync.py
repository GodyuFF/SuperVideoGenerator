"""镜内子镜与 video_clip 文字资产同步测试。"""

from __future__ import annotations

from core.edit.shot_sub_shot_video_clip_sync import sync_shot_sub_shot_video_clip_assets
from core.edit.video_plan_service import patch_shot_plan_fields
from core.models.entities import ShotSubShot, TextAssetType, VideoStyleMode
from tests.support.shot_fixtures import _store_with_shot


def test_sync_creates_video_clip_for_sub_shot_without_asset():
    """新增子镜应自动创建 video_clip 文字资产。"""
    store, script_id, shot = _store_with_shot()
    visual = ShotSubShot(start_ms=0, end_ms=3000, description="第二子镜")
    patched = shot.model_copy(update={"sub_shots": [*shot.sub_shots, visual]})
    result = sync_shot_sub_shot_video_clip_assets(store, script_id, patched)
    assert len(result.sub_shots) == 2
    clip_id = result.sub_shots[1].videos[0].video_clip_asset_id
    assert clip_id
    asset = store.get_text_asset(clip_id)
    assert asset is not None
    assert asset.type == TextAssetType.VIDEO_CLIP
    assert asset.content.get("video_prompt")


def test_patch_ai_video_plan_syncs_video_clips():
    """AI 视频模式 PATCH 应同步 video_clip 资产。"""
    store, script_id, shot = _store_with_shot()
    plan = store.get_video_plan_for_script(script_id)
    assert plan is not None
    store.set_video_plan(plan.model_copy(update={"mode": VideoStyleMode.AI_VIDEO}))
    result = patch_shot_plan_fields(
        store,
        script_id,
        shot.id,
        {
            "sub_shots": [
                {
                    "start_ms": 0,
                    "end_ms": 3000,
                    "description": "AI 视频子镜",
                    "camera_motion": "static",
                    "element_refs": {},
                }
            ],
        },
        expected_revision=0,
    )
    stored = store.get_video_plan_for_script(script_id)
    assert stored is not None
    assert stored.mode == VideoStyleMode.AI_VIDEO
    stored_shot = next(s for s in stored.shots if s.id == shot.id)
    assert stored_shot.sub_shots[0].videos, stored_shot.model_dump()
    updated = next(s for s in result["shots"] if s["id"] == shot.id)
    assert updated["sub_shots"][0]["videos"][0]["video_clip_asset_id"]
