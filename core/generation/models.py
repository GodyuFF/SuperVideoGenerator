"""生成队列领域模型。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal
import time
import uuid

GenerationKind = Literal["image", "video"]
GenerationStatus = Literal["queued", "running", "done", "failed"]
GenerationSource = Literal["regenerate", "batch", "agent"]


@dataclass
class GenerationJob:
    """单条图片或视频生成任务。"""

    id: str
    script_id: str
    project_id: str
    kind: GenerationKind
    asset_id: str
    label: str
    status: GenerationStatus
    source: GenerationSource
    error: str | None = None
    variant_id: str | None = None
    created_at: float = field(default_factory=lambda: time.time())
    started_at: float | None = None
    finished_at: float | None = None
    # Agent 单项执行载荷；regenerate 路径可为 None
    payload: dict[str, Any] | None = None

    def dedupe_key(self) -> str:
        """同剧本同资产同变体去重键。"""
        return f"{self.script_id}|{self.kind}|{self.asset_id}|{self.variant_id or ''}"

    def to_public_dict(self) -> dict[str, Any]:
        """WS/HTTP 公开字段（不含 payload）。"""
        d = asdict(self)
        d.pop("payload", None)
        return d


def new_job_id() -> str:
    """生成 gen_ 前缀任务 ID。"""
    return f"gen_{uuid.uuid4().hex[:16]}"
