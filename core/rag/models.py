"""RAG 复用流程的数据模型。"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class RagQuery(BaseModel):
    """单次共享资产检索查询。"""

    project_id: str
    script_id: str
    asset_type: Literal["character", "scene", "prop"]
    asset_name: str
    requirement_summary: str
    requirement_text: str


class RagHit(BaseModel):
    """向量检索命中的候选共享资产。"""

    asset_id: str
    name: str
    asset_type: str
    summary: str
    score: float
    content_preview: dict[str, Any] = Field(default_factory=dict)


class ReuseDecision(BaseModel):
    """LLM Reuse Judge 判定结果。"""

    requirement_summary: str = ""
    decision: Literal["reuse", "fork", "create_new"]
    selected_asset_id: str | None = None
    fork_patch: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    confidence: float = 0.0
