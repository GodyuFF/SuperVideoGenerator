/**
 * 分镜子镜「剪辑轴」摘要：仅基于真正的 EditTimeline，非子镜 video_tracks 短片。
 */

import type { EditTimelineData, TrackClip, TrackKind } from "../edit/types";

/** 迷你轨条上的单个 clip。 */
export interface EditTimelineStripClip {
  id: string;
  startMs: number;
  endMs: number;
  label: string;
}

/** 全片剪辑轴迷你摘要（供子镜卡片展示）。 */
export interface EditTimelineStripSummary {
  durationMs: number;
  tracks: Record<TrackKind, EditTimelineStripClip[]>;
}

const TRACK_KEYS: TrackKind[] = ["video", "audio", "subtitle"];

/** 是否应在分镜子镜中展示「剪辑轴」区块（须已有 EditTimeline）。 */
export function shouldShowShotEditTimelineSection(hasEditTimeline: boolean): boolean {
  return Boolean(hasEditTimeline);
}

/** 将 API EditTimeline 转为卡片迷你轨条摘要；无有效时长则返回 null。 */
export function buildEditTimelineStripSummary(
  timeline: EditTimelineData | null | undefined,
): EditTimelineStripSummary | null {
  if (!timeline) return null;
  const durationMs = Math.max(0, Number(timeline.duration_ms ?? 0));
  if (durationMs <= 0) return null;

  const tracks = {} as Record<TrackKind, EditTimelineStripClip[]>;
  for (const key of TRACK_KEYS) {
    const raw = (timeline.tracks?.[key] ?? []) as TrackClip[];
    tracks[key] = raw.map((clip, idx) => {
      const startMs = Math.max(0, Number(clip.start_ms ?? 0));
      const endMs = Math.max(startMs, Number(clip.end_ms ?? startMs + 1));
      return {
        id: String(clip.id ?? `${key}-${idx}-${startMs}`),
        startMs,
        endMs,
        label: String(clip.label ?? "").trim(),
      };
    });
  }
  return { durationMs, tracks };
}
