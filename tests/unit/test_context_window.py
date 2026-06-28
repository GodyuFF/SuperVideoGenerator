"""上下文滑窗与压缩测试。"""

from core.conversation import ConversationRole, ConversationStore
from core.agents.react_core import AgentRunContext
from core.prompt.context_window import (
    prepare_master_context,
    prepare_observation_window,
    prepare_sub_agent_context,
)


def test_observation_window_keeps_recent_items():
    items = [f"观察{i}" for i in range(20)]
    recent, summary, dropped = prepare_observation_window(items, window_size=5, max_chars=500)
    assert len(recent) <= 5
    assert dropped == 15
    assert "已压缩" in summary
    assert recent[-1] == "观察19"


def test_prepare_master_context_compresses_long_history():
    obs = [f"第{i}轮 observation " + ("x" * 200) for i in range(12)]
    prepared = prepare_master_context(obs)
    assert len(prepared.observations) <= 8
    assert prepared.dropped_observation_count > 0


def test_prepare_sub_agent_context_splits_history_and_observations():
    store = ConversationStore()
    script_id = "s1"
    agent = "script_agent"
    store.add(script_id, "agent", ConversationRole.TASK, "写剧本", agent)
    store.add(script_id, "agent", ConversationRole.THOUGHT, "先解析", agent)
    store.add(script_id, "agent", ConversationRole.ACTION, "parse_brief: {}", agent)

    ctx = AgentRunContext(
        task_brief="写剧本",
        work_context={"script_id": script_id},
        script_id=script_id,
        step_id="step1",
        agent_name=agent,
        observations=["已完成 parse_brief"],
    )
    prepared = prepare_sub_agent_context(ctx, store)
    assert prepared.observations == ["已完成 parse_brief"]
    assert "[思考]" not in " ".join(prepared.observations)
    assert "先解析" in prepared.history_summary or prepared.history_summary == ""
