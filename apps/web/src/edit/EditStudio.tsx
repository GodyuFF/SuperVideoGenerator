import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ClipInspector } from "./ClipInspector";
import { MediaBin } from "./MediaBin";
import { PreviewPanel } from "./PreviewPanel";
import { TimelineEditor } from "./TimelineEditor";
import { TimelinePlaybackEngine } from "./TimelinePlaybackEngine";
import type {
  EditCapabilities,
  EditTimelineData,
  MediaBinItem,
  TrackClip,
  TrackKind,
  VideoLayer,
} from "./types";
import { DEFAULT_TRANSFORM } from "./types";
import { keyframeAtPlayhead } from "./animationPresets";
import { useEditTimeline } from "./useEditTimeline";

const API = "/api";
const MAX_VIDEO_LAYERS = 5;
const MAX_UNDO = 50;

function boardToTimeline(board: Record<string, unknown> | null | undefined): EditTimelineData | null {
  if (!board) return null;
  const stats = (board.stats ?? board) as Record<string, unknown>;
  const tracks = stats.tracks as EditTimelineData["tracks"] | undefined;
  if (!tracks) return null;
  return {
    timeline_id: String(stats.timeline_id ?? ""),
    plan_id: String(stats.plan_id ?? ""),
    duration_ms: Number(stats.duration_ms ?? 0),
    revision: Number(stats.revision ?? 0),
    user_edited: Boolean(stats.user_edited),
    tracks,
    video_layers: stats.video_layers as VideoLayer[] | undefined,
  };
}

function ensureLayers(timeline: EditTimelineData): VideoLayer[] {
  if (timeline.video_layers && timeline.video_layers.length > 0) {
    return timeline.video_layers;
  }
  return [
    {
      id: "vly_main",
      name: "主画面",
      z_index: 0,
      clips: (timeline.tracks.video ?? []).map((c) => ({ ...c, track: "video" as const })),
    },
  ];
}

/** 深克隆 timeline（用于 undo 栈） */
function cloneTimeline(t: EditTimelineData): EditTimelineData {
  return JSON.parse(JSON.stringify(t));
}

interface EditStudioProps {
  projectId: string;
  scriptId: string;
  initialBoard?: EditTimelineData | null;
  editable?: boolean;
}

export function EditStudio({ projectId, scriptId, initialBoard, editable = true }: EditStudioProps) {
  const {
    timeline,
    setTimeline,
    loading,
    error,
    saving,
    scheduleSave,
    flushSave,
    exportVideo,
    exportVideoNoSubtitles,
    downloadExport,
    fetchTimeline,
  } = useEditTimeline(projectId, scriptId);
  const engineRef = useRef(new TimelinePlaybackEngine());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedLayerId, setSelectedLayerId] = useState<string | null>(null);
  const [selectedKeyframeIdx, setSelectedKeyframeIdx] = useState<number | null>(null);
  const [playheadMs, setPlayheadMs] = useState(0);
  const [capabilities, setCapabilities] = useState<EditCapabilities | null>(null);
  const [mediaItems, setMediaItems] = useState<MediaBinItem[]>([]);
  const [exporting, setExporting] = useState(false);
  const [exportMsg, setExportMsg] = useState("");
  const [exportProgress, setExportProgress] = useState<{ pct: number; msg: string } | null>(null);
  const [exportUrl, setExportUrl] = useState<string | null>(null);

  // ---- Undo/Redo ----
  const undoStack = useRef<EditTimelineData[]>([]);
  const redoStack = useRef<EditTimelineData[]>([]);
  const pendingUndo = useRef<EditTimelineData | null>(null);
  /** True while a clip is being dragged — suppress duplicate undo pushes */
  const clipDragActive = useRef(false);
  /** Snapshot captured at drag-start, pushed to undo on drag-end */
  const dragBeforeSnapshot = useRef<EditTimelineData | null>(null);

  const pushUndo = useCallback((t: EditTimelineData) => {
    pendingUndo.current = cloneTimeline(t);
  }, []);

  const flushUndo = useCallback(() => {
    if (!pendingUndo.current) return;
    undoStack.current.push(pendingUndo.current);
    if (undoStack.current.length > MAX_UNDO) undoStack.current.shift();
    redoStack.current = [];
    pendingUndo.current = null;
  }, []);

  function undo() {
    if (undoStack.current.length === 0 || !timeline) return;
    redoStack.current.push(cloneTimeline(timeline));
    const prev = undoStack.current.pop()!;
    // Strip revision so save uses current server revision from the ref
    prev.revision = undefined;
    setTimeline(prev);
    scheduleSave(prev);
  }

  function redo() {
    if (redoStack.current.length === 0 || !timeline) return;
    undoStack.current.push(cloneTimeline(timeline));
    const next = redoStack.current.pop()!;
    next.revision = undefined;
    setTimeline(next);
    scheduleSave(next);
  }

  // ---- Init ----
  useEffect(() => {
    if (!timeline && initialBoard) {
      const converted = boardToTimeline(initialBoard as unknown as Record<string, unknown>);
      if (converted) setTimeline(converted);
    }
  }, [initialBoard, timeline, setTimeline]);

  useEffect(() => {
    if (timeline) engineRef.current.setTimeline(timeline);
  }, [timeline]);

  useEffect(() => {
    return engineRef.current.subscribe((ms) => setPlayheadMs(ms));
  }, []);

  useEffect(() => {
    void fetch(`${API}/edit/capabilities`)
      .then((r) => r.json())
      .then((d) => setCapabilities(d as EditCapabilities))
      .catch(() => setCapabilities(null));
    void fetch(`${API}/projects/${projectId}/scripts/${scriptId}/media`)
      .then((r) => r.json())
      .then((items) => setMediaItems(items as MediaBinItem[]))
      .catch(() => setMediaItems([]));
  }, [projectId, scriptId]);

  const selectedClip = useMemo(() => {
    if (!timeline || !selectedId) return null;
    for (const layer of ensureLayers(timeline)) {
      const found = (layer.clips ?? []).find((c) => c.id === selectedId);
      if (found) return { ...found, track: "video" as const, layer_id: layer.id };
    }
    for (const key of ["audio", "subtitle"] as TrackKind[]) {
      const found = (timeline.tracks[key] ?? []).find((c) => c.id === selectedId);
      if (found) return found;
    }
    return null;
  }, [timeline, selectedId]);

  const commitTimeline = useCallback(
    (next: EditTimelineData) => {
      const layers = ensureLayers(next);
      const flatVideo = layers.flatMap((l) =>
        (l.clips ?? []).map((c) => ({ ...c, layer_id: l.id, track: "video" as const }))
      );
      const final: EditTimelineData = {
        ...next,
        video_layers: layers,
        tracks: { ...next.tracks, video: flatVideo },
      };
      if (!clipDragActive.current) {
        pushUndo(final);
        setTimeout(() => flushUndo(), 0);
      }
      scheduleSave(final);
    },
    [scheduleSave, pushUndo, flushUndo]
  );

  function updateClip(
    track: TrackKind | "video_layer",
    clipId: string,
    patch: Partial<TrackClip>,
    layerId?: string
  ) {
    if (!timeline) return;
    if (track === "video_layer" && layerId) {
      const layers = ensureLayers(timeline).map((layer) =>
        layer.id === layerId
          ? {
              ...layer,
              clips: (layer.clips ?? []).map((c) =>
                c.id === clipId
                  ? { ...c, ...patch, metadata: { ...c.metadata, edited_by: "user" } }
                  : c
              ),
            }
          : layer
      );
      commitTimeline({ ...timeline, video_layers: layers });
      return;
    }
    const t = track as TrackKind;
    commitTimeline({
      ...timeline,
      tracks: {
        ...timeline.tracks,
        [t]: (timeline.tracks[t] ?? []).map((c) =>
          c.id === clipId ? { ...c, ...patch, metadata: { ...c.metadata, edited_by: "user" } } : c
        ),
      },
    });
  }

  function deleteClip(layerId: string, clipId: string) {
    if (!timeline) return;
    const layers = ensureLayers(timeline).map((layer) =>
      layer.id === layerId
        ? { ...layer, clips: (layer.clips ?? []).filter((c) => c.id !== clipId) }
        : layer
    );
    if (selectedId === clipId) setSelectedId(null);
    commitTimeline({ ...timeline, video_layers: layers });
  }

  function addVideoLayer() {
    if (!timeline) return;
    const layers = ensureLayers(timeline);
    if (layers.length >= MAX_VIDEO_LAYERS) return;
    const z = Math.max(...layers.map((l) => l.z_index ?? 0), -1) + 1;
    layers.push({
      id: `vly_${Date.now()}`,
      name: `视频层 ${z + 1}`,
      z_index: z,
      clips: [],
    });
    commitTimeline({ ...timeline, video_layers: layers });
  }

  function handleMediaDrop(layerId: string, mediaId: string, startMs: number) {
    if (!timeline) return;
    const item = mediaItems.find((m) => m.id === mediaId);
    const duration = item?.duration_ms ?? 3000;
    const clip: TrackClip = {
      id: `clip_${Date.now()}`,
      track: "video",
      start_ms: startMs,
      end_ms: startMs + duration,
      label: item?.name || mediaId,
      asset_ref: mediaId,
      layer_id: layerId,
      transform: { ...DEFAULT_TRANSFORM },
      metadata: { edited_by: "user" },
    };
    const layers = ensureLayers(timeline).map((layer) =>
      layer.id === layerId ? { ...layer, clips: [...(layer.clips ?? []), clip] } : layer
    );
    commitTimeline({ ...timeline, video_layers: layers });
    setSelectedId(clip.id ?? null);
    setSelectedLayerId(layerId);
  }

  // ---- Keyboard shortcuts ----
  useEffect(() => {
    const canEditNow = editable && timeline?.editable !== false;
    function onKey(e: KeyboardEvent) {
      // Don't handle shortcuts when typing in inputs
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      // Space: play/pause
      if (e.key === " ") {
        e.preventDefault();
        const engine = engineRef.current;
        if (engine.isPlaying()) engine.pause();
        else engine.play();
        return;
      }

      // Ctrl+Z: undo
      if ((e.ctrlKey || e.metaKey) && e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        undo();
        return;
      }

      // Ctrl+Shift+Z or Ctrl+Y: redo
      if ((e.ctrlKey || e.metaKey) && (e.key === "y" || (e.key === "z" && e.shiftKey))) {
        e.preventDefault();
        redo();
        return;
      }

      // Ctrl+S: save
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (timeline) scheduleSave(timeline);
        return;
      }

      // Home: jump to start
      if (e.key === "Home") {
        e.preventDefault();
        engineRef.current.seek(0);
        return;
      }

      // End: jump to end
      if (e.key === "End") {
        e.preventDefault();
        engineRef.current.seek(timeline?.duration_ms ?? 0);
        return;
      }

      // K: add keyframe at playhead
      if ((e.key === "k" || e.key === "K") && canEditNow) {
        if (!selectedClip?.id || selectedClip.track !== "video" || !selectedLayerId) return;
        const tr = { ...DEFAULT_TRANSFORM, ...selectedClip.transform };
        const { keyframes, index } = keyframeAtPlayhead(selectedClip, playheadMs, tr);
        updateClip("video_layer", selectedClip.id, { transform: { ...tr, keyframes } }, selectedLayerId);
        setSelectedKeyframeIdx(index);
        e.preventDefault();
        return;
      }

      // Delete / Backspace: delete selected clip
      if ((e.key === "Delete" || e.key === "Backspace") && canEditNow) {
        if (!selectedId || !selectedLayerId) return;
        deleteClip(selectedLayerId, selectedId);
        e.preventDefault();
        return;
      }

      // Arrow keys: nudge playhead
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        const step = e.ctrlKey ? 1000 : e.shiftKey ? 5000 : 100;
        const dir = e.key === "ArrowRight" ? 1 : -1;
        e.preventDefault();
        engineRef.current.seek(Math.max(0, playheadMs + dir * step));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    editable,
    timeline,
    selectedClip,
    playheadMs,
    selectedLayerId,
    selectedId,
    updateClip,
    deleteClip,
    undo,
    redo,
    scheduleSave,
  ]);

  async function handleExport() {
    setExporting(true);
    setExportMsg("");
    setExportProgress(null);
    setExportUrl(null);
    try {
      const url = await exportVideo((pct, msg) => setExportProgress({ pct, msg }));
      setExportUrl(url);
      setExportMsg(url ? "导出完成！" : "导出完成");
    } catch (e) {
      setExportMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(false);
      setExportProgress(null);
    }
  }

  async function handleExportNoSubtitles() {
    setExporting(true);
    setExportMsg("");
    setExportProgress(null);
    setExportUrl(null);
    try {
      const url = await exportVideoNoSubtitles((pct, msg) => setExportProgress({ pct, msg }));
      setExportUrl(url);
      setExportMsg(url ? "导出完成（无字幕）！" : "导出完成");
    } catch (e) {
      setExportMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(false);
      setExportProgress(null);
    }
  }

  async function handleDownload() {
    if (!exportUrl) return;
    await downloadExport(exportUrl);
  }

  if (loading && !timeline) {
    return <p className="muted">加载剪辑工作室…</p>;
  }

  if (!timeline) {
    return (
      <p className="muted">
        {error || "尚无剪辑时间轴。请先运行 editing_agent 的 plan_edit_timeline。"}
        <button type="button" className="btn-secondary btn-sm" onClick={() => void fetchTimeline()}>
          重试
        </button>
      </p>
    );
  }

  const displayTimeline: EditTimelineData = {
    ...timeline,
    video_layers: ensureLayers(timeline),
  };
  const canEdit = editable && timeline.editable !== false;
  const ffmpegAvailable = capabilities?.ffmpeg_available !== false;
  const ffmpegHint =
    "未检测到 FFmpeg。请在后端目录执行 pip install -e . 安装内置 FFmpeg，或设置 SVG_FFMPEG_PATH / 系统 PATH（Windows: winget install ffmpeg）";

  return (
    <div className="edit-studio">
      {error && <p className="board-error">{error}</p>}
      <div className="edit-studio-toolbar">
        {saving && <span className="muted">保存中…</span>}
        <button
          type="button"
          className="btn-secondary btn-sm"
          disabled={undoStack.current.length === 0}
          onClick={undo}
          title="撤销 (Ctrl+Z)"
        >
          ↩ 撤销
        </button>
        <button
          type="button"
          className="btn-secondary btn-sm"
          disabled={redoStack.current.length === 0}
          onClick={redo}
          title="重做 (Ctrl+Y)"
        >
          ↪ 重做
        </button>
        <span className="edit-studio-shortcuts-hint">
          快捷键：Space 播放/暂停 · Delete 删除 · Ctrl+Z 撤销 · Ctrl+S 保存 · Home/End 跳转首尾 · ←→ 微调播放头
        </span>
      </div>
      <PreviewPanel
        engine={engineRef.current}
        durationMs={timeline.duration_ms}
        exporting={exporting}
        onExport={handleExport}
        onExportNoSubtitles={handleExportNoSubtitles}
        exportProgress={exportProgress}
        onDownloadExport={exportUrl ? handleDownload : undefined}
        exportUrl={exportUrl}
        ffmpegAvailable={ffmpegAvailable}
        ffmpegHint={ffmpegHint}
        projectId={projectId}
        scriptId={scriptId}
        selectedClip={selectedClip?.track === "video" ? selectedClip : null}
        editable={canEdit}
        onTransformChange={(patch) => {
          if (!selectedClip?.id || !selectedLayerId) return;
          const tr = { ...DEFAULT_TRANSFORM, ...selectedClip.transform, ...patch };
          updateClip("video_layer", selectedClip.id, { transform: tr }, selectedLayerId);
        }}
      />
      {exportMsg && <p className="muted">{exportMsg}</p>}
      <div className="edit-studio-body">
        <aside className="edit-studio-sidebar">
          <h4>素材库</h4>
          <MediaBin items={mediaItems} />
        </aside>
        <div className="edit-studio-main">
          <TimelineEditor
            timeline={displayTimeline}
            selectedId={selectedId}
            selectedKeyframeIdx={selectedKeyframeIdx}
            editable={canEdit}
            playheadMs={playheadMs}
            onSelectClip={(id) => {
              setSelectedId(id);
              setSelectedKeyframeIdx(null);
              if (id && timeline.video_layers) {
                const layer = timeline.video_layers.find((l) =>
                  (l.clips ?? []).some((c) => c.id === id)
                );
                setSelectedLayerId(layer?.id ?? null);
              }
            }}
            onKeyframeSelect={(_clipId, idx) => setSelectedKeyframeIdx(idx)}
            onUpdateClip={updateClip}
            onPlayheadSeek={(ms) => engineRef.current.seek(ms)}
            onDeleteClip={canEdit ? deleteClip : undefined}
            onAddVideoLayer={canEdit ? addVideoLayer : undefined}
            onMediaDrop={canEdit ? handleMediaDrop : undefined}
          />
        </div>
      </div>
      <ClipInspector
        clip={selectedClip}
        capabilities={capabilities}
        editable={canEdit}
        playheadMs={playheadMs}
        selectedKeyframeIdx={selectedKeyframeIdx}
        onKeyframeSelect={setSelectedKeyframeIdx}
        onChange={(patch) => {
          if (!selectedClip?.id) return;
          if (selectedClip.track === "video" && selectedLayerId) {
            updateClip("video_layer", selectedClip.id, patch, selectedLayerId);
          } else if (selectedClip.track) {
            updateClip(selectedClip.track as TrackKind, selectedClip.id, patch);
          }
        }}
      />
    </div>
  );
}