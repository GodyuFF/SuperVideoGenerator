/**
 * 镜内多轨：配音幕与子镜解析、合成与 patch 构建。
 */

import type {
  PatchVideoPlanShotBody,
  ShotAudioClip,
  ShotAudioTrack,
  ShotSubtitle,
  ShotSubShot,
  ShotSubShotImage,
  ShotVideoClip,
  VideoPlanShot,
} from "../types/videoPlan";
import { resolveMediaPlayUrl } from "./mediaUrl";
import type { ShotDetailItem } from "../components/board/storyboardShared";
import {
  normalizeProduceMode,
  produceModeToVideoGenMode,
  type ProduceMode,
} from "./subShotProduce";

export type { ProduceMode } from "./subShotProduce";
export {
  produceModeNeedsFrame,
  produceModeNeedsVideo,
  produceModeToVideoGenMode,
  syncProduceModeFromVideoGenModes,
  videoGenModeToProduceModeHint,
} from "./subShotProduce";

/** 画面视频生成策略。 */
export type VisualVideoGenMode = "still" | "img2video" | "text2video" | "keyframes";

/** 后端关键帧模式标记（对齐 core.llm.tools.video.agnes_client.KEYFRAMES_MODE_MARKER）。 */
export const KEYFRAMES_VIDEO_PROMPT = "svf:keyframes";

/** 视频风格允许的 AI 生视频子模式（对齐 CustomStyleMode.video）。 */
export type StyleVideoGenMode = "text2video" | "img2video" | "keyframes";

/** 根据风格 video 配置得到分镜可选成片模式（始终含静图）。 */
export function allowedVisualVideoGenModes(
  videoModes: StyleVideoGenMode[] | null | undefined,
): VisualVideoGenMode[] {
  const out: VisualVideoGenMode[] = ["still"];
  if (!videoModes?.length) return out;
  for (const m of videoModes) {
    if (m === "text2video" || m === "img2video" || m === "keyframes") {
      if (!out.includes(m)) out.push(m);
    }
  }
  return out;
}

/** 将成片模式限制在风格允许范围内。 */
export function clampVisualVideoGenMode(
  mode: VisualVideoGenMode,
  videoModes: StyleVideoGenMode[] | null | undefined,
): VisualVideoGenMode {
  const allowed = allowedVisualVideoGenModes(videoModes);
  return allowed.includes(mode) ? mode : "still";
}

/** 配音幕视图（镜内 voice clip）。 */
export interface ShotVoiceActView {
  id: string;
  startMs: number;
  endMs: number;
  text: string;
  characterRef: string;
  voice: string;
  mediaId?: string;
  audioUrl?: string;
}

/** 镜内句级字幕视图。 */
export interface ShotSubtitleView {
  id: string;
  startMs: number;
  endMs: number;
  text: string;
  character: string;
  color: string;
}

/** 从 VideoPlanShot 解析句级字幕列表。 */
export function parseSubtitlesFromPlan(shot: VideoPlanShot): ShotSubtitleView[] {
  const duration = shot.duration_ms ?? 3000;
  return (shot.subtitles ?? [])
    .map((sub, idx) => ({
      id: sub.id ?? `ssub-${idx}`,
      startMs: Number(sub.start_ms ?? 0),
      endMs: Number(sub.end_ms ?? 0) || duration,
      text: (sub.text ?? "").trim(),
      character: (sub.character ?? "").trim(),
      color: (sub.color ?? "").trim(),
    }))
    .filter((s) => s.text)
    .sort((a, b) => a.startMs - b.startMs);
}

/** 按中英文标点拆成句（用于配音幕 → 句级字幕）。 */
export function splitTextByPunctuations(text: string): string[] {
  const punct = new Set([
    "?",
    ",",
    ".",
    "、",
    ";",
    ":",
    "!",
    "…",
    "？",
    "，",
    "。",
    "；",
    "：",
    "！",
  ]);
  const result: string[] = [];
  let buf = "";
  const s = text || "";
  for (let i = 0; i < s.length; i += 1) {
    const char = s[i];
    if (char === "\n") {
      const part = buf.trim();
      if (part) result.push(part);
      buf = "";
      continue;
    }
    const prev = i > 0 ? s[i - 1] : "";
    const next = i + 1 < s.length ? s[i + 1] : "";
    if (char === "." && /\d/.test(prev) && /\d/.test(next)) {
      buf += char;
      continue;
    }
    if (char === "," && /\d/.test(prev) && /\d/.test(next)) {
      buf += char;
      continue;
    }
    if (!punct.has(char)) {
      buf += char;
    } else {
      const part = buf.trim();
      if (part) result.push(part);
      buf = "";
    }
  }
  const last = buf.trim();
  if (last) result.push(last);
  return result;
}

/**
 * （遗留）由配音幕文案按标点拆句估时——幕文案可能与实际配音不一致。
 * 分镜编辑请用 `fetchSubtitlesFromVoiceAudio`（配音文件 cues / ASR）。
 */
export function buildSubtitlesFromVoiceActs(
  voiceActs: ShotVoiceActView[],
  durationMs: number,
): ShotSubtitleView[] {
  const withText = voiceActs.filter((a) => a.text.trim());
  if (withText.length === 0) return [];
  const lines: ShotSubtitleView[] = [];
  let idx = 0;
  for (const act of withText) {
    const raw = act.text.trim();
    const parts = splitTextByPunctuations(raw);
    const sentences = parts.length > 0 ? parts : [raw];
    const actStart = Math.max(0, act.startMs);
    const actEnd = act.endMs > actStart ? act.endMs : durationMs;
    const span = Math.max(actEnd - actStart, 1);
    const totalChars = sentences.reduce((sum, s) => sum + s.length, 0) || 1;
    let cursor = actStart;
    const character = (act.characterRef ?? "").trim();
    sentences.forEach((sentence, sentenceIdx) => {
      const isLast = sentenceIdx === sentences.length - 1;
      const end = isLast
        ? actEnd
        : Math.min(
            actEnd,
            cursor + Math.max(1, Math.round((span * sentence.length) / totalChars)),
          );
      lines.push({
        id: `ssub-voice-${idx}`,
        startMs: cursor,
        endMs: Math.max(end, cursor + 1),
        text: sentence,
        character,
        color: "",
      });
      idx += 1;
      cursor = end;
    });
  }
  return lines;
}

/** 新建空字幕行。 */
export function newSubtitleLine(durationMs: number, startMs = 0): ShotSubtitleView {
  const end = Math.min(durationMs, startMs + 2500);
  return {
    id: `ssub-${Date.now()}`,
    startMs,
    endMs: end,
    text: "",
    character: "",
    color: "",
  };
}

/** 将字幕视图写回 patch 体。 */
export function subtitlesToPatchBody(lines: ShotSubtitleView[]): ShotSubtitle[] {
  return lines
    .filter((line) => line.text.trim())
    .map((line) => ({
      id: line.id.startsWith("ssub-") ? undefined : line.id,
      start_ms: line.startMs,
      end_ms: line.endMs,
      text: line.text.trim(),
      character: (line.character ?? "").trim(),
      color: (line.color ?? "").trim(),
    }));
}

/** 校验镜内字幕时段（含互不重叠）。 */
export function validateSubtitleEdits(
  durationMs: number,
  subtitles: ShotSubtitleView[],
): string | null {
  const active = subtitles
    .filter((line) => line.text.trim())
    .slice()
    .sort((a, b) => a.startMs - b.startMs || a.endMs - b.endMs);
  let prevEnd = -1;
  for (const line of active) {
    if (line.endMs <= line.startMs) return "storyboard.subtitle.validationTime";
    if (line.startMs < 0 || line.endMs > durationMs) return "storyboard.subtitle.validationRange";
    if (line.startMs < prevEnd) return "storyboard.subtitle.validationOverlap";
    prevEnd = Math.max(prevEnd, line.endMs);
  }
  return null;
}

/** 将镜内字幕按时段截断为互不重叠（保留较早条起点、截断其终点）。 */
export function normalizeNonOverlappingSubtitles(
  subtitles: ShotSubtitleView[],
): ShotSubtitleView[] {
  const prepared = subtitles
    .filter((line) => line.text.trim() && line.endMs > line.startMs)
    .map((line) => ({ ...line }))
    .sort((a, b) => a.startMs - b.startMs || a.endMs - b.endMs);
  for (let i = 0; i < prepared.length - 1; i += 1) {
    if (prepared[i].endMs > prepared[i + 1].startMs) {
      prepared[i] = { ...prepared[i], endMs: prepared[i + 1].startMs };
    }
  }
  return prepared.filter((line) => line.endMs > line.startMs);
}

/** 子镜关联的单段视频视图。 */
export interface ShotSubShotVideoView {
  id: string;
  mediaId?: string;
  url?: string;
  startMs: number;
  endMs: number;
  sourceKind?: string;
  cameraMotion?: string;
  /** 图生视频时关联的剧本画面资产 ID。 */
  sourceFrameAssetId?: string;
  /** 关联的 video_clip 文字资产 ID。 */
  videoClipAssetId?: string;
  videoClipName?: string;
}

/** 镜内视频轨 clip（剪辑轴投影）视图。 */
export interface ShotSubShotTimelineClipView {
  id: string;
  mediaId?: string;
  url?: string;
  startMs: number;
  endMs: number;
  sourceKind?: string;
  cameraMotion?: string;
}

/** 媒体清单条目元数据（类型与名称）。 */
export interface MediaMetaInfo {
  type: "image" | "video" | "audio" | "final" | "other";
  name: string;
}

/** 子镜关联的单张剧本画面视图。 */
export interface ShotSubShotFrameView {
  id: string;
  frameAssetId?: string;
  frameName?: string;
  imageMediaId?: string;
  imageUrl?: string;
  /** 绑定 media 的类型（来自媒体清单，非 URL 猜测）。 */
  mediaType?: MediaMetaInfo["type"];
  /** 绑定 media 的显示名。 */
  mediaName?: string;
  kind?: "static" | "video";
  sourceMediaIds: string[];
  /** 画面级关联资产（空镜/角色/物品）；主画面会同步至子镜 element_refs。 */
  elementRefs?: Record<string, string[]>;
  /** 相对镜起点的画面时段起点；解析缺省时回填子镜 startMs。 */
  startMs?: number;
  /** 相对镜起点的画面时段终点；解析缺省时回填子镜 endMs。 */
  endMs?: number;
}

/** 取子镜主画面的 element_refs（编辑与保存用）。 */
export function primaryFrameElementRefs(
  visual: Pick<ShotSubShotView, "images" | "elementRefs">,
): Record<string, string[]> {
  const primary = visual.images?.[0];
  if (primary?.elementRefs && Object.keys(primary.elementRefs).length > 0) {
    return primary.elementRefs;
  }
  return visual.elementRefs ?? {};
}

/** 子镜视图（镜内剧本时间轴时段；可关联多张图、多段视频）。 */
export interface ShotSubShotView {
  id: string;
  startMs: number;
  endMs: number;
  description: string;
  cameraMotion: string;
  elementRefs: Record<string, string[]>;
  /** 子镜关联的多张剧本画面。 */
  images: ShotSubShotFrameView[];
  frameAssetId?: string;
  imageMediaId?: string;
  imageUrl?: string;
  imageMediaIds: string[];
  /** 子镜直接关联的视频素材列表。 */
  videos: ShotSubShotVideoView[];
  videoGenMode: VisualVideoGenMode;
  /** 产出意图（still / text2video / img2video）。 */
  produceMode: ProduceMode;
  /** 产出意图说明（可选）。 */
  produceRationale?: string;
  sourceMediaIds: string[];
  videoClipMediaId?: string;
  videoClipUrl?: string;
  videoMediaIds: string[];
  sourceKind?: string;
  /** 镜内视频轨 clip，对应全片剪辑轴投影。 */
  timelineClip?: ShotSubShotTimelineClipView | null;
}

/** @deprecated 使用 ShotSubShotView */
export type ShotFrameView = ShotSubShotView;

/** 镜内 clip 是否为分镜可展示的剪辑轴视频（排除静图占位 still）。 */
function isEditTimelineVideoClip(sourceKind?: string | null): boolean {
  return (sourceKind ?? "").trim().toLowerCase() === "video";
}

/** 将 clip 时段裁剪到子镜区间内；无交集则返回 null。 */
function intersectClipRangeWithSubShot(
  clipStart: number,
  clipEnd: number,
  subStart: number,
  subEnd: number,
): { startMs: number; endMs: number } | null {
  const startMs = Math.max(clipStart, subStart);
  const endMs = Math.min(clipEnd, subEnd);
  if (endMs <= startMs) return null;
  return { startMs, endMs };
}

/** 子镜是否已有可播放视频片段（排除静图轨 still）。 */
export function subShotHasVideoClip(subShot: ShotSubShotView): boolean {
  if (subShot.videos.some((v) => Boolean(v.mediaId || v.url))) return true;
  const tl = subShot.timelineClip;
  if (tl && isEditTimelineVideoClip(tl.sourceKind) && (tl.mediaId || tl.url)) return true;
  if (subShot.sourceKind !== "video") return false;
  return Boolean(subShot.videoClipMediaId?.trim() || subShot.videoClipUrl?.trim());
}

/** 子镜是否已关联可展示的视频素材（videos[] 或兼容字段）。 */
export function subShotHasBoundVideo(subShot: ShotSubShotView): boolean {
  if (subShot.videos.some((v) => Boolean(v.mediaId || v.url))) return true;
  return Boolean(subShot.videoClipMediaId?.trim() || subShot.videoClipUrl?.trim());
}

/** 子镜是否在镜内视频轨有关联媒体的剪辑轴 clip（仅 video 且落在子镜时段内）。 */
export function subShotHasBoundTimeline(subShot: ShotSubShotView): boolean {
  const clip = subShot.timelineClip;
  if (!clip || !isEditTimelineVideoClip(clip.sourceKind)) return false;
  if (!(clip.mediaId || clip.url)) return false;
  return (
    intersectClipRangeWithSubShot(
      clip.startMs,
      clip.endMs,
      subShot.startMs,
      subShot.endMs,
    ) !== null
  );
}

/** 子镜是否具备可展示的画面轨内容（视频或剪辑，用于迷你时间轴画面段）。 */
export function subShotHasVisualMediaContent(subShot: ShotSubShotView): boolean {
  return subShotHasBoundVideo(subShot) || subShotHasBoundTimeline(subShot);
}

/** @deprecated 使用 subShotHasVideoClip */
export const visualHasVideoClip = subShotHasVideoClip;

/** 由子镜画面列表同步首张兼容字段（展示与旧逻辑）。 */
export function syncSubShotPrimaryImageFields(
  images: ShotSubShotFrameView[],
): Pick<
  ShotSubShotView,
  "frameAssetId" | "imageMediaId" | "imageUrl" | "imageMediaIds" | "sourceMediaIds"
> {
  const first = images[0];
  const mediaIds = images
    .map((i) => i.imageMediaId)
    .filter((mid): mid is string => Boolean(mid?.trim()));
  return {
    frameAssetId: first?.frameAssetId,
    imageMediaId: first?.imageMediaId,
    imageUrl: first?.imageUrl,
    imageMediaIds: mediaIds,
    sourceMediaIds: first?.sourceMediaIds ?? [],
  };
}

/** 为子镜画面槽生成前端临时 id（避免同毫秒碰撞）。 */
function newClientSubShotImageId(prefix = "ssi"): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * 将 plan 画面时段展开为视图字段；未显式设置（均为 0/缺省）时回填子镜区间。
 */
function expandImageTimingForView(
  img: Pick<ShotSubShotImage, "start_ms" | "end_ms">,
  subStartMs: number,
  subEndMs: number,
): { startMs: number; endMs: number } {
  const rawStart = Number(img.start_ms ?? 0);
  const rawEnd = Number(img.end_ms ?? 0);
  if (rawStart === 0 && rawEnd === 0) {
    return { startMs: subStartMs, endMs: subEndMs };
  }
  return { startMs: Math.max(0, rawStart), endMs: Math.max(0, rawEnd) };
}

/** 从 plan 子镜 images 解析画面视图列表。 */
function parseSubShotImagesFromPlan(
  sub: ShotSubShot,
  subShotId: string,
  subStartMs: number,
  subEndMs: number,
  projectId?: string | null,
  scriptId?: string | null,
  linkById?: Record<string, string>,
  mediaMetaById?: Record<string, MediaMetaInfo>,
): ShotSubShotFrameView[] {
  const raw = sub.images ?? [];
  const seen = new Set<string>();
  const mapped = raw.map((img, iIdx) => {
    let id = (img.id ?? "").trim() || `ssi-${subShotId}-${iIdx}`;
    if (seen.has(id)) {
      id = `${id}-${iIdx}-${Math.random().toString(36).slice(2, 6)}`;
    }
    seen.add(id);
    const timing = expandImageTimingForView(img, subStartMs, subEndMs);
    const mediaId = (img.media_id ?? "").trim();
    const meta = mediaId ? mediaMetaById?.[mediaId] : undefined;
    return {
      id,
      frameAssetId: img.frame_asset_id || undefined,
      imageMediaId: mediaId || undefined,
      imageUrl: mediaUrlFromId(img.media_id, projectId, scriptId, linkById),
      mediaType: meta?.type,
      mediaName: meta?.name || undefined,
      kind: (img.kind === "video" ? "video" : "static") as "static" | "video",
      sourceMediaIds: [...(img.source_media_ids ?? [])],
      elementRefs: iIdx === 0 ? { ...(sub.element_refs ?? {}) } : undefined,
      startMs: timing.startMs,
      endMs: timing.endMs,
    };
  });
  if (mapped.length > 0) return mapped;
  const legacy = sub.image;
  if (legacy?.frame_asset_id || legacy?.media_id) {
    const timing = expandImageTimingForView(legacy, subStartMs, subEndMs);
    const mediaId = (legacy.media_id ?? "").trim();
    const meta = mediaId ? mediaMetaById?.[mediaId] : undefined;
    return [
      {
        id: legacy.id ?? `ssi-${subShotId}-0`,
        frameAssetId: legacy.frame_asset_id || undefined,
        imageMediaId: mediaId || undefined,
        imageUrl: mediaUrlFromId(legacy.media_id, projectId, scriptId, linkById),
        mediaType: meta?.type,
        mediaName: meta?.name || undefined,
        kind: (legacy.kind === "video" ? "video" : "static") as "static" | "video",
        sourceMediaIds: [...(legacy.source_media_ids ?? [])],
        elementRefs: { ...(sub.element_refs ?? {}) },
        startMs: timing.startMs,
        endMs: timing.endMs,
      },
    ];
  }
  return [];
}

/** 取子镜首张关联图片（兼容旧 image 字段）。 */
function primarySubShotImage(
  sub: ShotSubShot,
): ShotSubShotImage | null | undefined {
  if (sub.images?.length) return sub.images[0];
  return sub.image ?? undefined;
}

/** 由 media_id 拼接可播放 URL；优先使用媒体清单中的 link/url。 */
export function mediaUrlFromId(
  mediaId: string | undefined,
  projectId?: string | null,
  scriptId?: string | null,
  linkById?: Record<string, string>,
): string {
  const id = (mediaId ?? "").trim();
  if (!id || !projectId || !scriptId) return "";
  const fromIndex = linkById?.[id]?.trim();
  if (fromIndex) {
    return resolveMediaPlayUrl(fromIndex, projectId, scriptId) || fromIndex;
  }
  return resolveMediaPlayUrl(id, projectId, scriptId);
}

/** 从剧本媒体 API 响应构建 media_id → 可播放 URL 索引。 */
export function buildMediaLinkIndex(
  items: Array<{ id?: string; link?: string; url?: string }>,
  projectId?: string | null,
  scriptId?: string | null,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const item of items) {
    const id = (item.id ?? "").trim();
    const raw = (item.link ?? item.url ?? "").trim();
    if (!id || !raw) continue;
    const play = resolveMediaPlayUrl(raw, projectId, scriptId) || raw;
    if (play) out[id] = play;
  }
  return out;
}

/** 规范化媒体 type 字段。 */
export function normalizeMediaMetaType(raw: unknown): MediaMetaInfo["type"] {
  const t = String(raw ?? "").trim().toLowerCase();
  if (t === "image" || t === "video" || t === "audio" || t === "final") return t;
  return "other";
}

/** 从剧本媒体 API 响应构建 media_id → 类型/名称索引。 */
export function buildMediaMetaIndex(
  items: Array<{ id?: string; type?: string; name?: string }>,
): Record<string, MediaMetaInfo> {
  const out: Record<string, MediaMetaInfo> = {};
  for (const item of items) {
    const id = (item.id ?? "").trim();
    if (!id) continue;
    out[id] = {
      type: normalizeMediaMetaType(item.type),
      name: String(item.name ?? "").trim(),
    };
  }
  return out;
}

/** 落盘镜时长步进：整秒（避免精确到毫秒的脏值）。 */
export const SHOT_DURATION_QUANTUM_MS = 1000;

/** 将时长向上对齐到整秒，避免裁短音视频。 */
export function quantizeDurationMs(ms: number, quantumMs = SHOT_DURATION_QUANTUM_MS): number {
  const n = Math.max(0, Math.round(Number(ms) || 0));
  const q = Math.max(1, Math.round(quantumMs));
  if (n <= 0) return q;
  return Math.ceil(n / q) * q;
}

/** 从剧本媒体 API 响应构建 media_id → 时长（毫秒）索引。 */
export function buildMediaDurationIndex(
  items: Array<{ id?: string; duration_ms?: number | null }>,
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const item of items) {
    const id = (item.id ?? "").trim();
    const ms = Number(item.duration_ms ?? 0);
    if (!id || !(ms > 0)) continue;
    out[id] = Math.round(ms);
  }
  return out;
}

/**
 * 用媒体实测时长回填配音幕终点（仅延长，不缩短用户裁剪）。
 */
export function applyMediaDurationToVoiceActs(
  voiceActs: ShotVoiceActView[],
  mediaDurationById?: Record<string, number>,
): ShotVoiceActView[] {
  if (!mediaDurationById) return voiceActs;
  let changed = false;
  const next = voiceActs.map((act) => {
    const mid = (act.mediaId ?? "").trim();
    if (!mid) return act;
    const mediaMs = Number(mediaDurationById[mid] ?? 0);
    if (!(mediaMs > 0)) return act;
    const desiredEnd = quantizeDurationMs(act.startMs + mediaMs);
    const nextEnd = Math.max(desiredEnd, quantizeDurationMs(act.endMs));
    if (nextEnd === act.endMs) return act;
    changed = true;
    return { ...act, endMs: nextEnd };
  });
  return changed ? next : voiceActs;
}

/** 从 VideoPlanShot 解析配音幕列表。 */
export function parseVoiceActsFromPlan(
  shot: VideoPlanShot,
  projectId?: string | null,
  scriptId?: string | null,
  linkById?: Record<string, string>,
): ShotVoiceActView[] {
  const acts: ShotVoiceActView[] = [];
  const duration = shot.duration_ms ?? 3000;
  for (const track of shot.audio_tracks ?? []) {
    if (track.kind !== "voice") continue;
    for (const clip of track.clips ?? []) {
      const startMs = Number(clip.start_ms ?? 0);
      const endMs = Number(clip.end_ms ?? 0) || duration;
      acts.push({
        id: clip.id ?? `vac-${acts.length}`,
        startMs,
        endMs,
        text: (clip.text ?? "").trim(),
        characterRef: (clip.character_ref ?? "").trim(),
        voice: (clip.voice ?? "").trim(),
        mediaId: clip.media_id || undefined,
        audioUrl: mediaUrlFromId(clip.media_id, projectId, scriptId, linkById),
      });
    }
  }
  acts.sort((a, b) => a.startMs - b.startMs);
  return acts;
}

/** 查找与子镜绑定的镜内视频 clip（含静图 still）。 */
function findVideoClipForSubShot(
  shot: VideoPlanShot,
  subShotId: string,
): ShotVideoClip | undefined {
  for (const track of shot.video_tracks ?? []) {
    if (Number(track.z_index ?? 0) !== 0) continue;
    for (const clip of track.clips ?? []) {
      if (clip.source_sub_shot_id === subShotId) return clip;
    }
  }
  for (const track of shot.video_tracks ?? []) {
    for (const clip of track.clips ?? []) {
      if (clip.source_sub_shot_id === subShotId) return clip;
    }
  }
  return undefined;
}

/** 查找子镜时段内可展示的剪辑轴 clip（source_kind=video 且有 media）。 */
function findEditTimelineClipForSubShot(
  shot: VideoPlanShot,
  subShotId: string,
  subStartMs: number,
  subEndMs: number,
): ShotVideoClip | undefined {
  const scan = (onlyZ0: boolean): ShotVideoClip | undefined => {
    for (const track of shot.video_tracks ?? []) {
      if (onlyZ0 && Number(track.z_index ?? 0) !== 0) continue;
      for (const clip of track.clips ?? []) {
        if (clip.source_sub_shot_id !== subShotId) continue;
        if (!isEditTimelineVideoClip(clip.source_kind)) continue;
        if (!(clip.media_id ?? "").trim()) continue;
        const clipStart = Number(clip.start_ms ?? 0);
        const clipEnd = Number(clip.end_ms ?? 0);
        if (!intersectClipRangeWithSubShot(clipStart, clipEnd, subStartMs, subEndMs)) continue;
        return clip;
      }
    }
    return undefined;
  };
  return scan(true) ?? scan(false);
}

/** 从 VideoPlanShot 解析子镜列表。 */
export function parseSubShotsFromPlan(
  shot: VideoPlanShot,
  projectId?: string | null,
  scriptId?: string | null,
  linkById?: Record<string, string>,
  mediaMetaById?: Record<string, MediaMetaInfo>,
): ShotSubShotView[] {
  const duration = shot.duration_ms ?? 3000;
  const subShots = [...(shot.sub_shots ?? [])].sort(
    (a, b) => Number(a.start_ms ?? 0) - Number(b.start_ms ?? 0),
  );
  if (subShots.length === 0) return [];

  return subShots.map((sub, idx) => {
    const id = sub.id ?? `ssb-${idx}`;
    const startMs = Number(sub.start_ms ?? 0);
    const endMs = Number(sub.end_ms ?? 0) || duration;
    const boundClip = findVideoClipForSubShot(shot, id);
    const editClip = findEditTimelineClipForSubShot(shot, id, startMs, endMs);
    const image = primarySubShotImage(sub);
    const produceMode = normalizeProduceMode(sub.produce_mode);
    const produceRationale = (sub.produce_rationale ?? "").trim() || undefined;
    const subShotImages = parseSubShotImagesFromPlan(
      sub,
      id,
      startMs,
      endMs,
      projectId,
      scriptId,
      linkById,
      mediaMetaById,
    );
    const imageMediaIds = subShotImages
      .map((i) => i.imageMediaId)
      .filter((mid): mid is string => Boolean(mid?.trim()));
    const videoMediaIds = (sub.videos ?? [])
      .map((v) => v.media_id)
      .filter((mid): mid is string => Boolean(mid?.trim()));
    const videos: ShotSubShotVideoView[] = (sub.videos ?? []).map((v, vIdx) => ({
      id: v.id ?? `vid-${id}-${vIdx}`,
      mediaId: v.media_id || undefined,
      url: mediaUrlFromId(v.media_id, projectId, scriptId, linkById),
      startMs: Number(v.start_ms ?? startMs),
      endMs: Number(v.end_ms ?? endMs),
      sourceKind: v.source_kind,
      cameraMotion: v.camera_motion,
      sourceFrameAssetId: v.source_frame_asset_id || undefined,
      videoClipAssetId: v.video_clip_asset_id || undefined,
    }));
    const timelineClip: ShotSubShotTimelineClipView | null = (() => {
      if (!editClip) return null;
      const rawStart = Number(editClip.start_ms ?? startMs);
      const rawEnd = Number(editClip.end_ms ?? endMs);
      const range = intersectClipRangeWithSubShot(rawStart, rawEnd, startMs, endMs);
      if (!range) return null;
      return {
        id: editClip.id ?? `tcl-${id}`,
        mediaId: editClip.media_id || undefined,
        url: mediaUrlFromId(editClip.media_id, projectId, scriptId, linkById),
        startMs: range.startMs,
        endMs: range.endMs,
        sourceKind: editClip.source_kind,
        cameraMotion: editClip.camera_motion,
      };
    })();
    return {
      id,
      startMs,
      endMs,
      description: (sub.description ?? "").trim(),
      cameraMotion: (sub.camera_motion ?? "static").trim() || "static",
      elementRefs: { ...(sub.element_refs ?? {}) },
      images: subShotImages,
      frameAssetId: image?.frame_asset_id || subShotImages[0]?.frameAssetId || undefined,
      imageMediaId: image?.media_id || undefined,
      imageUrl: mediaUrlFromId(image?.media_id, projectId, scriptId, linkById),
      imageMediaIds,
      videos,
      videoGenMode: produceModeToVideoGenMode(produceMode),
      produceMode,
      produceRationale,
      sourceMediaIds: [...(image?.source_media_ids ?? [])],
      videoClipMediaId: editClip?.media_id || videoMediaIds[0] || undefined,
      videoClipUrl: mediaUrlFromId(
        editClip?.media_id || videoMediaIds[0],
        projectId,
        scriptId,
        linkById,
      ),
      videoMediaIds,
      sourceKind: boundClip?.source_kind,
      timelineClip,
    };
  });
}

/** @deprecated 使用 parseSubShotsFromPlan */
export const parseFramesFromPlan = parseSubShotsFromPlan;

/** 无 plan 时从扁平 ShotDetailItem 合成单段视图。 */
export function fallbackVoiceActsFromDetail(
  item: ShotDetailItem,
  durationMs: number,
): ShotVoiceActView[] {
  const text = (item.narration_text ?? "").trim();
  if (!text) return [];
  return [
    {
      id: "vac-fallback",
      startMs: 0,
      endMs: durationMs,
      text,
      characterRef: "",
      voice: "",
      audioUrl: item.tts_audio_url,
    },
  ];
}

/** 无 plan 时从扁平 ShotDetailItem 合成单子镜。 */
export function fallbackSubShotsFromDetail(
  item: ShotDetailItem,
  durationMs: number,
): ShotSubShotView[] {
  const desc = (item.narration_text ?? item.display_instructions ?? "").trim();
  return [
    {
      id: "ssb-fallback",
      startMs: 0,
      endMs: durationMs,
      description: desc,
      cameraMotion: item.camera_motion_canonical ?? item.camera_motion_label ?? "static",
      elementRefs: { ...(item.asset_refs ?? {}) },
      images: item.frame_preview_url
        ? [
            {
              id: "ssi-fallback-0",
              imageUrl: item.frame_preview_url,
              kind: "static" as const,
              sourceMediaIds: [],
              startMs: 0,
              endMs: durationMs,
            },
          ]
        : [],
      imageUrl: item.frame_preview_url,
      imageMediaIds: [],
      videos: [],
      videoGenMode: "still",
      produceMode: "still",
      sourceMediaIds: [],
      videoMediaIds: [],
      timelineClip: null,
    },
  ];
}

/** @deprecated 使用 fallbackSubShotsFromDetail */
export const fallbackFramesFromDetail = fallbackSubShotsFromDetail;

/** 校验镜内分段编辑，返回 i18n 键或 null 表示通过。 */
export function validateShotSegmentEdits(
  durationMs: number,
  voiceActs: ShotVoiceActView[],
  subShots: ShotSubShotView[],
  subtitles: ShotSubtitleView[] = [],
): string | null {
  if (subShots.length === 0) return "storyboard.subShot.validationMin";
  for (const f of subShots) {
    if (f.endMs <= f.startMs) return "storyboard.subShot.validationTime";
    if (f.startMs < 0 || f.endMs > durationMs) return "storyboard.subShot.validationRange";
    for (const img of f.images) {
      if (img.startMs == null || img.endMs == null) continue;
      if (!(f.startMs <= img.startMs && img.startMs < img.endMs && img.endMs <= f.endMs)) {
        return "storyboard.subShot.validationImageTime";
      }
    }
  }
  for (const a of voiceActs) {
    if (a.endMs <= a.startMs) return "storyboard.voiceAct.validationTime";
    if (a.startMs < 0 || a.endMs > durationMs) return "storyboard.voiceAct.validationRange";
  }
  const subtitleErr = validateSubtitleEdits(durationMs, subtitles);
  if (subtitleErr) return subtitleErr;
  return null;
}

/** 按成片模式生成主画面 video_prompt。 */
function videoPromptForGenMode(
  mode: VisualVideoGenMode,
  description: string,
): string | undefined {
  if (mode === "still") return undefined;
  if (mode === "keyframes") return KEYFRAMES_VIDEO_PROMPT;
  if (mode === "text2video") {
    const text = description.trim();
    return text || undefined;
  }
  return undefined;
}

/** 将分段编辑写回镜内多轨 patch。 */
export function buildShotPatchFromSegments(
  shot: VideoPlanShot,
  edits: {
    durationMs: number;
    reviewNote: string;
    voiceActs: ShotVoiceActView[];
    subShots: ShotSubShotView[];
    subtitles?: ShotSubtitleView[];
  },
): PatchVideoPlanShotBody {
  const durationMs = Math.max(500, quantizeDurationMs(edits.durationMs));
  const sub_shots: ShotSubShot[] = edits.subShots.map((v) => {
    const prev = shot.sub_shots?.find((x) => x.id === v.id);
    const frameViews: ShotSubShotFrameView[] =
      v.images?.length > 0
        ? v.images
        : v.frameAssetId || v.imageMediaId
          ? [
              {
                id: `ssi-${v.id}-0`,
                frameAssetId: v.frameAssetId,
                imageMediaId: v.imageMediaId,
                imageUrl: v.imageUrl,
                kind: v.videoGenMode === "still" ? "static" : "video",
                sourceMediaIds: v.sourceMediaIds ?? [],
                startMs: v.startMs,
                endMs: v.endMs,
              },
            ]
          : [];
    const images: ShotSubShotImage[] = frameViews
      .filter(
        (img) => Boolean((img.frameAssetId ?? "").trim() || (img.imageMediaId ?? "").trim()),
      )
      .map((img, imgIdx) => {
      const prevImg = (prev?.images ?? []).find((x) => x.id === img.id);
      const isNewClientId = img.id.startsWith("ssi-") && !prevImg?.id;
      const isPrimary = imgIdx === 0;
      return {
        id: isNewClientId ? undefined : img.id,
        kind: (img.kind === "video" ? "video" : "static") as "static" | "video",
        frame_asset_id: img.frameAssetId ?? "",
        media_id: img.imageMediaId ?? "",
        source_media_ids: img.sourceMediaIds.length
          ? img.sourceMediaIds
          : (prevImg?.source_media_ids ?? []),
        video_prompt: isPrimary
          ? videoPromptForGenMode(v.videoGenMode, v.description)
          : prevImg?.video_prompt,
        start_ms: img.startMs ?? v.startMs,
        end_ms: img.endMs ?? v.endMs,
      };
    });
    const videos = v.videos.map((vid) => {
      const prevVid = (prev?.videos ?? []).find((x) => x.id === vid.id);
      return {
        id: vid.id.startsWith("vid-") && !prevVid?.id ? undefined : vid.id,
        media_id: vid.mediaId || undefined,
        start_ms: vid.startMs,
        end_ms: vid.endMs,
        source_kind: (vid.sourceKind ?? prevVid?.source_kind ?? "video") as "video" | "still",
        camera_motion: vid.cameraMotion || prevVid?.camera_motion,
        source_frame_asset_id: vid.sourceFrameAssetId || prevVid?.source_frame_asset_id,
        video_clip_asset_id: vid.videoClipAssetId || prevVid?.video_clip_asset_id,
      };
    });
    return {
      id: v.id.startsWith("ssb-") && !prev?.id ? undefined : v.id,
      start_ms: v.startMs,
      end_ms: v.endMs,
      description: v.description,
      camera_motion: v.cameraMotion,
      element_refs: primaryFrameElementRefs(v),
      images,
      videos,
      produce_mode: v.produceMode,
      produce_rationale: (v.produceRationale ?? "").trim() || undefined,
    };
  });

  const voiceClips: ShotAudioClip[] = edits.voiceActs.map((a) => {
    const prevTrack = shot.audio_tracks?.find((t) => t.kind === "voice");
    const prev = prevTrack?.clips?.find((c) => c.id === a.id);
    return {
      id: a.id.startsWith("vac-") && !prev?.id ? undefined : a.id,
      start_ms: a.startMs,
      end_ms: a.endMs,
      text: a.text,
      character_ref: a.characterRef || undefined,
      voice: a.voice || undefined,
      media_id: a.mediaId || prev?.media_id,
    };
  });

  const audioTracks: ShotAudioTrack[] = [...(shot.audio_tracks ?? [])];
  let voiceIdx = audioTracks.findIndex((t) => t.kind === "voice");
  const voiceTrack: ShotAudioTrack = {
    kind: "voice",
    name: voiceIdx >= 0 ? audioTracks[voiceIdx].name ?? "角色音" : "角色音",
    clips: voiceClips,
  };
  if (voiceIdx < 0) audioTracks.push(voiceTrack);
  else audioTracks[voiceIdx] = { ...audioTracks[voiceIdx], clips: voiceClips };

  // 显式传入 subtitles（含空数组）时按编辑结果写回；勿用配音幕文案冒充音频字幕
  const subtitleLines =
    edits.subtitles !== undefined
      ? edits.subtitles
      : parseSubtitlesFromPlan(shot);
  const subtitles = subtitlesToPatchBody(subtitleLines);

  return {
    duration_ms: durationMs,
    review_note: edits.reviewNote.trim() || undefined,
    sub_shots,
    audio_tracks: audioTracks,
    subtitles,
    camera_motion_refined: sub_shots[0]?.camera_motion,
  };
}

/** 新建空配音幕。 */
export function newVoiceAct(durationMs: number, startMs = 0): ShotVoiceActView {
  const end = Math.min(durationMs, startMs + 3000);
  return {
    id: `vac-${Date.now()}`,
    startMs,
    endMs: end,
    text: "",
    characterRef: "",
    voice: "",
  };
}

/** 新建空子镜视频条目。 */
export function newSubShotVideo(startMs: number, endMs: number): ShotSubShotVideoView {
  return {
    id: `vid-${Date.now()}`,
    startMs,
    endMs,
    sourceKind: "video",
  };
}

/** 新建空子镜画面条目。 */
export function newSubShotFrame(): ShotSubShotFrameView {
  return {
    id: newClientSubShotImageId("ssi"),
    kind: "static",
    sourceMediaIds: [],
  };
}

/** 新建空子镜。 */
export function newSubShot(durationMs: number, startMs = 0): ShotSubShotView {
  const end = Math.min(durationMs, startMs + 3000);
  return {
    id: `ssb-${Date.now()}`,
    startMs,
    endMs: end,
    description: "",
    cameraMotion: "static",
    elementRefs: {},
    images: [],
    videos: [],
    videoGenMode: "still",
    produceMode: "still",
    sourceMediaIds: [],
    imageMediaIds: [],
    videoMediaIds: [],
    timelineClip: null,
  };
}

/** @deprecated 使用 newSubShot */
export const newShotFrame = newSubShot;

/** 展示时长来源（优先级：剪辑 > 视频 > 配音 > 计划）。 */
export type ShotDurationSource = "timeline" | "video" | "voice" | "plan";

/** 解析后的展示时段。 */
export interface ResolvedShotDuration {
  startMs: number;
  endMs: number;
  durationMs: number;
  source: ShotDurationSource;
}

/** 镜内多轨原始字段（看板 item 或 VideoPlanShot 均可传入）。 */
export interface ShotDurationResolveInput {
  duration_ms?: number;
  video_tracks?: Array<{
    clips?: Array<{
      start_ms?: number;
      end_ms?: number;
      media_id?: string;
      source_kind?: string;
    }>;
  }>;
  audio_tracks?: Array<{
    kind?: string;
    clips?: Array<{ start_ms?: number; end_ms?: number; text?: string; media_id?: string }>;
  }>;
  sub_shots?: Array<{
    start_ms?: number;
    end_ms?: number;
    videos?: Array<{ start_ms?: number; end_ms?: number; media_id?: string }>;
  }>;
  tts_duration_ms?: number;
}

/** 从镜内多轨解析展示时长：剪辑轴 clip > 子镜视频 > 配音 > 计划镜长。 */
export function resolveShotDisplayDuration(
  input: ShotDurationResolveInput,
): ResolvedShotDuration {
  const planMs = Math.max(0, Number(input.duration_ms ?? 3000));

  let tlStart = Infinity;
  let tlEnd = 0;
  for (const track of input.video_tracks ?? []) {
    for (const clip of track.clips ?? []) {
      if (!(clip.media_id ?? "").trim()) continue;
      if (!isEditTimelineVideoClip(clip.source_kind)) continue;
      const start = Number(clip.start_ms ?? 0);
      const end = Number(clip.end_ms ?? 0);
      if (end > start) {
        tlStart = Math.min(tlStart, start);
        tlEnd = Math.max(tlEnd, end);
      }
    }
  }
  if (tlEnd > tlStart && tlStart !== Infinity) {
    return {
      startMs: tlStart,
      endMs: tlEnd,
      durationMs: tlEnd - tlStart,
      source: "timeline",
    };
  }

  let videoStart = Infinity;
  let videoEnd = 0;
  for (const sub of input.sub_shots ?? []) {
    const subStart = Number(sub.start_ms ?? 0);
    const subEnd = Number(sub.end_ms ?? 0);
    for (const video of sub.videos ?? []) {
      if (!(video.media_id ?? "").trim()) continue;
      const start = Number(video.start_ms ?? subStart);
      const end = Number(video.end_ms ?? subEnd);
      if (end > start) {
        videoStart = Math.min(videoStart, start);
        videoEnd = Math.max(videoEnd, end);
      }
    }
  }
  if (videoEnd > videoStart && videoStart !== Infinity) {
    return {
      startMs: videoStart,
      endMs: videoEnd,
      durationMs: videoEnd - videoStart,
      source: "video",
    };
  }

  let voiceStart = Infinity;
  let voiceEnd = 0;
  for (const track of input.audio_tracks ?? []) {
    if (track.kind !== "voice") continue;
    for (const clip of track.clips ?? []) {
      const start = Number(clip.start_ms ?? 0);
      const end = Number(clip.end_ms ?? 0);
      const hasContent = Boolean((clip.text ?? "").trim() || (clip.media_id ?? "").trim());
      if (!hasContent) continue;
      const effectiveEnd = end > start ? end : planMs;
      voiceStart = Math.min(voiceStart, start);
      voiceEnd = Math.max(voiceEnd, effectiveEnd);
    }
  }
  const ttsMs = Math.max(0, Number(input.tts_duration_ms ?? 0));
  if (voiceEnd > voiceStart && voiceStart !== Infinity) {
    return {
      startMs: voiceStart,
      endMs: voiceEnd,
      durationMs: voiceEnd - voiceStart,
      source: "voice",
    };
  }
  if (ttsMs > 0) {
    return {
      startMs: 0,
      endMs: ttsMs,
      durationMs: ttsMs,
      source: "voice",
    };
  }

  return {
    startMs: 0,
    endMs: planMs,
    durationMs: planMs,
    source: "plan",
  };
}

/** 从 VideoPlanShot 解析镜级展示时长。 */
export function resolveShotDisplayDurationFromPlan(
  shot: VideoPlanShot,
  ttsDurationMs?: number,
): ResolvedShotDuration {
  return resolveShotDisplayDuration({
    duration_ms: shot.duration_ms,
    video_tracks: shot.video_tracks,
    audio_tracks: shot.audio_tracks,
    sub_shots: shot.sub_shots,
    tts_duration_ms: ttsDurationMs,
  });
}

/**
 * 从编辑中分段状态推导镜时长（剪辑 > 视频 > 配音 > 计划），
 * 并结合媒体实测时长延长配音/视频占位终点。
 */
export function resolveShotDurationFromSegments(input: {
  planDurationMs?: number;
  voiceActs: ShotVoiceActView[];
  subShots: ShotSubShotView[];
  subtitles?: ShotSubtitleView[];
  mediaDurationById?: Record<string, number>;
}): ResolvedShotDuration {
  const planMs = Math.max(0, Number(input.planDurationMs ?? 3000));
  const mediaDurationById = input.mediaDurationById ?? {};

  let tlStart = Infinity;
  let tlEnd = 0;
  for (const sub of input.subShots) {
    const clip = sub.timelineClip;
    if (!clip || !(clip.mediaId ?? "").trim()) continue;
    if (!isEditTimelineVideoClip(clip.sourceKind)) continue;
    if (clip.endMs > clip.startMs) {
      tlStart = Math.min(tlStart, clip.startMs);
      tlEnd = Math.max(tlEnd, clip.endMs);
    }
  }
  if (tlEnd > tlStart && tlStart !== Infinity) {
    return {
      startMs: tlStart,
      endMs: tlEnd,
      durationMs: tlEnd - tlStart,
      source: "timeline",
    };
  }

  let videoStart = Infinity;
  let videoEnd = 0;
  for (const sub of input.subShots) {
    for (const video of sub.videos) {
      const mid = (video.mediaId ?? "").trim();
      if (!mid && !(video.url ?? "").trim()) continue;
      let start = video.startMs;
      let end = video.endMs;
      const mediaMs = mid ? Number(mediaDurationById[mid] ?? 0) : 0;
      if (mediaMs > 0 && !(end > start)) {
        end = start + mediaMs;
      }
      if (end > start) {
        videoStart = Math.min(videoStart, start);
        videoEnd = Math.max(videoEnd, end);
      }
    }
    if ((sub.videoClipMediaId || sub.videoClipUrl) && sub.endMs > sub.startMs) {
      videoStart = Math.min(videoStart, sub.startMs);
      videoEnd = Math.max(videoEnd, sub.endMs);
    }
  }
  if (videoEnd > videoStart && videoStart !== Infinity) {
    return {
      startMs: videoStart,
      endMs: videoEnd,
      durationMs: videoEnd - videoStart,
      source: "video",
    };
  }

  let voiceStart = Infinity;
  let voiceEnd = 0;
  for (const act of input.voiceActs) {
    const mid = (act.mediaId ?? "").trim();
    const hasContent = Boolean(act.text.trim() || mid);
    if (!hasContent) continue;
    let end = act.endMs > act.startMs ? act.endMs : planMs;
    const mediaMs = mid ? Number(mediaDurationById[mid] ?? 0) : 0;
    if (mediaMs > 0) {
      end = Math.max(end, act.startMs + mediaMs);
    }
    voiceStart = Math.min(voiceStart, act.startMs);
    voiceEnd = Math.max(voiceEnd, end);
  }
  if (voiceEnd > voiceStart && voiceStart !== Infinity) {
    return {
      startMs: voiceStart,
      endMs: voiceEnd,
      durationMs: voiceEnd - voiceStart,
      source: "voice",
    };
  }

  let structuralEnd = 0;
  for (const sub of input.subShots) {
    structuralEnd = Math.max(structuralEnd, sub.endMs);
  }
  for (const line of input.subtitles ?? []) {
    structuralEnd = Math.max(structuralEnd, line.endMs);
  }
  if (structuralEnd > planMs) {
    return {
      startMs: 0,
      endMs: structuralEnd,
      durationMs: structuralEnd,
      source: "plan",
    };
  }

  return {
    startMs: 0,
    endMs: planMs,
    durationMs: planMs,
    source: "plan",
  };
}

/** 子镜展示时段：剪辑 clip > 子镜视频 > 重叠配音 > 计划子镜区间。 */
export function resolveSubShotDisplayRange(
  visual: ShotSubShotView,
  voiceActs: ShotVoiceActView[],
): ResolvedShotDuration {
  if (subShotHasBoundTimeline(visual) && visual.timelineClip) {
    const clip = visual.timelineClip;
    return {
      startMs: clip.startMs,
      endMs: clip.endMs,
      durationMs: clip.endMs - clip.startMs,
      source: "timeline",
    };
  }

  if (subShotHasBoundVideo(visual)) {
    const videos = visual.videos.filter((v) => Boolean(v.mediaId || v.url));
    if (videos.length > 0) {
      const startMs = Math.min(...videos.map((v) => v.startMs));
      const endMs = Math.max(...videos.map((v) => v.endMs));
      if (endMs > startMs) {
        return {
          startMs,
          endMs,
          durationMs: endMs - startMs,
          source: "video",
        };
      }
    }
    if (visual.videoClipMediaId || visual.videoClipUrl) {
      return {
        startMs: visual.startMs,
        endMs: visual.endMs,
        durationMs: Math.max(0, visual.endMs - visual.startMs),
        source: "video",
      };
    }
  }

  const overlapping = voiceActs.filter(
    (act) =>
      act.text.trim() &&
      act.endMs > visual.startMs &&
      act.startMs < visual.endMs,
  );
  if (overlapping.length > 0) {
    const startMs = Math.min(...overlapping.map((act) => act.startMs));
    const endMs = Math.max(...overlapping.map((act) => act.endMs));
    if (endMs > startMs) {
      return {
        startMs,
        endMs,
        durationMs: endMs - startMs,
        source: "voice",
      };
    }
  }

  const durationMs = Math.max(0, visual.endMs - visual.startMs);
  return {
    startMs: visual.startMs,
    endMs: visual.endMs,
    durationMs,
    source: "plan",
  };
}
