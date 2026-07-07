"""Skill 单轮注入与未知 Skill 错误。"""

import pytest

from core.conversation import ConversationIndex, ConversationStore
from core.events.emitter import EventEmitter
from core.llm.a2ui.manager import ConfirmationManager
from core.logging.setup import setup_logging
from core.models.entities import GenerationMode, Project, Script, VideoStyleMode
from core.store.memory import MemoryStore
from core.super_video_master.super_video_master import SuperVideoMaster
from tests.conftest import inject_scripted_llm, setup_auto_confirm


@pytest.mark.asyncio
async def test_skill_prefix_injects_task_brief():
    setup_logging("WARNING")
    store = MemoryStore()
    emitter = EventEmitter()
    conversations = ConversationStore()
    conversation_index = ConversationIndex()
    confirmation = ConfirmationManager(emitter, default_timeout=5.0)
    master = SuperVideoMaster(
        store, emitter, confirmation, conversations, conversation_index=conversation_index
    )
    project = Project(title="Skill 测试")
    project.config.generation.mode = GenerationMode.AUTO
    project.config.generation.require_script_structure_approval = False
    store.add_project(project)
    script = Script(project_id=project.id, title="Skill 剧本", duration_sec=60)
    store.add_script(script)
    inject_scripted_llm(master, VideoStyleMode.DYNAMIC_IMAGE)
    setup_auto_confirm(emitter, confirmation)

    conv_id, _ = await master.run_from_message(
        project.id,
        script.id,
        "/thriller 单轮 skill 测试",
    )
    user_msgs = [
        m for m in conversations.list_messages(conv_id, "master") if m.role.value == "user"
    ]
    assert user_msgs
    assert "【Skill: 悬疑短片】" in user_msgs[-1].content
    assert "单轮 skill 测试" in user_msgs[-1].content


@pytest.mark.asyncio
async def test_unknown_skill_returns_error():
    setup_logging("WARNING")
    store = MemoryStore()
    emitter = EventEmitter()
    conversations = ConversationStore()
    conversation_index = ConversationIndex()
    confirmation = ConfirmationManager(emitter, default_timeout=5.0)
    master = SuperVideoMaster(
        store, emitter, confirmation, conversations, conversation_index=conversation_index
    )
    project = Project(title="Skill 错误测试")
    store.add_project(project)
    script = Script(project_id=project.id, title="错误", duration_sec=60)
    store.add_script(script)

    _, summary = await master.run_from_message(
        project.id,
        script.id,
        "/not-real-skill 测试",
    )
    assert "未知 Skill" in summary
