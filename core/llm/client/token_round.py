"""单轮对话（一次用户消息）内的多模型 token 预估汇总。"""

from dataclasses import dataclass, field
from typing import Any

from core.llm.client.tokens import TokenBreakdown, TokenEstimate


@dataclass
class ModelTokenUsage:
    """同一 provider/model 在一轮对话内的累计预估。"""

    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    system_tokens: int = 0
    tools_tokens: int = 0
    messages_tokens: int = 0

    def add(self, estimate: TokenEstimate, breakdown: TokenBreakdown | None = None) -> None:
        self.prompt_tokens += estimate.prompt_tokens
        self.completion_tokens += estimate.completion_tokens
        self.total_tokens += estimate.total_tokens
        self.calls += 1
        if breakdown:
            self.system_tokens += breakdown.system_tokens
            self.tools_tokens += breakdown.tools_tokens
            self.messages_tokens += breakdown.messages_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "calls": self.calls,
            "breakdown": {
                "system_tokens": self.system_tokens,
                "tools_tokens": self.tools_tokens,
                "messages_tokens": self.messages_tokens,
            },
        }


@dataclass
class TokenRoundAccumulator:
    """收集一轮对话内所有 LLM 调用的 token 预估。"""

    conversation_id: str
    project_id: str
    script_id: str
    _by_model: dict[tuple[str, str], ModelTokenUsage] = field(default_factory=dict)

    def add(
        self,
        provider: str,
        model: str,
        estimate: TokenEstimate,
        *,
        breakdown: TokenBreakdown | None = None,
        kind: str = "",
        agent_name: str = "",
    ) -> None:
        key = (provider, model)
        if key not in self._by_model:
            self._by_model[key] = ModelTokenUsage(provider=provider, model=model)
        self._by_model[key].add(estimate, breakdown)

    def snapshot(self) -> dict[str, Any]:
        models = [u.to_dict() for u in self._by_model.values()]
        total_prompt = sum(u.prompt_tokens for u in self._by_model.values())
        total_completion = sum(u.completion_tokens for u in self._by_model.values())
        total = sum(u.total_tokens for u in self._by_model.values())
        breakdown_totals = {
            "system_tokens": sum(u.system_tokens for u in self._by_model.values()),
            "tools_tokens": sum(u.tools_tokens for u in self._by_model.values()),
            "messages_tokens": sum(u.messages_tokens for u in self._by_model.values()),
        }
        return {
            "conversation_id": self.conversation_id,
            "project_id": self.project_id,
            "script_id": self.script_id,
            "estimated": True,
            "models": models,
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total,
            "breakdown": breakdown_totals,
        }
