/**
 * 镜内迷你时间轴：配音幕轨 + 画面轨双轨可视化。
 */

import { useMemo } from "react";
import type { CSSProperties } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { formatMs } from "./storyboardShared";
import type { ShotFrameView, ShotVoiceActView } from "../../utils/shotSegmentUtils";
import {
  resolveSubShotDisplayRange,
  subShotHasVisualMediaContent,
  type ResolvedShotDuration,
  type ShotDurationSource,
} from "../../utils/shotSegmentUtils";

export type ShotSegmentSelection =
  | { kind: "voice"; id: string }
  | { kind: "visual"; id: string }
  | null;

interface ShotMiniTimelineProps {
  durationMs: number;
  /** 按剪辑 > 视频 > 配音 > 计划解析的镜级展示总时长。 */
  displayDurationMs?: number;
  displayDurationSource?: ShotDurationSource;
  voiceActs: ShotVoiceActView[];
  sub_shots: ShotFrameView[];
  selected?: ShotSegmentSelection;
  onSelect?: (sel: ShotSegmentSelection) => void;
}

/** 将毫秒映射为轨道内百分比宽度。 */
function segmentStyle(startMs: number, endMs: number, totalMs: number): CSSProperties {
  const total = Math.max(totalMs, 1);
  const left = (Math.max(0, startMs) / total) * 100;
  const width = (Math.max(0, endMs - startMs) / total) * 100;
  return { left: `${left}%`, width: `${Math.max(width, 2)}%` };
}

/** 镜内双轨时间尺与段块。 */
export function ShotMiniTimeline({
  durationMs,
  displayDurationMs,
  displayDurationSource,
  voiceActs,
  sub_shots,
  selected,
  onSelect,
}: ShotMiniTimelineProps) {
  const { t } = useAppTranslation("board");
  const total = Math.max(displayDurationMs ?? durationMs, 1);

  const visualRanges = useMemo(
    () =>
      sub_shots
        .filter((vis) => subShotHasVisualMediaContent(vis))
        .map(
          (vis): { id: string; range: ResolvedShotDuration } => ({
            id: vis.id,
            range: resolveSubShotDisplayRange(vis, voiceActs),
          }),
        ),
    [sub_shots, voiceActs],
  );

  const ticks = useMemo(() => {
    const n = Math.min(7, Math.max(3, Math.ceil(total / 2000) + 1));
    return Array.from({ length: n }, (_, i) => Math.round((i / (n - 1)) * total));
  }, [total]);

  return (
    <section className="asset-detail-section shot-mini-timeline" aria-label={t("storyboard.miniTimeline.label")}>
      <div className="shot-mini-timeline__head">
        <h4>{t("storyboard.sectionTimeline")}</h4>
        <span className="shot-mini-timeline__duration tabular-nums">
          {formatMs(0)} – {formatMs(total)}
          <span className="muted">
            {" "}
            ·{" "}
            {t("storyboard.miniTimeline.displaySec", {
              sec: (total / 1000).toFixed(1),
              source: t(
                `storyboard.durationSource.${displayDurationSource ?? "plan"}`,
              ),
            })}
          </span>
        </span>
      </div>

      <div className="shot-mini-timeline__ruler" aria-hidden>
        {ticks.map((ms) => (
          <span key={ms} className="shot-mini-timeline__tick" style={{ left: `${(ms / total) * 100}%` }}>
            {formatMs(ms)}
          </span>
        ))}
      </div>

      <div className="shot-mini-timeline__track-row">
        <span className="shot-mini-timeline__track-label">{t("storyboard.miniTimeline.voiceTrack")}</span>
        <div className="shot-mini-timeline__track shot-mini-timeline__track--voice">
          {voiceActs.length === 0 ? (
            <span className="shot-mini-timeline__empty">{t("storyboard.miniTimeline.emptyVoice")}</span>
          ) : (
            voiceActs.map((act) => {
              const isSel = selected?.kind === "voice" && selected.id === act.id;
              return (
                <button
                  key={act.id}
                  type="button"
                  className={`shot-mini-timeline__seg shot-mini-timeline__seg--voice${isSel ? " is-selected" : ""}`}
                  style={segmentStyle(act.startMs, act.endMs, total)}
                  title={act.text || t("storyboard.miniTimeline.voiceSegment")}
                  onClick={() => onSelect?.({ kind: "voice", id: act.id })}
                />
              );
            })
          )}
        </div>
      </div>

      <div className="shot-mini-timeline__track-row">
        <span className="shot-mini-timeline__track-label">{t("storyboard.miniTimeline.visualTrack")}</span>
        <div className="shot-mini-timeline__track shot-mini-timeline__track--visual">
          {visualRanges.length === 0 ? (
            <span className="shot-mini-timeline__empty">{t("storyboard.miniTimeline.emptyFrame")}</span>
          ) : (
            visualRanges.map(({ id, range }) => {
              const isSel = selected?.kind === "visual" && selected.id === id;
              const vis = sub_shots.find((v) => v.id === id);
              return (
                <button
                  key={id}
                  type="button"
                  className={`shot-mini-timeline__seg shot-mini-timeline__seg--visual${isSel ? " is-selected" : ""}`}
                  style={segmentStyle(range.startMs, range.endMs, total)}
                  title={vis?.description || t("storyboard.miniTimeline.frame")}
                  onClick={() => onSelect?.({ kind: "visual", id })}
                />
              );
            })
          )}
        </div>
      </div>
    </section>
  );
}
