"""子 Agent 注册表。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.llm.agent.base import ReActAgent
from core.llm.agent.config_manager import get_agent_config_manager
from core.llm.a2ui.manager import ConfirmationManager
from core.conversation import ConversationStore
from core.llm.agent.definitions import AGENT_CLASSES, AGENT_DEFINITIONS
from core.events.emitter import EventEmitter
from core.interaction_log.recorder import InteractionRecorder
from core.llm.client import LLMClient
from core.llm.client.settings import LLMConfigManager
from core.store.memory import MemoryStore

if TYPE_CHECKING:
    from core.llm.agent.config_manager import AgentConfigManager


class AgentRegistry:
    """维护 agent 名称到 ReActAgent 实例的映射。"""

    def __init__(
        self,
        store: MemoryStore,
        emitter: EventEmitter,
        conversations: ConversationStore,
        llm_config: LLMConfigManager,
        llm_client: LLMClient,
        recorder: InteractionRecorder | None = None,
        agent_config: AgentConfigManager | None = None,
        confirmation_manager: ConfirmationManager | None = None,
    ) -> None:
        self._store = store
        self._agent_config = agent_config or get_agent_config_manager()
        self._agents: dict[str, ReActAgent] = {}
        for name, cls in AGENT_CLASSES.items():
            agent = cls(
                store,
                emitter,
                conversations,
                llm_config,
                llm_client,
                recorder,
                agent_config=self._agent_config,
                confirmation_manager=confirmation_manager,
            )
            definition = AGENT_DEFINITIONS.get(name)
            if definition:
                agent.role_prompt = definition.role_prompt
            self._agents[name] = agent

    @property
    def agent_config(self) -> AgentConfigManager:
        return self._agent_config

    def get(self, agent_name: str) -> ReActAgent:
        agent = self._agents.get(agent_name)
        if not agent:
            raise KeyError(f"未知 Agent: {agent_name}")
        return agent
