"""Agent 工具规格与只读工具执行测试。"""

import pytest

from core.agents.definitions import AGENT_DEFINITIONS
from core.agents.react_core import AgentRunContext
from core.agents.tools.executor import AgentToolExecutor
from core.agents.tools.specs import (
    AGENT_TOOLS,
    ad_hoc_actions,
    available_actions,
    is_read_only_action,
    pipeline_actions,
    read_actions,
)
from core.models.entities import (
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


def test_specs_pipeline_and_read_actions_partition():
    for name in AGENT_DEFINITIONS:
        pipeline = pipeline_actions(name)
        adhoc = ad_hoc_actions(name)
        reads = read_actions(name)
        assert pipeline, f"{name} 应有写操作 action"
        assert reads, f"{name} 应有只读 action"
        assert not set(pipeline) & set(reads)
        assert not set(pipeline) & set(adhoc)
        assert not set(adhoc) & set(reads)
        assert set(pipeline) == set(AGENT_DEFINITIONS[name].action_pipeline)
        assert set(adhoc) == set(AGENT_DEFINITIONS[name].ad_hoc_actions)
        assert set(reads) == set(AGENT_DEFINITIONS[name].read_actions)
        assert set(available_actions(name)) == set(pipeline) | set(adhoc) | set(reads)


def test_script_agent_has_crud_ad_hoc_actions():
    adhoc = set(ad_hoc_actions("script_agent"))
    assert "update_script" in adhoc
    assert "update_plot" in adhoc
    assert "delete_character" in adhoc


def test_all_tools_have_action_and_unique_names():
    for agent_name, tools in AGENT_TOOLS.items():
        names = [t.name for t in tools]
        actions = [t.action for t in tools]
        assert len(names) == len(set(names))
        assert len(actions) == len(set(actions))
        assert all(a for a in actions), f"{agent_name} 每个工具都应有 action"
        for tool in tools:
            if tool.read_only:
                assert tool.action in read_actions(agent_name)
            elif tool.ad_hoc:
                assert tool.action in ad_hoc_actions(agent_name)
            else:
                assert tool.action in pipeline_actions(agent_name)


def test_unified_tool_action_naming():
    """写操作 tool 名后缀应与 action 一致。"""
    for tools in AGENT_TOOLS.values():
        for tool in tools:
            if tool.action and not tool.read_only:
                suffix = tool.name.split(".", 1)[-1]
                assert suffix == tool.action, f"{tool.name} 与 action {tool.action} 不一致"


def test_read_only_executor_list_text_assets():
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    store.add_text_asset(
        TextAsset(
            project_id=project.id,
            script_id=script.id,
            type=TextAssetType.CHARACTER,
            name="主角",
            content={"bio": "test"},
        )
    )
    executor = AgentToolExecutor(store)
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id},
        script_id=script.id,
        step_id="step1",
        agent_name="script_agent",
    )
    result = executor.execute_by_action("script_agent", "list_text_assets", ctx)
    assert "主角" in result
    assert is_read_only_action("script_agent", "list_text_assets")


def test_read_only_executor_get_plan():
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    store.set_video_plan(
        VideoPlan(
            script_id=script.id,
            mode=VideoStyleMode.DYNAMIC_IMAGE,
            shots=[
                VideoPlanShot(
                    order=0,
                    duration_ms=3000,
                    camera_motion="pan",
                    narration_text="开场旁白",
                )
            ],
        )
    )
    executor = AgentToolExecutor(store)
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id},
        script_id=script.id,
        step_id="step1",
        agent_name="storyboard_agent",
    )
    result = executor.execute_by_action("storyboard_agent", "get_plan", ctx)
    assert "开场旁白" in result


def test_read_only_executor_list_media():
    store = MemoryStore()
    project = Project(title="p1")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    store.add_media_asset(
        MediaAsset(
            project_id=project.id,
            script_id=script.id,
            type=MediaAssetType.IMAGE,
            name="场景图",
            url="",
        )
    )
    executor = AgentToolExecutor(store)
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id},
        script_id=script.id,
        step_id="step1",
        agent_name="image_agent",
    )
    result = executor.execute_by_action("image_agent", "list_images", ctx)
    assert "场景图" in result
