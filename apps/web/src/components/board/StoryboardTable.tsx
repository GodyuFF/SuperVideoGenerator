/**
 * 分镜紧凑表格：精简列、行点击开详情。
 */

import { useAppTranslation } from "../../i18n/useAppTranslation";
import { AssetImagePreview } from "../AssetImagePreview";
import { MediaPreview } from "../MediaPreview";
import {
  formatShotDurationDisplay,
  type StoryboardShotView,
} from "./storyboardShared";

interface StoryboardTableProps {
  shots: StoryboardShotView[];
  projectId?: string | null;
  scriptId?: string | null;
  mergeMode?: boolean;
  mergeSelection?: string[];
  onOpenShot?: (shot: StoryboardShotView) => void;
}

/** 分镜紧凑表格视图。 */
export function StoryboardTable({
  shots,
  projectId,
  scriptId,
  mergeMode = false,
  mergeSelection = [],
  onOpenShot,
}: StoryboardTableProps) {
  const { t } = useAppTranslation("board");

  if (shots.length === 0) {
    return <p className="muted">{t("storyboard.empty")}</p>;
  }

  return (
    <div className="storyboard-table-wrap storyboard-table-wrap--compact">
      <table className="storyboard-table storyboard-table--compact">
        <thead>
          <tr>
            {mergeMode ? <th className="storyboard-table-merge-col" aria-hidden /> : null}
            <th>{t("storyboard.colNum")}</th>
            <th>{t("storyboard.colTime")}</th>
            <th>{t("storyboard.colDialogue")}</th>
            <th>{t("storyboard.colFrame")}</th>
            <th>{t("storyboard.colMotion")}</th>
            <th>{t("storyboard.colTts")}</th>
          </tr>
        </thead>
        <tbody>
          {shots.map((shot) => {
            const selected = mergeSelection.includes(shot.id);
            const activate = () => onOpenShot?.(shot);
            return (
              <tr
                key={shot.id}
                className={`${onOpenShot ? "storyboard-table-row--clickable" : ""}${
                  mergeMode && selected ? " storyboard-table-row--merge-selected" : ""
                }`.trim() || undefined}
                role={onOpenShot ? "button" : undefined}
                tabIndex={onOpenShot ? 0 : undefined}
                onClick={onOpenShot ? activate : undefined}
                onKeyDown={
                  onOpenShot
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          activate();
                        }
                      }
                    : undefined
                }
                aria-pressed={mergeMode ? selected : undefined}
              >
                {mergeMode ? (
                  <td className="storyboard-table-merge-col" onClick={(e) => e.stopPropagation()}>
                    <label className="storyboard-merge-check">
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={activate}
                        aria-label={t("storyboard.edit.mergeSelect", { num: shot.displayNumber })}
                      />
                    </label>
                  </td>
                ) : null}
                <td className="storyboard-table-num">{shot.displayNumber}</td>
                <td className="storyboard-table-time">
                  <span className="tabular-nums">{shot.time_label}</span>
                  {shot.timeline_source_label ? (
                    <span className="storyboard-source-chip">{shot.timeline_source_label}</span>
                  ) : null}
                  <span
                    className={
                      shot.duration_drift
                        ? "storyboard-table-duration storyboard-table-duration--drift"
                        : "muted storyboard-table-duration"
                    }
                  >
                    {formatShotDurationDisplay(shot, t)}
                  </span>
                  {shot.need_regen ? (
                    <span className="storyboard-regen-badge">{t("storyboard.badgeNeedRegen")}</span>
                  ) : null}
                  {shot.pending_detail ? (
                    <span className="storyboard-status-badge storyboard-status-badge--pending">
                      {t("storyboard.badgePendingDetail")}
                    </span>
                  ) : null}
                </td>
                <td className="storyboard-table-dialogue">
                  {shot.character_names.length > 0 && (
                    <p className="storyboard-table-characters">
                      {t("storyboard.characters")}: {shot.character_names.join("、")}
                    </p>
                  )}
                  {shot.narration_text ? (
                    <p className="storyboard-table-narration storyboard-table-narration--clamp">
                      {shot.narration_text}
                    </p>
                  ) : (
                    <span className="muted">—</span>
                  )}
                  {shot.subtitle_lines.length > 0 ? (
                    <span className="muted storyboard-shot-summary">
                      {t("storyboard.subtitleSummary", { count: shot.subtitle_lines.length })}
                    </span>
                  ) : null}
                </td>
                <td className="storyboard-table-frame">
                  {shot.frame_preview_url ? (
                    <div className="storyboard-frame-preview storyboard-frame-preview--compact">
                      <AssetImagePreview
                        url={shot.frame_preview_url}
                        name={shot.frame_asset_name || t("storyboard.frameFallback")}
                        size="card"
                        projectId={projectId}
                        scriptId={scriptId}
                      />
                    </div>
                  ) : shot.preview_fallback_url ? (
                    <div className="storyboard-frame-preview storyboard-frame-preview--compact storyboard-frame-preview--fallback">
                      <AssetImagePreview
                        url={shot.preview_fallback_url}
                        alt={t("storyboard.previewFallbackVideo")}
                        size="card"
                        projectId={projectId}
                        scriptId={scriptId}
                      />
                      <span className="storyboard-preview-source-chip">
                        {t("storyboard.previewFallbackVideo")}
                      </span>
                    </div>
                  ) : shot.frame_asset_name ? (
                    <span className="muted">{shot.frame_asset_name}</span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td className="storyboard-table-motion">
                  <span title={shot.camera_motion_canonical}>{shot.camera_motion_label}</span>
                </td>
                <td className="storyboard-table-tts" onClick={(e) => e.stopPropagation()}>
                  {shot.tts_audio_url ? (
                    <MediaPreview
                      kind="audio"
                      url={shot.tts_audio_url}
                      label={t("storyboard.previewTts")}
                      projectId={projectId}
                      scriptId={scriptId}
                      className="shot-tts-preview"
                    />
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
