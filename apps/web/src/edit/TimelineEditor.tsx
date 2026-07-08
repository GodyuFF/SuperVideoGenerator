import { useCallback, useState } from "react";
import { ClipBlock } from "./ClipBlock";
import type { EditTimelineData, TrackClip, TrackKind, VideoLayer } from "./types";

const TRACK_LABELS: Record<TrackKind, string> = {
  video: "视频轨",
  audio: "音频轨",
  subtitle: "字幕轨",
};

interface TimelineEditorProps {
  timeline: EditTimelineData;
  selectedId: string | null;
  selectedKeyframeIdx?: number | null;
  editable: boolean;
  playheadMs: number;
  onSelectClip: (id: string | null) => void;
  onKeyframeSelect?: (clipId: string, idx: number) => void;
  onUpdateClip: (
    track: TrackKind | "video_layer",
    clipId: string,
    patch: Partial<TrackClip>,
    layerId?: string
  ) => void;
  onPlayheadSeek: (ms: number) => void;
  onDeleteClip?: (layerId: string, clipId: string) => void;
  onAddVideoLayer?: () => void;
  onMediaDrop?: (layerId: string, mediaId: string, startMs: number) => void;
}

/** 时间轴缩放级别：像素/秒 */
const ZOOM_LEVELS = [20, 40, 80, 160, 320];
const SNAP_MS = 100; // 吸附精度

function formatMs(ms: number): string {
  const sec = Math.floor(ms / 1000);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function snapMs(ms: number, snap: number): number {
  return Math.round(ms / snap) * snap;
}

function seekFromEvent(e: React.MouseEvent<HTMLElement>, durationMs: number, onSeek: (ms: number) => void, snap?: number) {
  const rect = e.currentTarget.getBoundingClientRect();
  const ratio = (e.clientX - rect.left) / rect.width;
  const ms = Math.round(Math.max(0, Math.min(1, ratio)) * durationMs);
  onSeek(snap ? snapMs(ms, snap) : ms);
}

export function TimelineEditor({
  timeline,
  selectedId,
  selectedKeyframeIdx,
  editable,
  playheadMs,
  onSelectClip,
  onKeyframeSelect,
  onUpdateClip,
  onPlayheadSeek,
  onDeleteClip,
  onAddVideoLayer,
  onMediaDrop,
}: TimelineEditorProps) {
  const durationMs = timeline.duration_ms || 1;
  const [zoomIdx, setZoomIdx] = useState(2); // default 80px/s
  const pxPerSec = ZOOM_LEVELS[Math.min(zoomIdx, ZOOM_LEVELS.length - 1)];
  const totalSec = durationMs / 1000;
  const laneWidth = Math.max(600, totalSec * pxPerSec);
  const playheadPct = (playheadMs / durationMs) * 100;

  const videoLayers: VideoLayer[] =
    timeline.video_layers && timeline.video_layers.length > 0
      ? [...timeline.video_layers].sort((a, b) => (a.z_index ?? 0) - (b.z_index ?? 0))
      : [{ id: "legacy", name: "主画面", z_index: 0, clips: timeline.tracks.video ?? [] }];

  /** 右键菜单 */
  const [contextMenu, setContextMenu] = useState<{
    x: number; y: number; clipId: string; layerId: string;
  } | null>(null);

  function onContextMenu(e: React.MouseEvent, clipId: string, layerId: string) {
    if (!editable) return;
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, clipId, layerId });
  }

  function splitClip(layerId: string, clipId: string) {
    if (!timeline) return;
    const layer = ensureLayer(timeline, layerId);
    if (!layer) return;
    const clip = (layer.clips ?? []).find(c => c.id === clipId);
    if (!clip) return;
    const splitMs = snapMs(playheadMs, SNAP_MS);
    if (splitMs <= (clip.start_ms ?? 0) || splitMs >= (clip.end_ms ?? clip.start_ms! + 1000)) return;

    const origEnd = clip.end_ms ?? clip.start_ms! + 1000;
    const left: TrackClip = { ...clip, id: `clip_${Date.now()}_1`, end_ms: splitMs };
    const right: TrackClip = { ...clip, id: `clip_${Date.now()}_2`, start_ms: splitMs, end_ms: origEnd };
    const newClips = (layer.clips ?? []).flatMap(c =>
      c.id === clipId ? [left, right] : [c]
    );
    const layers = ensureLayers(timeline).map(l =>
      l.id === layerId ? { ...l, clips: newClips } : l
    );
    const flatVideo = layers.flatMap(l =>
      (l.clips ?? []).map(c => ({ ...c, layer_id: l.id, track: "video" as const }))
    );
    const final: EditTimelineData = {
      ...timeline,
      video_layers: layers,
      tracks: { ...timeline.tracks, video: flatVideo },
    };
    // 通过外部 commit 路径
    onSelectClip(left.id ?? null);
    // 保存通过 onUpdateClip 的父级提交
    onUpdateClip("video_layer", right.id ?? "", { start_ms: splitMs, end_ms: origEnd }, layerId);
    onUpdateClip("video_layer", left.id ?? "", { start_ms: clip.start_ms ?? 0, end_ms: splitMs }, layerId);
    setContextMenu(null);
  }

  // 轨道折叠
  const [collapsedTracks, setCollapsedTracks] = useState<Set<string>>(new Set());
  function toggleCollapse(key: string) {
    setCollapsedTracks(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  // 视频层可编辑名称
  const [editingLayerName, setEditingLayerName] = useState<string | null>(null);

  return (
    <div className="edit-studio-timeline" onContextMenu={(e) => e.preventDefault()}>
      {/* 缩放控制 */}
      <div className="edit-studio-timeline-controls">
        <button type="button" className="btn-secondary btn-sm" disabled={zoomIdx <= 0} onClick={() => setZoomIdx(z => z - 1)}>−</button>
        <span className="muted" style={{ fontSize: "0.75rem", margin: "0 4px" }}>缩放 {pxPerSec}px/s</span>
        <button type="button" className="btn-secondary btn-sm" disabled={zoomIdx >= ZOOM_LEVELS.length - 1} onClick={() => setZoomIdx(z => z + 1)}>+</button>
      </div>

      <div className="edit-studio-timeline-scroll" style={{ overflowX: "auto" }}>
        <div style={{ minWidth: laneWidth }}>
          <div
            className="edit-studio-ruler"
            onClick={(e) => seekFromEvent(e, durationMs, onPlayheadSeek, SNAP_MS)}
          >
            <div className="edit-studio-playhead" style={{ left: `${playheadPct}%` }} />
          </div>

          {videoLayers.map((layer) => (
            <div key={String(layer.id)} className="edit-studio-track-row">
              <div className="edit-studio-track-label" onDoubleClick={() => editable && setEditingLayerName(layer.id ?? null)}>
                {editingLayerName === layer.id ? (
                  <input
                    type="text"
                    autoFocus
                    defaultValue={layer.name || `视频层 ${(layer.z_index ?? 0) + 1}`}
                    onBlur={() => setEditingLayerName(null)}
                    onKeyDown={(e) => { if (e.key === "Enter") setEditingLayerName(null); }}
                    style={{ width: 80, fontSize: "0.75rem" }}
                    onChange={(ev) => {
                      // synthetic update - the parent needs this capability
                    }}
                  />
                ) : (
                  layer.name || `视频层 ${(layer.z_index ?? 0) + 1}`
                )}
              </div>
              <div
                className="edit-studio-track-lane"
                onClick={(e) => {
                  if (e.target === e.currentTarget) seekFromEvent(e, durationMs, onPlayheadSeek, SNAP_MS);
                }}
                onDragOver={(e) => {
                  if (editable) e.preventDefault();
                }}
                onDrop={(e) => {
                  if (!editable || !onMediaDrop || !layer.id) return;
                  e.preventDefault();
                  const mediaId = e.dataTransfer.getData("text/media-id");
                  if (!mediaId) return;
                  const rect = e.currentTarget.getBoundingClientRect();
                  const ratio = (e.clientX - rect.left) / rect.width;
                  const startMs = snapMs(Math.round(ratio * durationMs), SNAP_MS);
                  onMediaDrop(layer.id, mediaId, startMs);
                }}
              >
                {(layer.clips ?? []).length === 0 ? (
                  <span className="muted">（空）</span>
                ) : (
                  (layer.clips ?? []).map((clip) => (
                    <ClipBlock
                      key={String(clip.id)}
                      clip={clip}
                      durationMs={durationMs}
                      selected={clip.id === selectedId}
                      selectedKeyframeIdx={clip.id === selectedId ? selectedKeyframeIdx : null}
                      editable={editable}
                      onSelect={() => onSelectClip(clip.id ?? null)}
                      onKeyframeSelect={
                        clip.id && onKeyframeSelect
                          ? (idx) => onKeyframeSelect(clip.id!, idx)
                          : undefined
                      }
                      onMove={(startMs, endMs) => {
                        if (!clip.id || !layer.id) return;
                        onUpdateClip("video_layer", clip.id, { start_ms: snapMs(startMs, SNAP_MS), end_ms: snapMs(endMs, SNAP_MS) }, layer.id);
                      }}
                      onDelete={
                        editable && onDeleteClip && clip.id && layer.id
                          ? () => onDeleteClip(layer.id!, clip.id!)
                          : undefined
                      }
                      onContextMenu={clip.id && layer.id ? (e) => onContextMenu(e, clip.id!, layer.id!) : undefined}
                    />
                  ))
                )}
              </div>
            </div>
          ))}

          {editable && onAddVideoLayer && (
            <button type="button" className="btn-secondary btn-sm" onClick={onAddVideoLayer}>
              + 添加视频层
            </button>
          )}

          {(["audio", "subtitle"] as TrackKind[]).map((trackKey) => {
            const clips = timeline.tracks[trackKey] ?? [];
            const collapsed = collapsedTracks.has(trackKey);
            return (
              <div key={trackKey} className="edit-studio-track-row">
                <div
                  className="edit-studio-track-label"
                  onClick={() => toggleCollapse(trackKey)}
                  style={{ cursor: "pointer" }}
                >
                  {collapsed ? "▶" : "▼"} {TRACK_LABELS[trackKey]}
                </div>
                {!collapsed && (
                  <div
                    className="edit-studio-track-lane"
                    onClick={(e) => {
                      if (e.target === e.currentTarget) seekFromEvent(e, durationMs, onPlayheadSeek, SNAP_MS);
                    }}
                  >
                    {clips.length === 0 ? (
                      <span className="muted">（空）</span>
                    ) : (
                      clips.map((clip) => (
                        <ClipBlock
                          key={String(clip.id)}
                          clip={clip}
                          durationMs={durationMs}
                          selected={clip.id === selectedId}
                          editable={editable}
                          onSelect={() => onSelectClip(clip.id ?? null)}
                          onMove={(startMs, endMs) => {
                            if (!clip.id) return;
                            onUpdateClip(trackKey, clip.id, { start_ms: snapMs(startMs, SNAP_MS), end_ms: snapMs(endMs, SNAP_MS) });
                          }}
                          onContextMenu={clip.id ? (e) => onContextMenu(e, clip.id!, "") : undefined}
                        />
                      ))
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 右键菜单 */}
      {contextMenu && (
        <div
          className="edit-studio-context-menu"
          style={{ position: "fixed", left: contextMenu.x, top: contextMenu.y, zIndex: 1000 }}
          onClick={() => setContextMenu(null)}
        >
          <button type="button" onClick={() => { onDeleteClip?.(contextMenu.layerId, contextMenu.clipId); setContextMenu(null); }}>
            删除片段
          </button>
          {contextMenu.layerId && (
            <button type="button" onClick={() => splitClip(contextMenu.layerId, contextMenu.clipId)} disabled={playheadMs <= 0}>
              在播放头分割
            </button>
          )}
          <button type="button" onClick={() => setContextMenu(null)}>
            取消
          </button>
        </div>
      )}
    </div>
  );
}

function ensureLayers(timeline: EditTimelineData): VideoLayer[] {
  if (timeline.video_layers && timeline.video_layers.length > 0) return timeline.video_layers;
  return [{
    id: "vly_main",
    name: "主画面",
    z_index: 0,
    clips: (timeline.tracks.video ?? []).map(c => ({ ...c, track: "video" as const })),
  }];
}

function ensureLayer(timeline: EditTimelineData, layerId: string): VideoLayer | undefined {
  return ensureLayers(timeline).find(l => l.id === layerId);
}