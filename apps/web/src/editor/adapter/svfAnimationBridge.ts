/** OpenCut element.animations 与 SVF ClipKeyframe 双向桥接。 */

import type { ClipKeyframe } from "../../edit/types";
import type { ElementAnimations, ScalarAnimationKey } from "../opencut/animation/types";
import type { CanvasSize } from "./svfTransformBridge";
import { openCutParamsToSvfTransform } from "./svfTransformBridge";
import { msToTicks, ticksToMs } from "./svfTimeTicks";

const SVF_TRANSFORM_PATHS = [
  "transform.positionX",
  "transform.positionY",
  "transform.scaleX",
  "transform.scaleY",
  "transform.rotate",
  "opacity",
] as const;

type TransformPath = (typeof SVF_TRANSFORM_PATHS)[number];

/** 判断动画通道是否含标量关键帧列表。 */
function isScalarChannelData(
  data: unknown,
): data is { keys: ScalarAnimationKey[] } {
  return Boolean(
    data &&
      typeof data === "object" &&
      "keys" in data &&
      Array.isArray((data as { keys: unknown }).keys),
  );
}

/** 从 OpenCut 动画通道收集关键帧时间点（毫秒，相对片段起点）。 */
export function collectAnimationKeyframeTimesMs(
  animations: ElementAnimations | undefined,
): number[] {
  if (!animations) return [];
  const times = new Set<number>();
  for (const path of SVF_TRANSFORM_PATHS) {
    const data = animations[path];
    if (!isScalarChannelData(data)) continue;
    for (const key of data.keys) {
      times.add(ticksToMs(key.time));
    }
  }
  return [...times].sort((a, b) => a - b);
}

/** 在标量通道上对相对时间做线性插值采样。 */
function readChannelValueAt(
  animations: ElementAnimations,
  path: TransformPath,
  localMs: number,
  fallback: number,
): number {
  const data = animations[path];
  if (!isScalarChannelData(data) || data.keys.length === 0) return fallback;

  const localTicks = msToTicks(localMs);
  const keys = [...data.keys].sort((a, b) => a.time - b.time);
  if (localTicks <= keys[0].time) return keys[0].value;
  if (localTicks >= keys[keys.length - 1].time) return keys[keys.length - 1].value;

  let before = keys[0];
  let after = keys[keys.length - 1];
  for (let i = 0; i < keys.length; i++) {
    if (keys[i].time <= localTicks) before = keys[i];
    if (keys[i].time >= localTicks) {
      after = keys[i];
      break;
    }
  }
  if (before.time === after.time) return before.value;
  const span = Math.max(after.time - before.time, 1);
  const t = (localTicks - before.time) / span;
  return before.value + (after.value - before.value) * t;
}

/** 将 OpenCut 动画通道转回 SVF 关键帧列表（保存 PATCH 用）。 */
export function extractSvfKeyframesFromElement(
  animations: ElementAnimations | undefined,
  params: Record<string, unknown>,
  canvas: CanvasSize,
): ClipKeyframe[] {
  if (!animations) return [];
  const times = collectAnimationKeyframeTimesMs(animations);
  if (times.length === 0) return [];

  const base = openCutParamsToSvfTransform(params, canvas);
  const keyframes: ClipKeyframe[] = [];

  for (const timeMs of times) {
    const posX = readChannelValueAt(
      animations,
      "transform.positionX",
      timeMs,
      ((base.x ?? 0.5) - 0.5) * canvas.width,
    );
    const posY = readChannelValueAt(
      animations,
      "transform.positionY",
      timeMs,
      ((base.y ?? 0.5) - 0.5) * canvas.height,
    );
    const scaleX = readChannelValueAt(
      animations,
      "transform.scaleX",
      timeMs,
      (base.width ?? 1),
    );
    const scaleY = readChannelValueAt(
      animations,
      "transform.scaleY",
      timeMs,
      (base.height ?? 1),
    );
    const rotation = readChannelValueAt(
      animations,
      "transform.rotate",
      timeMs,
      base.rotation ?? 0,
    );
    const opacity = readChannelValueAt(
      animations,
      "opacity",
      timeMs,
      base.opacity ?? 1,
    );

    const scale =
      scaleX > 0 && Math.abs(scaleX - scaleY) < 1e-4 ? scaleX : scaleX;
    const width = scale > 0 ? scaleX / scale : scaleX;
    const height = scale > 0 ? scaleY / scale : scaleY;

    const kf: ClipKeyframe = { time_ms: timeMs };
    const x = posX / canvas.width + 0.5;
    const y = posY / canvas.height + 0.5;

    if (Math.abs(x - (base.x ?? 0.5)) > 1e-5) kf.x = x;
    if (Math.abs(y - (base.y ?? 0.5)) > 1e-5) kf.y = y;
    if (Math.abs(width - (base.width ?? 1)) > 1e-5) kf.width = width;
    if (Math.abs(height - (base.height ?? 1)) > 1e-5) kf.height = height;
    if (Math.abs(opacity - (base.opacity ?? 1)) > 1e-5) kf.opacity = opacity;
    if (Math.abs(rotation - (base.rotation ?? 0)) > 1e-5) kf.rotation = rotation;
    if (Math.abs(scale - 1) > 1e-5) kf.scale = scale;

    if (timeMs === 0 || Object.keys(kf).length > 1) {
      keyframes.push(kf);
    }
  }

  return keyframes;
}

/** 动画已编码运镜时，避免 API 侧 motion_detail 与关键帧双重叠加。 */
export function shouldFlattenMotionForSavedKeyframes(
  keyframes: ClipKeyframe[],
): boolean {
  return keyframes.length >= 2;
}

/** 清除 motion_detail 中已由关键帧承载的 Ken Burns 缩放，防止重复应用。 */
export function stripKenBurnsScaleFromMotionDetail(
  motionDetail: Record<string, unknown> | undefined,
): Record<string, unknown> | undefined {
  if (!motionDetail || typeof motionDetail !== "object") return motionDetail;
  const next = { ...motionDetail };
  delete next.scale_from;
  delete next.scale_to;
  return Object.keys(next).length > 0 ? next : undefined;
}
