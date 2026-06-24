"""子 Agent 注册表。"""

from core.agents.base import ReActAgent
from core.agents.config_manager import AgentConfigManager
from core.agents.conversation import ConversationStore
from core.agents.definitions import AGENT_CLASSES, AGENT_DEFINITIONS
from core.events.emitter import EventEmitter
from core.interaction_log.recorder import InteractionRecorder
from core.llm.react_decider import LLMReActDecider
from core.store.memory import MemoryStore


class AgentRegistry:
    """维护 agent 名称到 ReActAgent 实例的映射。"""

    def __init__(
        self,
        store: MemoryStore,
        emitter: EventEmitter,
        conversations: ConversationStore,
        llm_decider: LLMReActDecider,
        recorder: InteractionRecorder | None = None,
        agent_config: AgentConfigManager | None = None,
    ) -> None:
        agent_args = (store, emitter, conversations, llm_decider, recorder)
        llm_client = llm_decider._client
        llm_config = llm_decider._config
        self._store = store
        self._agent_config = agent_config or AgentConfigManager()
        self._agents: dict[str, ReActAgent] = {}
        for name, cls in AGENT_CLASSES.items():
            agent = cls(
                *agent_args,
                llm_config=llm_config,
                llm_client=llm_client,
                agent_config=self._agent_config,
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
