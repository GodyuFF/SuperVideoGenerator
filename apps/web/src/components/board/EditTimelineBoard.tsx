import type { BoardView } from "../../types/board";
import { MediaPreview } from "../MediaPreview";

type TrackClip = {
  id?: string;
  track?: string;
  start_ms?: number;
  end_ms?: number;
  label?: string;
  motion?: string;
  edit_description?: string;
  transition_in?: { type?: string; duration_ms?: number };
  transition_out?: { type?: string; duration_ms?: number };
  background?: { type?: string; color?: string; asset_ref?: string };
  motion_detail?: Record<string, unknown>;
  source_refs?: Record<string, unknown>;
  preview_url?: string;
  asset_ref?: string;
};

function formatMs(ms: number): string {
  const sec = Math.floor(ms / 1000);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function EditTimelineBoard({ board }: { board: BoardView }) {
  const stats = board.stats ?? {};
  const durationMs = Number(stats.duration_ms ?? 0);
  const tracks = (stats.tracks ?? {}) as Record<string, TrackClip[]>;
  const trackNames = ["video", "audio", "subtitle"] as const;
  const trackLabels: Record<string, string> = {
    video: "视频轨",
    audio: "音频轨",
    subtitle: "字幕轨",
  };

  if (durationMs <= 0 && !board.items?.length) {
    return (
      <p className="muted">
        {board.description ?? "剪辑计划稿将在 editing_agent 完成 plan_edit_timeline 后显示。"}
      </p>
    );
  }

  return (
    <div className="edit-timeline-board">
      <p className="board-description">
        {board.description}
        {durationMs > 0 && ` · 总时长 ${formatMs(durationMs)}`}
      </p>
      <div className="edit-timeline-ruler">
        <span>0:00</span>
        <span>{formatMs(durationMs)}</span>
      </div>
      {trackNames.map((trackKey) => {
        const clips = tracks[trackKey] ?? [];
        return (
          <div key={trackKey} className="edit-track-row">
            <div className="edit-track-label">{trackLabels[trackKey]}</div>
            <div className="edit-track-lane">
              {clips.length === 0 ? (
                <span className="muted edit-track-empty">（空）</span>
              ) : (
                clips.map((clip) => {
                  const start = Number(clip.start_ms ?? 0);
                  const end = Number(clip.end_ms ?? start + 1000);
                  const widthPct =
                    durationMs > 0 ? Math.max(2, ((end - start) / durationMs) * 100) : 10;
                  const leftPct = durationMs > 0 ? (start / durationMs) * 100 : 0;
                  return (
                    <div
                      key={String(clip.id ?? `${trackKey}-${start}`)}
                      className={`edit-clip edit-clip-${trackKey}`}
                      style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                      title={`${formatMs(start)} – ${formatMs(end)}`}
                    >
                      <span className="edit-clip-time">
                        {formatMs(start)}–{formatMs(end)}
                      </span>
                      <span className="edit-clip-label">{String(clip.label ?? "")}</span>
                      {clip.edit_description && (
                        <span className="edit-clip-meta" title={clip.edit_description}>
                          {clip.edit_description.slice(0, 48)}
                          {clip.edit_description.length > 48 ? "…" : ""}
                        </span>
                      )}
                      {clip.motion && trackKey === "video" && (
                        <span className="edit-clip-meta">{clip.motion}</span>
                      )}
                      {clip.transition_in?.type && trackKey === "video" && (
                        <span className="edit-clip-meta">入:{clip.transition_in.type}</span>
                      )}
                      {clip.background?.type && trackKey === "video" && (
                        <span className="edit-clip-meta">bg:{clip.background.type}</span>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        );
      })}
      {(tracks.audio ?? []).some((c) => c.preview_url) && (
        <div className="edit-audio-previews">
          <h4>配音试听</h4>
          <ul className="edit-audio-preview-list">
            {(tracks.audio ?? [])
              .filter((c) => c.preview_url)
              .map((clip) => (
                <li key={String(clip.id ?? clip.preview_url)} className="edit-audio-preview-item">
                  <span className="edit-audio-preview-label">
                    {formatMs(Number(clip.start_ms ?? 0))}–{formatMs(Number(clip.end_ms ?? 0))}
                    {clip.label ? ` · ${clip.label}` : ""}
                  </span>
                  <MediaPreview
                    kind="audio"
                    url={String(clip.preview_url)}
                    className="edit-clip-audio-preview"
                  />
                </li>
              ))}
          </ul>
        </div>
      )}
    </div>
  );
}
