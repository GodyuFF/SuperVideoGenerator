"""提示词与上下文：规则、Agent 固定/动态提示、滑窗压缩。"""

from core.llm.prompt.builder import (
    build_action_system,
    build_action_user,
    build_react_json_user,
    build_react_system,
    get_summary_system_prompt,
    render_template,
)
from core.llm.prompt.config import (
    ASSET_SUMMARY_MAX,
    COMPRESSION_SNIPPET_CHARS,
    HISTORY_MAX_CHARS,
    HISTORY_WINDOW_SIZE,
    OBSERVATION_MAX_CHARS,
    OBSERVATION_WINDOW_SIZE,
    SCRIPT_MD_CONTEXT_MAX,
)
from core.llm.prompt.context_manager import AgentContextManager, MasterContextProvider, SubAgentContextProvider
from core.llm.prompt.context_window import (
    PreparedContext,
    prepare_master_context,
    prepare_sub_agent_context,
    prepare_observation_window,
)
from core.llm.prompt.registry import (
    AGENT_PROMPT_PROFILES,
    AgentPromptBundle,
    PromptProfile,
    default_role_prompt,
    extract_role_summary,
    get_action_json_system_base,
    get_agent_bundle,
    get_react_system_prompt,
    list_prompt_profiles,
)

__all__ = [
    "AGENT_PROMPT_PROFILES",
    "AgentContextManager",
    "AgentPromptBundle",
    "MasterContextProvider",
    "PromptProfile",
    "PreparedContext",
    "SubAgentContextProvider",
    "ASSET_SUMMARY_MAX",
    "SCRIPT_MD_CONTEXT_MAX",
    "OBSERVATION_WINDOW_SIZE",
    "OBSERVATION_MAX_CHARS",
    "HISTORY_WINDOW_SIZE",
    "HISTORY_MAX_CHARS",
    "COMPRESSION_SNIPPET_CHARS",
    "build_action_system",
    "build_action_user",
    "build_react_json_user",
    "build_react_system",
    "default_role_prompt",
    "extract_role_summary",
    "get_action_json_system_base",
    "get_agent_bundle",
    "get_react_system_prompt",
    "get_summary_system_prompt",
    "list_prompt_profiles",
    "prepare_master_context",
    "prepare_observation_window",
    "prepare_sub_agent_context",
    "render_template",
]
