"""按全局 agent_config 过滤 ReAct 可用 action；系统工具始终加载。"""



from __future__ import annotations



from typing import Any



from core.llm.tools.shared.agent_tools import (

    ASK_USER_QUESTION_ACTION,

    ad_hoc_actions,

    pipeline_actions,

    read_actions,

)

from core.models.agent_config import AgentToolOverride



# 全 Agent 默认加载、不可在工作台勾选的系统工具

UNIVERSAL_SYSTEM_TOOLS: frozenset[str] = frozenset({"finish", ASK_USER_QUESTION_ACTION})



# 子 Agent 专属系统工具

SUB_AGENT_SYSTEM_TOOLS: frozenset[str] = frozenset({"return_to_master"})



_SYSTEM_TOOL_DESCRIPTIONS: dict[str, str] = {

    "finish": "结束当前 ReAct 轮次",

    ASK_USER_QUESTION_ACTION: "向用户发起结构化确认或提问",

    "return_to_master": "结束子 Agent 任务并返回主编排",

}





def is_system_tool(agent_name: str, action: str) -> bool:

    """判断 action 是否为系统工具（运行时默认加载，不参与白名单勾选）。"""

    if action in UNIVERSAL_SYSTEM_TOOLS:

        return True

    if agent_name == "super_video_master":

        return action == "delegate_agent"

    return action in SUB_AGENT_SYSTEM_TOOLS





def list_system_tools(agent_name: str) -> list[str]:

    """返回某 Agent 的全部系统工具名（有序）。"""

    names: set[str] = set(UNIVERSAL_SYSTEM_TOOLS)

    if agent_name == "super_video_master":

        from core.llm.master.delegate_tool import DELEGATE_AGENT_ACTION

        names.add(DELEGATE_AGENT_ACTION)

    elif agent_name != "super_video_master":

        names.update(SUB_AGENT_SYSTEM_TOOLS)

    return sorted(names)





def list_configurable_tool_names(agent_name: str) -> list[str]:

    """返回 Agent 实现上的默认可配置工具名（排除系统工具）。"""

    return [name for name in list_agent_tool_names(agent_name) if not is_system_tool(agent_name, name)]





def list_global_configurable_tools() -> list[str]:

    """返回全局 Registry 中全部非 system 可配置 action（可跨 Agent 挂载）。"""

    from core.llm.tools import get_tool_registry



    names: set[str] = set()

    for agent in (

        "super_video_master",

        "script_agent",

        "image_agent",

        "storyboard_agent",

        "storyboard_refine_agent",

        "video_agent",

        "tts_agent",

        "editing_agent",

    ):

        for action in list_agent_tool_names(agent):

            if not is_system_tool(agent, action):

                names.add(action)

    registry = get_tool_registry()

    for spec in registry.list_tools():

        if not is_system_tool(spec.agent, spec.name):

            names.add(spec.name)

    return sorted(names)





def preserved_actions(agent_name: str) -> frozenset[str]:

    """应用 override 时始终保留的系统 action 集合。"""

    return frozenset(list_system_tools(agent_name))





def system_tool_description(agent_name: str, action: str) -> str:

    """返回系统工具说明文案。"""

    if action in _SYSTEM_TOOL_DESCRIPTIONS:

        return _SYSTEM_TOOL_DESCRIPTIONS[action]

    if agent_name == "super_video_master" and action == "delegate_agent":

        from core.llm.master.actions import action_label

        return action_label(action)

    return action





def resolve_tool_override(

    agent_name: str,

    *,

    profile_id: str | None = None,

    style_mode: str | None = None,

    global_profiles: dict[str, str] | None = None,

    config: Any | None = None,

) -> AgentToolOverride | None:

    """按 Profile 或 style_mode 解析工具覆盖，回退全局 tool_overrides。"""

    from core.llm.agent.config_manager import get_agent_config_manager

    from core.llm.agent.prompt_resolver import resolve_prompt_profile



    mgr = config or get_agent_config_manager()

    data = mgr.get_data()

    pid = profile_id

    if not pid and style_mode is not None:

        pid = resolve_prompt_profile(

            agent_name,

            style_mode=style_mode,

            global_profiles=global_profiles or mgr.get_profiles(),

            config=mgr,

        )

    if pid:

        scoped = data.tool_overrides_by_profile.get(pid, {}).get(agent_name)

        if scoped is not None:

            return scoped

    return data.tool_overrides.get(agent_name)





def apply_agent_tool_overrides(

    agent_name: str,

    actions: list[str],

    override: AgentToolOverride | None,

) -> list[str]:

    """应用 include_only 或 exclude（exclude 优先）；始终保留系统工具。"""

    preserved = preserved_actions(agent_name)

    if override is None:

        return list(actions)

    if override.exclude:

        excluded = set(override.exclude)

        return [a for a in actions if a in preserved or a not in excluded]

    if override.include_only:

        allowed = set(override.include_only) | preserved

        return [a for a in actions if a in allowed]

    return list(actions)





def resolve_effective_configurable_tools(

    agent_name: str,

    impl: str,

    override: AgentToolOverride | None,

) -> list[str]:

    """解析非 system 生效工具列表（支持 include_only 跨 Agent 挂载）。"""

    default = list_configurable_tool_names(impl)

    global_pool = set(list_global_configurable_tools())

    if override and override.include_only is not None:

        selected = [t for t in override.include_only if t in global_pool]

        return sorted(set(selected))

    if override and override.exclude:

        excluded = set(override.exclude)

        return sorted(t for t in default if t not in excluded)

    return list(default)





def split_effective_tools_for_react(

    impl: str,

    effective: list[str],

) -> tuple[list[str], list[str], list[str]]:

    """将生效工具拆分为 pipeline / read / adhoc（跨 Agent 工具归入 adhoc）。"""

    default_pipeline = set(pipeline_actions(impl))

    default_read = set(read_actions(impl))

    default_adhoc = set(ad_hoc_actions(impl))

    pipeline: list[str] = []

    reads: list[str] = []

    adhoc: list[str] = []

    for action in effective:

        if action in default_pipeline:

            pipeline.append(action)

        elif action in default_read:

            reads.append(action)

        elif action in default_adhoc:

            adhoc.append(action)

        else:

            adhoc.append(action)

    return pipeline, reads, adhoc





def list_agent_tool_names(agent_name: str) -> list[str]:

    """列出 Agent 在 Registry 中的全部 tool/action 名（含系统工具）。"""

    from core.llm.master.tools import MASTER_TOOL_ACTIONS

    from core.llm.tools import get_tool_registry



    if agent_name == "super_video_master":

        names = list(MASTER_TOOL_ACTIONS)

        names.extend(list(UNIVERSAL_SYSTEM_TOOLS))

        from core.llm.master.delegate_tool import DELEGATE_AGENT_ACTION

        names.append(DELEGATE_AGENT_ACTION)

        return sorted(set(names))



    pipeline = pipeline_actions(agent_name)

    reads = read_actions(agent_name)

    adhoc = ad_hoc_actions(agent_name)

    registry = get_tool_registry()

    reg_names = [s.name for s in registry.list_tools(agent_name)]

    all_names = set(pipeline) | set(reads) | set(adhoc) | set(reg_names)

    all_names.update(UNIVERSAL_SYSTEM_TOOLS)

    all_names.update(SUB_AGENT_SYSTEM_TOOLS)

    return sorted(all_names)





def apply_master_tool_overrides(

    actions: list[str],

    override: AgentToolOverride | None,

) -> list[str]:

    """主编排仅过滤 tool_* 行动，delegate 与 finish 等系统 action 不受影响。"""

    if override is None:

        return list(actions)

    tool_names = [a for a in actions if a.startswith("tool_")]

    allowed_tools = set(apply_agent_tool_overrides("super_video_master", tool_names, override))

    return [a for a in actions if not a.startswith("tool_") or a in allowed_tools]


