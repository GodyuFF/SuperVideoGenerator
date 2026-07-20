/**
 * EditTimeline（SVF snake_case API）↔ EditorTimeline（前端 camelCase）双向映射。
 */

import type {
  EditTimelineData,
  TrackClip,
  VideoLayer,
} from "../../edit/types";
import type {
  EditorClip,
  EditorTimeline,
  MediaAsset,
  VideoLayer as EditorVideoLayer,
} from "../types";
import { defaultTransform, emptyTimeline } from "../types";
import { MAIN_VIDEO_LAYER_ID } from "./svfShotProjection";

/** 将 API 时间轴转为编辑器内部模型。 */
export function apiToEditorTimeline(data: EditTimelineData | null): EditorTimeline {
  if (!data) return emptyTimeline();

  const mapClip = (c: TrackClip, track: EditorClip["track"]): EditorClip => ({
    id: c.id || `clip_${Math.random().toString(36).slice(2, 9)}`,
    track,
    startMs: c.start_ms ?? 0,
    endMs: c.end_ms ?? 0,
    label: c.label || "",
    assetRef: c.asset_ref,
    previewUrl: c.preview_url,
    previewMediaType: c.preview_media_type,
    layerId: c.layer_id,
    motion: c.motion,
    transitionIn: c.transition_in
      ? { type: c.transition_in.type || "cut", durationMs: c.transition_in.duration_ms ?? 0 }
      : undefined,
    transitionOut: c.transition_out
      ? { type: c.transition_out.type || "cut", durationMs: c.transition_out.duration_ms ?? 0 }
      : undefined,
    background: c.background as EditorClip["background"],
    transform: c.transform
      ? {
          x: c.transform.x ?? 0.5,
          y: c.transform.y ?? 0.5,
          width: c.transform.width ?? 1,
          height: c.transform.height ?? 1,
          opacity: c.transform.opacity ?? 1,
          rotation: c.transform.rotation ?? 0,
          keyframes: (c.transform.keyframes || []).map((k) => ({
            timeMs: k.time_ms ?? 0,
            x: k.x,
            y: k.y,
            width: k.width,
            height: k.height,
            opacity: k.opacity,
            rotation: k.rotation,
          })),
        }
      : defaultTransform(),
    metadata: c.metadata,
  });

  const videoLayers: EditorVideoLayer[] = (data.video_layers?.length
    ? data.video_layers
    : [{ id: MAIN_VIDEO_LAYER_ID, name: "主画面", z_index: 0, clips: data.tracks?.video || [] }]
  ).map((lyr: VideoLayer) => ({
    id: lyr.id || MAIN_VIDEO_LAYER_ID,
    name: lyr.name || "主画面",
    zIndex: lyr.z_index ?? 0,
    clips: (lyr.clips || []).map((c) => mapClip({ ...c, track: "video" }, "video")),
  }));

  return {
    durationMs: data.duration_ms ?? 0,
    revision: data.revision ?? 0,
    videoLayers,
    audioClips: (data.tracks?.audio || []).map((c) => mapClip(c, "audio")),
    subtitleClips: (data.tracks?.subtitle || []).map((c) => mapClip(c, "subtitle")),
  };
}

/** 将编辑器内部模型转为 PATCH API 请求体。 */
export function editorToApiPatch(
  editor: EditorTimeline,
  meta?: Partial<EditTimelineData>,
): Pick<EditTimelineData, "tracks" | "video_layers" | "duration_ms"> & Partial<EditTimelineData> {
  const toTrackClip = (c: EditorClip): TrackClip => ({
    id: c.id,
    track: c.track,
    start_ms: c.startMs,
    end_ms: c.endMs,
    label: c.label,
    asset_ref: c.assetRef,
    preview_url: c.previewUrl,
    preview_media_type: c.previewMediaType,
    layer_id: c.layerId,
    motion: c.motion,
    transition_in: c.transitionIn
      ? { type: c.transitionIn.type, duration_ms: c.transitionIn.durationMs }
      : undefined,
    transition_out: c.transitionOut
      ? { type: c.transitionOut.type, duration_ms: c.transitionOut.durationMs }
      : undefined,
    background: c.background,
    transform: c.transform
      ? {
          x: c.transform.x,
          y: c.transform.y,
          width: c.transform.width,
          height: c.transform.height,
          opacity: c.transform.opacity,
          rotation: c.transform.rotation,
          keyframes: (c.transform.keyframes || []).map((k) => ({
            time_ms: k.timeMs,
            x: k.x,
            y: k.y,
            width: k.width,
            height: k.height,
            opacity: k.opacity,
            rotation: k.rotation,
          })),
        }
      : undefined,
    metadata: c.metadata,
  });

  return {
    ...meta,
    duration_ms: editor.durationMs,
    video_layers: editor.videoLayers.map((lyr) => ({
      id: lyr.id,
      name: lyr.name,
      z_index: lyr.zIndex,
      clips: lyr.clips.map(toTrackClip),
    })),
    tracks: {
      video: editor.videoLayers.flatMap((l) => l.clips.map(toTrackClip)),
      audio: editor.audioClips.map(toTrackClip),
      subtitle: editor.subtitleClips.map(toTrackClip),
    },
  };
}

/** 合并 API 响应与时间轴元数据。 */
export function mergeApiTimeline(
  editor: EditorTimeline,
  api: EditTimelineData,
): EditTimelineData {
  const patch = editorToApiPatch(editor);
  return {
    ...api,
    ...patch,
    revision: api.revision ?? editor.revision,
    user_edited: api.user_edited,
    last_edited_by: api.last_edited_by,
    timeline_id: api.timeline_id,
    plan_id: api.plan_id,
  };
}

/** 媒体 API 项 → 编辑器 MediaAsset。 */
export function apiMediaToEditor(
  items: Array<{
    id: string;
    name: string;
    type: string;
    url: string;
    is_accessible?: boolean;
    duration_ms?: number;
    source_asset_id?: string;
  }>,
): MediaAsset[] {
  return items.map((m) => ({
    id: m.id,
    name: m.name,
    type: (m.type as MediaAsset["type"]) || "image",
    url: m.url,
    isAccessible: m.is_accessible ?? true,
    durationMs: m.duration_ms,
    sourceAssetId: m.source_asset_id,
  }));
}
