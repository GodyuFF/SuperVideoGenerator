"""A2UI（Agent-to-UI）确认协议的数据结构：服务端推送表单，前端回传用户选择。"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from core.models.entities import new_id


class A2UIComponentType(str):
    """A2UI 组件类型常量。"""

    TEXT = "text"
    MARKDOWN = "markdown"
    SELECT = "select"
    CHECKBOX = "checkbox"
    COST_SUMMARY = "cost_summary"


class A2UIComponent(BaseModel):
    """A2UI 表单单个字段/组件描述。"""

    id: str
    component: Literal["text", "markdown", "select", "checkbox", "cost_summary"]
    label: str
    value: Any = None
    options: list[dict[str, str]] = Field(default_factory=list)
    required: bool = False


class A2UIConfirmationKind(str):
    """确认请求的业务类型。"""

    SCRIPT_STRUCTURE = "script_structure"  # 剧本结构/粒度确认
    PLAN_APPROVAL = "plan_approval"  # Plan 审批
    VIDEO_GENERATION_COST = "video_generation_cost"  # 视频生成费用确认
    SCRIPT_REQUIREMENTS = "script_requirements"  # 剧本需求收集（AskUserQuestion）
    GENERIC = "generic"  # 通用确认


class A2UIConfirmationRequest(BaseModel):
    """服务端通过 WebSocket 推送给前端的确认请求。"""

    type: Literal["a2ui_confirmation_required"] = "a2ui_confirmation_required"
    confirmation_id: str = Field(default_factory=lambda: new_id("conf"))
    kind: Literal[
        "script_structure",
        "plan_approval",
        "video_generation_cost",
        "script_requirements",
        "generic",
    ]
    title: str
    description: str = ""
    components: list[A2UIComponent] = Field(default_factory=list)
    estimated_cost_usd: float | None = None
    expires_in_sec: int = 300
    step_id: str | None = None  # 关联的 Plan 步骤 ID


class A2UIConfirmationResponse(BaseModel):
    """前端用户确认后回传给服务端的响应。"""

    type: Literal["a2ui_confirmation_response"] = "a2ui_confirmation_response"
    confirmation_id: str
    approved: bool  # 用户是否同意继续
    values: dict[str, Any] = Field(default_factory=dict)  # 表单字段值
