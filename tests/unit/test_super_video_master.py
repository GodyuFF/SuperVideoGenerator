"""单元测试：超级视频大师 ReAct 与各生成模式。"""

import asyncio

import pytest

from core.a2ui.manager import ConfirmationManager
from core.a2ui.schemas import A2UIConfirmationResponse
from core.agents.conversation import ConversationStore
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
    confirmation = ConfirmationManager(emitter, default_timeout=5.0)
    master = SuperVideoMaster(store, emitter, confirmation, conversations)

    project = Project(title="测试项目")
    project.config.generation.mode = GenerationMode.AUTO
    project.config.style.mode = VideoStyleMode.DYNAMIC_IMAGE
    store.add_project(project)

    script = Script(project_id=project.id, title="第一集", duration_sec=60)
    store.add_script(script)

    inject_scripted_llm(master, VideoStyleMode.DYNAMIC_IMAGE)

    return store, emitter, conversations, confirmation, master, project, script


@pytest.mark.asyncio
async def test_run_from_message_completes_pipeline(harness):
    """对话入口应通过 ReAct 完成全流程。"""
    store, emitter, _, _, master, project, script = harness
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
    store, emitter, conversations, _, master, project, script = harness
    await master.run_from_message(project.id, script.id, "用户私密创意内容")

    master_msgs = conversations.list_messages(script.id, "master")
    assert any(m.role.value == "user" and "用户私密" in m.content for m in master_msgs)

    agent_msgs = conversations.list_messages(script.id, "agent", "script_agent")
    assert len(agent_msgs) > 0
    assert not any(m.role.value == "user" for m in agent_msgs)
    assert any(
        m.role.value == "task" and "用户创意" in m.content for m in agent_msgs
    )


@pytest.mark.asyncio
async def test_run_dynamic_image_no_video_step(harness):
    """动态图片模式不应包含 video_gen 步骤。"""
    store, emitter, _, _, master, project, script = harness
    await master.run_from_message(project.id, script.id, "动态图片短片")
    plan = store.get_plan(script.id)
    step_types = [s.type for s in plan.steps]
    assert "video_gen" not in step_types
    assert script.status == ScriptStatus.COMPLETED


@pytest.mark.asyncio
async def test_ai_video_auto_mode_completes(harness):
    """AI 视频 + 自动模式：不弹 A2UI。"""
    store, emitter, _, confirmation, master, project, script = harness
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
async def test_ai_video_cost_confirm_requires_approval(harness):
    """AI 视频 + 费用确认：应先 A2UI 确认再完成。"""
    store, emitter, _, confirmation, master, project, script = harness
    project.config.style.mode = VideoStyleMode.AI_VIDEO
    project.config.generation.mode = GenerationMode.COST_CONFIRM
    inject_scripted_llm(master, VideoStyleMode.AI_VIDEO)

    events = []

    async def capture(e):
        events.append(e)

    emitter.subscribe(capture)

    async def auto_approve():
        for _ in range(50):
            await asyncio.sleep(0.05)
            for e in events:
                if e.get("type") == "a2ui_confirmation_required":
                    confirmation.resolve(
                        A2UIConfirmationResponse(
                            confirmation_id=e["confirmation_id"], approved=True
                        )
                    )
                    return

    approve_task = asyncio.create_task(auto_approve())
    await master.run_from_message(project.id, script.id, "视频费用确认测试")
    await approve_task

    assert script.status == ScriptStatus.COMPLETED
    a2ui_events = [e for e in events if e.get("type") == "a2ui_confirmation_required"]
    assert len(a2ui_events) >= 1


@pytest.mark.asyncio
async def test_ai_video_cost_confirm_rejected_fails(harness):
    """AI 视频 + 费用确认 + 用户拒绝：执行应失败。"""
    store, emitter, _, confirmation, master, project, script = harness
    project.config.style.mode = VideoStyleMode.AI_VIDEO
    project.config.generation.mode = GenerationMode.COST_CONFIRM
    inject_scripted_llm(master, VideoStyleMode.AI_VIDEO)

    events = []

    async def capture(e):
        events.append(e)

    emitter.subscribe(capture)

    async def auto_reject():
        for _ in range(50):
            await asyncio.sleep(0.05)
            for e in events:
                if e.get("type") == "a2ui_confirmation_required":
                    confirmation.resolve(
                        A2UIConfirmationResponse(
                            confirmation_id=e["confirmation_id"], approved=False
                        )
                    )
                    return

    reject_task = asyncio.create_task(auto_reject())
    await master.run_from_message(project.id, script.id, "视频费用拒绝测试")
    await reject_task

    assert script.status == ScriptStatus.FAILED
    plan = store.get_plan(script.id)
    video_step = next(s for s in plan.steps if s.type == "video_gen")
    assert video_step.error is not None


@pytest.mark.asyncio
async def test_sub_agents_emit_react_events(harness):
    """子 Agent 应推送 agent_react_* 事件。"""
    store, emitter, _, _, master, project, script = harness
    events = []

    async def capture(e):
        events.append(e)

    emitter.subscribe(capture)
    await master.run_from_message(project.id, script.id, "视频流水线事件测试")

    agent_thoughts = [e for e in events if e.get("type") == "agent_react_thought"]
    assert len(agent_thoughts) >= 5
    assert all(e.get("agent_name") for e in agent_thoughts)
