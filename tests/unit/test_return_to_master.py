"""return_to_master 工具与主编排暂停处理单元测试。"""

from __future__ import annotations

import pytest

from core.conversation import ConversationStore
from core.llm.agent.react_core import AgentRunContext
from core.llm.hook.react_guard import EditComposeMissingAssetsError
from core.llm.hook.return_to_master import ReturnToMasterError
from core.llm.tools.shared.return_to_master_handler import handle_return_to_master
from core.store.memory import MemoryStore


def test_return_to_master_handler_raises_structured():
    store = MemoryStore()
    ctx = AgentRunContext(
        task_brief="test",
        work_context={},
        script_id="script_x",
        step_id="step_x",
        agent_name="image_agent",
        conversation_id="conv_x",
        project_id="proj_x",
    )
    with pytest.raises(ReturnToMasterError) as exc:
        handle_return_to_master(
            store,
            ctx,
            {
                "reason": "missing_upstream",
                "observation": "缺少文字资产",
                "suggested_agent_ids": ["script_agent"],
                "resume_hint": "剧本完成后重新 delegate_agent(agent_id=image_agent)",
            },
        )
    err = exc.value
    assert err.reason == "missing_upstream"
    assert "script_agent" in err.structured.get("suggested_agent_ids", [])
    assert "【return_to_master" in err.to_master_observation()


def test_edit_compose_missing_is_return_to_master_subclass():
    err = EditComposeMissingAssetsError("report_missing_assets", "缺图")
    assert isinstance(err, ReturnToMasterError)
    assert err.reason == "missing_upstream"


def test_conversation_suspend_and_clear():
    conv = ConversationStore()
    conv.add_task_brief("c1", "p1", "s1", "brief", "image_agent")
    conv.suspend_agent_session("c1", "image_agent", {"reason": "missing_upstream"})
    payload = conv.pop_agent_suspend("c1", "image_agent")
    assert payload and payload.get("reason") == "missing_upstream"
    conv.clear_agent_session("c1", "image_agent")
    assert conv.list_messages("c1", "agent", "image_agent") == []
