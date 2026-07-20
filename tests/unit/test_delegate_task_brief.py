"""主编排委派任务简报测试。"""

from core.llm.agent.react_core import MasterRunContext, ReActDecision
from core.llm.master.master_react import MasterReActEngine
from core.models.entities import GenerationMode, VideoStyleMode


class _StoreStub:
    def get_script(self, script_id: str):
        return None


def test_build_delegate_task_brief_uses_session_task_brief():
    engine = MasterReActEngine.__new__(MasterReActEngine)
    engine._store = _StoreStub()
    ctx = MasterRunContext(
        project_id="p1",
        script_id="s1",
        user_message="你好",
        style_mode=VideoStyleMode.STORYBOOK,
        generation_mode=GenerationMode.AUTO,
    )
    session = type(
        "Session",
        (),
        {"task_brief": "用户补充：\n- theme: 科幻\n- duration_sec: 60"},
    )()
    decision = ReActDecision(
        thought="",
        action="delegate_agent",
        action_input={"agent_id": "script_agent"},
    )
    brief = engine._build_delegate_task_brief(ctx, session, "script_design", decision)
    assert "用户补充" in brief
    assert "theme: 科幻" in brief
    assert "你好" not in brief
