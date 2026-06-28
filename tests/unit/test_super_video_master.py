"""单元测试：超级视频大师 ReAct 与各生成模式。"""

import asyncio

import pytest

from core.a2ui.manager import ConfirmationManager
from core.a2ui.schemas import A2UIConfirmationResponse
from core.conversation import ConversationIndex, ConversationStore
from core.super_video_master.super_video_master import SuperVideoMaster
from core.events.emitter import EventEmitter
from core.logging.setup import setup_logging
from core.models.entities import GenerationMode, Project, Script, ScriptStatus, VideoStyleMode
from core.store.memory import MemoryStore
from tests.conftest import inject_scripted_llm


@pytest.fixture
def harness():
    setup_logging("WARNING")
    store = MemoryStore()
    emitter = EventEmitter()
    conversations = ConversationStore()
    conversation_index = ConversationIndex()
    confirmation = ConfirmationManager(emitter, default_timeout=5.0)
    master = SuperVideoMaster(
        store, emitter, confirmation, conversations, conversation_index=conversation_index
    )

    project = Project(title="测试项目")
    project.config.generation.mode = GenerationMode.AUTO
    project.config.style.mode = VideoStyleMode.DYNAMIC_IMAGE
    store.add_project(project)

    script = Script(project_id=project.id, title="第一集", duration_sec=60)
    store.add_script(script)

    inject_scripted_llm(master, VideoStyleMode.DYNAMIC_IMAGE)

    return store, emitter, conversations, conversation_index, confirmation, master, project, script


@pytest.mark.asyncio
async def test_run_from_message_completes_pipeline(harness):
    """对话入口应通过 ReAct 完成全流程。"""
    store, emitter, _, _, _, master, project, script = harness
    await master.run_from_message(project.id, script.id, "制作一段60秒都市短片")
    assert script.status == ScriptStatus.COMPLETED
    assert script.style_locked is True
    assert script.style_mode == VideoStyleMode.DYNAMIC_IMAGE
    plan = store.get_plan(script.id)
    assert plan is not None
    assert plan.constraints.get("conversation_isolation") is True
    assert len(plan.steps) >= 4


@pytest.mark.asyncio
async def test_conversation_isolation(harness):
    """用户消息仅在主会话；子 Agent 仅通过任务简报接收创意摘要，无 user 角色消息。"""
    store, emitter, conversations, conversation_index, _, master, project, script = harness
    conv_id, _ = await master.run_from_message(project.id, script.id, "用户私密创意内容")

    master_msgs = conversations.list_messages(conv_id, "master")
    assert any(m.role.value == "user" and "用户私密" in m.content for m in master_msgs)

    agent_msgs = conversations.list_messages(conv_id, "agent", "script_agent")
    assert len(agent_msgs) > 0
    assert not any(m.role.value == "user" for m in agent_msgs)
    assert any(
        m.role.value == "task" and "用户创意" in m.content for m in agent_msgs
    )


@pytest.mark.asyncio
async def test_run_dynamic_image_no_video_step(harness):
    """动态图片模式不应包含 video_gen 步骤。"""
    store, emitter, _, _, _, master, project, script = harness
    await master.run_from_message(project.id, script.id, "动态图片短片")
    plan = store.get_plan(script.id)
    step_types = [s.type for s in plan.steps]
    assert "video_gen" not in step_types
    assert script.status == ScriptStatus.COMPLETED


@pytest.mark.asyncio
async def test_ai_video_auto_mode_completes(harness):
    """AI 视频 + 自动模式：不弹 A2UI。"""
    store, emitter, _, _, confirmation, master, project, script = harness
    project.config.style.mode = VideoStyleMode.AI_VIDEO
    project.config.generation.mode = GenerationMode.AUTO
    inject_scripted_llm(master, VideoStyleMode.AI_VIDEO)

    events = []

    async def capture(e):
        events.append(e)

    emitter.subscribe(capture)
    await master.run_from_message(project.id, script.id, "AI 视频测试")

    assert script.status == ScriptStatus.COMPLETED
    a2ui_events = [e for e in events if e.get("type") == "a2ui_confirmation_required"]
    assert len(a2ui_events) == 0


@pytest.mark.asyncio
async def test_run_from_message_records_token_usage(harness):
    """每轮对话应记录按模型汇总的 token 预估。"""
    store, emitter, _, conversation_index, _, master, project, script = harness
    conv_id, _ = await master.run_from_message(project.id, script.id, "token 统计测试")
    conv = conversation_index.get(conv_id)
    assert conv is not None
    usage = conv.last_round_token_usage
    assert usage.get("estimated") is True
    assert int(usage.get("total_tokens", 0)) > 0
    assert usage.get("models")


@pytest.mark.asyncio
async def test_sub_agents_emit_react_events(harness):
    """子 Agent 应推送 agent_react_* 事件。"""
    store, emitter, _, _, _, master, project, script = harness
    events = []

    async def capture(e):
        events.append(e)

    emitter.subscribe(capture)
    await master.run_from_message(project.id, script.id, "视频流水线事件测试")

    agent_thoughts = [e for e in events if e.get("type") == "agent_react_thought"]
    assert len(agent_thoughts) >= 5
    assert all(e.get("agent_name") for e in agent_thoughts)
