"""领域实体与枚举定义：项目、剧本、资产、计划稿等核心数据结构。"""

from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    """生成带类型前缀的唯一 ID，例如 proj_abc123。"""
    return f"{prefix}_{uuid4().hex[:12]}"


class GenerationMode(str, Enum):
    """视频生成确认模式。"""

    AUTO = "auto"  # 自动生成：跳过视频生成费用确认
    COST_CONFIRM = "cost_confirm"  # 费用确认：视频生成前需用户 A2UI 确认


class ScriptStatus(str, Enum):
    """剧本生命周期状态。"""

    DRAFT = "draft"  # 草稿，可编辑
    PLANNED = "planned"  # 已生成 Plan，未执行
    EXECUTING = "executing"  # 执行中，资产只读
    COMPLETED = "completed"  # 执行完成
    FAILED = "failed"  # 执行失败


class AssetStatus(str, Enum):
    """单资产状态。"""

    DRAFT = "draft"
    READY = "ready"
    LOCKED = "locked"  # 执行中锁定
    GENERATED = "generated"  # 已有下游数字资产
    ARCHIVED = "archived"


class TextAssetType(str, Enum):
    """文字资产类型。"""

    CHARACTER = "character"  # 人物
    PROP = "prop"  # 道具
    SCENE = "scene"  # 场景
    PLOT = "plot"  # 剧情段落
    NARRATION = "narration"  # 旁白/配音文案


class AssetScope(str, Enum):
    """资产归属范围。"""

    PROJECT_SHARED = "project_shared"  # 项目共享池（人物/道具/场景）
    SCRIPT_PRIVATE = "script_private"  # 剧本私有


class RelationType(str, Enum):
    """资产引用关系类型。"""

    USES = "uses"  # 引用
    DERIVED_FROM = "derived_from"  # 派生自
    RAG_REUSE = "rag_reuse"  # RAG 复用
    GENERATES = "generates"  # 生成（文字→数字）
    VOICE_OF = "voice_of"  # 声音绑定角色


class StepStatus(str, Enum):
    """Plan 步骤执行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # 等待 A2UI 用户确认


class VideoStyleMode(str, Enum):
    """视频生产风格模式。"""

    DYNAMIC_IMAGE = "dynamic_image"  # 动态图片：图片+运镜+配音，不调视频 API
    AI_VIDEO = "ai_video"  # AI 视频：调用视频生成 API


class GenerationConfig(BaseModel):
    """生成行为配置（项目级）。"""

    mode: GenerationMode = GenerationMode.COST_CONFIRM
    require_plan_approval: bool = False  # 是否强制 Plan 后人工确认再执行
    require_script_structure_approval: bool = True  # 是否确认剧本粒度结构


class StyleConfig(BaseModel):
    """视频风格与画面配置。"""

    mode: VideoStyleMode = VideoStyleMode.DYNAMIC_IMAGE
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    transition: str = "fade"
    watermark_free_images_only: bool = True
    bgm_enabled: bool = False


class ProjectConfig(BaseModel):
    """项目完整配置。"""

    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    style: StyleConfig = Field(default_factory=StyleConfig)


class Project(BaseModel):
    """视频项目根实体。"""

    id: str = Field(default_factory=lambda: new_id("proj"))
    title: str
    config: ProjectConfig = Field(default_factory=ProjectConfig)
    created_at: str = ""


class Script(BaseModel):
    """剧本（章节/集），隶属于项目。"""

    id: str = Field(default_factory=lambda: new_id("script"))
    project_id: str
    title: str
    duration_sec: int = 60
    status: ScriptStatus = ScriptStatus.DRAFT
    content_md: str = ""
    plan_version: int = 0
    # 视频风格在生成剧本时绑定，锁定后全链路不可修改
    style_mode: VideoStyleMode | None = None
    style_locked: bool = False


class TextAsset(BaseModel):
    """文字资产：人物、场景、剧情等结构化描述。"""

    id: str = Field(default_factory=lambda: new_id("txt"))
    project_id: str
    script_id: str | None = None
    scope: AssetScope = AssetScope.SCRIPT_PRIVATE
    type: TextAssetType
    name: str
    content: dict[str, Any] = Field(default_factory=dict)
    status: AssetStatus = AssetStatus.DRAFT
    user_edited: bool = False  # 用户是否在 UI 手工修改过
    source_script_id: str | None = None  # 首次创建来源剧本


class AssetReference(BaseModel):
    """资产之间的引用边，用于删除守卫与看板。"""

    id: str = Field(default_factory=lambda: new_id("ref"))
    source_id: str
    target_id: str
    relation: RelationType
    script_id: str | None = None


class StepOutput(BaseModel):
    """Plan 步骤执行产出的单条结果。"""

    kind: Literal["text", "image", "video", "audio", "json"]
    label: str
    asset_id: str
    url: str = ""


class PlanStep(BaseModel):
    """ReAct 编排中的单个执行步骤。"""

    id: str = Field(default_factory=lambda: new_id("step"))
    type: str
    title: str
    description: str = ""
    agent: str  # 负责的子 Agent 名称
    depends_on: list[str] = Field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    progress: int = 0
    outputs: list[StepOutput] = Field(default_factory=list)
    error: str | None = None
    estimated_cost_usd: float | None = None  # 预估费用（视频生成等）


class PlanDocument(BaseModel):
    """超级视频大师输出的结构化执行计划。"""

    version: int = 1
    goal: str = ""
    constraints: dict[str, Any] = Field(default_factory=dict)
    steps: list[PlanStep] = Field(default_factory=list)


class VideoPlanShot(BaseModel):
    """视频计划稿中的单个镜头。"""

    id: str = Field(default_factory=lambda: new_id("shot"))
    order: int = 0
    duration_ms: int = 3000
    camera_motion: str = "static"
    narration_text: str = ""
    asset_refs: dict[str, list[str]] = Field(default_factory=dict)


class VideoPlan(BaseModel):
    """分镜 Agent 输出的视频计划稿。"""

    id: str = Field(default_factory=lambda: new_id("plan"))
    script_id: str
    mode: VideoStyleMode = VideoStyleMode.DYNAMIC_IMAGE
    shots: list[VideoPlanShot] = Field(default_factory=list)
