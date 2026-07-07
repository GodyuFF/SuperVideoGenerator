"""单元测试：超级视频大师 ReAct 与各生成模式。"""

import asyncio

import pytest

from core.llm.a2ui.manager import ConfirmationManager
from core.llm.a2ui.schemas import A2UIConfirmationResponse
from core.conversation import ConversationIndex, ConversationStore
from core.super_video_master.super_video_master import SuperVideoMaster
from core.events.emitter import EventEmitter
from core.logging.setup import setup_logging
from core.models.entities import GenerationMode, Project, Script, ScriptStatus, StepStatus, VideoStyleMode
from core.store.memory import MemoryStore
from tests.conftest import inject_scripted_llm, setup_auto_confirm


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
    setup_auto_confirm(emitter, confirmation)

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
        m.message_kind.value == "task_brief" and "用户创意" in str(m.content)
        for m in agent_msgs
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
    cost_events = [e for e in a2ui_events if e.get("kind") == "video_generation_cost"]
    assert len(cost_events) == 0


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
    assert all(e.get("conversation_id") for e in agent_thoughts)


@pytest.mark.asyncio
async def test_script_design_confirm_regenerate_redelegates():
    """剧本确认网关：regenerate 应清除完成标记并重新委派 script_design。"""
    setup_logging("WARNING")
    store = MemoryStore()
    emitter = EventEmitter()
    conversations = ConversationStore()
    conversation_index = ConversationIndex()
    confirmation = ConfirmationManager(emitter, default_timeout=5.0)
    master = SuperVideoMaster(
        store, emitter, confirmation, conversations, conversation_index=conversation_index
    )

    project = Project(title="确认测试")
    project.config.generation.mode = GenerationMode.AUTO
    project.config.style.mode = VideoStyleMode.DYNAMIC_IMAGE
    store.add_project(project)
    script = Script(project_id=project.id, title="确认剧本", duration_sec=60)
    store.add_script(script)
    inject_scripted_llm(master, VideoStyleMode.DYNAMIC_IMAGE)

    confirm_count = 0
    delegate_actions: list[str] = []

    async def capture(event: dict) -> None:
        nonlocal confirm_count
        if (
            event.get("type") == "a2ui_confirmation_required"
            and event.get("kind") == "script_structure"
        ):
            confirm_count += 1
            if confirm_count == 1:
                confirmation.resolve(
                    A2UIConfirmationResponse(
                        confirmation_id=str(event["confirmation_id"]),
                        approved=False,
                        values={"intent": "regenerate", "feedback": "加强冲突"},
                    )
                )
            else:
                confirmation.resolve(
                    A2UIConfirmationResponse(
                        confirmation_id=str(event["confirmation_id"]),
                        approved=True,
                        values={"intent": "continue", "feedback": ""},
                    )
                )
        if (
            event.get("type") == "react_action"
            and event.get("action") == "delegate_script_design"
        ):
            delegate_actions.append("yes")

    emitter.subscribe(capture)
    conv_id, _ = await master.run_from_message(
        project.id, script.id, "需要两次剧本确认测试"
    )
    assert delegate_actions.count("yes") >= 2
    master_msgs = conversations.list_messages(conv_id, "master")
    assert any("加强冲突" in m.content for m in master_msgs)


@pytest.mark.asyncio
async def test_script_structure_approval_disabled_skips_a2ui(harness):
    """require_script_structure_approval=False 时不弹剧本结构确认。"""
    store, emitter, _, _, _, master, project, script = harness
    project.config.generation.require_script_structure_approval = False
    events: list[dict] = []

    async def capture(e: dict) -> None:
        events.append(e)

    emitter.subscribe(capture)
    await master.run_from_message(project.id, script.id, "跳过剧本确认测试")

    structure_events = [
        e
        for e in events
        if e.get("type") == "a2ui_confirmation_required"
        and e.get("kind") == "script_structure"
    ]
    assert len(structure_events) == 0
    assert script.status == ScriptStatus.COMPLETED


@pytest.mark.asyncio
async def test_script_structure_abort_stops_pipeline():
    """用户 abort 剧本结构确认后主编排不应继续委派下一步。"""
    setup_logging("WARNING")
    store = MemoryStore()
    emitter = EventEmitter()
    conversations = ConversationStore()
    conversation_index = ConversationIndex()
    confirmation = ConfirmationManager(emitter, default_timeout=5.0)
    master = SuperVideoMaster(
        store, emitter, confirmation, conversations, conversation_index=conversation_index
    )

    project = Project(title="中止测试")
    project.config.generation.mode = GenerationMode.AUTO
    project.config.style.mode = VideoStyleMode.DYNAMIC_IMAGE
    store.add_project(project)
    script = Script(project_id=project.id, title="中止剧本", duration_sec=60)
    store.add_script(script)
    inject_scripted_llm(master, VideoStyleMode.DYNAMIC_IMAGE)

    delegate_after_script: list[str] = []

    async def capture(event: dict) -> None:
        if (
            event.get("type") == "a2ui_confirmation_required"
            and event.get("kind") == "script_structure"
        ):
            confirmation.resolve(
                A2UIConfirmationResponse(
                    confirmation_id=str(event["confirmation_id"]),
                    approved=False,
                    values={"intent": "abort", "feedback": ""},
                )
            )
        if (
            event.get("type") == "react_action"
            and event.get("action") == "delegate_storyboard"
        ):
            delegate_after_script.append("yes")

    emitter.subscribe(capture)
    await master.run_from_message(project.id, script.id, "确认后中止测试")

    assert delegate_after_script == []
    plan = store.get_plan(script.id)
    assert plan is not None
    awaiting = [
        s for s in plan.steps if s.type == "script_design" and s.status.value == "awaiting_confirmation"
    ]
    assert len(awaiting) >= 1 or script.status != ScriptStatus.COMPLETED


@pytest.mark.asyncio
async def test_script_structure_waits_for_user_confirmation():
    """剧本结构确认应无限等待，用户操作后再继续后续步骤。"""
    setup_logging("WARNING")
    store = MemoryStore()
    emitter = EventEmitter()
    conversations = ConversationStore()
    conversation_index = ConversationIndex()
    confirmation = ConfirmationManager(emitter, default_timeout=None)
    master = SuperVideoMaster(
        store, emitter, confirmation, conversations, conversation_index=conversation_index
    )

    project = Project(title="等待确认测试")
    project.config.generation.mode = GenerationMode.AUTO
    project.config.style.mode = VideoStyleMode.DYNAMIC_IMAGE
    store.add_project(project)
    script = Script(project_id=project.id, title="等待剧本", duration_sec=60)
    store.add_script(script)
    inject_scripted_llm(master, VideoStyleMode.DYNAMIC_IMAGE)

    delegate_after_script: list[str] = []
    confirm_seen = asyncio.Event()

    async def capture(event: dict) -> None:
        if (
            event.get("type") == "a2ui_confirmation_required"
            and event.get("kind") == "script_structure"
        ):
            confirm_seen.set()
            await asyncio.sleep(0.15)
            confirmation.resolve(
                A2UIConfirmationResponse(
                    confirmation_id=str(event["confirmation_id"]),
                    approved=True,
                    values={"intent": "continue", "feedback": ""},
                )
            )
        if (
            event.get("type") == "react_action"
            and event.get("action") == "delegate_storyboard"
        ):
            delegate_after_script.append("yes")

    emitter.subscribe(capture)
    run_task = asyncio.create_task(
        master.run_from_message(project.id, script.id, "等待用户确认测试")
    )
    await asyncio.wait_for(confirm_seen.wait(), timeout=2.0)
    assert confirmation.has_pending()
    await asyncio.sleep(0.05)
    assert confirmation.has_pending()
    await run_task

    assert delegate_after_script
    plan = store.get_plan(script.id)
    assert plan is not None
    script_design = next(s for s in plan.steps if s.type == "script_design")
    assert script_design.status == StepStatus.COMPLETED

