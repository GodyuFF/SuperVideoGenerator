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

function seekFromEvent(e: React.MouseEvent<HTMLElement>, durationMs: number, onSeek: (ms: number) => void) {
  const rect = e.currentTarget.getBoundingClientRect();
  const ratio = (e.clientX - rect.left) / rect.width;
  onSeek(Math.round(Math.max(0, Math.min(1, ratio)) * durationMs));
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
  const playheadPct = (playheadMs / durationMs) * 100;
  const videoLayers: VideoLayer[] = [...(timeline.video_layers ?? [])].sort(
    (a, b) => (a.z_index ?? 0) - (b.z_index ?? 0),
  );

  return (
    <div className="edit-studio-timeline">
      <div
        className="edit-studio-ruler"
        onClick={(e) => seekFromEvent(e, durationMs, onPlayheadSeek)}
      >
        <div className="edit-studio-playhead" style={{ left: `${playheadPct}%` }} />
      </div>

      {videoLayers.map((layer) => (
        <div key={String(layer.id)} className="edit-studio-track-row">
          <div className="edit-studio-track-label">
            {layer.name || `视频层 ${(layer.z_index ?? 0) + 1}`}
          </div>
          <div
            className="edit-studio-track-lane"
            onClick={(e) => {
              if (e.target === e.currentTarget) seekFromEvent(e, durationMs, onPlayheadSeek);
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
              const startMs = Math.round(ratio * durationMs / 100) * 100;
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
                    onUpdateClip("video_layer", clip.id, { start_ms: startMs, end_ms: endMs }, layer.id);
                  }}
                  onDelete={
                    editable && onDeleteClip && clip.id && layer.id
                      ? () => onDeleteClip(layer.id!, clip.id!)
                      : undefined
                  }
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
        return (
          <div key={trackKey} className="edit-studio-track-row">
            <div className="edit-studio-track-label">{TRACK_LABELS[trackKey]}</div>
            <div
              className="edit-studio-track-lane"
              onClick={(e) => {
                if (e.target === e.currentTarget) seekFromEvent(e, durationMs, onPlayheadSeek);
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
                      onUpdateClip(trackKey, clip.id, { start_ms: startMs, end_ms: endMs });
                    }}
                  />
                ))
              )}
            </div>
          </div>
        );
      })}

      <div className="edit-studio-playhead-rail" style={{ left: `${playheadPct}%` }} aria-hidden />
    </div>
  );
}
