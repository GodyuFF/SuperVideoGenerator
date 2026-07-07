import type { ClipKeyframe, ClipTransform, TrackClip } from "./types";
import { DEFAULT_TRANSFORM } from "./types";

export interface ResolvedTransform {
  x: number;
  y: number;
  width: number;
  height: number;
  opacity: number;
  rotation: number;
  scale: number;
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function keyframesAround(keyframes: ClipKeyframe[], localMs: number) {
  const sorted = [...keyframes].sort((a, b) => (a.time_ms ?? 0) - (b.time_ms ?? 0));
  let before: ClipKeyframe | null = null;
  let after: ClipKeyframe | null = null;
  for (const kf of sorted) {
    const t = kf.time_ms ?? 0;
    if (t <= localMs) before = kf;
    else if (!after) {
      after = kf;
      break;
    }
  }
  if (!before || !after) return { before, after, t: 0 };
  const span = Math.max((after.time_ms ?? 0) - (before.time_ms ?? 0), 1);
  return { before, after, t: (localMs - (before.time_ms ?? 0)) / span };
}

function interpAttr(
  base: number,
  before: ClipKeyframe | null,
  after: ClipKeyframe | null,
  key: keyof ClipKeyframe,
  t: number
): number {
  const vb = before?.[key];
  const va = after?.[key];
  if (vb != null && va != null) return lerp(Number(vb), Number(va), t);
  if (vb != null) return Number(vb);
  if (va != null) return Number(va);
  return base;
}

export function interpolateTransform(clip: TrackClip, localMs: number): ResolvedTransform {
  const base: ClipTransform = { ...DEFAULT_TRANSFORM, ...clip.transform };
  const { before, after, t } = keyframesAround(base.keyframes ?? [], localMs);
  let scale = 1;
  const md = clip.motion_detail as Record<string, number> | undefined;
  const clipDur = Math.max((clip.end_ms ?? 0) - (clip.start_ms ?? 0), 1);
  const progress = Math.min(1, Math.max(0, localMs / clipDur));
  if (md?.scale_from != null && md?.scale_to != null) {
    scale *= lerp(md.scale_from, md.scale_to, progress);
  }
  return {
    x: interpAttr(base.x ?? 0.5, before, after, "x", t),
    y: interpAttr(base.y ?? 0.5, before, after, "y", t),
    width: interpAttr(base.width ?? 1, before, after, "width", t),
    height: interpAttr(base.height ?? 1, before, after, "height", t),
    opacity: interpAttr(base.opacity ?? 1, before, after, "opacity", t),
    rotation: interpAttr(base.rotation ?? 0, before, after, "rotation", t),
    scale: interpAttr(scale, before, after, "scale", t),
  };
}
