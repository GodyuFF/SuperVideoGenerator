"""接口交互记录 API。"""

import re

from fastapi import APIRouter, HTTPException, Query

from apps.api.state import state

router = APIRouter(prefix="/api/interactions")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("")
def list_interactions(
    script_id: str | None = None,
    project_id: str | None = None,
    kind: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """查询持久化交互记录（LLM / HTTP / Agent 动作）。"""
    records = state.interaction_log_store.list_records(
        script_id=script_id,
        project_id=project_id,
        kind=kind,
        limit=limit,
    )
    llm_count = state.interaction_log_store.count_llm_calls(
        script_id=script_id,
        project_id=project_id,
    )
    return {
        "total": len(records),
        "llm_call_count": llm_count,
        "records": [r.model_dump() for r in records],
    }


@router.get("/files")
def list_interaction_log_files(project_id: str | None = None):
    """列出本地 JSONL 交互日志文件（按项目 + 日期）。"""
    files = state.interaction_file_store.list_log_files(project_id=project_id)
    return {
        "log_dir": str(state.interaction_file_store.log_dir),
        "project_id": project_id or "",
        "files": files,
    }


@router.get("/stats")
def interaction_stats(script_id: str | None = None):
    """交互统计：LLM 调用与 Agent 动作次数。"""
    store = state.interaction_log_store
    all_recs = store.list_records(script_id=script_id, limit=500)
    stats = {
        "llm_response": 0,
        "llm_request": 0,
        "llm_error": 0,
        "agent_action": 0,
        "api_request": 0,
    }
    for r in all_recs:
        if r.kind in stats:
            stats[r.kind] += 1
    stats["llm_real_calls"] = stats["llm_response"]
    return stats


@router.delete("")
def delete_interaction_logs(
    project_id: str = Query(..., min_length=1),
    date: str = Query(..., min_length=10, max_length=10),
    script_id: str | None = None,
):
    """按项目 + 日期删除交互日志（SQLite 与 JSONL 同步清理）。"""
    if not _DATE_RE.match(date):
        raise HTTPException(400, detail="date 须为 YYYY-MM-DD")
    sqlite_deleted = state.interaction_log_store.delete_records(
        project_id=project_id,
        date=date,
        script_id=script_id,
    )
    jsonl_deleted = state.interaction_file_store.delete_log_file(project_id, date)
    return {
        "ok": True,
        "project_id": project_id,
        "date": date,
        "script_id": script_id or "",
        "sqlite_deleted": sqlite_deleted,
        "jsonl_deleted": jsonl_deleted,
    }
