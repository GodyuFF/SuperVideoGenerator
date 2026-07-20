/**
 * 镜内多轨投影 metadata 往返（对齐 core/edit/shot_flatten.py）。
 */

import type { TrackClip } from "../../edit/types";

/** 与后端 META_* 常量对应的 clip.metadata 键。 */
export const SHOT_PROJECTION_META_KEYS = [
  "shot_offset_ms",
  "shot_sub_shot_id",
  "source_kind",
  "shot_track_id",
  "audio_kind",
  "voice",
  "character_ref",
  "volume",
  "character",
  "color",
] as const;

/** 主画面层 ID（与 compile_timeline_from_shots 的 vly_z0 一致）。 */
export const MAIN_VIDEO_LAYER_ID = "vly_z0";

/** 解析 clip.source_refs 对象。 */
export function extractClipSourceRefs(
  clip: TrackClip,
): Record<string, unknown> | undefined {
  const refs = clip.source_refs;
  if (refs && typeof refs === "object" && !Array.isArray(refs)) {
    return refs;
  }
  return undefined;
}

/** SVF clip → Classic element metadata 中的镜归属与投影字段。 */
export function clipShotMetadata(clip: TrackClip): Record<string, unknown> {
  const meta = clip.metadata ?? {};
  const refs = extractClipSourceRefs(clip);
  const out: Record<string, unknown> = {};
  const shotId =
    (typeof refs?.shot_id === "string" ? refs.shot_id : "") ||
    (typeof meta.shot_id === "string" ? meta.shot_id : "");
  if (shotId) out.shot_id = shotId;
  if (refs?.video_plan_shot_order != null) {
    out.video_plan_shot_order = refs.video_plan_shot_order;
  } else if (meta.video_plan_shot_order != null) {
    out.video_plan_shot_order = meta.video_plan_shot_order;
  }
  for (const key of SHOT_PROJECTION_META_KEYS) {
    if (meta[key] != null) out[key] = meta[key];
  }
  return out;
}

/** Classic element → SVF TrackClip 的 source_refs 与投影 metadata。 */
export function elementShotFields(el: {
  metadata?: Record<string, unknown>;
  mediaId?: string;
}): {
  source_refs?: Record<string, unknown>;
  metadata: Record<string, unknown>;
} {
  const proj = el.metadata ?? {};
  const source_refs: Record<string, unknown> = {};
  const shotId = typeof proj.shot_id === "string" ? proj.shot_id : "";
  if (shotId) source_refs.shot_id = shotId;
  if (proj.video_plan_shot_order != null) {
    source_refs.video_plan_shot_order = proj.video_plan_shot_order;
  }
  if (el.mediaId) source_refs.media_ids = [el.mediaId];

  const metadata: Record<string, unknown> = {};
  if (shotId) metadata.shot_id = shotId;
  for (const key of SHOT_PROJECTION_META_KEYS) {
    if (proj[key] != null) metadata[key] = proj[key];
  }
  if (proj.video_plan_shot_order != null) {
    metadata.video_plan_shot_order = proj.video_plan_shot_order;
  }
  return {
    source_refs: Object.keys(source_refs).length ? source_refs : undefined,
    metadata,
  };
}
