import type { ClipKeyframe, TrackClip } from "./types";
import { clipBadgeSummary, keyframeTooltip } from "./clipBadges";

function formatMs(ms: number): string {
  const sec = Math.floor(ms / 1000);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  const frac = Math.floor((ms % 1000) / 100);
  return `${m}:${s.toString().padStart(2, "0")}.${frac}`;
}

interface ClipBlockProps {
  clip: TrackClip;
  durationMs: number;
  selected: boolean;
  editable: boolean;
  selectedKeyframeIdx?: number | null;
  onSelect: () => void;
  onMove: (startMs: number, endMs: number) => void;
  onDelete?: () => void;
  onKeyframeSelect?: (idx: number) => void;
}

export function ClipBlock({
  clip,
  durationMs,
  selected,
  editable,
  selectedKeyframeIdx,
  onSelect,
  onMove,
  onDelete,
  onKeyframeSelect,
}: ClipBlockProps) {
  const start = Number(clip.start_ms ?? 0);
  const end = Number(clip.end_ms ?? start + 1000);
  const clipDuration = Math.max(end - start, 1);
  const widthPct = durationMs > 0 ? Math.max(2, ((end - start) / durationMs) * 100) : 10;
  const leftPct = durationMs > 0 ? (start / durationMs) * 100 : 0;
  const showTime = widthPct >= 12;
  const displayLabel = clip.label || clip.id || "片段";
  const keyframes: ClipKeyframe[] = clip.transform?.keyframes ?? [];
  const badges = clip.track === "video" ? clipBadgeSummary(clip) : [];

  function onPointerDown(edge: "move" | "start" | "end", e: React.PointerEvent) {
    if (!editable) return;
    e.stopPropagation();
    e.preventDefault();
    const lane = (e.currentTarget as HTMLElement).parentElement;
    if (!lane) return;
    const rect = lane.getBoundingClientRect();
    const origStart = start;
    const origEnd = end;

    function onMoveEvt(ev: PointerEvent) {
      const ratio = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
      const ms = Math.round((ratio * durationMs) / 100) * 100;
      if (edge === "move") {
        const len = origEnd - origStart;
        onMove(Math.max(0, ms), Math.max(ms + 500, ms + len));
      } else if (edge === "start") {
        onMove(Math.min(ms, origEnd - 500), origEnd);
      } else {
        onMove(origStart, Math.max(origStart + 500, ms));
      }
    }
    function onUp() {
      window.removeEventListener("pointermove", onMoveEvt);
      window.removeEventListener("pointerup", onUp);
    }
    window.addEventListener("pointermove", onMoveEvt);
    window.addEventListener("pointerup", onUp);
  }

  return (
    <div
      className={`edit-studio-clip edit-studio-clip-${clip.track ?? "video"} ${selected ? "selected" : ""}`}
      style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
      onClick={(e) => {
        e.stopPropagation();
        onSelect();
      }}
      title={`${displayLabel} · ${formatMs(start)}–${formatMs(end)}`}
    >
      {badges.length > 0 && (
        <div className="edit-studio-clip-badges">
          {badges.map((b) => (
            <span key={b} className="edit-studio-clip-badge">
              {b}
            </span>
          ))}
        </div>
      )}
      {keyframes.map((kf, idx) => {
        const pct = Math.max(0, Math.min(100, ((kf.time_ms ?? 0) / clipDuration) * 100));
        return (
          <button
            key={`${idx}-${kf.time_ms ?? 0}`}
            type="button"
            className={`edit-studio-kf-marker ${selectedKeyframeIdx === idx ? "selected" : ""}`}
            style={{ left: `${pct}%` }}
            title={keyframeTooltip(kf)}
            onClick={(e) => {
              e.stopPropagation();
              onSelect();
              onKeyframeSelect?.(idx);
            }}
          />
        );
      })}
      <div className="edit-studio-clip-content">
        <span className="edit-studio-clip-label">{displayLabel}</span>
        {showTime && (
          <span className="edit-studio-clip-time">
            {formatMs(start)}–{formatMs(end)}
          </span>
        )}
      </div>
      {editable && onDelete && (
        <button
          type="button"
          className="edit-studio-clip-delete"
          title="删除片段"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
        >
          ×
        </button>
      )}
      {editable && (
        <>
          <span
            className="edit-studio-clip-handle edit-studio-clip-handle-start"
            onPointerDown={(e) => onPointerDown("start", e)}
          />
          <span
            className="edit-studio-clip-handle edit-studio-clip-handle-move"
            onPointerDown={(e) => onPointerDown("move", e)}
          />
          <span
            className="edit-studio-clip-handle edit-studio-clip-handle-end"
            onPointerDown={(e) => onPointerDown("end", e)}
          />
        </>
      )}
    </div>
  );
}
