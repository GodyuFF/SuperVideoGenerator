/** Canvas 预览渲染 */

import { type FC, useEffect, useRef } from "react";
import type { EditorTimeline } from "../editor/types";

interface Props {
  timeline: EditorTimeline;
  playheadMs: number;
}

const CANVAS_W = 640;
const CANVAS_H = 360;

export const PreviewCanvas: FC<Props> = ({ timeline, playheadMs }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgCache = useRef<Map<string, HTMLImageElement>>(new Map());

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // 背景
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

    // 按 z_index 从低到高绘制各层
    const layers = [...timeline.videoLayers].sort(
      (a, b) => a.zIndex - b.zIndex,
    );

    for (const layer of layers) {
      for (const clip of layer.clips) {
        if (playheadMs < clip.startMs || playheadMs > clip.endMs) continue;
        if (!clip.previewUrl) continue;

        const img = imgCache.current.get(clip.previewUrl);
        if (img && img.complete) {
          const tr = clip.transform || {
            x: 0.5,
            y: 0.5,
            width: 1,
            height: 1,
            opacity: 1,
            rotation: 0,
          };
          ctx.save();
          ctx.globalAlpha = tr.opacity;
          const drawW = CANVAS_W * tr.width;
          const drawH = CANVAS_H * tr.height;
          const cx = tr.x * CANVAS_W;
          const cy = tr.y * CANVAS_H;
          ctx.translate(cx, cy);
          ctx.rotate((tr.rotation * Math.PI) / 180);
          ctx.drawImage(img, -drawW / 2, -drawH / 2, drawW, drawH);
          ctx.restore();
        } else if (!img && clip.previewUrl) {
          const newImg = new Image();
          newImg.crossOrigin = "anonymous";
          newImg.src = clip.previewUrl;
          imgCache.current.set(clip.previewUrl, newImg);
        }
      }
    }
  }, [timeline, playheadMs]);

  return (
    <canvas
      ref={canvasRef}
      width={CANVAS_W}
      height={CANVAS_H}
      className="preview-canvas"
    />
  );
};
