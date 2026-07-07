"""领域实体与枚举定义：项目、剧本、资产、计划稿等核心数据结构。"""

from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


def new_id(prefix: str) -> str:
    """生成带类型前缀的唯一 ID，例如 proj_abc123。"""
    return f"{prefix}_{uuid4().hex[:12]}"


class GenerationMode(str, Enum):
    """视频生成模式（保留枚举以兼容持久化数据）。"""

    AUTO = "auto"

    @classmethod
    def _missing_(cls, value: object) -> "GenerationMode | None":
        if value == "cost_confirm":
            return cls.AUTO
        return None


class ExecutionMode(str, Enum):
    """执行交互模式：interactive 需用户确认；goal 全自主执行。"""

    INTERACTIVE = "interactive"
    GOAL = "goal"


class ScriptStatus(str, Enum):
    """剧本生命周期状态。"""

    DRAFT = "draft"  # 草稿，可编辑
    PLANNED = "planned"  # 已生成 Plan，未执行
    EXECUTING = "executing"  # 执行中，资产只读
    COMPLETED = "completed"  # 执行完成
    FAILED = "failed"  # 执行失败


class ConversationStatus(str, Enum):
    """用户对话线程状态。"""

    ACTIVE = "active"
    ARCHIVED = "archived"


class Conversation(BaseModel):
    """用户与超级视频大师的一次对话线程（可跨多轮消息）。"""

    id: str = Field(default_factory=lambda: new_id("conv"))
    project_id: str
    script_id: str
    title: str = ""
    created_at: str = ""
    updated_at: str = ""
    status: ConversationStatus = ConversationStatus.ACTIVE
    last_summary: str = ""
    last_round_token_usage: dict[str, Any] = Field(default_factory=dict)
    total_token_usage: dict[str, Any] = Field(default_factory=dict)


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
    PAUSED = "paused"  # 子 Agent return_to_master，等待主编排协调


class VideoStyleMode(str, Enum):
    """视频生产风格模式。"""

    DYNAMIC_IMAGE = "dynamic_image"  # 动态图文：科普/汇报/讲解，图片+运镜+配音
    DYNAMIC_COMIC = "dynamic_comic"  # 动态漫画：漫画分格+运镜+配音
    AI_VIDEO = "ai_video"  # AI 视频：调用视频生成 API


class ImageSourceMode(str, Enum):
    """角色/物品/场景图片获取方式。"""

    GENERATE = "generate"  # 批量 AI 生图
    SEARCH = "search"  # 批量搜索配图
    USER_CHOICE = "user_choice"  # 执行图片步骤前弹窗让用户选择


class ImageTextConfig(BaseModel):
    """图文/漫画模式下的图片批量策略（项目级，可被全局默认覆盖）。"""

    source_mode: ImageSourceMode = ImageSourceMode.GENERATE
    image_text_preset: Literal["explainer", "report", "lecture"] = "explainer"
    comic_preset: Literal["manga", "webtoon", "ink"] = "manga"
    batch_pending_assets: bool = True
    allow_search_fallback: bool = True


class GenerationConfig(BaseModel):
    """生成行为配置（项目级）。"""

    mode: GenerationMode = GenerationMode.AUTO
    execution_mode: ExecutionMode = ExecutionMode.INTERACTIVE
    require_plan_approval: bool = False  # 是否强制 Plan 后人工确认再执行
    require_script_structure_approval: bool = True  # 是否确认剧本粒度结构


class StyleConfig(BaseModel):
    """视频风格与画面配置。"""

    mode: VideoStyleMode = VideoStyleMode.DYNAMIC_IMAGE
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    transition: str = "fade"
    watermark_free_images_only: bool = True
    bgm_enabled: bool = False


class MediaAssetType(str, Enum):
    """数字媒体资产类型。"""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FINAL = "final"


class MediaAsset(BaseModel):
    """图片、视频、配音、成片等数字资产。"""

    id: str = Field(default_factory=lambda: new_id("media"))
    project_id: str
    script_id: str | None = None
    type: MediaAssetType
    name: str
    url: str = ""
    source_asset_id: str | None = None
    status: AssetStatus = AssetStatus.DRAFT
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentPromptOverride(BaseModel):
    """项目级单 Agent 提示词覆盖。"""

    prompt_profile: str | None = None  # PromptProfile value
    role_prompt: str | None = None


class AgentsProjectConfig(BaseModel):
    """项目级 Agent 配置。"""

    overrides: dict[str, AgentPromptOverride] = Field(default_factory=dict)


class ProjectConfig(BaseModel):
    """项目完整配置。"""

    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    style: StyleConfig = Field(default_factory=StyleConfig)
    image_text: ImageTextConfig = Field(default_factory=ImageTextConfig)
    agents: AgentsProjectConfig = Field(default_factory=AgentsProjectConfig)


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
    primary_media_id: str | None = None  # 主展示图（图文资产）
    reuse_policy: Literal["shared", "private"] = "shared"

    @model_validator(mode="before")
    @classmethod
    def _coerce_string_content(cls, data: Any) -> Any:
        """LLM 可能返回字符串 content，统一规范为 dict。"""
        if not isinstance(data, dict):
            return data
        raw = data.get("content")
        if raw is None:
            return data
        if isinstance(raw, dict):
            return data
        from core.llm.agent.asset_content import normalize_asset_content

        asset_type = data.get("type")
        normalized = normalize_asset_content(raw, asset_type=asset_type)
        return {**data, "content": normalized}

    @field_validator("content", mode="before")
    @classmethod
    def _validate_content_dict(cls, value: Any, info: ValidationInfo) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        from core.llm.agent.asset_content import normalize_asset_content

        return normalize_asset_content(value, asset_type=info.data.get("type"))


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


class PlanDocument(BaseModel):
    """超级视频大师输出的结构化执行计划。"""

    version: int = 1
    goal: str = ""
    constraints: dict[str, Any] = Field(default_factory=dict)
    steps: list[PlanStep] = Field(default_factory=list)
    runtime_summary: str = ""  # 主编排最新 plan_status 摘要


class VideoPlanShot(BaseModel):
    """视频计划稿中的单个镜头。"""

    id: str = Field(default_factory=lambda: new_id("shot"))
    order: int = 0
    duration_ms: int = 3000
    camera_motion: str = "static"
    narration_text: str = ""
    asset_refs: dict[str, list[str]] = Field(default_factory=dict)
    variant_refs: dict[str, str] = Field(default_factory=dict)


def normalize_shot_orders(shots: list[VideoPlanShot]) -> list[VideoPlanShot]:
    """按 order 排序后重写为 0..n-1，避免 LLM 返回 1 基序号导致展示错位。"""
    ordered = sorted(shots, key=lambda s: s.order)
    return [shot.model_copy(update={"order": i}) for i, shot in enumerate(ordered)]


class VideoPlan(BaseModel):
    """分镜 Agent 输出的视频计划稿。"""

    id: str = Field(default_factory=lambda: new_id("plan"))
    script_id: str
    mode: VideoStyleMode = VideoStyleMode.DYNAMIC_IMAGE
    shots: list[VideoPlanShot] = Field(default_factory=list)


EditTrackKind = Literal["video", "audio", "subtitle"]
EditTransitionType = Literal["cut", "fade", "dissolve"]
EditBackgroundType = Literal["solid", "image", "blur"]


class EditClipTransition(BaseModel):
    """片段衔接转场。"""

    type: EditTransitionType = "cut"
    duration_ms: int = 0


class EditClipBackground(BaseModel):
    """片段背景（纯色 / 背景图 / 模糊底）。"""

    type: EditBackgroundType = "solid"
    color: str = "#0f172a"
    asset_ref: str | None = None


class EditClipMotionDetail(BaseModel):
    """Ken Burns 等运镜细粒度参数（归一化坐标 0–1）。"""

    type: str = "ken_burns_in"
    from_focal: tuple[float, float] | None = None
    to_focal: tuple[float, float] | None = None
    scale_from: float | None = None
    scale_to: float | None = None


class EditClipKeyframe(BaseModel):
    """片段内关键帧（时间相对 clip 起点）。"""

    time_ms: int = 0
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    scale: float | None = None
    opacity: float | None = None
    rotation: float | None = None


class EditClipTransform(BaseModel):
    """画布变换（归一化坐标，中心点 x/y，宽高 width/height）。"""

    x: float = 0.5
    y: float = 0.5
    width: float = 1.0
    height: float = 1.0
    opacity: float = 1.0
    rotation: float = 0.0
    keyframes: list[EditClipKeyframe] = Field(default_factory=list)


class EditClipSourceRefs(BaseModel):
    """关联的分镜 / 文字 / 媒体 ID。"""

    shot_id: str = ""
    text_asset_ids: list[str] = Field(default_factory=list)
    media_ids: list[str] = Field(default_factory=list)
    variant_ids: list[str] = Field(default_factory=list)
    video_plan_shot_order: int | None = None


class EditClip(BaseModel):
    """剪辑时间轴上的单个片段。"""

    id: str = Field(default_factory=lambda: new_id("clip"))
    track: EditTrackKind
    start_ms: int = 0
    end_ms: int = 3000
    label: str = ""
    asset_ref: str | None = None
    motion: str | None = None
    edit_description: str = ""
    transition_in: EditClipTransition | None = None
    transition_out: EditClipTransition | None = None
    background: EditClipBackground | None = None
    motion_detail: EditClipMotionDetail | None = None
    source_refs: EditClipSourceRefs | None = None
    transform: EditClipTransform | None = None
    layer_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EditVideoLayer(BaseModel):
    """视频图层（多轨叠加，z_index 越大越靠前）。"""

    id: str = Field(default_factory=lambda: new_id("vly"))
    name: str = ""
    z_index: int = 0
    clips: list[EditClip] = Field(default_factory=list)


class EditTimeline(BaseModel):
    """剪辑计划稿：多轨文字时间轴源数据。"""

    id: str = Field(default_factory=lambda: new_id("etl"))
    script_id: str
    plan_id: str = ""
    duration_ms: int = 0
    tracks: dict[str, list[EditClip]] = Field(
        default_factory=lambda: {"video": [], "audio": [], "subtitle": []}
    )
    video_layers: list[EditVideoLayer] = Field(default_factory=list)
    revision: int = 0
    user_edited: bool = False
    last_edited_by: Literal["user", "agent", ""] = ""
    updated_at: str = ""
