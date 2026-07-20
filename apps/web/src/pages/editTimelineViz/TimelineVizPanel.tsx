/**
 * 多轨 EditTimeline 可视化：按 video_layers 分层 + audio/subtitle 轨。
 */

import type { EditTimelineData, TrackClip, VideoLayer } from "../../edit/types";
import { formatMs } from "./formatMs";

interface TimelineVizPanelProps {
  timeline: EditTimelineData;
  selectedClipId: string | null;
  onSelectClip: (clip: TrackClip | null) => void;
}

/** 在时间轴 lane 内按比例渲染 clip 块。 */
function ClipBlock({
  clip,
  trackKind,
  durationMs,
  selected,
  onSelect,
}: {
  clip: TrackClip;
  trackKind: string;
  durationMs: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const start = Number(clip.start_ms ?? 0);
  const end = Number(clip.end_ms ?? start + 1000);
  const widthPct = durationMs > 0 ? Math.max(1.5, ((end - start) / durationMs) * 100) : 12;
  const leftPct = durationMs > 0 ? (start / durationMs) * 100 : 0;
  const clipId = String(clip.id ?? `${trackKind}-${start}`);

  return (
    <button
      type="button"
      className={`etviz-clip etviz-clip--${trackKind}${selected ? " etviz-clip--selected" : ""}`}
      style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
      title={`${formatMs(start)} – ${formatMs(end)} · ${clip.label ?? clipId}`}
      onClick={onSelect}
    >
      <span className="etviz-clip-time tabular-nums">
        {formatMs(start)}–{formatMs(end)}
      </span>
      <span className="etviz-clip-label">{String(clip.label ?? clipId).slice(0, 40)}</span>
    </button>
  );
}

/** 单行轨道 lane。 */
function TrackLane({
  label,
  clips,
  trackKind,
  durationMs,
  selectedClipId,
  onSelectClip,
}: {
  label: string;
  clips: TrackClip[];
  trackKind: string;
  durationMs: number;
  selectedClipId: string | null;
  onSelectClip: (clip: TrackClip | null) => void;
}) {
  return (
    <div className="etviz-track-row">
      <div className="etviz-track-label">{label}</div>
      <div className="etviz-track-lane">
        {clips.length === 0 ? (
          <span className="muted etviz-track-empty">（空）</span>
        ) : (
          clips.map((clip) => {
            const id = String(clip.id ?? "");
            return (
              <ClipBlock
                key={id || `${trackKind}-${clip.start_ms}`}
                clip={clip}
                trackKind={trackKind}
                durationMs={durationMs}
                selected={Boolean(id && selectedClipId === id)}
                onSelect={() => onSelectClip(clip)}
              />
            );
          })
        )}
      </div>
    </div>
  );
}

/** 多轨时间轴主视图。 */
export function TimelineVizPanel({
  timeline,
  selectedClipId,
  onSelectClip,
}: TimelineVizPanelProps) {
  const durationMs = Math.max(0, Number(timeline.duration_ms ?? 0));
  const videoLayers = timeline.video_layers ?? [];
  const audioClips = timeline.tracks?.audio ?? [];
  const subtitleClips = timeline.tracks?.subtitle ?? [];

  if (durationMs <= 0 && !videoLayers.length && !audioClips.length && !subtitleClips.length) {
    return (
      <p className="muted etviz-empty">
        尚无剪辑时间轴数据（editing_agent 完成 plan_edit_timeline 后可见）。
      </p>
    );
  }

  return (
    <div className="etviz-timeline">
      <div className="etviz-ruler">
        <span className="tabular-nums">0:00</span>
        <span className="tabular-nums">{formatMs(durationMs)}</span>
      </div>
      {videoLayers.map((layer: VideoLayer) => (
        <TrackLane
          key={String(layer.id ?? layer.name)}
          label={`视频 · ${layer.name || layer.id || "layer"} (z=${layer.z_index ?? 0})`}
          clips={layer.clips ?? []}
          trackKind="video"
          durationMs={durationMs}
          selectedClipId={selectedClipId}
          onSelectClip={onSelectClip}
        />
      ))}
      {videoLayers.length === 0 && (timeline.tracks?.video?.length ?? 0) > 0 ? (
        <TrackLane
          label="视频（扁平 tracks.video）"
          clips={timeline.tracks?.video ?? []}
          trackKind="video"
          durationMs={durationMs}
          selectedClipId={selectedClipId}
          onSelectClip={onSelectClip}
        />
      ) : null}
      <TrackLane
        label="音频"
        clips={audioClips}
        trackKind="audio"
        durationMs={durationMs}
        selectedClipId={selectedClipId}
        onSelectClip={onSelectClip}
      />
      <TrackLane
        label="字幕"
        clips={subtitleClips}
        trackKind="subtitle"
        durationMs={durationMs}
        selectedClipId={selectedClipId}
        onSelectClip={onSelectClip}
      />
    </div>
  );
}
