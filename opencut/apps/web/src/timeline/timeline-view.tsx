/** 时间轴容器 */

import { useEditorStore } from "../editor/editor-store";

const PX_PER_SEC = 80;
const TRACK_HEIGHT = 48;
const RULER_HEIGHT = 24;

export function TimelineView() {
  const timeline = useEditorStore((s) => s.timeline);
  const playheadMs = useEditorStore((s) => s.playheadMs);
  const setPlayheadMs = useEditorStore((s) => s.setPlayheadMs);
  const selectedClipId = useEditorStore((s) => s.selectedClipId);
  const setSelectedClipId = useEditorStore((s) => s.setSelectedClipId);

  const totalWidth = Math.max(
    (timeline.durationMs / 1000) * PX_PER_SEC,
    800,
  );

  const playheadX = (playheadMs / 1000) * PX_PER_SEC;

  function handleRulerClick(e: React.MouseEvent) {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    setPlayheadMs(Math.max(0, Math.round(ratio * timeline.durationMs)));
  }

  return (
    <div className="timeline-view">
      {/* 刻度尺 */}
      <div
        className="timeline-ruler"
        style={{ width: totalWidth }}
        onClick={handleRulerClick}
      >
        {Array.from({ length: Math.ceil(timeline.durationMs / 1000) + 1 }).map(
          (_, i) => (
            <div
              key={i}
              className="timeline-ruler-tick"
              style={{ left: i * PX_PER_SEC }}
            >
              {i}s
            </div>
          ),
        )}
        {/* 播放头 */}
        <div
          className="timeline-playhead"
          style={{ left: playheadX, height: RULER_HEIGHT + timeline.videoLayers.length * TRACK_HEIGHT }}
        />
      </div>

      {/* 视频层 */}
      {timeline.videoLayers.map((layer) => (
        <div key={layer.id} className="timeline-track-row">
          <div className="timeline-track-label">{layer.name}</div>
          <div
            className="timeline-track-lane"
            style={{ width: totalWidth }}
            onClick={(e) => {
              if (e.target === e.currentTarget) handleRulerClick(e);
            }}
          >
            {layer.clips.map((clip) => {
              const left = (clip.startMs / 1000) * PX_PER_SEC;
              const width = Math.max(
                ((clip.endMs - clip.startMs) / 1000) * PX_PER_SEC,
                4,
              );
              return (
                <div
                  key={clip.id}
                  className={`timeline-clip ${selectedClipId === clip.id ? "selected" : ""}`}
                  style={{ left, width }}
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedClipId(clip.id);
                  }}
                  title={`${clip.label} (${formatMs(clip.startMs)}–${formatMs(clip.endMs)})`}
                >
                  <span className="timeline-clip-label">{clip.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* 音频轨 */}
      <div className="timeline-track-row">
        <div className="timeline-track-label">音频</div>
        <div className="timeline-track-lane" style={{ width: totalWidth }}>
          {timeline.audioClips.map((clip) => {
            const left = (clip.startMs / 1000) * PX_PER_SEC;
            const width = Math.max(
              ((clip.endMs - clip.startMs) / 1000) * PX_PER_SEC,
              4,
            );
            return (
              <div
                key={clip.id}
                className="timeline-clip audio"
                style={{ left, width }}
                title={clip.label}
              >
                <span className="timeline-clip-label">{clip.label}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function formatMs(ms: number): string {
  const sec = Math.floor(ms / 1000);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}
