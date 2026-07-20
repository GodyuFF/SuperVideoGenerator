/** VideoPlan 与镜内多轨 Shot 类型（对齐后端 core.models.entities.Shot）。 */

/** 子镜关联的单张画面图片。 */
export interface ShotSubShotImage {
  id?: string;
  kind?: "static" | "video";
  frame_asset_id?: string;
  media_id?: string;
  source_media_ids?: string[];
  video_prompt?: string;
  /** 相对镜起点；与所属子镜同坐标系；未设置时可视为 (0,0)。 */
  start_ms?: number;
  end_ms?: number;
}

/** 子镜关联的单段视频。 */
export interface ShotSubShotVideo {
  id?: string;
  media_id?: string;
  start_ms?: number;
  end_ms?: number;
  source_kind?: "video" | "still";
  camera_motion?: string;
  source_frame_asset_id?: string;
  /** 关联的 video_clip 文字资产 ID。 */
  video_clip_asset_id?: string;
}

/** 镜内子镜（剧本时间轴时段单元）。 */
export interface ShotSubShot {
  id?: string;
  start_ms?: number;
  end_ms?: number;
  description?: string;
  camera_motion?: string;
  element_refs?: Record<string, string[]>;
  images?: ShotSubShotImage[];
  videos?: ShotSubShotVideo[];
  /** 产出意图：静帧剪辑 / AI 生视频 / 混合。 */
  produce_mode?: "still" | "text2video" | "img2video" | "still_edit" | "ai_video" | "hybrid";
  /** Agent 或用户填写的意图简要说明。 */
  produce_rationale?: string;
  /** @deprecated 兼容旧 payload，解析时并入 images[0] */
  image?: ShotSubShotImage | null;
}

/** 镜内视频 clip。 */
export interface ShotVideoClip {
  id?: string;
  start_ms?: number;
  end_ms?: number;
  media_id?: string;
  source_sub_shot_id?: string;
  source_kind?: string;
  camera_motion?: string;
}

/** 镜内视频轨。 */
export interface ShotVideoTrack {
  id?: string;
  name?: string;
  z_index?: number;
  clips?: ShotVideoClip[];
}

/** 镜内音频 clip。 */
export interface ShotAudioClip {
  id?: string;
  start_ms?: number;
  end_ms?: number;
  media_id?: string;
  text?: string;
  character_ref?: string;
  voice?: string;
  volume?: number;
}

/** 镜内音频轨。 */
export interface ShotAudioTrack {
  id?: string;
  kind?: "voice" | "background";
  name?: string;
  clips?: ShotAudioClip[];
}

/** 镜内字幕。 */
export interface ShotSubtitle {
  id?: string;
  start_ms?: number;
  end_ms?: number;
  text?: string;
  /** 角色名或 txt_*；空表示旁白/未指定。 */
  character?: string;
  /** 剪辑用颜色（如 #RRGGBB）；空表示沿用默认样式。 */
  color?: string;
}

/** 音画协调单条策略（与后端 SyncAction 对齐）。 */
export interface AvSyncAction {
  kind: string;
  params?: Record<string, unknown>;
  quality_score?: number;
  auto_eligible?: boolean;
  label?: string;
  description?: string;
}

/** 视频计划稿单镜（镜内多轨权威结构）。 */
export interface VideoPlanShot {
  id: string;
  order?: number;
  duration_ms?: number;
  title?: string;
  summary?: string;
  sub_shots?: ShotSubShot[];
  video_tracks?: ShotVideoTrack[];
  audio_tracks?: ShotAudioTrack[];
  subtitles?: ShotSubtitle[];
  review_note?: string;
  review_revision?: number;
  need_regen?: boolean;
  regen_reason?: string;
  /** 音画主轨策略。 */
  sync_policy?: "narration_master" | "visual_master" | "balanced";
  lip_sync_required?: boolean;
  sync_notes?: string;
  /** Tier2 可选协调方案。 */
  proposed_sync_actions?: AvSyncAction[];
  plan_note?: string;
  /** 看板派生运镜（非持久化根字段） */
  camera_motion?: string;
}

/** GET/PATCH video-plan 响应。 */
export interface VideoPlanData {
  id?: string;
  script_id?: string;
  shots?: VideoPlanShot[];
  detail_revision?: number;
  editable?: boolean;
  shot_timings?: Record<string, unknown>[];
  side_effects?: VideoPlanSideEffects;
}

/** 写操作副作用摘要。 */
export interface VideoPlanSideEffects {
  tts_stale?: boolean;
  tts_stale_shot_ids?: string[];
  timeline_realigned?: boolean;
}

/** 单镜 patch 请求体。 */
export interface PatchVideoPlanShotBody {
  title?: string;
  summary?: string;
  duration_ms?: number;
  review_note?: string;
  camera_motion_refined?: string;
  need_regen?: boolean;
  regen_reason?: string;
  sync_policy?: "narration_master" | "visual_master" | "balanced";
  lip_sync_required?: boolean;
  sync_notes?: string;
  proposed_sync_actions?: AvSyncAction[];
  sub_shots?: ShotSubShot[];
  video_tracks?: ShotVideoTrack[];
  audio_tracks?: ShotAudioTrack[];
  subtitles?: ShotSubtitle[];
}

/** 结构 op 请求体。 */
export interface VideoPlanOp {
  op: string;
  shot_id?: string;
  shot_ids?: string[];
  ordered_shot_ids?: string[];
  after_order?: number;
  new_shot?: Record<string, unknown>;
  new_shots?: Record<string, unknown>[];
  merged_shot?: Record<string, unknown>;
  regen_reason?: string;
  [key: string]: unknown;
}
