/** SVF clip 运镜/关键帧插值，与 core/edit/transform_interp.py 语义对齐。 */

import type { ClipKeyframe, TrackClip } from "../../edit/types";
import type { ResolvedTransform } from "./svfTransformBridge";
import { baseClipTransform } from "./svfTransformBridge";
import { msToTicks } from "./svfTimeTicks";
import type { ElementAnimations, ScalarAnimationKey } from "../opencut/animation/types";

const KEN_BURNS_BOUNDARY_STEP_MS = 250;

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function keyframesAround(
  keyframes: ClipKeyframe[],
  localMs: number,
): [ClipKeyframe | null, ClipKeyframe | null, number] {
  if (!keyframes.length) return [null, null, 0];
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
  if (!before) return [null, after, 0];
  if (!after) return [before, null, 0];
  const span = Math.max((after.time_ms ?? 0) - (before.time_ms ?? 0), 1);
  const t = (localMs - (before.time_ms ?? 0)) / span;
  return [before, after, t];
}

function interpOptional(
  base: number,
  before: ClipKeyframe | null,
  after: ClipKeyframe | null,
  attr: keyof ClipKeyframe,
  t: number,
): number {
  if (!before && !after) return base;
  if (before && after) {
    const va = before[attr];
    const vb = after[attr];
    if (va != null && vb != null) return lerp(Number(va), Number(vb), t);
  }
  if (before?.[attr] != null) return Number(before[attr]);
  if (after?.[attr] != null) return Number(after[attr]);
  return base;
}

function clipHasKenBurns(clip: TrackClip): boolean {
  const motion = (clip.motion || "ken_burns_in").trim().toLowerCase();
  if (motion && motion !== "static") return true;
  const md = clip.motion_detail as Record<string, unknown> | undefined;
  if (!md) return false;
  if (md.scale_from != null || md.scale_to != null) return true;
  if (md.from_focal || md.to_focal) return true;
  const type = String(md.type || "").trim().toLowerCase();
  return Boolean(type && type !== "static");
}

/** 按 clip 内相对时间插值 transform（含 keyframes 与 Ken Burns scale）。 */
export function interpolateTransform(clip: TrackClip, localMs: number): ResolvedTransform {
  const base = baseClipTransform(clip);
  const safeLocal = Math.max(0, localMs);
  const kfs = base.keyframes ?? [];
  const [before, after, t] = keyframesAround(kfs, safeLocal);

  let x = interpOptional(base.x ?? 0.5, before, after, "x", t);
  let y = interpOptional(base.y ?? 0.5, before, after, "y", t);
  let width = interpOptional(base.width ?? 1, before, after, "width", t);
  let height = interpOptional(base.height ?? 1, before, after, "height", t);
  const opacity = interpOptional(base.opacity ?? 1, before, after, "opacity", t);
  const rotation = interpOptional(base.rotation ?? 0, before, after, "rotation", t);
  let scale = interpOptional(1, before, after, "scale", t);

  const motion = (clip.motion || "ken_burns_in").trim().toLowerCase();
  const md = clip.motion_detail as Record<string, unknown> | undefined;
  if (md && motion !== "static") {
    const start = clip.start_ms ?? 0;
    const end = clip.end_ms ?? start + 1;
    const clipDuration = Math.max(end - start, 1);
    const progress = Math.min(1, Math.max(0, safeLocal / clipDuration));
    const scaleFrom = md.scale_from;
    const scaleTo = md.scale_to;
    if (scaleFrom != null && scaleTo != null) {
      scale *= lerp(Number(scaleFrom), Number(scaleTo), progress);
    }
  }

  return { x, y, width, height, opacity, rotation, scale };
}

/** 收集运镜插值采样点（与 FFmpeg composite 边界步长一致）。 */
export function collectMotionSampleTimes(clip: TrackClip): number[] {
  const start = clip.start_ms ?? 0;
  const end = clip.end_ms ?? start;
  const duration = Math.max(end - start, 1);
  const times = new Set<number>([0, Math.max(0, duration - 1)]);

  for (const kf of clip.transform?.keyframes ?? []) {
    const t = kf.time_ms ?? 0;
    if (t >= 0 && t <= duration) times.add(t);
  }

  if (clipHasKenBurns(clip)) {
    let t = KEN_BURNS_BOUNDARY_STEP_MS;
    while (t < duration) {
      times.add(t);
      t += KEN_BURNS_BOUNDARY_STEP_MS;
    }
  }

  return [...times].sort((a, b) => a - b);
}

/** 片段是否需要生成 OpenCut 运镜动画通道。 */
export function clipNeedsMotionAnimation(clip: TrackClip): boolean {
  const kfs = clip.transform?.keyframes ?? [];
  if (kfs.length > 0) return true;
  return clipHasKenBurns(clip);
}

function makeScalarKey(id: string, localMs: number, value: number): ScalarAnimationKey {
  return {
    id,
    time: msToTicks(localMs) as ScalarAnimationKey["time"],
    value,
    segmentToNext: "linear",
    tangentMode: "auto",
  };
}

function buildScalarChannel(
  clip: TrackClip,
  pick: (tr: ResolvedTransform) => number,
  prefix: string,
): ScalarAnimationKey[] {
  const samples = collectMotionSampleTimes(clip);
  return samples.map((localMs, idx) =>
    makeScalarKey(`${prefix}_${idx}`, localMs, pick(interpolateTransform(clip, localMs))),
  );
}

/** 为 clip 生成 OpenCut 运镜/关键帧动画（覆盖 transform 与 opacity 通道）。 */
export function buildMotionAnimations(
  clip: TrackClip,
  canvas: { width: number; height: number },
): ElementAnimations | undefined {
  if (!clipNeedsMotionAnimation(clip)) return undefined;

  const posXKeys = buildScalarChannel(clip, (tr) => (tr.x - 0.5) * canvas.width, "px");
  const posYKeys = buildScalarChannel(clip, (tr) => (tr.y - 0.5) * canvas.height, "py");
  const scaleXKeys = buildScalarChannel(clip, (tr) => tr.width * tr.scale, "sx");
  const scaleYKeys = buildScalarChannel(clip, (tr) => tr.height * tr.scale, "sy");
  const rotateKeys = buildScalarChannel(clip, (tr) => tr.rotation, "rot");
  const opacityKeys = buildScalarChannel(clip, (tr) => tr.opacity, "op");

  return {
    "transform.positionX": { keys: posXKeys },
    "transform.positionY": { keys: posYKeys },
    "transform.scaleX": { keys: scaleXKeys },
    "transform.scaleY": { keys: scaleYKeys },
    "transform.rotate": { keys: rotateKeys },
    opacity: { keys: opacityKeys },
  };
}
