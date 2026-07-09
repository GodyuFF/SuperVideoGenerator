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

import { DEFAULT_TRANSFORM } from "../../edit/types";

import {

  buildMediaIdLookup,

  inferClipMediaType,

  resolveMediaIdForClip,

  type MediaIdLookup,

} from "./SvfMediaBridge";

import { DEFAULT_FPS } from "../opencut/fps/defaults";

import { floatToFrameRate } from "../opencut/fps/utils";



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

}



/** 存入 EditTimeline.metadata 的 Classic 项目快照。 */

export interface ClassicProjectSnapshot {

  scenes?: ClassicSceneJson[];

  currentSceneId?: string;

  settings?: ClassicProjectJson["settings"];

  timelineViewState?: ClassicProjectJson["timelineViewState"];

  version?: number;

}



const TICKS_PER_SECOND = 48000;



/** 毫秒转 Classic MediaTime ticks。 */

export function msToTicks(ms: number): number {

  return Math.round((ms / 1000) * TICKS_PER_SECOND);

}



/** Classic MediaTime ticks 转毫秒。 */

export function ticksToMs(ticks: number): number {

  return Math.round((ticks / TICKS_PER_SECOND) * 1000);

}



function ensureVideoLayers(timeline: EditTimelineData): VideoLayer[] {

  if (timeline.video_layers?.length) return timeline.video_layers;

  return [

    {

      id: "vly_main",

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



function mergeClassicElement(

  base: ClassicElementJson,

  classic?: unknown,

): ClassicElementJson {

  if (!classic || typeof classic !== "object") return base;

  const c = classic as Record<string, unknown>;

  return {

    ...base,

    ...c,

    id: base.id,

    name: (c.name as string) || base.name,

    type: (c.type as string) || base.type,

    duration: (c.duration as number) ?? base.duration,

    startTime: (c.startTime as number) ?? base.startTime,

    trimStart: (c.trimStart as number) ?? base.trimStart,

    trimEnd: (c.trimEnd as number) ?? base.trimEnd,

    mediaId: (c.mediaId as string) || base.mediaId,

    params: { ...base.params, ...((c.params as Record<string, unknown>) || {}) },

    metadata: { ...base.metadata, ...((c.metadata as Record<string, unknown>) || {}) },

    effects: (c.effects as unknown[]) ?? base.effects,

    masks: (c.masks as unknown[]) ?? base.masks,

    animations: c.animations ?? base.animations,

    blendMode: (c.blendMode as string) ?? base.blendMode,

  };

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

function clipToElement(

  clip: TrackClip,

  mediaType: string,

  lookup: MediaIdLookup,

): ClassicElementJson {

  const start = clip.start_ms ?? 0;

  const end = clip.end_ms ?? start + 3000;

  const duration = end - start;

  const tr = { ...DEFAULT_TRANSFORM, ...clip.transform };

  const base: ClassicElementJson = {

    id: clip.id || `clip_${start}`,

    name: clip.label || clip.id || "片段",

    type: mediaType === "video" ? "video" : mediaType === "audio" ? "audio" : "image",

    duration: msToTicks(duration),

    startTime: msToTicks(start),

    trimStart: 0,

    trimEnd: msToTicks(duration),

    mediaId: resolveMediaIdForClip(clip, lookup),

    params: {

      opacity: tr.opacity ?? 1,

      "transform.positionX": (tr.x ?? 0.5) - 0.5,

      "transform.positionY": (tr.y ?? 0.5) - 0.5,

      "transform.scaleX": tr.width ?? 1,

      "transform.scaleY": tr.height ?? 1,

      "transform.rotate": tr.rotation ?? 0,

    },

    metadata: {

      svf: {

        motion: clip.motion,

        transition_in: clip.transition_in,

        transition_out: clip.transition_out,

        background: clip.background,

        keyframes: clip.transform?.keyframes,

        layer_id: clip.layer_id,

        track: clip.track,

      },

      edited_by: clip.metadata?.edited_by,

      user_locked: clip.metadata?.user_locked,

    },

  };

  const merged = mergeClassicElement(base, clip.metadata?.classic);

  return reconcileElementMediaType(merged, lookup);

}



/** 按媒体库类型校正 element type，避免 classic 快照锁死错误分支。 */

function reconcileElementMediaType(

  el: ClassicElementJson,

  lookup: MediaIdLookup,

): ClassicElementJson {

  return remapSnapshotElement(el, lookup);

}

function elementToClip(el: ClassicElementJson, track: TrackClip["track"], layerId?: string): TrackClip {

  const svfMeta = (el.metadata?.svf || {}) as Record<string, unknown>;

  const startMs = ticksToMs(el.startTime);

  const endMs = startMs + ticksToMs(el.duration);

  const params = el.params || {};

  const { metadata: _meta, ...classicRest } = el;

  return {

    id: el.id,

    track,

    start_ms: startMs,

    end_ms: endMs,

    label: el.name,

    asset_ref: el.mediaId,

    layer_id: layerId,

    motion: svfMeta.motion as string | undefined,

    transition_in: svfMeta.transition_in as TrackClip["transition_in"],

    transition_out: svfMeta.transition_out as TrackClip["transition_out"],

    background: svfMeta.background as TrackClip["background"],

    transform: {

      x: 0.5 + Number(params["transform.positionX"] ?? 0),

      y: 0.5 + Number(params["transform.positionY"] ?? 0),

      width: Number(params["transform.scaleX"] ?? 1),

      height: Number(params["transform.scaleY"] ?? 1),

      opacity: Number(params.opacity ?? 1),

      rotation: Number(params["transform.rotate"] ?? 0),

      keyframes: svfMeta.keyframes as TrackClip["transform"] extends { keyframes?: infer K }

        ? K

        : never,

    },

    metadata: {

      edited_by: el.metadata?.edited_by as string | undefined,

      user_locked: el.metadata?.user_locked as boolean | undefined,

      classic: classicRest,

    },

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

  const layers = [...ensureVideoLayers(timeline)].sort(

    (a, b) => (a.z_index ?? 0) - (b.z_index ?? 0),

  );

  const mainLayer = layers[0];

  const overlayLayers = layers.slice(1);

  const now = new Date().toISOString();

  const sceneId = snapshot?.currentSceneId || `scene_${projectKey}`;



  const mainTrack: ClassicTrackJson = {

    id: "track_main",

    name: mainLayer?.name || "主画面",

    type: "video",

    elements: (mainLayer?.clips ?? []).map((c) =>

      clipToElement(c, inferClipMediaType(c, lookup, "image"), lookup),

    ),

    muted: false,

    hidden: false,

  };



  const overlayTracks: ClassicTrackJson[] = overlayLayers.map((layer, idx) => ({

    id: layer.id || `track_overlay_${idx}`,

    name: layer.name || `视频层 ${idx + 2}`,

    type: "video",

    elements: (layer.clips ?? []).map((c) =>

      clipToElement(c, inferClipMediaType(c, lookup, "image"), lookup),

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

        clipToElement(c, inferClipMediaType(c, lookup, "audio"), lookup),

      ),

      muted: false,

    },

  ];



  const textTrack: ClassicTrackJson = {

    id: "track_text_0",

    name: "字幕",

    type: "text",

    elements: (timeline.tracks?.subtitle ?? []).map((c) => ({

      ...clipToElement(c, "text", lookup),

      type: "text",

      params: {

        content: c.label || "",

        ...(clipToElement(c, "text", lookup).params || {}),

      },

    })),

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



  const scenes = snapshot?.scenes?.length
    ? remapSnapshotScenes(snapshot.scenes, lookup)
    : defaultScenes;

  const settings = normalizeClassicSettings(snapshot?.settings);



  return {

    metadata: {

      id: projectKey,

      name: scriptName || "SVF 剪辑项目",

      duration: msToTicks(timeline.duration_ms || 0),

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



  const videoLayers: VideoLayer[] = [];

  const mainClips = scene.tracks.main.elements.map((el) =>

    elementToClip(el, "video", "vly_main"),

  );

  videoLayers.push({

    id: "vly_main",

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

      clips: track.elements.map((el) => elementToClip(el, "video", track.id)),

    });

  }



  const textTrack = scene.tracks.overlay.find((t) => t.type === "text");

  const subtitleClips = (textTrack?.elements ?? []).map((el) => elementToClip(el, "subtitle"));



  const audioClips = scene.tracks.audio.flatMap((t) =>

    t.elements.map((el) => elementToClip(el, "audio")),

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



/** SVF 项目复合键。 */

export function svfProjectKey(projectId: string, scriptId: string): string {

  return `${projectId}__${scriptId}`;

}



/** 解析 SVF 复合键。 */

export function parseSvfProjectKey(key: string): { projectId: string; scriptId: string } | null {

  const idx = key.indexOf("__");

  if (idx <= 0) return null;

  return { projectId: key.slice(0, idx), scriptId: key.slice(idx + 2) };

}


