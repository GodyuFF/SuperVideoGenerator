/**
 * 分镜看板共享：时间格式化、镜头字段解析与详情模型。
 */

import type { BoardView } from "../../types/board";
import {
  resolveShotDisplayDuration,
  type ShotDurationResolveInput,
  type ShotDurationSource,
} from "../../utils/shotSegmentUtils";
import { resolveNarrationText } from "../../utils/shotTrackUtils";

/** 字幕时间行。 */
export interface StoryboardSubtitleLine {
  start_ms?: number;
  end_ms?: number;
  absolute_start_ms?: number;
  absolute_end_ms?: number;
  text?: string;
  character?: string;
  color?: string;
}

/** 分镜单镜视图模型（表格/卡片/抽屉共用）。 */
export interface StoryboardShotView {
  id: string;
  order: number;
  /** 用户可见镜号（1 起，按排序后位置，与 order 字段解耦）。 */
  displayNumber: number;
  start_ms: number;
  end_ms: number;
  time_label: string;
  timeline_source: string;
  timeline_source_label: string;
  duration_ms: number;
  /** 按剪辑 > 视频 > 配音 > 计划 优先级解析的展示时长（毫秒）。 */
  display_duration_ms: number;
  /** 展示时长来源。 */
  display_duration_source: ShotDurationSource;
  /** TTS 实测时长（毫秒）；优先 tts_duration_ms，否则 actual_duration_ms。 */
  tts_duration_ms?: number;
  actual_duration_ms: number;
  duration_drift: boolean;
  display_instructions: string;
  need_regen: boolean;
  narration_text: string;
  subtitle_lines: StoryboardSubtitleLine[];
  character_names: string[];
  frame_preview_url: string;
  frame_asset_name: string;
  /** 无 frame 图片时的兼容预览 URL（通常为视频）。 */
  preview_fallback_url: string;
  /** 兼容预览来源：video。 */
  preview_fallback_kind: string;
  camera_motion_label: string;
  camera_motion_canonical: string;
  tts_audio_url: string;
  /** 有 TTS 与旁白但缺字幕行，需 sync-from-tts。 */
  missing_subtitle_sync: boolean;
  pending_detail: boolean;
  /** 看板派生元素引用（来自镜内 visuals.element_refs）。 */
  asset_refs?: Record<string, string[]>;
}

/** 镜头详情抽屉数据（由 StoryboardShotView 派生）。 */
export interface ShotDetailItem {
  id: string;
  order?: number;
  /** 用户可见镜号（1 起）。 */
  displayNumber?: number;
  start_ms?: number;
  end_ms?: number;
  time_label?: string;
  timeline_source_label?: string;
  duration_ms?: number;
  display_duration_ms?: number;
  display_duration_source?: ShotDurationSource;
  tts_duration_ms?: number;
  actual_duration_ms?: number;
  duration_drift?: boolean;
  narration_text?: string;
  character_names?: string[];
  subtitle_lines?: StoryboardSubtitleLine[];
  display_instructions?: string;
  need_regen?: boolean;
  pending_detail?: boolean;
  missing_subtitle_sync?: boolean;
  asset_refs?: Record<string, string[]>;
  frame_preview_url?: string;
  frame_asset_name?: string;
  preview_fallback_url?: string;
  preview_fallback_kind?: string;
  camera_motion_label?: string;
  camera_motion_canonical?: string;
  tts_audio_url?: string;
}

export type StoryboardViewMode = "filmstrip" | "table";

export const STORYBOARD_VIEW_STORAGE_KEY = "svg.storyboard.view";

/** 将毫秒格式化为 m:ss.s（与后端 time_label 一致）。 */
export function formatMs(ms: number): string {
  const totalSec = Math.max(0, ms) / 1000;
  const minutes = Math.floor(totalSec / 60);
  const seconds = totalSec % 60;
  const secStr = seconds.toFixed(1);
  const paddedSec = secStr.length >= 4 ? secStr : secStr.padStart(4, "0");
  return `${minutes}:${paddedSec}`;
}

/** 格式化镜级展示时长行（含来源标签）。 */
export function formatShotDurationDisplay(
  shot: Pick<StoryboardShotView, "display_duration_ms" | "display_duration_source">,
  t: (key: string, params?: Record<string, unknown>) => string,
): string {
  return t("storyboard.durationDisplayShort", {
    sec: (shot.display_duration_ms / 1000).toFixed(1),
    source: t(`storyboard.durationSource.${shot.display_duration_source}`),
  });
}

/** 格式化总时长为 m:ss。 */
export function formatTotalDurationMs(ms: number): string {
  const totalSec = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(totalSec / 60);
  const seconds = totalSec % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/** 从看板原始 item 解析单镜视图。 */
export function parseStoryboardShot(
  raw: Record<string, unknown>,
  index: number,
  timelineLabels: { edit: string; plan: string },
): StoryboardShotView {
  const startMs = Number(raw.start_ms ?? 0);
  const endMs = Number(raw.end_ms ?? startMs + Number(raw.duration_ms ?? 0));
  const timeLabel =
    typeof raw.time_label === "string" && raw.time_label
      ? raw.time_label
      : `${formatMs(startMs)} – ${formatMs(endMs)}`;
  const timelineSource = String(raw.timeline_source ?? "");
  const timelineSourceLabel =
    timelineSource === "edit_timeline"
      ? timelineLabels.edit
      : timelineSource === "plan_estimate"
        ? timelineLabels.plan
        : "";
  const durationMs = Number(raw.duration_ms ?? 0);
  const cachedActualMs = Number(raw.actual_duration_ms ?? 0);
  const ttsDurationMs = Number(raw.tts_duration_ms ?? 0) || cachedActualMs;
  const actualDurationMs = ttsDurationMs;
  const displayResolved =
    typeof raw.display_duration_ms === "number" && raw.display_duration_source
      ? {
          durationMs: Number(raw.display_duration_ms),
          source: String(raw.display_duration_source) as ShotDurationSource,
        }
      : (() => {
          const resolved = resolveShotDisplayDuration({
            duration_ms: durationMs,
            video_tracks: raw.video_tracks as ShotDurationResolveInput["video_tracks"],
            audio_tracks: raw.audio_tracks as ShotDurationResolveInput["audio_tracks"],
            sub_shots: raw.sub_shots as ShotDurationResolveInput["sub_shots"],
            tts_duration_ms: ttsDurationMs,
          });
          return { durationMs: resolved.durationMs, source: resolved.source };
        })();
  const displayDurationMs = displayResolved.durationMs;
  const displayDurationSource = displayResolved.source;
  const durationDrift =
    displayDurationSource !== "plan" &&
    displayDurationMs > 0 &&
    Math.abs(displayDurationMs - durationMs) > 200;
  const displayInstructions = String(
    raw.review_note ?? raw.display_instructions ?? "",
  ).trim();
  const needRegen = Boolean(raw.need_regen);
  const narration = resolveNarrationText(raw);
  const subtitleLines = Array.isArray(raw.subtitle_lines)
    ? (raw.subtitle_lines as Array<Record<string, unknown>>).map((line) => ({
        start_ms: Number(line.start_ms ?? 0),
        end_ms: Number(line.end_ms ?? 0),
        absolute_start_ms: Number(line.absolute_start_ms ?? line.start_ms ?? 0),
        absolute_end_ms: Number(line.absolute_end_ms ?? line.end_ms ?? 0),
        text: String(line.text ?? "").trim(),
        character: String(line.character ?? "").trim(),
        color: String(line.color ?? "").trim(),
      }))
    : [];
  const charNames = Array.isArray(raw.character_names)
    ? (raw.character_names as string[]).filter(Boolean)
    : [];
  const frameUrl = raw.frame_preview_url ? String(raw.frame_preview_url) : "";
  const frameName = raw.frame_asset_name ? String(raw.frame_asset_name) : "";
  const previewFallbackUrl = raw.preview_fallback_url
    ? String(raw.preview_fallback_url)
    : "";
  const previewFallbackKind = raw.preview_fallback_kind
    ? String(raw.preview_fallback_kind)
    : "";
  const camera = String(raw.camera_motion ?? "static");
  const cameraLabel =
    typeof raw.camera_motion_label === "string" && raw.camera_motion_label
      ? raw.camera_motion_label
      : camera;
  const cameraCanonical =
    typeof raw.camera_motion_canonical === "string"
      ? raw.camera_motion_canonical
      : camera;
  const ttsUrl = raw.tts_audio_url ? String(raw.tts_audio_url) : "";
  const missingSubtitleSync = Boolean(ttsUrl && subtitleLines.length === 0 && narration);

  return {
    id: String(raw.id),
    order: Number(raw.order ?? index),
    displayNumber: index + 1,
    start_ms: startMs,
    end_ms: endMs,
    time_label: timeLabel,
    timeline_source: timelineSource,
    timeline_source_label: timelineSourceLabel,
    duration_ms: durationMs,
    display_duration_ms: displayDurationMs,
    display_duration_source: displayDurationSource,
    tts_duration_ms: ttsDurationMs,
    actual_duration_ms: actualDurationMs,
    duration_drift: durationDrift,
    display_instructions: displayInstructions,
    need_regen: needRegen,
    narration_text: narration,
    subtitle_lines: subtitleLines.filter((l) => l.text),
    character_names: charNames,
    frame_preview_url: frameUrl,
    frame_asset_name: frameName,
    preview_fallback_url: previewFallbackUrl,
    preview_fallback_kind: previewFallbackKind,
    camera_motion_label: cameraLabel,
    camera_motion_canonical: cameraCanonical,
    tts_audio_url: ttsUrl,
    missing_subtitle_sync: missingSubtitleSync,
    pending_detail: !displayInstructions,
    asset_refs: (raw.asset_refs as Record<string, string[]>) ?? undefined,
  };
}

/** 从看板数据解析并排序镜头列表。 */
export function parseStoryboardShots(
  board: BoardView,
  timelineLabels: { edit: string; plan: string },
): StoryboardShotView[] {
  const items = [...(board.items ?? [])].sort(
    (a, b) =>
      Number((a as Record<string, unknown>).order ?? 0) -
      Number((b as Record<string, unknown>).order ?? 0),
  );
  return items.map((raw, index) =>
    parseStoryboardShot(raw as Record<string, unknown>, index, timelineLabels),
  );
}

/** 将镜头视图转为详情抽屉项。 */
export function buildShotDetailItem(shot: StoryboardShotView): ShotDetailItem {
  return {
    id: shot.id,
    order: shot.order,
    displayNumber: shot.displayNumber,
    start_ms: shot.start_ms,
    end_ms: shot.end_ms,
    time_label: shot.time_label,
    timeline_source_label: shot.timeline_source_label,
    duration_ms: shot.duration_ms,
    display_duration_ms: shot.display_duration_ms,
    display_duration_source: shot.display_duration_source,
    tts_duration_ms: shot.tts_duration_ms,
    actual_duration_ms: shot.actual_duration_ms,
    duration_drift: shot.duration_drift,
    narration_text: shot.narration_text || undefined,
    character_names: shot.character_names.length > 0 ? shot.character_names : undefined,
    subtitle_lines: shot.subtitle_lines.length > 0 ? shot.subtitle_lines : undefined,
    display_instructions: shot.display_instructions || undefined,
    need_regen: shot.need_regen,
    pending_detail: shot.pending_detail,
    missing_subtitle_sync: shot.missing_subtitle_sync,
    asset_refs: shot.asset_refs,
    frame_preview_url: shot.frame_preview_url || undefined,
    frame_asset_name: shot.frame_asset_name || undefined,
    preview_fallback_url: shot.preview_fallback_url || undefined,
    preview_fallback_kind: shot.preview_fallback_kind || undefined,
    camera_motion_label: shot.camera_motion_label,
    camera_motion_canonical: shot.camera_motion_canonical,
    tts_audio_url: shot.tts_audio_url || undefined,
  };
}

/** 读取持久化的分镜视图模式。 */
export function loadStoryboardViewMode(): StoryboardViewMode {
  try {
    const v = localStorage.getItem(STORYBOARD_VIEW_STORAGE_KEY);
    if (v === "table" || v === "filmstrip") return v;
  } catch {
    /* ignore */
  }
  return "filmstrip";
}

/** 持久化分镜视图模式。 */
export function saveStoryboardViewMode(mode: StoryboardViewMode): void {
  try {
    localStorage.setItem(STORYBOARD_VIEW_STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}
