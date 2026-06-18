"""接口交互记录 API。"""

from fastapi import APIRouter, Query

from apps.api.state import state

router = APIRouter(prefix="/api/interactions")


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
    llm_count = state.interaction_log_store.count_llm_calls(script_id=script_id)
    return {
        "total": len(records),
        "llm_call_count": llm_count,
        "records": [r.model_dump() for r in records],
    }


@router.get("/files")
def list_interaction_log_files():
    """列出本地 JSONL 交互日志文件（data/logs/interactions/）。"""
    files = state.interaction_file_store.list_log_files()
    return {
        "log_dir": str(state.interaction_file_store.log_dir),
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
