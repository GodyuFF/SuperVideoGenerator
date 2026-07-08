"""storyboard create_frames 与 shot 1:1 测试。"""

from core.llm.agent.llm_action import (
    _create_frame_assets_from_data,
    apply_action_result,
    parse_shots_from_data,
)
from core.llm.agent.react_core import AgentRunContext
from core.models.entities import (
    AssetScope,
    Project,
    Script,
    TextAsset,
    TextAssetType,
    VideoPlanShot,
)
from core.store.memory import MemoryStore


def test_create_frames_links_shot_and_frame_asset():
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

    shot = VideoPlanShot(
        order=0,
        narration_text="旁白",
        asset_refs={"scene": [scene.id]},
    )
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id, "script_id": script.id},
        script_id=script.id,
        step_id="",
        agent_name="storyboard_agent",
    )
    created, updated = _create_frame_assets_from_data(
        store,
        ctx,
        [
            {
                "shot_id": shot.id,
                "description": "纯空镜，无人物",
                "element_refs": {"scene": [scene.id]},
            }
        ],
        [shot],
    )
    assert len(created) == 1
    assert created[0].type == TextAssetType.FRAME
    assert updated[0].asset_refs.get("frame") == [created[0].id]
    assert created[0].content.get("shot_id") == shot.id


def test_apply_create_frames_action():
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    shot = VideoPlanShot(order=0, narration_text="旁白")
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
    scene = TextAsset(
        project_id=project.id,
        type=TextAssetType.SCENE,
        scope=AssetScope.PROJECT_SHARED,
        name="空镜",
        content={"description": "背景描述足够长用于测试验证。" * 2},
        source_script_id=script.id,
    )
    store.add_text_asset(scene)

    obs = apply_action_result(
        store,
        "storyboard_agent",
        "create_frames",
        ctx,
        {
            "observation": "创建画面",
            "frames": [
                {
                    "shot_id": shot.id,
                    "description": "空镜镜头",
                    "element_refs": {"scene": [scene.id]},
                }
            ],
        },
    )
    assert "画面" in obs
    pending = ctx.work_context["_pending_shots"]
    assert pending[0].asset_refs.get("frame")
