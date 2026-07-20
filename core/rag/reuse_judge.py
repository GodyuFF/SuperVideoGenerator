"""LLM Reuse Judge：判定 reuse / fork / create_new。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Protocol

from core.llm.json_parse import parse_llm_json_object
from core.llm.model.chat_message import ChatMessage
from core.llm.model.llm_request import LlmRequest
from core.llm.prompt.loader import load_text
from core.models.entities import RagConfig
from core.rag.models import RagHit, RagQuery, ReuseDecision
from core.store.memory import MemoryStore

if TYPE_CHECKING:
    from core.llm.client.client import LLMClient

JudgeFn = Callable[
    [MemoryStore, RagQuery, list[RagHit], RagConfig],
    Awaitable[ReuseDecision],
]


class ReuseJudge(Protocol):
    """复用判定协议。"""

    async def decide(
        self,
        store: MemoryStore,
        query: RagQuery,
        candidates: list[RagHit],
        *,
        rag_config: RagConfig,
    ) -> ReuseDecision:
        ...


def _aggression_hint(rag_config: RagConfig) -> str:
    mapping = {
        "conservative": "保守：仅当候选与需求高度一致时才 reuse；轻微差异 prefer fork 或 create_new。",
        "balanced": "平衡：语义一致且无明显冲突时可 reuse；设定差异明显时 fork。",
        "aggressive": "激进：只要核心实体一致即可 reuse；仅在明显冲突时 fork 或 create_new。",
    }
    return mapping.get(rag_config.reuse_aggression, mapping["balanced"])


def _build_judge_system(rag_config: RagConfig) -> str:
    fixed = load_text("agents/script_agent/fixed/reuse_judge.md")
    if not fixed:
        fixed = (
            "你是共享资产复用 Judge。根据剧本上下文、待创建实体与候选列表，"
            "输出 JSON：decision(reuse|fork|create_new)、selected_asset_id、fork_patch、reason、confidence。"
        )
    fork_hint = (
        "冲突时优先 fork（新建变体并 derived_from 溯源）。"
        if rag_config.auto_fork_on_conflict
        else "冲突时 prefer create_new。"
    )
    return f"{fixed}\n\n策略：{_aggression_hint(rag_config)}\n{fork_hint}"


def _build_judge_user(
    store: MemoryStore,
    query: RagQuery,
    candidates: list[RagHit],
) -> str:
    script = store.get_script(query.script_id)
    script_block = {
        "id": query.script_id,
        "title": script.title if script else "",
        "content_preview": (script.content_md or "")[:800] if script else "",
    }
    requirement = {
        "asset_type": query.asset_type,
        "asset_name": query.asset_name,
        "summary": query.requirement_summary,
        "text": query.requirement_text,
    }
    candidate_rows = [
        {
            "asset_id": hit.asset_id,
            "name": hit.name,
            "summary": hit.summary,
            "score": round(hit.score, 4),
            "content_preview": hit.content_preview,
        }
        for hit in candidates
    ]
    return json.dumps(
        {
            "script": script_block,
            "requirement": requirement,
            "candidates": candidate_rows,
        },
        ensure_ascii=False,
        indent=2,
    )


def _parse_decision(raw: dict, query: RagQuery) -> ReuseDecision:
    decision = str(raw.get("decision", "create_new")).strip().lower()
    if decision not in ("reuse", "fork", "create_new"):
        decision = "create_new"
    selected = raw.get("selected_asset_id")
    selected_id = str(selected).strip() if selected else None
    fork_patch = raw.get("fork_patch") or {}
    if not isinstance(fork_patch, dict):
        fork_patch = {}
    reason = str(raw.get("reason", "")).strip()
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return ReuseDecision(
        requirement_summary=query.requirement_summary,
        decision=decision,  # type: ignore[arg-type]
        selected_asset_id=selected_id,
        fork_patch=fork_patch,
        reason=reason,
        confidence=confidence,
    )


class LlmReuseJudge:
    """调用 LLM 输出结构化 ReuseDecision。"""

    def __init__(self, llm_client: Any | None = None) -> None:
        if llm_client is None:
            from core.llm.client.client import LLMClient

            llm_client = LLMClient()
        self._llm = llm_client

    async def decide(
        self,
        store: MemoryStore,
        query: RagQuery,
        candidates: list[RagHit],
        *,
        rag_config: RagConfig,
    ) -> ReuseDecision:
        if not candidates:
            return ReuseDecision(
                requirement_summary=query.requirement_summary,
                decision="create_new",
                reason="无候选资产",
                confidence=1.0,
            )
        request = LlmRequest(
            system=_build_judge_system(rag_config),
            messages=[
                ChatMessage(
                    role="user",
                    content=_build_judge_user(store, query, candidates),
                )
            ],
            max_tokens=1024,
        )
        try:
            text = await self._llm.complete(request, summary_prefix="RAG reuse judge")
            raw = parse_llm_json_object(text)
            decision = _parse_decision(raw, query)
            if decision.decision in ("reuse", "fork") and not decision.selected_asset_id:
                decision.selected_asset_id = candidates[0].asset_id
            if decision.decision == "reuse":
                valid_ids = {c.asset_id for c in candidates}
                if decision.selected_asset_id not in valid_ids:
                    decision.decision = "create_new"
                    decision.selected_asset_id = None
                    decision.reason = (decision.reason or "") + " selected_asset_id 无效，回退 create_new"
            return decision
        except Exception as exc:
            return ReuseDecision(
                requirement_summary=query.requirement_summary,
                decision="create_new",
                reason=f"Judge 失败: {exc}",
                confidence=0.0,
            )


_default_judge: LlmReuseJudge | None = None


def get_reuse_judge() -> LlmReuseJudge:
    """返回进程级默认 Reuse Judge。"""
    global _default_judge
    if _default_judge is None:
        _default_judge = LlmReuseJudge()
    return _default_judge
