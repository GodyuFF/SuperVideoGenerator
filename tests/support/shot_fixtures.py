"""测试用镜内多轨 Shot 与 VideoPlan 辅助。"""

from __future__ import annotations

from core.models.entities import (
    Project,
    Script,
    Shot,
    ShotAudioClip,
    ShotAudioTrack,
    ShotVideoClip,
    ShotVideoTrack,
    ShotSubShot,
    VideoPlan,
    VideoStyleMode,
    new_id,
)
from core.store.memory import MemoryStore


def make_shot(
    *,
    order: int = 0,
    duration_ms: int = 3000,
    text: str = "测试旁白",
    camera_motion: str = "static",
    media_id: str = "",
) -> Shot:
    """构造含画面 + voice 轨 + z0 视频轨的最小可投影 Shot。"""
    visual = ShotSubShot(
        start_ms=0,
        end_ms=duration_ms,
        description=text,
        camera_motion=camera_motion,
    )
    return Shot(
        order=order,
        duration_ms=duration_ms,
        sub_shots=[visual],
        video_tracks=[
            ShotVideoTrack(
                id=new_id("svt"),
                name="主画面",
                z_index=0,
                clips=[
                    ShotVideoClip(
                        id=new_id("svc"),
                        start_ms=0,
                        end_ms=duration_ms,
                        source_sub_shot_id=visual.id,
                        media_id=media_id,
                        source_kind="still",
                        camera_motion=camera_motion,
                    )
                ],
            )
        ],
        audio_tracks=[
            ShotAudioTrack(
                kind="voice",
                name="角色音",
                clips=[
                    ShotAudioClip(start_ms=0, end_ms=duration_ms, text=text)
                ],
            )
        ],
    )


def shot_design_payload(
    *,
    order: int = 0,
    duration_ms: int = 5000,
    text: str = "测试旁白",
    camera_motion: str = "ken_burns_in",
    element_refs: dict[str, list[str]] | None = None,
) -> dict:
    """构造符合 create_shots schema 的镜头 JSON。"""
    refs = element_refs or {}
    return {
        "order": order,
        "duration_ms": duration_ms,
        "sub_shots": [
            {
                "start_ms": 0,
                "end_ms": duration_ms,
                "description": text,
                "camera_motion": camera_motion,
                "element_refs": refs,
            }
        ],
        "audio_tracks": [
            {
                "kind": "voice",
                "name": "角色音",
                "clips": [
                    {"start_ms": 0, "end_ms": duration_ms, "text": text},
                ],
            }
        ],
    }


def _store_with_shot(
    *,
    text: str = "测试旁白",
    duration_ms: int = 8000,
) -> tuple[MemoryStore, str, Shot]:
    """构建含单镜的最小 store。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    shot = make_shot(order=0, duration_ms=duration_ms, text=text)
    plan = VideoPlan(script_id=script.id, mode=VideoStyleMode.STORYBOOK, shots=[shot])
    store.set_video_plan(plan)
    return store, script.id, shot


def _store_with_two_shots() -> tuple[MemoryStore, str, Shot, Shot]:
    """构建含两镜的最小 store。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    shot1 = make_shot(order=0, duration_ms=3000, text="镜一")
    shot2 = make_shot(order=1, duration_ms=4000, text="镜二")
    plan = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.STORYBOOK,
        shots=[shot1, shot2],
    )
    store.set_video_plan(plan)
    return store, script.id, shot1, shot2
