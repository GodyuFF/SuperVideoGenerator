import { useCallback, useEffect, useRef, useState } from "react";
import { interpolateKenBurns } from "./kenBurnsPreview";
import { TransformOverlay } from "./TransformOverlay";
import { TimelineAudioSync } from "./TimelineAudioSync";
import type { TimelinePlaybackEngine } from "./TimelinePlaybackEngine";
import { interpolateTransform } from "./transformInterp";
import type { ClipTransform, TrackClip } from "./types";

const CANVAS_W = 640;
const CANVAS_H = 360;

function formatMs(ms: number): string {
  const sec = Math.floor(ms / 1000);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  const frac = Math.floor((ms % 1000) / 100);
  return `${m}:${s.toString().padStart(2, "0")}.${frac}`;
}

function isFileUrl(url: string): boolean {
  return url.toLowerCase().startsWith("file://");
}

function isVideoClip(clip: TrackClip): boolean {
  return clip.preview_media_type === "video";
}

interface PreviewPanelProps {
  engine: TimelinePlaybackEngine;
  durationMs: number;
  exporting: boolean;
  onExport: () => void;
  onExportNoSubtitles?: () => void;
  exportProgress?: { pct: number; msg: string } | null;
  onDownloadExport?: () => void;
  exportUrl?: string | null;
  ffmpegAvailable?: boolean;
  ffmpegHint?: string;
  selectedClip?: TrackClip | null;
  editable?: boolean;
  onTransformChange?: (patch: Partial<ClipTransform>) => void;
  projectId?: string | null;
  scriptId?: string | null;
}

export function PreviewPanel({
  engine,
  durationMs,
  exporting,
  onExport,
  onExportNoSubtitles,
  exportProgress,
  onDownloadExport,
  exportUrl,
  ffmpegAvailable = true,
  ffmpegHint,
  selectedClip,
  editable = false,
  onTransformChange,
  projectId,
  scriptId,
}: PreviewPanelProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const audioSyncRef = useRef<TimelineAudioSync | null>(null);
  if (!audioSyncRef.current) {
    audioSyncRef.current = new TimelineAudioSync();
  }
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const imgCache = useRef<Map<string, HTMLImageElement>>(new Map());
  const videoCache = useRef<Map<string, HTMLVideoElement>>(new Map());

  const drawClipLayer = useCallback(
    (
      ctx: CanvasRenderingContext2D,
      clip: TrackClip,
      ms: number,
      w: number,
      h: number,
      onNeedRedraw: () => void
    ) => {
      if (!clip.preview_url) return;
      const url = clip.preview_url;
      const start = Number(clip.start_ms ?? 0);
      const localMs = ms - start;
      const tr = interpolateTransform(clip, localMs);
      const drawW = w * tr.width * tr.scale;
      const drawH = h * tr.height * tr.scale;
      const cx = tr.x * w;
      const cy = tr.y * h;

      const drawSource = (source: CanvasImageSource) => {
        ctx.save();
        ctx.globalAlpha = tr.opacity;
        ctx.translate(cx, cy);
        ctx.rotate((tr.rotation * Math.PI) / 180);
        const progress = Math.max(
          0,
          Math.min(1, (ms - start) / Math.max((clip.end_ms ?? start) - start, 1))
        );
        const kb = interpolateKenBurns(progress, clip.motion, clip.motion_detail);
        const kbW = drawW * kb.scale;
        const kbH = drawH * kb.scale;
        const kbX = (-kbW / 2) + (kb.offsetX / 100) * w;
        const kbY = (-kbH / 2) + (kb.offsetY / 100) * h;
        ctx.drawImage(source, kbX, kbY, kbW, kbH);
        ctx.restore();
      };

      if (isVideoClip(clip)) {
        let video = videoCache.current.get(url);
        if (!video) {
          video = document.createElement("video");
          video.muted = true;
          video.playsInline = true;
          if (!isFileUrl(url)) video.crossOrigin = "anonymous";
          video.src = url;
          video.onloadeddata = onNeedRedraw;
          videoCache.current.set(url, video);
          return;
        }
        const clipDurationSec = Math.max(((clip.end_ms ?? start) - start) / 1000, 0.001);
        const localSec = Math.max(0, Math.min(localMs / 1000, clipDurationSec));
        if (Math.abs(video.currentTime - localSec) > 0.05) video.currentTime = localSec;
        if (video.readyState >= 2) drawSource(video);
        return;
      }

      let img = imgCache.current.get(url);
      if (!img) {
        img = new Image();
        if (!isFileUrl(url)) img.crossOrigin = "anonymous";
        img.src = url;
        img.onload = onNeedRedraw;
        imgCache.current.set(url, img);
        return;
      }
      if (!img.complete) return;
      drawSource(img);
    },
    []
  );

  const drawFrame = useCallback(
    (ms: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const w = canvas.width;
      const h = canvas.height;

      // 先画背景
      ctx.fillStyle = "#0f172a";
      ctx.fillRect(0, 0, w, h);

      // 按 z_index 排序所有激活的视频层（从低到高）
      const layers = engine.activeVideoLayersAt(ms);
      layers.sort((a, b) => (a.layer.z_index ?? 0) - (b.layer.z_index ?? 0));

      const redraw = () => drawFrame(ms);

      // 多图层合成：低层先画，高层覆盖（PIP 效果）
      for (const { clip } of layers) {
        drawClipLayer(ctx, clip, ms, w, h, redraw);
      }

      // 字幕叠加在最顶层
      const subLabel = engine.activeClipsAt(ms).subtitle?.label?.trim();
      if (subLabel) {
        const fontSize = Math.max(14, Math.round(h * 0.045));
        ctx.save();
        ctx.font = `600 ${fontSize}px system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        const textY = h - Math.round(h * 0.08);
        const metrics = ctx.measureText(subLabel);
        const padX = 10;
        const padY = 6;
        const boxW = metrics.width + padX * 2;
        const boxH = fontSize + padY * 2;
        ctx.fillStyle = "rgba(0, 0, 0, 0.55)";
        ctx.fillRect(w / 2 - boxW / 2, textY - boxH + padY, boxW, boxH);
        ctx.fillStyle = "#ffffff";
        ctx.fillText(subLabel, w / 2, textY);
        ctx.restore();
      }

      // 图层标识叠加（调试用，仅在多图层时显示）
      if (layers.length > 1) {
        ctx.save();
        ctx.font = "9px monospace";
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        for (let i = 0; i < layers.length; i++) {
          const { layer } = layers[i];
          ctx.fillStyle = "rgba(0,0,0,0.6)";
          ctx.fillRect(4, 4 + i * 16, 100, 14);
          ctx.fillStyle = "#8f8";
          ctx.fillText(`L${layer.z_index ?? i}: ${layer.name || ""}`, 6, 5 + i * 16);
        }
        ctx.restore();
      }
    },
    [engine, drawClipLayer]
  );

  useEffect(() => {
    const audioSync = audioSyncRef.current;
    return engine.subscribe((ms, isPlaying) => {
      setPlayhead(ms);
      setPlaying(isPlaying);
      audioSync?.sync(engine, ms, isPlaying, projectId, scriptId);
      drawFrame(ms);
    });
  }, [engine, drawFrame, projectId, scriptId]);

  useEffect(() => {
    return () => audioSyncRef.current?.dispose();
  }, []);

  return (
    <div className="edit-studio-preview">
      <div className="edit-studio-canvas-wrap">
        <canvas ref={canvasRef} className="edit-studio-canvas" width={CANVAS_W} height={CANVAS_H} />
        {selectedClip && onTransformChange && (
          <TransformOverlay
            clip={selectedClip}
            playheadMs={playhead}
            canvasWidth={CANVAS_W}
            canvasHeight={CANVAS_H}
            editable={editable}
            onTransformChange={onTransformChange}
          />
        )}
      </div>
      <div className="edit-studio-preview-controls">
        <button type="button" className="btn-secondary btn-sm" onClick={() => engine.toggle()}>
          {playing ? "暂停" : "播放"}
        </button>
        <span className="edit-studio-time">
          {formatMs(playhead)} / {formatMs(durationMs)}
        </span>
        <button
          type="button"
          className="btn-primary btn-sm"
          disabled={exporting || !ffmpegAvailable}
          onClick={() => void onExport()}
          title={!ffmpegAvailable ? ffmpegHint : undefined}
        >
          {exporting ? "导出中…" : "导出成片"}
        </button>
        {onExportNoSubtitles && (
          <button
            type="button"
            className="btn-secondary btn-sm"
            disabled={exporting || !ffmpegAvailable}
            onClick={() => void onExportNoSubtitles()}
            title="导出纯画面+配音，不烧录字幕"
          >
            导出(无字幕)
          </button>
        )}
        {exportUrl && onDownloadExport && (
          <button
            type="button"
            className="btn-primary btn-sm"
            onClick={() => void onDownloadExport()}
          >
            下载成片
          </button>
        )}
        {exportProgress && (
          <div className="edit-studio-export-progress">
            <div className="edit-studio-export-progress-bar" style={{ width: `${exportProgress.pct}%` }} />
            <span className="edit-studio-export-progress-text">{exportProgress.msg} ({Math.round(exportProgress.pct)}%)</span>
          </div>
        )}
        {!ffmpegAvailable && ffmpegHint && (
          <span className="edit-studio-ffmpeg-hint muted">{ffmpegHint}</span>
        )}
      </div>
    </div>
  );
}
