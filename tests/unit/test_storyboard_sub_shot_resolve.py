# -*- coding: utf-8 -*-
"""create_frames / create_video_clips 定位与回传修复测试。"""

from __future__ import annotations

import json

import pytest

from core.edit.shot_query import serialize_shots_for_agent
from core.edit.sub_shot_helpers import link_sub_shot_frame, link_sub_shot_video
from core.llm.agent.llm_action import (
    _create_frame_assets_from_data,
    _create_video_clip_assets_from_data,
)
from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.shared.media_common import apply_agent_action
from core.models.entities import (
    AssetScope,
    Project,
    Script,
    ShotSubShotImage,
    ShotSubShotVideo,
    TextAsset,
    TextAssetType,
)
from core.store.memory import MemoryStore
from tests.support.shot_fixtures import make_shot


def _ctx(store: MemoryStore, script: Script, project: Project, shot) -> AgentRunContext:
    """构造带 pending shots 的分镜 Agent 上下文。"""
    return AgentRunContext(
        task_brief="",
        work_context={
            "project_id": project.id,
            "script_id": script.id,
            "_pending_shots": [shot],
        },
        script_id=script.id,
        step_id="",
        agent_name="storyboard_agent",
    )


def test_create_frames_resolves_by_sub_shot_id_alone():
    """仅传 sub_shot_id（无 shot_id）时应能关联父镜并创建 frame。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    shot = make_shot(order=0, text="旁白", duration_ms=3000)
    sub_id = shot.sub_shots[0].id
    ctx = _ctx(store, script, project, shot)

    created, updated, links = _create_frame_assets_from_data(
        store,
        ctx,
        [
            {
                "sub_shot_id": sub_id,
                "image_prompt": "温暖厨房角落，橘猫探头看向盘中煎鱼，阳光斜照。" * 2,
                "element_refs": {},
            }
        ],
        [shot],
    )
    assert len(created) == 1
    assert links[0]["shot_id"] == shot.id
    assert links[0]["sub_shot_id"] == sub_id
    assert updated[0].sub_shots[0].images[0].frame_asset_id == created[0].id


def test_create_frames_unknown_sub_shot_id_raises_clear_error():
    """未知 sub_shot_id 应给出可读错误，而非静默跳过。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    shot = make_shot(order=0, text="旁白", duration_ms=3000)
    ctx = _ctx(store, script, project, shot)

    with pytest.raises(ValueError, match="未找到子镜|未能定位"):
        _create_frame_assets_from_data(
            store,
            ctx,
            [
                {
                    "sub_shot_id": "ssb_does_not_exist",
                    "image_prompt": "空镜描述足够长用于测试定位失败路径。" * 2,
                    "element_refs": {},
                }
            ],
            [shot],
        )


def test_create_frames_upserts_empty_image_slot():
    """已有空 images 占位时应写入该槽，而不是再 append 第二条。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    shot = make_shot(order=0, text="旁白", duration_ms=3000)
    shot.sub_shots[0].images = [
        ShotSubShotImage(start_ms=0, end_ms=3000, kind="static"),
    ]
    sub_id = shot.sub_shots[0].id
    ctx = _ctx(store, script, project, shot)

    created, updated, _ = _create_frame_assets_from_data(
        store,
        ctx,
        [
            {
                "sub_shot_id": sub_id,
                "image_prompt": "空镜占位回填测试，画面描述足够长。" * 2,
                "element_refs": {},
            }
        ],
        [shot],
    )
    assert len(created) == 1
    assert len(updated[0].sub_shots[0].images) == 1
    assert updated[0].sub_shots[0].images[0].frame_asset_id == created[0].id


def test_create_video_clips_auto_binds_source_frame():
    """同子镜已有 frame 时，create_video_clips 应自动回填 source_frame_asset_id。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    frame = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.FRAME,
        scope=AssetScope.SCRIPT_PRIVATE,
        name="frame",
        content={"image_prompt": "静帧"},
        source_script_id=script.id,
    )
    store.add_text_asset(frame)

    shot = make_shot(order=0, text="旁白", duration_ms=3000)
    sub_id = shot.sub_shots[0].id
    shot.sub_shots[0].images = [ShotSubShotImage(frame_asset_id=frame.id)]
    ctx = _ctx(store, script, project, shot)

    created, updated, links = _create_video_clip_assets_from_data(
        store,
        ctx,
        [
            {
                "sub_shot_id": sub_id,
                "video_prompt": "小猫缓慢探头，鼻子抽动，铃铛轻晃。" * 2,
                "element_refs": {},
            }
        ],
        [shot],
    )
    assert len(created) == 1
    assert updated[0].sub_shots[0].videos[0].source_frame_asset_id == frame.id
    assert links[0].get("source_frame_asset_id") == frame.id


def test_serialize_shots_for_agent_includes_asset_links():
    """serialize_shots_for_agent 应暴露 frame / video_clip / source_frame 映射。"""
    shot = make_shot(order=0, text="旁白", duration_ms=3000)
    shot.sub_shots[0].images = [ShotSubShotImage(frame_asset_id="txt_frame_1")]
    shot.sub_shots[0].videos = [
        ShotSubShotVideo(
            video_clip_asset_id="txt_clip_1",
            source_frame_asset_id="txt_frame_1",
        )
    ]
    payload = serialize_shots_for_agent([shot])
    sub = payload[0]["sub_shots"][0]
    assert sub["images"][0]["frame_asset_id"] == "txt_frame_1"
    assert sub["videos"][0]["video_clip_asset_id"] == "txt_clip_1"
    assert sub["videos"][0]["source_frame_asset_id"] == "txt_frame_1"


def test_apply_agent_action_create_frames_observation_includes_links():
    """create_frames 的 observation 应包含 frame_links JSON，即使 LLM 自带 observation。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    shot = make_shot(order=0, text="旁白", duration_ms=3000)
    sub_id = shot.sub_shots[0].id
    ctx = _ctx(store, script, project, shot)

    result = apply_agent_action(
        store,
        ctx,
        {
            "observation": "自写摘要，不应吞掉映射",
            "frames": [
                {
                    "sub_shot_id": sub_id,
                    "image_prompt": "观察回传映射测试，画面描述足够长。" * 2,
                    "element_refs": {},
                }
            ],
        },
        agent="storyboard_agent",
        action="create_frames",
    )
    assert "frame_links" in result.observation
    data = json.loads(result.observation.split("\n\n", 1)[1])
    assert data["frame_links"][0]["sub_shot_id"] == sub_id
    assert data["frame_links"][0]["frame_asset_id"].startswith("txt_")


def test_link_sub_shot_frame_fills_empty_slot():
    """link_sub_shot_frame 应优先填空槽。"""
    shot = make_shot(order=0, text="旁白", duration_ms=3000)
    sub = shot.sub_shots[0]
    sub = sub.model_copy(
        update={"images": [ShotSubShotImage(start_ms=0, end_ms=3000)]}
    )
    linked = link_sub_shot_frame(sub, ShotSubShotImage(frame_asset_id="txt_f1"))
    assert len(linked.images) == 1
    assert linked.images[0].frame_asset_id == "txt_f1"
    assert linked.images[0].end_ms == 3000


def test_link_sub_shot_video_fills_empty_slot():
    """link_sub_shot_video 应优先填空槽。"""
    shot = make_shot(order=0, text="旁白", duration_ms=3000)
    sub = shot.sub_shots[0]
    sub = sub.model_copy(
        update={"videos": [ShotSubShotVideo(start_ms=0, end_ms=3000)]}
    )
    linked = link_sub_shot_video(
        sub,
        ShotSubShotVideo(
            video_clip_asset_id="txt_c1",
            source_frame_asset_id="txt_f1",
        ),
    )
    assert len(linked.videos) == 1
    assert linked.videos[0].video_clip_asset_id == "txt_c1"
    assert linked.videos[0].source_frame_asset_id == "txt_f1"
