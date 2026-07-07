/**
 * 前后端共享的类型定义：A2UI、WebSocket 事件、资产与计划步骤。
 */

/** A2UI 表单单个组件描述 */
export interface A2UIComponent {
  id: string;
  component: "text" | "markdown" | "select" | "checkbox" | "cost_summary";
  label: string;
  value?: unknown;
  options?: { label: string; value: string }[];
  required?: boolean;
}

/** 服务端推送的 A2UI 确认请求 */
export interface A2UIConfirmationRequest {
  type: "a2ui_confirmation_required";
  confirmation_id: string;
  kind: string;
  title: string;
  description?: string;
  components: A2UIComponent[];
  estimated_cost_usd?: number;
  expires_in_sec?: number;
  step_id?: string;
}

/** WebSocket 事件（通用字典） */
export type WsEvent = Record<string, unknown>;

/** 生图进度 WebSocket 事件 */
export interface ImageGenProgressEvent {
  type: "image_gen_progress";
  script_id: string;
  step_id: string;
  total: number;
  index: number;
  source_text_asset_id: string;
  name: string;
  status: "started" | "completed" | "failed";
  url?: string;
  error?: string;
}

/** Plan 步骤产出 */
export interface StepOutput {
  kind: string;
  label: string;
  asset_id: string;
  url?: string;
}

/** Plan 执行步骤 */
export interface PlanStep {
  id: string;
  type: string;
  title: string;
  description?: string;
  agent?: string;
  status: string;
  progress?: number;
  error?: string;
  outputs?: StepOutput[];
}

/** 主编排 PlanDocument（与 API / WS 对齐） */
export interface PlanDocument {
  version: number;
  goal: string;
  constraints?: Record<string, unknown>;
  steps: PlanStep[];
  runtime_summary?: string;
}

/** 前端 Plan 视图（含 Plan 模式运行时字段） */
export interface PlanViewState extends PlanDocument {
  plan_status_history: string[];
  last_remaining_plan: string[];
}

/** 分镜镜头 */
export interface VideoPlanShot {
  id: string;
  order: number;
  duration_ms: number;
  camera_motion: string;
  narration_text: string;
}

/** 视频计划稿 */
export interface VideoPlan {
  id: string;
  script_id: string;
  mode: string;
  shots: VideoPlanShot[];
}

/** 剧本详情 */
export interface ScriptDetail {
  id: string;
  title: string;
  status: string;
  content_md: string;
  style_mode?: string;
  style_locked?: boolean;
  duration_sec?: number;
}

/** 图文资产 content 结构化字段 */
export interface ImageTextAssetContent {
  summary?: string;
  description?: string;
  visual_style?: string;
  color_palette?: string;
  tags?: string[];
  prompt_hint?: string;
  display_mode?: "static_image" | "dynamic_image";
  notes?: string;
  [key: string]: unknown;
}

/** 文字资产 */
export interface TextAsset {
  id: string;
  name: string;
  type: string;
  scope: string;
  content: ImageTextAssetContent | Record<string, unknown>;
  primary_media_id?: string | null;
  reuse_policy?: string;
  status?: string;
  source_script_id?: string | null;
}

/** 图文资产视图（看板 item） */
export interface ImageTextAsset {
  id: string;
  type: "character" | "prop" | "scene";
  name: string;
  summary?: string;
  description?: string;
  visual_style?: string;
  tags?: string[];
  display_mode?: string;
  traits?: Record<string, string>;
  content?: ImageTextAssetContent;
  images?: { id: string; url: string; name: string; type: string }[];
  primary_media_id?: string | null;
  status?: string;
  scope?: string;
}

/** LLM 服务商选项 */
export interface LLMProviderOption {
  id: string;
  label: string;
  default_model: string;
}

/** 图文/漫画模式图片策略 */
export type ImageSourceMode = "generate" | "search" | "user_choice";

export interface ImageTextConfig {
  source_mode: ImageSourceMode;
  image_text_preset: "explainer" | "report" | "lecture";
  comic_preset: "manga" | "webtoon" | "ink";
  batch_pending_assets: boolean;
  allow_search_fallback: boolean;
}

/** LLM 分区配置 */
export interface LlmConfigSection {
  provider: string;
  provider_label: string;
  model: string;
  base_url: string;
  temperature: number;
  max_tokens: number;
  use_llm_react: boolean;
  /** 工作台 ReAct：true=完整思考/观察；false=仅工具名称 */
  show_react_details: boolean;
  has_api_key: boolean;
  llm_active: boolean;
  available_providers: LLMProviderOption[];
}

/** 图片生图 API 配置 */
export interface ImageGenConfigSection {
  enabled: boolean;
  provider: string;
  provider_label: string;
  model: string;
  base_url: string;
  default_size: string;
  available_sizes: string[];
  timeout_sec: number;
  has_api_key: boolean;
  active: boolean;
}

/** 图片流水线策略（图文/漫画） */
export interface ImagePipelineConfig {
  source_mode: ImageSourceMode;
  image_text_preset: "explainer" | "report" | "lecture";
  comic_preset: "manga" | "webtoon" | "ink";
  batch_pending_assets: boolean;
  allow_search_fallback: boolean;
}

export interface ImageConfigSection extends ImageGenConfigSection {
  pipeline: ImagePipelineConfig;
}

export interface VideoConfigSection {
  enabled: boolean;
  provider: string;
  model: string;
  base_url: string;
  max_duration_sec: number;
  resolution: string;
  timeout_sec: number;
  has_api_key: boolean;
  active: boolean;
}

export interface TtsConfigSection {
  enabled: boolean;
  provider: string;
  model: string;
  base_url: string;
  default_language: string;
  default_voice: string;
  voice_rate: number;
  voice_volume: number;
  sample_rate: number;
  timeout_sec: number;
  edge_tts_timeout_sec: number;
  max_concurrency: number;
  ffmpeg_path: string;
  mimo_base_url: string;
  mimo_tts_model: string;
  mimo_style_prompt: string;
  azure_speech_region: string;
  has_api_key: boolean;
  has_gemini_api_key: boolean;
  has_mimo_api_key: boolean;
  has_siliconflow_api_key: boolean;
  has_azure_speech_key: boolean;
  active: boolean;
}

/** 剪辑 FFmpeg 导出配置 */
export interface ExportConfigSection {
  enabled: boolean;
  export_enabled: boolean;
  ffmpeg_path: string;
  ffmpeg_available: boolean;
  ffmpeg_bundled: boolean;
  fps: number;
  width: number;
  height: number;
  crf: number;
  active: boolean;
}

export interface AiConfig {
  llm: LlmConfigSection;
  image: ImageConfigSection;
  video: VideoConfigSection;
  tts: TtsConfigSection;
  export: ExportConfigSection;
}

export type AiConfigTab = "llm" | "image" | "video" | "tts" | "export";

/** PATCH /api/ai/config 请求体 */
export interface AiConfigPatch {
  llm?: Partial<{
    provider: string;
    model: string;
    api_key: string;
    base_url: string;
    use_llm_react: boolean;
    show_react_details: boolean;
    temperature: number;
    max_tokens: number;
  }>;
  image?: Partial<{
    enabled: boolean;
    provider: string;
    model: string;
    api_key: string;
    base_url: string;
    default_size: string;
    timeout_sec: number;
    pipeline: Partial<ImagePipelineConfig>;
  }>;
  video?: Partial<{
    enabled: boolean;
    provider: string;
    model: string;
    api_key: string;
    base_url: string;
    max_duration_sec: number;
    resolution: string;
    timeout_sec: number;
  }>;
  tts?: Partial<{
    enabled: boolean;
    provider: string;
    model: string;
    api_key: string;
    base_url: string;
    default_language: string;
    default_voice: string;
    voice_rate: number;
    voice_volume: number;
    sample_rate: number;
    timeout_sec: number;
    edge_tts_timeout_sec: number;
    max_concurrency: number;
    ffmpeg_path: string;
    gemini_api_key: string;
    mimo_api_key: string;
    mimo_base_url: string;
    mimo_tts_model: string;
    mimo_style_prompt: string;
    siliconflow_api_key: string;
    azure_speech_key: string;
    azure_speech_region: string;
  }>;
  export?: Partial<{
    enabled: boolean;
    ffmpeg_path: string;
    fps: number;
    width: number;
    height: number;
    crf: number;
  }>;
}

/** @deprecated 兼容旧类型别名 */
export type LLMConfig = LlmConfigSection & { image_text_defaults?: ImagePipelineConfig };

/** @deprecated 兼容旧 PATCH */
export type LLMConfigPatch = AiConfigPatch["llm"] &
  Partial<{
    image_source_default: ImageSourceMode;
    image_text_preset: ImagePipelineConfig["image_text_preset"];
    comic_preset: ImagePipelineConfig["comic_preset"];
    image_batch_pending_assets: boolean;
    image_allow_search_fallback: boolean;
  }>;
