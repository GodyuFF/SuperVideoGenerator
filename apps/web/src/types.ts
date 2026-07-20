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

/** A2UI 确认提交的 WebSocket ack 结果。 */
export interface A2UIConfirmAck {
  resolved: boolean;
  reason?: "expired" | "already_resolved" | "unknown" | string;
}

/** WebSocket 事件（通用字典） */
export type WsEvent = Record<string, unknown>;

/** 生成队列单条任务（与后端 GenerationJob.to_public_dict 对齐）。 */
export interface GenerationQueueJob {
  id: string;
  kind: "image" | "video";
  asset_id: string;
  label: string;
  status: "queued" | "running" | "done" | "failed";
  error?: string | null;
  variant_id?: string | null;
  source?: string;
}

/** 生成队列快照（HTTP GET 与 WS generation_queue_snapshot）。 */
export interface GenerationQueueSnapshot {
  type: "generation_queue_snapshot";
  script_id: string;
  project_id?: string;
  active: GenerationQueueJob | null;
  queued: GenerationQueueJob[];
  recent: GenerationQueueJob[];
  counts: { queued: number; running: number };
}

/** WebSocket 推送的生成队列快照事件。 */
export type GenerationQueueSnapshotEvent = GenerationQueueSnapshot;

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

/** 单张生图任务进度（Plan 步骤内嵌）。 */
export interface ImageGenProgressItem {
  index: number;
  sourceTextAssetId: string;
  name: string;
  status: "pending" | "started" | "completed" | "failed";
  url?: string;
  error?: string;
}

/** Plan 步骤内嵌的生图进度。 */
export interface PlanStepImageGenProgress {
  total: number;
  items: ImageGenProgressItem[];
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
  /** 生图进行中时的逐张进度，步骤完成后清除。 */
  image_gen_progress?: PlanStepImageGenProgress;
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

/** 分镜镜头与视频计划稿（对齐镜内多轨 API） */
export type { VideoPlanShot, VideoPlanData as VideoPlan } from "./types/videoPlan";

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
  /** 输出 Token 上限（API max_tokens） */
  max_tokens: number;
  /** 输入 Token 上限，超限时触发历史压缩（默认 1M） */
  context_window_tokens: number;
  /** 压缩时保留最近 ReAct 轮次数 */
  history_keep_messages: number;
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
  available_providers: { id: string; label: string }[];
  model: string;
  base_url: string;
  default_size: string;
  available_sizes: string[];
  timeout_sec: number;
  has_api_key: boolean;
  active: boolean;
  // SD 相关
  sd_detected: boolean;
  sd_current_model: string;
  sd_models: string[];
  sd_error: string;
  sd_base_url: string;
  sd_steps: number;
  sd_cfg_scale: number;
  sd_sampler: string;
  sd_samplers: string[];
  sd_negative_prompt: string;
  // 百炼相关
  bailian_workspace_id: string;
  bailian_txt2img_model: string;
  bailian_img2img_model: string;
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
  provider_label?: string;
  available_providers?: { id: string; label: string }[];
  model: string;
  base_url: string;
  default_model_volcengine?: string;
  default_base_url_volcengine?: string;
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

/** RAG Embedding（共享资产复用）配置分区。 */
export interface EmbeddingConfigSection {
  enabled: boolean;
  base_url: string;
  model: string;
  has_api_key: boolean;
  active: boolean;
}

export interface AiConfig {
  llm: LlmConfigSection;
  image: ImageConfigSection;
  video: VideoConfigSection;
  tts: TtsConfigSection;
  export: ExportConfigSection;
  embedding: EmbeddingConfigSection;
}

export type AiConfigTab = "llm" | "image" | "video" | "tts" | "export" | "embedding";

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
    context_window_tokens: number;
    history_keep_messages: number;
  }>;
  image?: Partial<{
    enabled: boolean;
    provider: string;
    model: string;
    api_key: string;
    base_url: string;
    default_size: string;
    timeout_sec: number;
    sd_base_url: string;
    sd_steps: number;
    sd_cfg_scale: number;
    sd_sampler: string;
    sd_negative_prompt: string;
    bailian_workspace_id: string;
    bailian_txt2img_model: string;
    bailian_img2img_model: string;
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
  embedding?: Partial<{
    enabled: boolean;
    api_key: string;
    base_url: string;
    model: string;
  }>;
}
