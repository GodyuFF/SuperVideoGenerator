"""生成队列 HTTP API：快照查询与手动入队。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.api.state import state
from core.generation.queue import get_generation_queue
from core.models.entities import Script

router = APIRouter(prefix="/api", tags=["generation-queue"])


class EnqueueBody(BaseModel):
    """生成队列入队请求体。"""

    kind: str = Field(..., pattern="^(image|video)$")
    asset_id: str
    variant_id: str | None = None
    label: str | None = None
    source: str = Field(default="regenerate", pattern="^(regenerate|batch|agent)$")


def _require_script(project_id: str, script_id: str) -> Script:
    """校验项目与剧本存在且归属一致，否则抛出 404。"""
    if not state.store.get_project(project_id):
        raise HTTPException(404, detail="项目不存在")
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, detail="剧本不存在")
    return script


@router.get("/projects/{project_id}/scripts/{script_id}/generation-queue")
async def get_generation_queue_snapshot(project_id: str, script_id: str):
    """返回指定剧本维度的生成队列快照。"""
    _require_script(project_id, script_id)
    return get_generation_queue().snapshot_for_script(script_id)


@router.post(
    "/projects/{project_id}/scripts/{script_id}/generation-queue/enqueue",
    status_code=202,
)
async def enqueue_generation_job(
    project_id: str,
    script_id: str,
    body: EnqueueBody,
):
    """将图片或视频生成任务加入全局串行队列。"""
    _require_script(project_id, script_id)
    job = await get_generation_queue().enqueue(
        project_id=project_id,
        script_id=script_id,
        kind=body.kind,  # type: ignore[arg-type]
        asset_id=body.asset_id,
        label=body.label or body.asset_id,
        source=body.source,  # type: ignore[arg-type]
        variant_id=body.variant_id,
    )
    return {
        "job": job.to_public_dict(),
        "snapshot": get_generation_queue().snapshot_for_script(script_id),
    }
