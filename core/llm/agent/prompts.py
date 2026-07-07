"""Agent 提示词：从 core.llm.prompt 加载。"""

from core.llm.prompt.registry import (
    AGENT_PROMPT_PROFILES,
    AgentPromptBundle,
    PromptProfile,
    default_role_prompt,
    get_action_json_system_base,
    get_react_system_prompt,
    list_prompt_profiles,
)

__all__ = [
    "AGENT_PROMPT_PROFILES",
    "AgentPromptBundle",
    "PromptProfile",
    "default_role_prompt",
    "get_action_json_system_base",
    "get_react_system_prompt",
    "list_prompt_profiles",
]
