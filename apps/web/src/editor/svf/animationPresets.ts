import type { ClipTransform, TrackClip } from "./types";
import { DEFAULT_TRANSFORM } from "./types";

export interface AnimationPreset {
  id: string;
  label: string;
}

export const ANIMATION_PRESETS: AnimationPreset[] = [
  { id: "fade_in", label: "淡入" },
  { id: "fade_out", label: "淡出" },
  { id: "zoom_in", label: "放大进入" },
  { id: "zoom_out", label: "缩小退出" },
  { id: "slide_in_left", label: "左滑入" },
  { id: "slide_in_right", label: "右滑入" },
  { id: "ken_burns_in", label: "Ken Burns 推入" },
];

function sortedKeyframes(kfs: NonNullable<ClipTransform["keyframes"]>) {
  return [...kfs].sort((a, b) => (a.time_ms ?? 0) - (b.time_ms ?? 0));
}

export function applyAnimationPreset(
  clip: TrackClip,
  presetId: string,
  clipDurationMs: number
): Partial<TrackClip> {
  const base: ClipTransform = { ...DEFAULT_TRANSFORM, ...clip.transform };
  const dur = Math.max(clipDurationMs, 500);
  const endMs = dur;

  if (presetId === "ken_burns_in") {
    return {
      motion: "ken_burns_in",
      transform: { ...base, keyframes: [] },
    };
  }

  const startKf = {
    x: base.x ?? 0.5,
    y: base.y ?? 0.5,
    width: base.width ?? 1,
    height: base.height ?? 1,
    opacity: base.opacity ?? 1,
    rotation: base.rotation ?? 0,
  };
  const endKf = { ...startKf, time_ms: endMs };

  switch (presetId) {
    case "fade_in":
      return {
        transform: {
          ...base,
          keyframes: sortedKeyframes([
            { time_ms: 0, ...startKf, opacity: 0 },
            { time_ms: endMs, ...startKf, opacity: 1 },
          ]),
        },
      };
    case "fade_out":
      return {
        transform: {
          ...base,
          keyframes: sortedKeyframes([
            { time_ms: 0, ...startKf, opacity: 1 },
            { time_ms: endMs, ...startKf, opacity: 0 },
          ]),
        },
      };
    case "zoom_in":
      return {
        transform: {
          ...base,
          keyframes: sortedKeyframes([
            { time_ms: 0, ...startKf, width: 0.8, height: 0.8 },
            { time_ms: endMs, ...startKf, width: 1, height: 1 },
          ]),
        },
      };
    case "zoom_out":
      return {
        transform: {
          ...base,
          keyframes: sortedKeyframes([
            { time_ms: 0, ...startKf, width: 1, height: 1 },
            { time_ms: endMs, ...startKf, width: 0.8, height: 0.8 },
          ]),
        },
      };
    case "slide_in_left":
      return {
        transform: {
          ...base,
          keyframes: sortedKeyframes([
            { time_ms: 0, ...startKf, x: -0.2 },
            { time_ms: endMs, ...startKf, x: 0.5 },
          ]),
        },
      };
    case "slide_in_right":
      return {
        transform: {
          ...base,
          keyframes: sortedKeyframes([
            { time_ms: 0, ...startKf, x: 1.2 },
            { time_ms: endMs, ...startKf, x: 0.5 },
          ]),
        },
      };
    default:
      return {};
  }
}

export function keyframeAtPlayhead(
  clip: TrackClip,
  playheadMs: number,
  transform: ClipTransform
): { keyframes: NonNullable<ClipTransform["keyframes"]>; index: number } {
  const start = Number(clip.start_ms ?? 0);
  const localMs = Math.max(0, playheadMs - start);
  const kfs = [...(transform.keyframes ?? [])];
  const snapshot = {
    time_ms: localMs,
    x: transform.x,
    y: transform.y,
    width: transform.width,
    height: transform.height,
    opacity: transform.opacity,
    rotation: transform.rotation,
  };
  const existingIdx = kfs.findIndex((kf) => (kf.time_ms ?? 0) === localMs);
  if (existingIdx >= 0) {
    kfs[existingIdx] = { ...kfs[existingIdx], ...snapshot };
    return { keyframes: sortedKeyframes(kfs), index: existingIdx };
  }
  kfs.push(snapshot);
  const sorted = sortedKeyframes(kfs);
  const index = sorted.findIndex((kf) => (kf.time_ms ?? 0) === localMs);
  return { keyframes: sorted, index };
}
