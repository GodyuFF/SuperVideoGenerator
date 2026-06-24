"""看板视图数据模型。"""

from typing import Any

from pydantic import BaseModel, Field


class BoardNode(BaseModel):
    """看板图节点。"""

    id: str
    kind: str
    label: str
    subtitle: str = ""
    group: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class BoardEdge(BaseModel):
    """看板图边。"""

    id: str
    source: str
    target: str
    relation: str
    label: str = ""


class PipelineStepView(BaseModel):
    """生成流水线步骤（固定顺序 + 实际状态）。"""

    order: int
    step_type: str
    title: str
    agent: str
    status: str = "pending"
    description: str = ""


class BoardView(BaseModel):
    """单个看板 Tab 的完整数据。"""

    kind: str
    title: str
    description: str = ""
    nodes: list[BoardNode] = Field(default_factory=list)
    edges: list[BoardEdge] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list)
    pipeline: list[PipelineStepView] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
