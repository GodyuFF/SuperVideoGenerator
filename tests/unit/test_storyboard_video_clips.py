"""storyboard create_video_clips 与子镜 video_clip 关联测试。"""

import pytest

from core.llm.agent.llm_action import (
    _create_video_clip_assets_from_data,
    apply_action_result,
)
from core.llm.agent.react_core import AgentRunContext
from core.models.entities import (
    AssetScope,
    Project,
    Script,
    TextAsset,
    TextAssetType,
)
from core.store.memory import MemoryStore
from tests.support.shot_fixtures import make_shot


def test_create_video_clips_links_shot_and_clip_asset():
    """create_video_clips 应创建 video_clip 并回填 sub_shot.videos。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    scene = TextAsset(
        project_id=project.id,
        type=TextAssetType.SCENE,
        scope=AssetScope.PROJECT_SHARED,
        name="空镜",
        content={"description": "城市夜景背景板描述足够长用于测试。" * 2},
        source_script_id=script.id,
    )
    store.add_text_asset(scene)

    shot = make_shot(order=0, text="旁白", duration_ms=3000)
    sub_id = shot.sub_shots[0].id
    shot.sub_shots[0].element_refs = {"scene": [scene.id]}
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id, "script_id": script.id},
        script_id=script.id,
        step_id="",
        agent_name="storyboard_agent",
    )
    created, updated, links = _create_video_clip_assets_from_data(
        store,
        ctx,
        [
            {
                "shot_id": shot.id,
                "sub_shot_id": sub_id,
                "video_prompt": "镜头向前推进，城市霓虹闪烁",
                "element_refs": {"scene": [scene.id]},
            }
        ],
        [shot],
    )
    assert len(created) == 1
    assert created[0].type == TextAssetType.VIDEO_CLIP
    assert updated[0].sub_shots[0].videos
    assert updated[0].sub_shots[0].videos[0].video_clip_asset_id == created[0].id
    assert created[0].content.get("shot_id") == shot.id
    assert created[0].content.get("sub_shot_id") == sub_id
    assert links[0]["video_clip_asset_id"] == created[0].id


def test_create_video_clips_requires_sub_shot_id():
    """缺 sub_shot_id 时应报错。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    shot = make_shot(order=0, text="旁白", duration_ms=3000)
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id, "script_id": script.id},
        script_id=script.id,
        step_id="",
        agent_name="storyboard_agent",
    )
    with pytest.raises(ValueError, match="sub_shot_id"):
        _create_video_clip_assets_from_data(
            store,
            ctx,
            [{"shot_id": shot.id, "description": "空镜"}],
            [shot],
        )


def test_apply_create_video_clips_action():
    """apply_action_result 应处理 create_video_clips。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    shot = make_shot(order=0, text="旁白", duration_ms=3000)
    sub_id = shot.sub_shots[0].id
    ctx = AgentRunContext(
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
    obs = apply_action_result(
        store,
        "storyboard_agent",
        "create_video_clips",
        ctx,
        {
            "observation": "创建 video_clip",
            "video_clips": [
                {
                    "shot_id": shot.id,
                    "sub_shot_id": sub_id,
                    "video_prompt": "空镜镜头",
                    "element_refs": {},
                }
            ],
        },
    )
    assert "video_clip" in obs.lower()
    pending = ctx.work_context["_pending_shots"]
    assert pending[0].sub_shots[0].videos
    assert pending[0].sub_shots[0].videos[0].video_clip_asset_id
    assert ctx.work_context.get("_video_clip_links")
