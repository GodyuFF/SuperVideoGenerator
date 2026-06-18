"""REST API：项目、剧本、配置、Plan/Execute。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apps.api.state import create_project, create_script, state
from core.guards.script_style import ScriptStyleLockedError
from core.models.entities import GenerationMode, VideoStyleMode

router = APIRouter(prefix="/api")


class CreateProjectRequest(BaseModel):
    """创建项目请求体。"""

    title: str


class CreateScriptRequest(BaseModel):
    """创建剧本请求体。"""

    title: str
    duration_sec: int = 60
    style_mode: VideoStyleMode | None = None  # 若提供则在创建时绑定并锁定风格


class UpdateConfigRequest(BaseModel):
    """更新项目配置请求体（不含视频风格，风格绑定在剧本级）。"""

    generation_mode: GenerationMode | None = None
    require_plan_approval: bool | None = None


class ChatRequest(BaseModel):
    """用户对话请求：超级视频大师自动 Plan 并调度子 Agent 执行。"""

    message: str
    generation_mode: GenerationMode | None = None
    style_mode: VideoStyleMode | None = None


@router.post("/projects")
def post_project(body: CreateProjectRequest):
    """创建新项目。"""
    return create_project(body.title).model_dump()


@router.get("/projects/{project_id}")
def get_project(project_id: str):
    """获取项目详情。"""
    project = state.store.get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    return project.model_dump()


@router.patch("/projects/{project_id}/config")
def patch_config(project_id: str, body: UpdateConfigRequest):
    """更新项目配置（生成模式、视频风格等）。"""
    project = state.store.get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if body.generation_mode is not None:
        project.config.generation.mode = body.generation_mode
    if body.require_plan_approval is not None:
        project.config.generation.require_plan_approval = body.require_plan_approval
    return project.config.model_dump()


@router.post("/projects/{project_id}/scripts")
def post_script(project_id: str, body: CreateScriptRequest):
    """在项目下创建剧本。"""
    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    project = state.store.get_project(project_id)
    script = create_script(project_id, body.title, body.duration_sec)
    if body.style_mode is not None and project:
        from core.guards.script_style import bind_script_style

        bind_script_style(script, project, body.style_mode)
    return script.model_dump()


@router.get("/projects/{project_id}/scripts/{script_id}")
def get_script(project_id: str, script_id: str):
    """获取剧本详情。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    return script.model_dump()


@router.get("/projects/{project_id}/scripts/{script_id}/assets")
def list_assets(project_id: str, script_id: str):
    """列出剧本相关资产（含共享池）。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    assets = state.store.list_assets_for_script(script_id)
    return [a.model_dump() for a in assets]


@router.get("/projects/{project_id}/scripts/{script_id}/plan")
def get_plan(project_id: str, script_id: str):
    """获取当前 PlanDocument。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    plan = state.store.get_plan(script_id)
    if not plan:
        raise HTTPException(404, "计划不存在")
    return plan.model_dump()


@router.get("/projects/{project_id}/scripts/{script_id}/video-plan")
def get_video_plan(project_id: str, script_id: str):
    """获取分镜视频计划稿（镜头列表与旁白）。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    vp = state.store.get_video_plan_for_script(script_id)
    if not vp:
        raise HTTPException(404, "视频计划稿不存在")
    return vp.model_dump()


@router.post("/projects/{project_id}/scripts/{script_id}/chat")
async def post_chat(project_id: str, script_id: str, body: ChatRequest):
    """
    用户对话入口：超级视频大师自动规划并调用子 Agent。
    视频风格在首次生成剧本时绑定到 script，之后不可修改。
    """
    project = state.store.get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")

    if body.generation_mode is not None:
        project.config.generation.mode = body.generation_mode

    if not body.message.strip():
        raise HTTPException(400, "消息不能为空")

    # 已锁定风格时，禁止传入不同 style_mode
    if script.style_locked and body.style_mode is not None:
        if script.style_mode and body.style_mode != script.style_mode:
            raise HTTPException(
                400,
                f"剧本视频风格已锁定为 {script.style_mode.value}，不可修改",
            )

    try:
        conversation_id, summary = await state.super_video_master.run_from_message(
            project_id,
            script_id,
            body.message,
            requested_style=body.style_mode,
        )
    except ScriptStyleLockedError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))

    state.persist_store()

    script = state.store.get_script(script_id)
    plan = state.store.get_plan(script_id)
    return {
        "conversation_id": conversation_id,
        "summary": summary,
        "script": script.model_dump() if script else None,
        "plan": plan.model_dump() if plan else None,
    }
