"""注册全部 Agent tools 到 ToolRegistry。"""

from __future__ import annotations

from core.llm.tools.common.register import register_common_tools
from core.llm.tools.editing.register import register_editing_tools
from core.llm.tools.image.register import register_image_tools
from core.llm.tools.registry import ToolRegistry
from core.llm.tools.script.register import register_script_tools
from core.llm.tools.storyboard.register import register_storyboard_tools
from core.llm.tools.storyboard_refine.register import register_storyboard_refine_tools
from core.llm.tools.tts.register import register_tts_tools
from core.llm.tools.video.register import register_video_tools


def register_all_tools(registry: ToolRegistry) -> None:
    register_common_tools(registry)
    from core.llm.tools.plan.register import register_plan_tools
    from core.llm.tools.shared.return_to_master_register import register_return_to_master_tool

    register_return_to_master_tool(registry)
    register_plan_tools(registry)
    register_script_tools(registry)
    register_image_tools(registry)
    register_storyboard_tools(registry)
    register_storyboard_refine_tools(registry)
    register_video_tools(registry)
    register_tts_tools(registry)
    register_editing_tools(registry)


def build_agent_tools() -> dict[str, list]:
    from core.llm.tools import get_tool_registry

    return agent_tools_from_registry(get_tool_registry())


def agent_tools_from_registry(registry: ToolRegistry) -> dict[str, list]:
    from core.llm.tools.shared.agent_tools import ASK_USER_QUESTION_ACTION, AgentToolSpec
    from core.llm.tools.web_fetch.tool import COMMON_AGENT

    by_agent: dict[str, list] = {}
    common_specs: list[AgentToolSpec] = []
    for spec in registry.list_tools():
        entry = AgentToolSpec(
            name=spec.logical_name or spec.name,
            description=spec.description,
            action=spec.name,
            read_only=spec.read_only,
            ad_hoc=spec.ad_hoc,
        )
        if spec.agent == COMMON_AGENT:
            common_specs.append(entry)
            continue
        by_agent.setdefault(spec.agent, []).append(entry)
    ask = AgentToolSpec(
        "common.ask_user_question",
        "向用户询问缺失信息（A2UI 弹窗）",
        ASK_USER_QUESTION_ACTION,
        ad_hoc=True,
    )
    _exclude_common: dict[str, frozenset[str]] = {
        # 分镜 Agent 应通过 load_context 读取剧本，勿用 read_webpage
        "storyboard_agent": frozenset({"read_webpage"}),
        "storyboard_refine_agent": frozenset({"read_webpage"}),
        "tts_agent": frozenset({"read_webpage"}),
        "editing_agent": frozenset({"read_webpage"}),
        "image_agent": frozenset({"read_webpage"}),
        "video_agent": frozenset({"read_webpage"}),
    }
    for agent in by_agent:
        excluded = _exclude_common.get(agent, frozenset())
        for shared in common_specs:
            if shared.action in excluded:
                continue
            if not any(t.action == shared.action for t in by_agent[agent]):
                by_agent[agent].append(shared)
        if not any(t.action == ASK_USER_QUESTION_ACTION for t in by_agent[agent]):
            by_agent[agent].append(ask)
    return by_agent
