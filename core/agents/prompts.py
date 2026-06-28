"""Agent 提示词：从 core.prompt 加载，本模块保持向后兼容导入。"""

from core.prompt.registry import (
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
