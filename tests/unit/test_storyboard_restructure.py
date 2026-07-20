"""分镜结构性复核单元测试（新模型：镜内多轨 Shot）。"""

from core.edit.storyboard_restructure import apply_restructure_ops
from core.models.entities import (
    Project,
    Script,
    Shot,
    ShotAudioClip,
    ShotAudioTrack,
    ShotSubtitle,
    ShotSubShot,
    ShotSubShotImage,
    VideoPlan,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from tests.support.shot_fixtures import make_shot


def _store_with_script() -> tuple[MemoryStore, str]:
    """创建内存 store 与剧本 ID。"""
    store = MemoryStore()
    project = Project(title="复核测试")
    store.add_project(project)
    script = Script(project_id=project.id, title="测试", content_md="# 测试")
    store.add_script(script)
    return store, script.id


def _plan_with_shot(store: MemoryStore, script_id: str) -> Shot:
    """写入单镜计划稿并返回镜头。"""
    shot = make_shot(order=0, duration_ms=4000, text="测试旁白")
    plan = VideoPlan(script_id=script_id, mode=VideoStyleMode.STORYBOOK, shots=[shot])
    store.set_video_plan(plan)
    return shot


def test_apply_restructure_adjust_duration():
    """adjust 操作应更新镜时长。"""
    store, script_id = _store_with_script()
    shot = _plan_with_shot(store, script_id)
    plan = apply_restructure_ops(
        store,
        script_id,
        [{"op": "adjust", "shot_id": shot.id, "duration_ms": 6000}],
    )
    assert plan.shots[0].duration_ms == 6000
    assert plan.detail_revision == 1


def test_apply_restructure_delete_shot():
    """delete 操作应移除镜头。"""
    store, script_id = _store_with_script()
    shot = _plan_with_shot(store, script_id)
    plan = apply_restructure_ops(
        store,
        script_id,
        [{"op": "delete", "shot_id": shot.id}],
    )
    assert len(plan.shots) == 0


def test_apply_restructure_adjust_audio_tracks():
    """adjust 带 audio_tracks 应整体替换镜内音轨。"""
    store, script_id = _store_with_script()
    shot = _plan_with_shot(store, script_id)
    plan = apply_restructure_ops(
        store,
        script_id,
        [
            {
                "op": "adjust",
                "shot_id": shot.id,
                "audio_tracks": [
                    {
                        "kind": "voice",
                        "name": "角色音",
                        "clips": [
                            {
                                "start_ms": 0,
                                "end_ms": 8000,
                                "text": "新旁白",
                            }
                        ],
                    }
                ],
                "duration_ms": 8000,
            }
        ],
    )
    updated = plan.shots[0]
    assert updated.duration_ms == 8000
    assert updated.audio_tracks[0].clips[0].text == "新旁白"


def test_apply_restructure_adjust_partial_sub_shot_by_id():
    """adjust 子镜 patch 仅含 id+时段时应增量合并，保留 description。"""
    store, script_id = _store_with_script()
    shot = _plan_with_shot(store, script_id)
    original_desc = shot.sub_shots[0].description
    ssb_id = shot.sub_shots[0].id
    plan = apply_restructure_ops(
        store,
        script_id,
        [
            {
                "op": "adjust",
                "shot_id": shot.id,
                "duration_ms": 2500,
                "sub_shots": [{"id": ssb_id, "start_ms": 0, "end_ms": 2500}],
            }
        ],
    )
    updated = plan.shots[0]
    assert updated.duration_ms == 2500
    assert updated.sub_shots[0].end_ms == 2500
    assert updated.sub_shots[0].description == original_desc
    assert updated.video_tracks[0].clips[0].end_ms == 2500


def test_apply_restructure_add_repairs_stale_image_timings():
    """新增镜头前应钳制既有镜越界 images，避免全量结构校验失败。"""
    store, script_id = _store_with_script()
    dirty = Shot(
        order=0,
        duration_ms=4581,
        sub_shots=[
            ShotSubShot(
                id="ssb_a",
                start_ms=0,
                end_ms=4580,
                description="A",
                images=[ShotSubShotImage(start_ms=0, end_ms=8000)],
            ),
            ShotSubShot(
                id="ssb_b",
                start_ms=4580,
                end_ms=4581,
                description="B",
                images=[ShotSubShotImage(start_ms=8000, end_ms=15000)],
            ),
        ],
        audio_tracks=[
            ShotAudioTrack(
                kind="voice",
                name="角色音",
                clips=[ShotAudioClip(start_ms=0, end_ms=4581, text="旁白")],
            )
        ],
    )
    store.set_video_plan(
        VideoPlan(script_id=script_id, mode=VideoStyleMode.STORYBOOK, shots=[dirty])
    )
    plan = apply_restructure_ops(
        store,
        script_id,
        [
            {
                "op": "add",
                "after_order": 0,
                "new_shot": {
                    "order": 1,
                    "duration_ms": 3000,
                    "sub_shots": [
                        {
                            "start_ms": 0,
                            "end_ms": 3000,
                            "description": "",
                            "camera_motion": "static",
                        }
                    ],
                    "audio_tracks": [
                        {
                            "kind": "voice",
                            "name": "角色音",
                            "clips": [{"start_ms": 0, "end_ms": 3000, "text": ""}],
                        }
                    ],
                },
            }
        ],
    )
    assert len(plan.shots) == 2
    first = plan.shots[0]
    assert first.sub_shots[0].images[0].end_ms == 4580
    assert first.sub_shots[1].images[0].start_ms == 4580
    assert first.sub_shots[1].images[0].end_ms == 4581
