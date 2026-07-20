/** SVF 归一化 transform 与 OpenCut 像素 transform 的双向映射。 */

import type { ClipTransform, TrackClip } from "../../edit/types";
import { DEFAULT_TRANSFORM } from "../../edit/types";

export interface CanvasSize {
  width: number;
  height: number;
}

export const DEFAULT_CANVAS: CanvasSize = { width: 1920, height: 1080 };

/** 从 EditTimeline metadata 解析导出画布尺寸。 */
export function resolveCanvasSize(metadata?: Record<string, unknown>): CanvasSize {
  const exportMeta = metadata?.export;
  if (exportMeta && typeof exportMeta === "object") {
    const raw = exportMeta as Record<string, unknown>;
    const w = Number(raw.width);
    const h = Number(raw.height);
    if (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0) {
      return { width: Math.round(w), height: Math.round(h) };
    }
  }
  return DEFAULT_CANVAS;
}

export interface ResolvedTransform {
  x: number;
  y: number;
  width: number;
  height: number;
  opacity: number;
  rotation: number;
  scale: number;
}

/** 将插值后的 SVF transform 转为 OpenCut element params 片段。 */
export function svfTransformToOpenCutParams(
  transform: ResolvedTransform,
  canvas: CanvasSize,
): Record<string, number> {
  return {
    opacity: transform.opacity,
    "transform.positionX": (transform.x - 0.5) * canvas.width,
    "transform.positionY": (transform.y - 0.5) * canvas.height,
    "transform.scaleX": transform.width * transform.scale,
    "transform.scaleY": transform.height * transform.scale,
    "transform.rotate": transform.rotation,
  };
}

/** 从 OpenCut element params 还原 SVF ClipTransform。 */
export function openCutParamsToSvfTransform(
  params: Record<string, unknown>,
  canvas: CanvasSize,
): ClipTransform {
  const posX = Number(params["transform.positionX"] ?? 0);
  const posY = Number(params["transform.positionY"] ?? 0);
  const scaleX = Number(params["transform.scaleX"] ?? 1);
  const scaleY = Number(params["transform.scaleY"] ?? 1);
  const scale = scaleX > 0 && Math.abs(scaleX - scaleY) < 1e-6 ? scaleX : scaleX;
  const width = scale > 0 ? scaleX / scale : scaleX;
  const height = scale > 0 ? scaleY / scale : scaleY;
  return {
    x: posX / canvas.width + 0.5,
    y: posY / canvas.height + 0.5,
    width,
    height,
    opacity: Number(params.opacity ?? 1),
    rotation: Number(params["transform.rotate"] ?? 0),
  };
}

/** 合并 clip 默认 transform 与插值结果。 */
export function baseClipTransform(clip: TrackClip): ClipTransform {
  return { ...DEFAULT_TRANSFORM, ...clip.transform };
}
