/** 编辑器数据类型定义 */

export interface EditorClip {
  id: string;
  track: "video" | "audio" | "subtitle";
  startMs: number;
  endMs: number;
  label: string;
  assetRef?: string;
  previewUrl?: string;
  previewMediaType?: string;
  layerId?: string;
  motion?: string;
  transitionIn?: { type: string; durationMs: number };
  transitionOut?: { type: string; durationMs: number };
  background?: { type: string; color: string; assetRef?: string };
  transform?: ClipTransform;
  metadata?: Record<string, unknown>;
}

export interface ClipTransform {
  x: number;
  y: number;
  width: number;
  height: number;
  opacity: number;
  rotation: number;
  keyframes?: ClipKeyframe[];
}

export interface ClipKeyframe {
  timeMs: number;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  opacity?: number;
  rotation?: number;
}

export interface VideoLayer {
  id: string;
  name: string;
  zIndex: number;
  clips: EditorClip[];
}

export interface EditorTimeline {
  durationMs: number;
  revision: number;
  videoLayers: VideoLayer[];
  audioClips: EditorClip[];
  subtitleClips: EditorClip[];
}

export interface MediaAsset {
  id: string;
  name: string;
  type: "image" | "audio" | "video" | "final";
  url: string;
  isAccessible: boolean;
  durationMs?: number;
  sourceAssetId?: string;
}

/** postMessage 命令 */
export interface HostCommand {
  source: "super-video-generator";
  type: "load_project" | "apply_action" | "seek_to" | "play" | "pause" | "export" | "ping";
  [key: string]: unknown;
}

/** 回传给宿主的消息 */
export interface EditorEvent {
  source: "video-editor";
  type: "ready" | "timeline_changed" | "playhead" | "selection_changed" | "pong" | "error";
  [key: string]: unknown;
}

export function emptyTimeline(): EditorTimeline {
  return {
    durationMs: 0,
    revision: 0,
    videoLayers: [{ id: "main", name: "主画面", zIndex: 0, clips: [] }],
    audioClips: [],
    subtitleClips: [],
  };
}

export function defaultTransform(): ClipTransform {
  return { x: 0.5, y: 0.5, width: 1, height: 1, opacity: 1, rotation: 0 };
}
