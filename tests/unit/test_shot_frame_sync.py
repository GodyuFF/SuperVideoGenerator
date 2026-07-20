"""镜内画面与 frame 文字资产同步测试。"""

from __future__ import annotations

from core.edit.shot_sub_shot_frame_sync import sync_shot_sub_shot_frame_assets
from core.edit.video_plan_service import patch_shot_plan_fields
from core.models.entities import ShotSubShot, TextAssetType
from tests.support.shot_fixtures import _store_with_shot


def test_sync_creates_frame_for_visual_without_asset():
    """新增镜内画面应自动创建 frame 文字资产。"""
    store, script_id, shot = _store_with_shot()
    visual = ShotSubShot(start_ms=0, end_ms=3000, description="第二画面")
    patched = shot.model_copy(update={"sub_shots": [*shot.sub_shots, visual]})
    result = sync_shot_sub_shot_frame_assets(store, script_id, patched)
    assert len(result.sub_shots) == 2
    frame_id = result.sub_shots[1].images[0].frame_asset_id
    assert frame_id
    asset = store.get_text_asset(frame_id)
    assert asset is not None
    assert asset.type == TextAssetType.FRAME
    assert "第二画面" in str(asset.content.get("image_prompt") or "")


def test_patch_add_visual_creates_frame_and_rebuilds_video_tracks():
    """PATCH 增删画面应创建 frame 并重派生 video_tracks。"""
    store, script_id, shot = _store_with_shot(duration_ms=6000)
    old_clip_count = sum(len(t.clips) for t in shot.video_tracks)
    assert old_clip_count == 1

    result = patch_shot_plan_fields(
        store,
        script_id,
        shot.id,
        {
            "duration_ms": 6000,
            "sub_shots": [
                {
                    "start_ms": 0,
                    "end_ms": 3000,
                    "description": "前半",
                    "camera_motion": "static",
                    "element_refs": {},
                },
                {
                    "start_ms": 3000,
                    "end_ms": 6000,
                    "description": "后半",
                    "camera_motion": "ken_burns_in",
                    "element_refs": {},
                },
            ],
            "audio_tracks": [
                {
                    "kind": "voice",
                    "name": "角色音",
                    "clips": [
                        {"start_ms": 0, "end_ms": 6000, "text": "连续旁白"},
                    ],
                }
            ],
        },
        expected_revision=0,
    )
    updated = next(s for s in result["shots"] if s["id"] == shot.id)
    assert len(updated["sub_shots"]) == 2
    assert updated["sub_shots"][0]["images"][0]["frame_asset_id"]
    assert updated["sub_shots"][1]["images"][0]["frame_asset_id"]
    clip_count = sum(len(t.get("clips") or []) for t in updated["video_tracks"])
    assert clip_count == 2


def test_patch_clear_voice_clips_allowed():
    """PATCH 可清空配音幕（无 voice clip）。"""
    store, script_id, shot = _store_with_shot()
    result = patch_shot_plan_fields(
        store,
        script_id,
        shot.id,
        {
            "audio_tracks": [
                {"kind": "voice", "name": "角色音", "clips": []},
            ],
        },
        expected_revision=0,
    )
    updated = next(s for s in result["shots"] if s["id"] == shot.id)
    voice = next(t for t in updated["audio_tracks"] if t["kind"] == "voice")
    assert voice["clips"] == []


def test_patch_link_existing_frame_asset():
    """PATCH 可绑定已有 frame 文字资产，不重复创建。"""
    store, script_id, shot = _store_with_shot()
    shot = sync_shot_sub_shot_frame_assets(store, script_id, shot)
    existing_id = shot.sub_shots[0].images[0].frame_asset_id

    result = patch_shot_plan_fields(
        store,
        script_id,
        shot.id,
        {
            "sub_shots": [
                {
                    "start_ms": 0,
                    "end_ms": 8000,
                    "description": "沿用已有画面",
                    "camera_motion": "static",
                    "element_refs": {},
                    "images": [
                        {
                            "kind": "static",
                            "frame_asset_id": existing_id,
                        }
                    ],
                }
            ],
        },
        expected_revision=0,
    )
    updated = next(s for s in result["shots"] if s["id"] == shot.id)
    assert updated["sub_shots"][0]["images"][0]["frame_asset_id"] == existing_id
    frame_assets = [
        a for a in store.text_assets.values() if a.type == TextAssetType.FRAME
    ]
    assert len(frame_assets) == 1


def test_sync_updates_existing_frame_description():
    """修改镜内画面描述应回写 frame.image_prompt（未锁定时）。"""
    store, script_id, shot = _store_with_shot()
    shot = sync_shot_sub_shot_frame_assets(store, script_id, shot)
    frame_id = shot.sub_shots[0].images[0].frame_asset_id

    visual = shot.sub_shots[0].model_copy(update={"description": "更新后的画面"})
    sync_shot_sub_shot_frame_assets(store, script_id, shot.model_copy(update={"sub_shots": [visual]}))
    asset = store.get_text_asset(frame_id)
    assert "更新后的画面" in str(asset.content.get("image_prompt") or "")
