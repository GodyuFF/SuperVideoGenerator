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

interface EditStudioProps {
  projectId: string;
  scriptId: string;
  initialBoard?: EditTimelineData | null;
  editable?: boolean;
}

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

export function EditStudio({ projectId, scriptId, initialBoard, editable = true }: EditStudioProps) {
  const {
    timeline,
    setTimeline,
    loading,
    error,
    saving,
    scheduleSave,
    exportVideo,
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
      scheduleSave({
        ...next,
        video_layers: layers,
        tracks: { ...next.tracks, video: flatVideo },
      });
    },
    [scheduleSave]
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

  useEffect(() => {
    const canEditNow = editable && timeline?.editable !== false;
    function onKey(e: KeyboardEvent) {
      if (e.key === "k" || e.key === "K") {
        if (!selectedClip?.id || selectedClip.track !== "video" || !canEditNow || !selectedLayerId) return;
        const tr = { ...DEFAULT_TRANSFORM, ...selectedClip.transform };
        const { keyframes, index } = keyframeAtPlayhead(selectedClip, playheadMs, tr);
        updateClip("video_layer", selectedClip.id, { transform: { ...tr, keyframes } }, selectedLayerId);
        setSelectedKeyframeIdx(index);
        e.preventDefault();
        return;
      }
      if (!selectedId || !selectedLayerId || e.key !== "Delete") return;
      deleteClip(selectedLayerId, selectedId);
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
  ]);

  async function handleExport() {
    setExporting(true);
    setExportMsg("");
    try {
      const url = await exportVideo();
      setExportMsg(url ? `导出完成：${url}` : "导出完成");
    } catch (e) {
      setExportMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(false);
    }
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
      {saving && <p className="muted">保存中…</p>}
      <PreviewPanel
        engine={engineRef.current}
        durationMs={timeline.duration_ms}
        exporting={exporting}
        onExport={handleExport}
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
