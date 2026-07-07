"""目标模式：禁用 ask_user 与全部 A2UI。"""

import pytest

from core.conversation import ConversationIndex, ConversationStore
from core.events.emitter import EventEmitter
from core.llm.a2ui.manager import ConfirmationManager
from core.llm.execution_mode import is_goal_mode
from core.llm.master.session import create_master_react_session
from core.logging.setup import setup_logging
from core.models.entities import (
    ExecutionMode,
    GenerationMode,
    Project,
    Script,
    ScriptStatus,
    VideoStyleMode,
)
from core.store.memory import MemoryStore
from core.super_video_master.super_video_master import SuperVideoMaster
from tests.conftest import inject_scripted_llm, setup_auto_confirm


def test_is_goal_mode_project_default():
    project = Project(title="t")
    assert not is_goal_mode(project)
    project.config.generation.execution_mode = ExecutionMode.GOAL
    assert is_goal_mode(project)


def test_goal_mode_excludes_ask_user_from_available_actions():
    session = create_master_react_session(
        "conv",
        "proj",
        "script",
        "测试",
        VideoStyleMode.DYNAMIC_IMAGE,
        GenerationMode.AUTO,
        execution_mode=ExecutionMode.GOAL,
    )
    assert "ask_user_question" not in session.available_actions()


@pytest.mark.asyncio
async def test_goal_mode_skips_a2ui_and_completes():
    setup_logging("WARNING")
    store = MemoryStore()
    emitter = EventEmitter()
    conversations = ConversationStore()
    conversation_index = ConversationIndex()
    confirmation = ConfirmationManager(emitter, default_timeout=5.0)
    master = SuperVideoMaster(
        store, emitter, confirmation, conversations, conversation_index=conversation_index
    )
    project = Project(title="目标模式")
    project.config.generation.mode = GenerationMode.AUTO
    project.config.generation.execution_mode = ExecutionMode.GOAL
    project.config.generation.require_script_structure_approval = True
    store.add_project(project)
    script = Script(project_id=project.id, title="自主剧本", duration_sec=60)
    store.add_script(script)
    inject_scripted_llm(master, VideoStyleMode.DYNAMIC_IMAGE)

    a2ui_events: list[dict] = []

    async def capture(event: dict) -> None:
        if event.get("type") == "a2ui_confirmation_required":
            a2ui_events.append(event)

    emitter.subscribe(capture)
    await master.run_from_message(
        project.id,
        script.id,
        "目标模式全流程测试，60秒动态图文",
        execution_mode=ExecutionMode.GOAL,
    )

    assert a2ui_events == []
    script = store.get_script(script.id)
    assert script.status == ScriptStatus.COMPLETED
