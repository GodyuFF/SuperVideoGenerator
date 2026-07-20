"""子 Agent 工具规格定义（与 product-plan §8 Tool 接口对齐）。"""

from dataclasses import dataclass

ASK_USER_QUESTION_ACTION = "ask_user_question"

# 成功后从 available_actions 剔除的一次性步骤（可重复的 create_*/update_*/read 不在此列）。
ONE_TIME_COMPLETED_ACTIONS = frozenset(
    {
        "parse_brief",
        "load_context",
        "load_edit_context",
        "load_shots",
        "extract_narration",
        "gather_media",
        "plan_edit_timeline",
        "report_missing_assets",
        "create_shots",
        "create_frames",
        "create_video_clips",
        "persist_plan",
        "sync_actual_assets",
        "update_frames",
        "persist_review",
        "compose_final",
        "synthesize",
    }
)


def should_hide_when_completed(action: str) -> bool:
    """是否在完成一次后从 prompt available_actions 中移除。"""
    if action == "delegate_agent":
        return False
    if action.startswith("tool_"):
        return False
    return action in ONE_TIME_COMPLETED_ACTIONS


@dataclass(frozen=True)
class AgentToolSpec:
    """Agent 可调用的逻辑工具。"""

    name: str
    description: str
    action: str | None = None  # 运行时 ReAct action 名
    read_only: bool = False  # True 表示只读查询，走 AgentToolExecutor
    ad_hoc: bool = False  # True 表示可在 ReAct 任意时刻调用的写操作（更新/删除等）


def _load_agent_tools() -> dict[str, list[AgentToolSpec]]:
    """从 MCP 语义 ToolRegistry 加载（单源真相）。"""
    from core.llm.tools.bootstrap import build_agent_tools

    return build_agent_tools()


_AGENT_TOOLS_CACHE: dict[str, list[AgentToolSpec]] | None = None


def get_agent_tools() -> dict[str, list[AgentToolSpec]]:
    global _AGENT_TOOLS_CACHE
    if _AGENT_TOOLS_CACHE is None:
        _AGENT_TOOLS_CACHE = _load_agent_tools()
    return _AGENT_TOOLS_CACHE


class _AgentToolsProxy:
    """AGENT_TOOLS 延迟加载代理。"""

    def get(self, key: str, default=None):
        return get_agent_tools().get(key, default)

    def items(self):
        return get_agent_tools().items()

    def keys(self):
        return get_agent_tools().keys()

    def values(self):
        return get_agent_tools().values()

    def __iter__(self):
        return iter(get_agent_tools())

    def __getitem__(self, key: str):
        return get_agent_tools()[key]

    def __contains__(self, key: object) -> bool:
        return key in get_agent_tools()


AGENT_TOOLS = _AgentToolsProxy()


def is_ask_user_question_action(action: str) -> bool:
    return action == ASK_USER_QUESTION_ACTION


def pipeline_actions(agent_name: str) -> list[str]:
    """写操作 / 流水线 action（ReAct 主流程）。"""
    return [
        t.action
        for t in get_agent_tools().get(agent_name, [])
        if t.action and not t.read_only and not t.ad_hoc
    ]


def ad_hoc_actions(agent_name: str) -> list[str]:
    """可在任意时刻调用的写操作（更新、删除等）。"""
    return [
        t.action
        for t in get_agent_tools().get(agent_name, [])
        if t.action and not t.read_only and t.ad_hoc
    ]


def read_actions(agent_name: str) -> list[str]:
    """只读查询 action（任意时刻可调用）。"""
    return [
        t.action
        for t in get_agent_tools().get(agent_name, [])
        if t.action and t.read_only
    ]


def available_actions(agent_name: str) -> list[str]:
    """子 Agent ReAct 全部可选 action（不含 finish）。"""
    return pipeline_actions(agent_name) + ad_hoc_actions(agent_name) + read_actions(agent_name)


def is_read_only_action(agent_name: str, action: str) -> bool:
    for tool in get_agent_tools().get(agent_name, []):
        if tool.action == action:
            return tool.read_only
    return False
