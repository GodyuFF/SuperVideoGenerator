"""测试用 Reuse Judge：按规则或预设表返回确定性判定。"""

from __future__ import annotations

from typing import Any

from core.models.entities import RagConfig
from core.rag.models import RagHit, RagQuery, ReuseDecision
from core.store.memory import MemoryStore


class ScriptedReuseJudge:
    """按 asset_name 或候选匹配返回预设 decision。"""

    def __init__(
        self,
        *,
        decisions: dict[str, dict[str, Any]] | None = None,
        default: str = "create_new",
    ) -> None:
        self._decisions = decisions or {}
        self._default = default

    async def decide(
        self,
        store: MemoryStore,
        query: RagQuery,
        candidates: list[RagHit],
        *,
        rag_config: RagConfig,
    ) -> ReuseDecision:
        """按 query.asset_name 或首个候选 id 查找预设。"""
        key = query.asset_name.strip()
        preset = self._decisions.get(key)
        if preset is None and candidates:
            preset = self._decisions.get(candidates[0].asset_id)
        if preset is None:
            if self._default == "reuse" and candidates:
                return ReuseDecision(
                    requirement_summary=query.requirement_summary,
                    decision="reuse",
                    selected_asset_id=candidates[0].asset_id,
                    reason="scripted default reuse",
                    confidence=0.95,
                )
            return ReuseDecision(
                requirement_summary=query.requirement_summary,
                decision="create_new",  # type: ignore[arg-type]
                reason="scripted default create_new",
                confidence=0.9,
            )
        decision = str(preset.get("decision", self._default))
        selected = preset.get("selected_asset_id")
        if not selected and candidates and decision in ("reuse", "fork"):
            selected = candidates[0].asset_id
        fork_patch = preset.get("fork_patch") or {}
        if not isinstance(fork_patch, dict):
            fork_patch = {}
        return ReuseDecision(
            requirement_summary=query.requirement_summary,
            decision=decision,  # type: ignore[arg-type]
            selected_asset_id=str(selected) if selected else None,
            fork_patch=fork_patch,
            reason=str(preset.get("reason", "scripted")),
            confidence=float(preset.get("confidence", 0.9)),
        )
