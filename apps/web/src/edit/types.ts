/** Edit Studio 类型 */

export type TrackKind = "video" | "audio" | "subtitle";

export interface ClipKeyframe {
  time_ms?: number;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  scale?: number;
  opacity?: number;
  rotation?: number;
}

export interface ClipTransform {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  opacity?: number;
  rotation?: number;
  keyframes?: ClipKeyframe[];
}

export interface TrackClip {
  id?: string;
  track?: TrackKind;
  start_ms?: number;
  end_ms?: number;
  label?: string;
  motion?: string;
  edit_description?: string;
  transition_in?: { type?: string; duration_ms?: number };
  transition_out?: { type?: string; duration_ms?: number };
  background?: { type?: string; color?: string; asset_ref?: string };
  motion_detail?: Record<string, unknown>;
  source_refs?: Record<string, unknown>;
  preview_url?: string;
  preview_media_type?: string;
  asset_ref?: string;
  layer_id?: string;
  transform?: ClipTransform;
  metadata?: Record<string, unknown>;
}

export interface VideoLayer {
  id?: string;
  name?: string;
  z_index?: number;
  clips?: TrackClip[];
}

export interface EditTimelineData {
  timeline_id?: string;
  plan_id?: string;
  duration_ms: number;
  revision?: number;
  user_edited?: boolean;
  last_edited_by?: string;
  updated_at?: string;
  editable?: boolean;
  tracks: Record<TrackKind, TrackClip[]>;
  video_layers?: VideoLayer[];
}

export interface EditCapabilities {
  motions?: string[];
  motion_aliases?: Record<string, string>;
  transitions?: string[];
  backgrounds?: string[];
  transition_max_duration_ms?: number;
  ffmpeg_available?: boolean;
  ffmpeg_bundled?: boolean;
  export_enabled?: boolean;
  ffmpeg_path?: string;
  max_video_layers?: number;
}

export interface MediaBinItem {
  id: string;
  name: string;
  type: string;
  url?: string;
  link?: string;
  duration_ms?: number;
}

export const DEFAULT_TRANSFORM: ClipTransform = {
  x: 0.5,
  y: 0.5,
  width: 1,
  height: 1,
  opacity: 1,
  rotation: 0,
  keyframes: [],
};
