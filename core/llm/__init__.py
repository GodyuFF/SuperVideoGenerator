"""LLM 集成：HTTP 客户端、多服务商配置、JSON ReAct 决策。"""

from core.llm.client import LLMClient, LLMConfigManager, list_providers
from core.llm.master import MasterReActEngine
from core.llm.model import ReActAgentInfo, ReActToolInfo, new_conversation_id
from core.llm.react_decide import decide_master_session, decide_react, decide_sub_agent

__all__ = [
    "LLMClient",
    "LLMConfigManager",
    "MasterReActEngine",
    "ReActAgentInfo",
    "ReActToolInfo",
    "decide_master_session",
    "decide_react",
    "decide_sub_agent",
    "list_providers",
    "new_conversation_id",
]
