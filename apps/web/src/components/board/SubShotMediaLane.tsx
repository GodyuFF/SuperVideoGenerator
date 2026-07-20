/**
 * 子镜内媒体时段条：在子镜区间上可视化多画面 / 多视频占用。
 */

import type { CSSProperties } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { formatMs } from "./storyboardShared";

/** 子镜内一条媒体时段。 */
export interface SubShotMediaLaneSegment {
  id: string;
  startMs: number;
  endMs: number;
  label: string;
  kind: "frame" | "video";
}

interface SubShotMediaLaneProps {
  /** 子镜起点（相对镜）。 */
  subStartMs: number;
  /** 子镜终点（相对镜）。 */
  subEndMs: number;
  segments: SubShotMediaLaneSegment[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}

/** 相对子镜区间计算百分比定位。 */
function laneStyle(
  startMs: number,
  endMs: number,
  subStartMs: number,
  subEndMs: number,
): CSSProperties {
  const span = Math.max(subEndMs - subStartMs, 1);
  const left = ((Math.max(startMs, subStartMs) - subStartMs) / span) * 100;
  const width = ((Math.min(endMs, subEndMs) - Math.max(startMs, subStartMs)) / span) * 100;
  return { left: `${left}%`, width: `${Math.max(width, 2.5)}%` };
}

/** 子镜内画面/视频双轨迷你时间轴。 */
export function SubShotMediaLane({
  subStartMs,
  subEndMs,
  segments,
  selectedId,
  onSelect,
}: SubShotMediaLaneProps) {
  const { t } = useAppTranslation("board");
  const frames = segments.filter((s) => s.kind === "frame");
  const videos = segments.filter((s) => s.kind === "video");

  if (frames.length === 0 && videos.length === 0) {
    return (
      <p className="muted sub-shot-media-lane__empty">{t("storyboard.subShot.laneEmpty")}</p>
    );
  }

  /** 渲染单轨。 */
  const renderTrack = (
    kind: "frame" | "video",
    items: SubShotMediaLaneSegment[],
  ) => (
    <div className="sub-shot-media-lane__track-row">
      <span className="sub-shot-media-lane__track-label">
        {kind === "frame"
          ? t("storyboard.subShot.frameSection")
          : t("storyboard.subShot.videoSection")}
      </span>
      <div
        className={`sub-shot-media-lane__track sub-shot-media-lane__track--${kind}`}
        role="list"
      >
        {items.map((seg) => (
          <button
            key={seg.id}
            type="button"
            role="listitem"
            className={`sub-shot-media-lane__seg${selectedId === seg.id ? " is-selected" : ""}`}
            style={laneStyle(seg.startMs, seg.endMs, subStartMs, subEndMs)}
            title={`${seg.label} · ${formatMs(seg.startMs)}–${formatMs(seg.endMs)}`}
            onClick={() => onSelect?.(seg.id)}
          >
            <span className="sub-shot-media-lane__seg-label">{seg.label}</span>
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <section
      className="sub-shot-media-lane"
      aria-label={t("storyboard.subShot.laneLabel")}
    >
      <header className="sub-shot-media-lane__head">
        <span className="sub-shot-media-lane__eyebrow">
          {t("storyboard.subShot.laneLabel")}
        </span>
        <span className="tabular-nums muted">
          {formatMs(subStartMs)}–{formatMs(subEndMs)}
        </span>
      </header>
      {frames.length > 0 ? renderTrack("frame", frames) : null}
      {videos.length > 0 ? renderTrack("video", videos) : null}
    </section>
  );
}
