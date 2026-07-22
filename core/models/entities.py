"""领域实体与枚举定义：项目、剧本、资产、计划稿等核心数据结构。"""

from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


def new_id(prefix: str) -> str:
    """生成带类型前缀的唯一 ID，例如 proj_abc123。"""
    return f"{prefix}_{uuid4().hex[:12]}"


class GenerationMode(str, Enum):
    """视频生成模式。"""

    AUTO = "auto"


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
    active_skill_id: str = ""


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
    FRAME = "frame"  # 画面（分镜合成图）
    VIDEO_CLIP = "video_clip"  # 视频片段（生视频描述 + 生成 mp4）
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

    STORYBOOK = "storybook"  # 故事书：按画面资产逐镜配图，图片+运镜+配音
    AI_VIDEO = "ai_video"  # AI 视频：调用视频生成 API
    FRAME_I2V = "frame_i2v"  # 画面图生视频：实体+frame 合成后以 frame 为唯一图生源 I2V

    @classmethod
    def _missing_(cls, value: object) -> "VideoStyleMode | None":
        """历史持久化数据迁移：已下线风格 id → storybook。"""
        if value in ("dynamic_image", "dynamic_comic", "marketing_video", "marketing"):
            return cls.STORYBOOK
        return None


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

    mode: str = VideoStyleMode.STORYBOOK.value
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


class RagConfig(BaseModel):
    """项目级 RAG 共享资产复用配置。"""

    enabled: bool = True
    top_k: int = 10
    similarity_threshold: float = 0.75
    reuse_aggression: Literal["conservative", "balanced", "aggressive"] = "balanced"
    auto_fork_on_conflict: bool = True
    index_types: list[Literal["character", "prop", "scene"]] = Field(
        default_factory=lambda: ["character", "prop", "scene"]
    )


class ProjectConfig(BaseModel):
    """项目完整配置。"""

    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    style: StyleConfig = Field(default_factory=StyleConfig)
    image_text: ImageTextConfig = Field(default_factory=ImageTextConfig)
    agents: AgentsProjectConfig = Field(default_factory=AgentsProjectConfig)
    rag: RagConfig = Field(default_factory=RagConfig)


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
    # 创建时间（ISO UTC）；整体看板按此升序编号展示
    created_at: str = ""
    # 视频风格在生成剧本时绑定，锁定后全链路不可修改
    style_mode: str | None = None
    style_locked: bool = False
    # 可选通用提示词（如 image_style / target_duration），随风格一并锁定；未选择则为空
    style_hints: dict[str, str] = Field(default_factory=dict)


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
    embedding_id: str | None = None  # RAG 向量索引行 ID（默认同 asset_id）

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
    last_replan_reason: str = ""  # 最近一次 replan 原因
    affected_step_ids: list[str] = Field(default_factory=list)  # 最近 replan 受影响步骤


class SubtitleSegment(BaseModel):
    """句级字幕片段（相对起点毫秒）。"""

    text: str = ""
    start_ms: int = 0
    end_ms: int = 0


def normalize_shot_orders(shots: "list[Shot]") -> "list[Shot]":
    """按 order 字段排序镜头列表。"""
    return sorted(shots, key=lambda s: s.order)


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
        default_factory=lambda: {"audio": [], "subtitle": []}
    )
    video_layers: list[EditVideoLayer] = Field(default_factory=list)
    revision: int = 0
    user_edited: bool = False
    # 记录最近写入方：user / agent / system_tts_sync 等；宽松为 str 以兼容系统同步来源
    last_edited_by: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 分镜镜内多轨结构（Shot 镜内小时间轴）
#
# 设计目标：分镜是「剪辑可控」的权威源——每个分镜本身就是一段镜内多轨
# 小时间轴，含多个「子镜」+ 多条视频轨 + 多条音频轨（背景音/角色音）+ 字幕。
# 该结构可确定性投影为 EditTimeline（供 OpenCut/FFmpeg/NLE 消费），OpenCut 手改
# 亦可无损回写。字段设计以能干净映射 OpenCut TProject/track/element 为先决约束。
# 单镜时长由配音/素材实测驱动，不做硬上限强约束（AI 生视频 API 另有自身时长限制）。
# ---------------------------------------------------------------------------

ShotSubShotImageKind = Literal["static", "video"]
ShotVideoSourceKind = Literal["video", "still"]
ShotAudioKind = Literal["voice", "background"]
ProduceMode = Literal["still", "text2video", "img2video"]
# 音画主轨策略：旁白驱动画面 / 画面驱动配音 / 双向微调
ShotSyncPolicy = Literal["narration_master", "visual_master", "balanced"]


class ShotSubShotImage(BaseModel):
    """子镜关联的单张画面图片（可多张）。

    kind=static 表示静态图；kind=video 表示图生/文生视频意图。
    frame_asset_id 可选关联剧本 Tab「画面」文字资产，非 1:1 绑定。
    start_ms/end_ms 为相对镜起点的占用时段；0+0 表示未显式设置，由回填逻辑继承子镜区间。
    """

    id: str = Field(default_factory=lambda: new_id("ssi"))
    kind: ShotSubShotImageKind = "static"
    frame_asset_id: str = ""
    source_media_ids: list[str] = Field(default_factory=list)
    media_id: str = ""
    video_prompt: str = ""
    prompt_locked: bool = False
    start_ms: int = 0  # 相对镜起点；0+0 表示未显式设置
    end_ms: int = 0


class ShotSubShotVideo(BaseModel):
    """子镜关联的单段视频（可多个，相对子镜起点计时）。"""

    id: str = Field(default_factory=lambda: new_id("ssv"))
    media_id: str = ""
    start_ms: int = 0
    end_ms: int = 0
    source_kind: ShotVideoSourceKind = "video"
    camera_motion: str = "static"
    source_frame_asset_id: str = ""
    video_clip_asset_id: str = ""


class ShotSubShot(BaseModel):
    """子镜：镜内剧本时间轴上的一个时段单元。

    与剧本 Tab「画面」(frame) 解耦；可关联多张图片与多段视频。
    element_refs 与 FrameContent.element_refs 语义一致。
    videos[].video_clip_asset_id 可指向 type=video_clip 的文字资产。
    produce_mode 声明产出意图（静图视频 / 文生视频 / 图生视频），produce_rationale 为可选短理由。
    """

    id: str = Field(default_factory=lambda: new_id("ssb"))
    start_ms: int = 0
    end_ms: int = 0
    description: str = ""
    element_refs: dict[str, list[str]] = Field(default_factory=dict)
    camera_motion: str = "static"
    images: list[ShotSubShotImage] = Field(default_factory=list)
    videos: list[ShotSubShotVideo] = Field(default_factory=list)
    produce_mode: ProduceMode = "still"
    produce_rationale: str = ""

    @field_validator("produce_mode", mode="before")
    @classmethod
    def _coerce_produce_mode(cls, value: Any) -> str:
        """将仍帧剪辑/AI生视频等历史枚举规范为三值产出意图。"""
        mode = str(value or "").strip()
        legacy = {
            "still_edit": "still",
            "ai_video": "img2video",
            "hybrid": "img2video",
            "keyframes": "img2video",
        }
        if mode in legacy:
            return legacy[mode]
        if mode in {"still", "text2video", "img2video"}:
            return mode
        return "still"


class ShotVideoClip(BaseModel):
    """视频轨片段：镜内某段时间的实际画面内容（可剪辑标准视频 clip）。

    所有画面最终都落成 ShotVideoClip；source_kind=still 表示底层素材为静态图，
    但仍带时长/变换/关键帧，剪辑能力与 video 一致，无「纯图片轨」降级形态。
    """

    id: str = Field(default_factory=lambda: new_id("svc"))
    start_ms: int = 0  # 相对镜起点毫秒
    end_ms: int = 0
    source_sub_shot_id: str = ""  # 来源子镜 id
    media_id: str = ""  # 已生成的视频/图片 media id
    source_kind: ShotVideoSourceKind = "still"
    camera_motion: str = "static"
    transform: EditClipTransform | None = None
    transition_in: EditClipTransition | None = None
    transition_out: EditClipTransition | None = None
    background: EditClipBackground | None = None
    motion_detail: EditClipMotionDetail | None = None
    edit_description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ShotVideoTrack(BaseModel):
    """视频轨：镜内一条视频图层（z_index 越大越靠前，对应 OpenCut overlay 层）。"""

    id: str = Field(default_factory=lambda: new_id("svt"))
    name: str = ""
    z_index: int = 0
    clips: list[ShotVideoClip] = Field(default_factory=list)


class ShotAudioClip(BaseModel):
    """音频轨片段：镜内某段时间的角色音或背景音。"""

    id: str = Field(default_factory=lambda: new_id("sac"))
    start_ms: int = 0  # 相对镜起点毫秒
    end_ms: int = 0
    media_id: str = ""  # TTS/BGM media id
    text: str = ""  # 角色音文案（voice 轨）
    character_ref: str = ""  # 角色对白填 txt_*；留空表示旁白/画外音
    voice: str = ""  # 音色
    volume: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ShotAudioTrack(BaseModel):
    """音频轨：镜内一条音轨（背景音或角色音，可有多条）。"""

    id: str = Field(default_factory=lambda: new_id("sat"))
    name: str = ""
    kind: ShotAudioKind = "voice"
    clips: list[ShotAudioClip] = Field(default_factory=list)


class ShotSubtitle(BaseModel):
    """镜内字幕片段（相对镜起点毫秒）。"""

    id: str = Field(default_factory=lambda: new_id("ssub"))
    text: str = ""
    start_ms: int = 0
    end_ms: int = 0
    character: str = ""  # 角色名或 txt_*；空表示旁白/未指定
    color: str = ""  # 剪辑用颜色（如 #RRGGBB）；空表示沿用默认样式


class Shot(BaseModel):
    """分镜：镜内多轨小时间轴，剪辑可控的权威结构。

    时长由配音/素材实测驱动，无硬上限。sub_shots 为子镜设计层；
    video_tracks/audio_tracks/subtitles 为可剪辑轨道层。可经
    core.edit.shot_flatten 投影为 EditTimeline 供 OpenCut/FFmpeg/NLE 消费。
    """

    id: str = Field(default_factory=lambda: new_id("shot"))
    order: int = 0
    duration_ms: int = 3000
    title: str = ""
    summary: str = ""
    sub_shots: list[ShotSubShot] = Field(default_factory=list)
    video_tracks: list[ShotVideoTrack] = Field(default_factory=list)
    audio_tracks: list[ShotAudioTrack] = Field(default_factory=list)
    subtitles: list[ShotSubtitle] = Field(default_factory=list)
    # 设计态（storyboard_agent）
    plan_note: str = ""
    design_locked: bool = False
    # 复核态（storyboard_refine_agent）
    review_revision: int = 0
    review_note: str = ""
    need_regen: bool = False
    regen_reason: str = ""
    # 音画协调：主轨策略与打回说明
    sync_policy: ShotSyncPolicy = "narration_master"
    lip_sync_required: bool = False
    sync_notes: str = ""
    # Tier2 可选方案（SyncAction 字典列表，由 av_sync 写入）
    proposed_sync_actions: list[dict[str, Any]] = Field(default_factory=list)


class VideoPlan(BaseModel):
    """分镜 Agent 输出的视频计划稿：镜内多轨分镜的有序集合。"""

    id: str = Field(default_factory=lambda: new_id("plan"))
    script_id: str
    mode: VideoStyleMode = VideoStyleMode.STORYBOOK
    shots: list[Shot] = Field(default_factory=list)
    detail_revision: int = 0
