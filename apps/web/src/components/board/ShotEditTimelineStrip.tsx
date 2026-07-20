/**
 * 分镜子镜内的全片 EditTimeline 迷你轨条（非单段短视频预览）。
 */

import type { CSSProperties } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import type { EditTimelineStripSummary } from "../../utils/editTimelineSummary";
import { formatMs } from "./storyboardShared";

interface ShotEditTimelineStripProps {
  summary: EditTimelineStripSummary;
  /** 跳转剪辑 Tab；仅有真正 EditTimeline 时传入。 */
  onOpenEditTimeline?: () => void;
}

const TRACK_ORDER = ["video", "audio", "subtitle"] as const;

/** clip 在全片时长上的定位样式。 */
function clipStyle(startMs: number, endMs: number, totalMs: number): CSSProperties {
  const total = Math.max(totalMs, 1);
  const left = (Math.max(0, startMs) / total) * 100;
  const width = (Math.max(0, endMs - startMs) / total) * 100;
  return { left: `${left}%`, width: `${Math.max(width, 1.5)}%` };
}

/** 全片剪辑轴迷你可视化 + 前往剪辑 Tab。 */
export function ShotEditTimelineStrip({
  summary,
  onOpenEditTimeline,
}: ShotEditTimelineStripProps) {
  const { t } = useAppTranslation("board");
  const trackLabels: Record<(typeof TRACK_ORDER)[number], string> = {
    video: t("storyboard.subShot.timelineTrackVideo"),
    audio: t("storyboard.subShot.timelineTrackAudio"),
    subtitle: t("storyboard.subShot.timelineTrackSubtitle"),
  };

  return (
    <section className="shot-subshot-content shot-subshot-content--timeline">
      <div className="shot-subshot-content__head">
        <span className="shot-subshot-content__eyebrow">
          {t("storyboard.subShot.timelineSection")}
        </span>
      </div>
      <p className="muted shot-edit-timeline-strip__lead">
        {t("storyboard.subShot.timelineEditHint")}
      </p>
      <p className="muted tabular-nums shot-edit-timeline-strip__duration">
        {t("storyboard.subShot.timelineDuration", {
          duration: formatMs(summary.durationMs),
        })}
      </p>
      <div className="shot-edit-timeline-strip" aria-label={t("storyboard.subShot.timelineSection")}>
        <div className="shot-edit-timeline-strip__ruler">
          <span>0:00</span>
          <span>{formatMs(summary.durationMs)}</span>
        </div>
        {TRACK_ORDER.map((key) => {
          const clips = summary.tracks[key] ?? [];
          return (
            <div key={key} className="shot-edit-timeline-strip__row">
              <span className="shot-edit-timeline-strip__label">{trackLabels[key]}</span>
              <div className="shot-edit-timeline-strip__lane">
                {clips.length === 0 ? (
                  <span className="muted shot-edit-timeline-strip__empty">—</span>
                ) : (
                  clips.map((clip) => (
                    <div
                      key={clip.id}
                      className={`shot-edit-timeline-strip__clip shot-edit-timeline-strip__clip--${key}`}
                      style={clipStyle(clip.startMs, clip.endMs, summary.durationMs)}
                      title={`${formatMs(clip.startMs)}–${formatMs(clip.endMs)}${
                        clip.label ? ` · ${clip.label}` : ""
                      }`}
                    />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
      {onOpenEditTimeline ? (
        <button
          type="button"
          className="btn-secondary btn-sm"
          onClick={(e) => {
            e.stopPropagation();
            onOpenEditTimeline();
          }}
        >
          {t("storyboard.subShot.openEditTimeline")}
        </button>
      ) : null}
    </section>
  );
}
