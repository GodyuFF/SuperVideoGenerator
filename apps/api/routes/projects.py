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
    conversation_id: str | None = None
    generation_mode: GenerationMode | None = None
    style_mode: VideoStyleMode | None = None


class CreateConversationRequest(BaseModel):
    """显式创建对话线程。"""

    title: str = ""


@router.get("/projects")
def list_projects():
    """列出本地持久化的所有项目。"""
    projects = state.store.list_projects()
    result = []
    for p in projects:
        scripts = state.store.list_scripts_for_project(p.id)
        result.append(
            {
                **p.model_dump(),
                "script_count": len(scripts),
                "scripts": [
                    {"id": s.id, "title": s.title, "status": s.status.value}
                    for s in scripts
                ],
            }
        )
    return result


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


@router.get("/projects/{project_id}/scripts/{script_id}/media")
def list_media(project_id: str, script_id: str):
    """列出剧本相关数字媒体资产（图片/视频/配音/成片）。"""
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    assets = state.store.list_media_for_script(script_id)
    return [a.model_dump() for a in assets]


@router.post("/projects/{project_id}/scripts/{script_id}/conversations")
def post_conversation(
    project_id: str, script_id: str, body: CreateConversationRequest | None = None
):
    """创建新对话线程并返回 conversation_id。"""
    project = state.store.get_project(project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    script = state.store.get_script(script_id)
    if not script or script.project_id != project_id:
        raise HTTPException(404, "剧本不存在")
    title = (body.title if body else "") or "新对话"
    conv = state.conversation_index.create(project_id, script_id, title=title)
    state.persist_store()
    return {
        "conversation_id": conv.id,
        "project_id": conv.project_id,
        "script_id": conv.script_id,
        "created_at": conv.created_at,
    }


@router.get("/projects/{project_id}/conversations")
def list_conversations(project_id: str, script_id: str | None = None):
    """列出项目下历史对话（可按剧本过滤）。"""
    if not state.store.get_project(project_id):
        raise HTTPException(404, "项目不存在")
    items = state.conversation_index.list_for_project(
        project_id, script_id=script_id
    )
    return [
        {
            "id": c.id,
            "script_id": c.script_id,
            "title": c.title,
            "last_summary": c.last_summary,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
            "status": c.status.value,
            "last_round_token_usage": c.last_round_token_usage,
            "total_token_usage": c.total_token_usage,
        }
        for c in items
    ]


@router.get("/projects/{project_id}/conversations/{conversation_id}/messages")
def get_conversation_messages(project_id: str, conversation_id: str):
    """加载单对话的用户可见消息（唤醒 UI）。"""
    conv = state.conversation_index.get(conversation_id)
    if not conv or conv.project_id != project_id:
        raise HTTPException(404, "对话不存在")
    msgs = state.conversations.list_master_messages_for_ui(conversation_id)
    return [
        {
            "role": m.role.value,
            "content": m.content,
            "created_at": m.created_at,
        }
        for m in msgs
    ]


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
        if body.conversation_id:
            state.conversation_index.require(
                body.conversation_id,
                project_id=project_id,
                script_id=script_id,
            )
            conversation_id = body.conversation_id
        else:
            preview = body.message.strip().replace("\n", " ")
            if len(preview) > 48:
                preview = preview[:48] + "…"
            conv = state.conversation_index.create(
                project_id,
                script_id,
                title=preview or "新对话",
            )
            conversation_id = conv.id

        conversation_id, summary = await state.super_video_master.run_from_message(
            project_id,
            script_id,
            body.message,
            requested_style=body.style_mode,
            conversation_id=conversation_id,
        )
    except ScriptStyleLockedError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        msg = str(e)
        if "对话" in msg:
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)
    except RuntimeError as e:
        raise HTTPException(502, str(e))

    state.persist_store()

    script = state.store.get_script(script_id)
    plan = state.store.get_plan(script_id)
    conv = state.conversation_index.get(conversation_id)
    return {
        "conversation_id": conversation_id,
        "summary": summary,
        "token_usage": conv.last_round_token_usage if conv else {},
        "script": script.model_dump() if script else None,
        "plan": plan.model_dump() if plan else None,
    }
