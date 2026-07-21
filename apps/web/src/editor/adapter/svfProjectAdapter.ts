/**

 * EditTimeline（SVF API）↔ OpenCut Classic TProject 双向映射。

 * 无法 1:1 映射的 Classic 字段存入 clip.metadata.classic 与 timeline.metadata.classic_project。

 */



import type {
  EditTimelineData,
  MediaBinItem,
  TrackClip,
  VideoLayer,
} from "../../edit/types";

import {

  buildMediaIdLookup,

  getSvfProjectMediaCache,

  inferClipMediaType,

  resolveMediaIdForClip,

  type MediaIdLookup,

} from "./SvfMediaBridge";

import { DEFAULT_FPS } from "../opencut/fps/defaults";

import { floatToFrameRate } from "../opencut/fps/utils";

import {
  resolveCanvasSize,
  svfTransformToOpenCutParams,
  openCutParamsToSvfTransform,
  type CanvasSize,
} from "./svfTransformBridge";

import { interpolateTransform, buildMotionAnimations } from "./svfMotionBridge";
import {
  extractSvfKeyframesFromElement,
  shouldFlattenMotionForSavedKeyframes,
  stripKenBurnsScaleFromMotionDetail,
} from "./svfAnimationBridge";
import type { ElementAnimations } from "../opencut/animation/types";

import { sortClipsForExport } from "./svfClipOrder";

import { computeMediaTrimFields } from "./svfTrimFields";
import { subtitleClipToTextElement } from "../opencut/subtitles/subtitle-clip-to-element";
import { calculateTotalDuration } from "../opencut/timeline";
import {
  clipShotMetadata,
  elementShotFields,
  MAIN_VIDEO_LAYER_ID,
} from "./svfShotProjection";



/** OpenCut wasm 帧率结构（与 opencut-wasm FrameRate 一致）。 */

export interface ClassicFrameRate {

  numerator: number;

  denominator: number;

}



/** 规范化 Classic 项目 settings，修复 legacy 数字 fps。 */

export function normalizeClassicSettings(

  settings?: Partial<ClassicProjectJson["settings"]> | null,

): ClassicProjectJson["settings"] {

  const canvasSize = settings?.canvasSize ?? { width: 1920, height: 1080 };

  const background = settings?.background ?? { type: "color" as const, color: "#000000" };

  const rawFps = settings?.fps;

  let fps: ClassicFrameRate = DEFAULT_FPS;

  if (

    rawFps &&

    typeof rawFps === "object" &&

    typeof (rawFps as ClassicFrameRate).numerator === "number" &&

    typeof (rawFps as ClassicFrameRate).denominator === "number"

  ) {

    fps = rawFps as ClassicFrameRate;

  } else if (typeof rawFps === "number" && Number.isFinite(rawFps)) {

    fps = floatToFrameRate(rawFps);

  }

  return {

    fps,

    canvasSize,

    background,

    canvasSizeMode: settings?.canvasSizeMode,

    lastCustomCanvasSize: settings?.lastCustomCanvasSize,

    originalCanvasSize: settings?.originalCanvasSize,

  };

}



/** Classic 项目 JSON（避免直接依赖 opencut 类型以解耦构建）。 */

export interface ClassicProjectJson {

  metadata: {

    id: string;

    name: string;

    duration: number;

    createdAt: string;

    updatedAt: string;

  };

  scenes: ClassicSceneJson[];

  currentSceneId: string;

  settings: {

    fps: ClassicFrameRate;

    canvasSize: { width: number; height: number };

    background: { type: "color"; color: string };

    canvasSizeMode?: string;

    lastCustomCanvasSize?: { width: number; height: number } | null;

    originalCanvasSize?: { width: number; height: number } | null;

  };

  version: number;

  timelineViewState?: {

    zoomLevel: number;

    scrollLeft: number;

    playheadTime: number;

  };

}



export interface ClassicSceneJson {

  id: string;

  name: string;

  isMain: boolean;

  tracks: {

    main: ClassicTrackJson;

    overlay: ClassicTrackJson[];

    audio: ClassicTrackJson[];

  };

  bookmarks: unknown[];

  createdAt: string;

  updatedAt: string;

}



export interface ClassicTrackJson {

  id: string;

  name: string;

  type: string;

  elements: ClassicElementJson[];

  muted?: boolean;

  hidden?: boolean;

}



export interface ClassicElementJson {

  id: string;

  name: string;

  type: string;

  duration: number;

  startTime: number;

  trimStart: number;

  trimEnd: number;

  mediaId?: string;

  params?: Record<string, unknown>;

  metadata?: Record<string, unknown>;

  effects?: unknown[];

  masks?: unknown[];

  animations?: unknown;

  blendMode?: string;

  /** OpenCut 音频元素来源；TTS 配音须为 upload 才能被 AudioManager 播放。 */
  sourceType?: "upload" | "library";

  /** 源媒体全长（ticks）；audio/video 裁切语义必需。 */
  sourceDuration?: number;

}



/** 存入 EditTimeline.metadata 的 Classic 项目快照。 */

export interface ClassicProjectSnapshot {

  scenes?: ClassicSceneJson[];

  currentSceneId?: string;

  settings?: ClassicProjectJson["settings"];

  timelineViewState?: ClassicProjectJson["timelineViewState"];

  version?: number;

}



import { msToTicks, ticksToMs } from "./svfTimeTicks";



function ensureVideoLayers(timeline: EditTimelineData): VideoLayer[] {

  if (timeline.video_layers?.length) return timeline.video_layers;

  return [

    {

      id: MAIN_VIDEO_LAYER_ID,

      name: "主画面",

      z_index: 0,

      clips: timeline.tracks?.video ?? [],

    },

  ];

}



function readClassicSnapshot(timeline: EditTimelineData): ClassicProjectSnapshot | undefined {

  const raw = timeline.metadata?.classic_project;

  if (!raw || typeof raw !== "object") return undefined;

  return raw as ClassicProjectSnapshot;

}



/** 用户锁定 clip 时允许 Classic 快照覆盖布局；否则仅合并装饰字段。 */
function mergeSnapshotDecorations(
  base: ClassicElementJson,
  classic: ClassicElementJson,
  userLocked: boolean,
): ClassicElementJson {
  if (userLocked) {
    return {
      ...base,
      ...classic,
      id: base.id,
      type: base.type,
      mediaId: base.mediaId || classic.mediaId,
      metadata: { ...base.metadata, ...classic.metadata },
    };
  }
  return {
    ...base,
    name: classic.name || base.name,
    effects: classic.effects ?? base.effects,
    masks: classic.masks ?? base.masks,
    blendMode: classic.blendMode ?? base.blendMode,
    animations: classic.animations ?? base.animations,
    metadata: { ...base.metadata, ...classic.metadata },
  };
}

/** 按 clip id 将快照中的装饰字段合并到 API 投影场景。 */
function applySnapshotDecorationsToScenes(
  apiScenes: ClassicSceneJson[],
  snapshotScenes: ClassicSceneJson[],
): ClassicSceneJson[] {
  const index = new Map<string, ClassicElementJson>();
  for (const scene of snapshotScenes) {
    const tracks = [scene.tracks.main, ...scene.tracks.overlay, ...scene.tracks.audio];
    for (const track of tracks) {
      for (const el of track.elements) {
        index.set(el.id, el);
      }
    }
  }

  const decorateTrack = (track: ClassicTrackJson): ClassicTrackJson => ({
    ...track,
    elements: track.elements.map((el) => {
      const snap = index.get(el.id);
      if (!snap) return el;
      const clipForMatch: TrackClip = {
        id: el.id,
        start_ms: ticksToMs(el.startTime ?? 0),
        end_ms: ticksToMs(el.startTime ?? 0) + ticksToMs(el.duration ?? 0),
        metadata: el.metadata as TrackClip["metadata"],
      };
      const userLocked =
        Boolean(el.metadata?.user_locked) ||
        (el.metadata?.edited_by === "user" &&
          typeof snap.startTime === "number" &&
          typeof snap.duration === "number" &&
          classicLayoutMatchesApi(clipForMatch, snap));
      return mergeSnapshotDecorations(el, snap, userLocked);
    }),
  });

  return apiScenes.map((scene) => ({
    ...scene,
    tracks: {
      main: decorateTrack(scene.tracks.main),
      overlay: scene.tracks.overlay.map(decorateTrack),
      audio: scene.tracks.audio.map(decorateTrack),
    },
  }));
}



/** 将 Classic 快照中的 mediaId 重映射到当前剧本媒体列表。 */
function remapSnapshotScenes(
  scenes: ClassicSceneJson[],
  lookup: MediaIdLookup,
): ClassicSceneJson[] {
  const remapTrack = (track: ClassicTrackJson): ClassicTrackJson => ({
    ...track,
    elements: track.elements.map((el) => remapSnapshotElement(el, lookup)),
  });

  return scenes.map((scene) => ({
    ...scene,
    tracks: {
      main: remapTrack(scene.tracks.main),
      overlay: scene.tracks.overlay.map(remapTrack),
      audio: scene.tracks.audio.map(remapTrack),
    },
  }));
}

/** 重映射单个 Classic element 的 mediaId 与类型。 */
function remapSnapshotElement(
  el: ClassicElementJson,
  lookup: MediaIdLookup,
): ClassicElementJson {
  if (!el.mediaId || el.type === "text" || el.type === "effect") return el;

  const resolved = lookup.resolveMediaId({
    asset_ref: el.mediaId,
    preview_url: el.mediaId,
  });
  if (!resolved || !lookup.hasMediaId(resolved)) {
    if (el.mediaId && !lookup.hasMediaId(el.mediaId)) {
      console.warn(`[svfProjectAdapter] 未匹配媒体: ${el.mediaId}`);
    }
    return el;
  }

  const mediaType = lookup.getMediaType(resolved);
  return {
    ...el,
    mediaId: resolved,
    type:
      mediaType && (mediaType === "video" || mediaType === "image" || mediaType === "audio")
        ? mediaType === "audio"
          ? "audio"
          : mediaType
        : el.type,
  };
}

/** 确保 TTS 音频元素走 upload 分支，供 AudioManager 用已水合 File 解码。 */
function ensureUploadAudioSourceType(el: ClassicElementJson): ClassicElementJson {
  if (el.type !== "audio" || !el.mediaId) return el;
  if (el.sourceType === "upload") return el;
  return { ...el, sourceType: "upload" };
}

function resolveSourceDurationMs(
  mediaId: string | undefined,
  lookup: MediaIdLookup,
  clipDurationMs: number,
  projectKey?: string,
): number {
  let resolvedMs = clipDurationMs;
  if (projectKey && mediaId) {
    const cached = getSvfProjectMediaCache(projectKey).find((asset) => asset.id === mediaId);
    if (cached?.duration != null && cached.duration > 0) {
      resolvedMs = Math.max(resolvedMs, Math.round(cached.duration * 1000));
    }
  }
  const sec = mediaId ? lookup.getMediaDurationSec(mediaId) : undefined;
  if (sec != null && sec > 0) {
    resolvedMs = Math.max(resolvedMs, Math.round(sec * 1000));
  }
  return resolvedMs;
}

/** 校验 Classic 快照时序是否与 API clip 区间一致，避免错误保存的紧凑布局覆盖计划时长。 */
function classicLayoutMatchesApi(clip: TrackClip, classic: ClassicElementJson): boolean {
  const apiStart = clip.start_ms ?? 0;
  const apiEnd = clip.end_ms ?? apiStart + 1000;
  const apiDurMs = apiEnd - apiStart;
  const classicStartMs = ticksToMs(classic.startTime ?? 0);
  const classicDurMs = ticksToMs(classic.duration ?? 0);
  const startDrift = Math.abs(classicStartMs - apiStart);
  const endDrift = Math.abs(classicStartMs + classicDurMs - apiEnd);
  if (startDrift > 500) return false;
  if (classicDurMs < apiDurMs * 0.7) return false;
  if (endDrift > 500) return false;
  return true;
}

/** 用户已在 OpenCut 保存过布局时，Classic 快照的 startTime/duration 优先于 API 重算。 */
function isClassicLayoutLocked(clip: TrackClip): boolean {
  if (Boolean(clip.metadata?.user_locked)) return true;
  const classic = clip.metadata?.classic;
  if (!classic || typeof classic !== "object") return false;
  if (clip.metadata?.edited_by !== "user") return false;
  const c = classic as ClassicElementJson;
  if (typeof c.startTime !== "number" || typeof c.duration !== "number") return false;
  return classicLayoutMatchesApi(clip, c);
}

/** 音频 clip 区间短于源文件时扩展可见时长（非 user_locked）。 */
function resolveAudioClipDurationMs(
  clip: TrackClip,
  elementType: string,
  clipDurationMs: number,
  sourceDurationMs: number,
): number {
  if (elementType !== "audio") return clipDurationMs;
  if (isClassicLayoutLocked(clip)) return clipDurationMs;
  if (sourceDurationMs <= clipDurationMs + 50) return clipDurationMs;
  return sourceDurationMs;
}

function clipToElement(
  clip: TrackClip,
  mediaType: string,
  lookup: MediaIdLookup,
  canvas: CanvasSize,
  projectKey?: string,
): ClassicElementJson {
  const start = clip.start_ms ?? 0;
  // end_ms 缺失时兜底 +1000ms，与后端 _parse_clip_from_raw 保持一致
  const end = clip.end_ms ?? start + 1000;
  const duration = end - start;
  const resolved = interpolateTransform(clip, 0);
  const motionAnimations =
    mediaType === "audio" ? [] : buildMotionAnimations(clip, canvas);
  const mediaId = resolveMediaIdForClip(clip, lookup);
  const elementType =
    mediaType === "video" ? "video" : mediaType === "audio" ? "audio" : "image";

  const sourceDurationMs = resolveSourceDurationMs(mediaId, lookup, duration, projectKey);
  const visibleDurationMs = resolveAudioClipDurationMs(
    clip,
    elementType,
    duration,
    sourceDurationMs,
  );
  const trimFields =
    elementType === "audio" || elementType === "video"
      ? computeMediaTrimFields(visibleDurationMs, sourceDurationMs, {
          // 视频槽位长于源时长时同样 pad，配合导出 freeze/慢放铺满配音
          padSourceToClip: elementType === "audio" || elementType === "video",
        })
      : null;

  const shotMeta = clipShotMetadata(clip);

  const playbackRateRaw = clip.metadata?.playback_rate;
  const playbackRate =
    typeof playbackRateRaw === "number" && playbackRateRaw > 0
      ? playbackRateRaw
      : typeof playbackRateRaw === "string" && Number(playbackRateRaw) > 0
        ? Number(playbackRateRaw)
        : 1;

  const base: ClassicElementJson = {
    id: clip.id || `clip_${start}`,
    name:
      clip.label && clip.label !== (clip.id || "")
        ? clip.label
        : elementType === "audio"
          ? "配音"
          : clip.id || "片段",
    type: elementType,
    duration: msToTicks(visibleDurationMs),
    startTime: msToTicks(start),
    trimStart: trimFields?.trimStart ?? 0,
    trimEnd: trimFields?.trimEnd ?? 0,
    ...(trimFields ? { sourceDuration: trimFields.sourceDuration } : {}),
    mediaId,
    params: {
      ...svfTransformToOpenCutParams(resolved, canvas),
      ...(elementType === "audio" ? { volume: 1 } : {}),
    },
    animations: motionAnimations,
    // 音画协调写入的 playback_rate → OpenCut retime
    ...(Math.abs(playbackRate - 1) > 0.001
      ? { retime: { rate: playbackRate } }
      : {}),
    metadata: {
      svf: {
        motion: clip.motion,
        transition_in: clip.transition_in,
        transition_out: clip.transition_out,
        background: clip.background,
        keyframes: clip.transform?.keyframes,
        motion_detail: clip.motion_detail,
        layer_id: clip.layer_id,
        track: clip.track,
      },
      edited_by: clip.metadata?.edited_by,
      user_locked: clip.metadata?.user_locked,
      playback_rate: playbackRate !== 1 ? playbackRate : undefined,
      freeze_tail_ms: clip.metadata?.freeze_tail_ms,
      ...shotMeta,
    },
  };

  const classicMeta = clip.metadata?.classic;
  if (classicMeta && typeof classicMeta === "object") {
    const userLocked = isClassicLayoutLocked(clip);
    return ensureUploadAudioSourceType(
      reconcileElementMediaType(
        mergeSnapshotDecorations(base, classicMeta as ClassicElementJson, userLocked),
        lookup,
      ),
    );
  }

  return ensureUploadAudioSourceType(reconcileElementMediaType(base, lookup));
}



/** 按媒体库类型校正 element type，避免 classic 快照锁死错误分支。 */

function reconcileElementMediaType(

  el: ClassicElementJson,

  lookup: MediaIdLookup,

): ClassicElementJson {

  return remapSnapshotElement(el, lookup);

}

function elementToClip(
  el: ClassicElementJson,
  track: TrackClip["track"],
  layerId?: string,
  canvas: CanvasSize = resolveCanvasSize(),
): TrackClip {
  const svfMeta = (el.metadata?.svf || {}) as Record<string, unknown>;
  const startMs = ticksToMs(el.startTime);
  const endMs = startMs + ticksToMs(el.duration);
  const params = el.params || {};
  const { metadata: _meta, ...classicRest } = el;
  const { source_refs, metadata: shotMeta } = elementShotFields(el);

  const animationKeyframes = extractSvfKeyframesFromElement(
    el.animations as ElementAnimations | undefined,
    params,
    canvas,
  );
  const legacyKeyframes = svfMeta.keyframes as TrackClip["transform"] extends {
    keyframes?: infer K;
  }
    ? K
    : never;
  const keyframes =
    animationKeyframes.length > 0 ? animationKeyframes : legacyKeyframes;

  let motion = svfMeta.motion as string | undefined;
  let motion_detail = svfMeta.motion_detail as TrackClip["motion_detail"];
  if (
    animationKeyframes.length > 0 &&
    shouldFlattenMotionForSavedKeyframes(animationKeyframes)
  ) {
    motion = "static";
    motion_detail = stripKenBurnsScaleFromMotionDetail(
      motion_detail as Record<string, unknown> | undefined,
    ) as TrackClip["motion_detail"];
  }

  return {
    id: el.id,
    track,
    start_ms: startMs,
    end_ms: endMs,
    label: el.name,
    asset_ref: el.mediaId,
    layer_id: layerId,
    source_refs,
    motion,
    motion_detail,
    transition_in: svfMeta.transition_in as TrackClip["transition_in"],
    transition_out: svfMeta.transition_out as TrackClip["transition_out"],
    background: svfMeta.background as TrackClip["background"],
    transform: {
      ...openCutParamsToSvfTransform(params, canvas),
      keyframes,
    },
    metadata: {
      edited_by: el.metadata?.edited_by as string | undefined,
      user_locked: el.metadata?.user_locked as boolean | undefined,
      ...shotMeta,
      // OpenCut retime → 领域 playback_rate（导出 FFmpeg setpts/atempo）
      playback_rate:
        typeof (el as { retime?: { rate?: number } }).retime?.rate === "number"
          ? (el as { retime: { rate: number } }).retime.rate
          : (el.metadata?.playback_rate as number | undefined),
      freeze_tail_ms: el.metadata?.freeze_tail_ms as number | undefined,
      classic: classicRest,
    },
  };
}



/** 生成时间轴内容指纹（不含 revision/updated_at），用于 soft-reload 判定。 */
export function buildTimelineFingerprint(timeline: EditTimelineData): string {
  const layerSig = (timeline.video_layers ?? [])
    .flatMap((layer) =>
      (layer.clips ?? []).map(
        (c) =>
          `${c.id ?? ""}:${c.start_ms ?? 0}:${c.end_ms ?? 0}:${c.asset_ref ?? ""}:${c.layer_id ?? ""}`,
      ),
    )
    .join("|");
  const audioSig = (timeline.tracks?.audio ?? [])
    .map(
      (c) =>
        `${c.id ?? ""}:${c.start_ms ?? 0}:${c.end_ms ?? 0}:${c.asset_ref ?? ""}`,
    )
    .join("|");
  // 不含 revision/updated_at：自动 PATCH 只抬版本号时不得触发预览重载闪烁。
  return `${layerSig}:A:${audioSig}:${timeline.duration_ms ?? 0}`;
}

/** 审计 Classic 项目投影时长是否与 EditTimeline duration_ms 一致。 */
export function auditClassicProjectDuration(
  project: ClassicProjectJson,
  expectedDurationMs: number,
): { projectedMs: number; expectedMs: number; ok: boolean } {
  const scene =
    project.scenes.find((s) => s.id === project.currentSceneId) || project.scenes[0];
  if (!scene) {
    return { projectedMs: 0, expectedMs: expectedDurationMs, ok: false };
  }
  const ticks = calculateTotalDuration({
    tracks: scene.tracks as import("../opencut/timeline/types").SceneTracks,
  });
  const projectedMs = ticksToMs(ticks);
  return {
    projectedMs,
    expectedMs: expectedDurationMs,
    ok: Math.abs(projectedMs - expectedDurationMs) <= 500,
  };
}



/** 从 SVF EditTimeline 与媒体列表构建 Classic 项目 JSON。 */

export function loadFromSvf(

  timeline: EditTimelineData,

  mediaAssets: MediaBinItem[],

  projectKey: string,

  scriptName?: string,

): ClassicProjectJson {

  const snapshot = readClassicSnapshot(timeline);

  const lookup = buildMediaIdLookup(mediaAssets);

  const canvas = resolveCanvasSize(timeline.metadata);

  const layers = [...ensureVideoLayers(timeline)].sort(
    (a, b) => (a.z_index ?? 0) - (b.z_index ?? 0),
  );

  const mainLayer = layers[0];

  const overlayLayers = layers.slice(1);

  const now = new Date().toISOString();

  const sceneId = snapshot?.currentSceneId || `scene_${projectKey}`;

  const mainClips = sortClipsForExport(mainLayer?.clips ?? []);

  const mainTrack: ClassicTrackJson = {
    id: "track_main",
    name: mainLayer?.name || "主画面",
    type: "video",
    elements: mainClips.map((c) =>
      clipToElement(c, inferClipMediaType(c, lookup, "image"), lookup, canvas, projectKey),
    ),
    muted: false,
    hidden: false,
  };



  const overlayTracks: ClassicTrackJson[] = overlayLayers.map((layer, idx) => ({

    id: layer.id || `track_overlay_${idx}`,

    name: layer.name || `视频层 ${idx + 2}`,

    type: "video",

    elements: (layer.clips ?? []).map((c) =>
      clipToElement(c, inferClipMediaType(c, lookup, "image"), lookup, canvas, projectKey),
    ),

    muted: false,

    hidden: false,

  }));



  const audioTracks: ClassicTrackJson[] = [

    {

      id: "track_audio_0",

      name: "音频",

      type: "audio",

      elements: (timeline.tracks?.audio ?? []).map((c) =>
        clipToElement(c, inferClipMediaType(c, lookup, "audio"), lookup, canvas, projectKey),
      ),

      muted: false,

    },

  ];



  const textTrack: ClassicTrackJson = {

    id: "track_text_0",

    name: "字幕",

    type: "text",

    elements: (timeline.tracks?.subtitle ?? []).map((c, index) => {
      const base = subtitleClipToTextElement({ clip: c, canvas, index });
      const classicMeta = c.metadata?.classic;
      if (classicMeta && typeof classicMeta === "object") {
        const userLocked = isClassicLayoutLocked(c);
        return mergeSnapshotDecorations(
          base,
          classicMeta as ClassicElementJson,
          userLocked,
        );
      }
      return base;
    }),

    hidden: false,

  };



  if (textTrack.elements.length > 0) {

    overlayTracks.push(textTrack);

  }



  const defaultScenes: ClassicSceneJson[] = [

    {

      id: sceneId,

      name: "主场景",

      isMain: true,

      tracks: {

        main: mainTrack,

        overlay: overlayTracks,

        audio: audioTracks,

      },

      bookmarks: [],

      createdAt: now,

      updatedAt: now,

    },

  ];



  let scenes = defaultScenes;

  if (snapshot?.scenes?.length) {
    scenes = applySnapshotDecorationsToScenes(
      defaultScenes,
      remapSnapshotScenes(snapshot.scenes, lookup),
    );
  }

  const settings = normalizeClassicSettings(snapshot?.settings);

  const activeScene = scenes.find((s) => s.id === (snapshot?.currentSceneId || sceneId)) || scenes[0];
  const sceneDurationTicks = activeScene
    ? calculateTotalDuration({ tracks: activeScene.tracks as import("../opencut/timeline/types").SceneTracks })
    : 0;
  const storedDurationTicks = msToTicks(timeline.duration_ms || 0);
  const projectDurationTicks =
    sceneDurationTicks > 0 ? sceneDurationTicks : storedDurationTicks;

  return {

    metadata: {

      id: projectKey,

      name: scriptName || "SVF 剪辑项目",

      duration: projectDurationTicks,

      createdAt: now,

      updatedAt: now,

    },

    scenes,

    currentSceneId: snapshot?.currentSceneId || scenes[0]?.id || sceneId,

    settings,

    version: snapshot?.version ?? 22,

    timelineViewState: snapshot?.timelineViewState ?? {

      zoomLevel: 1,

      scrollLeft: 0,

      playheadTime: 0,

    },

  };

}



/** 将 Classic 项目 JSON 转回 SVF PATCH 请求体。 */

export function saveToSvf(

  project: ClassicProjectJson,

  base: EditTimelineData,

): EditTimelineData {

  const scene = project.scenes.find((s) => s.id === project.currentSceneId) || project.scenes[0];

  if (!scene) return base;

  const canvas = resolveCanvasSize(base.metadata);

  const videoLayers: VideoLayer[] = [];

  const mainClips = scene.tracks.main.elements.map((el) =>
    elementToClip(el, "video", MAIN_VIDEO_LAYER_ID, canvas),
  );

  videoLayers.push({

    id: MAIN_VIDEO_LAYER_ID,

    name: scene.tracks.main.name || "主画面",

    z_index: 0,

    clips: mainClips,

  });



  let z = 1;

  for (const track of scene.tracks.overlay) {

    if (track.type === "text") continue;

    videoLayers.push({

      id: track.id,

      name: track.name,

      z_index: z++,

      clips: track.elements.map((el) => elementToClip(el, "video", track.id, canvas)),

    });

  }



  const textTrack = scene.tracks.overlay.find((t) => t.type === "text");

  const subtitleClips = (textTrack?.elements ?? []).map((el) =>
    elementToClip(el, "subtitle", undefined, canvas),
  );

  const audioClips = scene.tracks.audio.flatMap((t) =>
    t.elements.map((el) => elementToClip(el, "audio", undefined, canvas)),
  );



  const maxEnd = Math.max(

    base.duration_ms,

    ...videoLayers.flatMap((l) => (l.clips ?? []).map((c) => c.end_ms ?? 0)),

    ...audioClips.map((c) => c.end_ms ?? 0),

    ...subtitleClips.map((c) => c.end_ms ?? 0),

    0,

  );



  const flatVideo = videoLayers.flatMap((l) =>

    (l.clips ?? []).map((c) => ({ ...c, layer_id: l.id, track: "video" as const })),

  );



  const classicProject: ClassicProjectSnapshot = {

    scenes: project.scenes,

    currentSceneId: project.currentSceneId,

    settings: normalizeClassicSettings(project.settings),

    timelineViewState: project.timelineViewState,

    version: project.version,

  };



  return {

    ...base,

    duration_ms: maxEnd,

    video_layers: videoLayers,

    tracks: {

      video: flatVideo,

      audio: audioClips,

      subtitle: subtitleClips,

    },

    metadata: {

      ...(base.metadata || {}),

      classic_project: classicProject,

    },

    user_edited: true,

    last_edited_by: "user",

  };

}



export { msToTicks, ticksToMs } from "./svfTimeTicks";

export function svfProjectKey(projectId: string, scriptId: string): string {

  return `${projectId}__${scriptId}`;

}



/** 解析 SVF 复合键。 */

export function parseSvfProjectKey(key: string): { projectId: string; scriptId: string } | null {

  const idx = key.indexOf("__");

  if (idx <= 0) return null;

  return { projectId: key.slice(0, idx), scriptId: key.slice(idx + 2) };

}


