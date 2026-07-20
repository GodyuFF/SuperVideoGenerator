"""REST API：看板视图。"""

from fastapi import APIRouter, HTTPException, Query

from apps.api.state import state
from core.board.builder import BOARD_KINDS, BOARD_TITLES, BoardBuilder

router = APIRouter(prefix="/api")


@router.get("/board/kinds")
def list_board_kinds():
    """返回可用看板 Tab 列表。"""
    return [
        {"id": k, "title": BOARD_TITLES[k]}
        for k in BOARD_KINDS
    ]


@router.get("/projects/{project_id}/board/{kind}")
def get_board(
    project_id: str,
    kind: str,
    script_id: str | None = Query(None),
):
    """获取指定看板视图数据（由仓储内容动态生成）。"""
    if kind not in BOARD_KINDS:
        raise HTTPException(400, f"未知看板类型: {kind}")
    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    if kind == "storyboard" and script_id:
        from core.edit.shot_detail_sync import (
            lazy_sync_storyboard_if_needed,
            refresh_shot_tts_durations_if_drifted,
        )

        changed = lazy_sync_storyboard_if_needed(state.store, script_id)
        refreshed, _ = refresh_shot_tts_durations_if_drifted(state.store, script_id)
        if changed or refreshed:
            from core.store.persist import schedule_save

            schedule_save(
                state.store,
                conversation_index=state.conversation_index,
                conversation_store=None,
            )
    try:
        view = BoardBuilder(state.store).build(kind, project_id, script_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return view.model_dump()


@router.get("/projects/{project_id}/overview")
def get_project_overview(project_id: str, script_id: str | None = Query(None)):
    """项目整体看板快捷入口。"""
    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    view = BoardBuilder(state.store).build("overview", project_id, script_id)
    project = state.store.get_project(project_id)
    scripts = state.store.list_scripts_for_project(project_id)
    return {
        "project": project.model_dump() if project else None,
        "scripts": [s.model_dump() for s in scripts],
        "board": view.model_dump(),
    }
