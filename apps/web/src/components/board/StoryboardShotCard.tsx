/**
 * 分镜单镜胶片条卡片：16:9 预览、时间轨节点、状态徽章与试听。
 */

import { type KeyboardEvent } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { AssetImagePreview } from "../AssetImagePreview";
import { AssetGeneratingBadge } from "../AssetGeneratingBadge";
import { useAssetGeneration } from "../../context/AssetGenerationContext";
import { MediaPreview } from "../MediaPreview";
import type { StoryboardShotView } from "./storyboardShared";
import { formatShotDurationDisplay } from "./storyboardShared";

interface StoryboardShotCardProps {
  shot: StoryboardShotView;
  displayIndex: number;
  projectId?: string | null;
  scriptId?: string | null;
  /** 合并模式：展示勾选框，点击卡片切换选中。 */
  mergeMode?: boolean;
  mergeSelected?: boolean;
  onOpen?: (shot: StoryboardShotView) => void;
}

/** 单镜胶片条卡片。 */
export function StoryboardShotCard({
  shot,
  displayIndex,
  projectId,
  scriptId,
  mergeMode = false,
  mergeSelected = false,
  onOpen,
}: StoryboardShotCardProps) {
  const { t } = useAppTranslation("board");
  const { getShotEntry } = useAssetGeneration();
  const genEntry = getShotEntry(shot);
  const isGenerating = genEntry?.phase === "generating";

  const handleOpen = () => onOpen?.(shot);
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleOpen();
    }
  };

  const subtitleCount = shot.subtitle_lines.length;

  return (
    <article
      className={`storyboard-shot-card${onOpen ? " storyboard-shot-card--clickable" : ""}${
        mergeMode && mergeSelected ? " storyboard-shot-card--merge-selected" : ""
      }${isGenerating ? " board-card--generating" : ""}`}
      role={onOpen ? "button" : undefined}
      tabIndex={onOpen ? 0 : undefined}
      onClick={onOpen ? handleOpen : undefined}
      onKeyDown={onOpen ? handleKeyDown : undefined}
      aria-pressed={mergeMode ? mergeSelected : undefined}
    >
      <div className="storyboard-timeline-rail" aria-hidden="true">
        <span className="storyboard-timeline-dot" />
      </div>

      <div className="storyboard-shot-card__body">
        <header className="storyboard-shot-card__header">
          {mergeMode ? (
            <label
              className="storyboard-merge-check"
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => e.stopPropagation()}
            >
              <input
                type="checkbox"
                checked={mergeSelected}
                onChange={() => handleOpen()}
                aria-label={t("storyboard.edit.mergeSelect", { num: displayIndex })}
              />
            </label>
          ) : null}
          <div className="storyboard-shot-card__meta">
            <span className="storyboard-shot-num">
              {t("storyboard.shotLabel", { num: displayIndex })}
            </span>
            <span className="storyboard-shot-time tabular-nums">{shot.time_label}</span>
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
          </div>
          <div className="storyboard-shot-card__badges">
            {genEntry ? <AssetGeneratingBadge entry={genEntry} /> : null}
            {shot.need_regen ? (
              <span className="storyboard-status-badge storyboard-status-badge--warn">
                {t("storyboard.badgeNeedRegen")}
              </span>
            ) : null}
            {shot.duration_drift ? (
              <span className="storyboard-status-badge storyboard-status-badge--warn">
                {t("storyboard.badgeDurationDrift")}
              </span>
            ) : null}
            {shot.pending_detail ? (
              <span
                className="storyboard-status-badge storyboard-status-badge--pending"
                title={t("storyboard.pendingDetailHint")}
              >
                {t("storyboard.badgePendingDetail")}
              </span>
            ) : null}
            {shot.missing_subtitle_sync ? (
              <span className="storyboard-status-badge storyboard-status-badge--pending">
                {t("storyboard.badgeSubtitleSync")}
              </span>
            ) : null}
          </div>
        </header>

        <div className="storyboard-shot-card__main">
          <div className="storyboard-shot-preview">
            {shot.frame_preview_url ? (
              <AssetImagePreview
                url={shot.frame_preview_url}
                name={shot.frame_asset_name || t("storyboard.frameFallback")}
                size="detail"
                projectId={projectId}
                scriptId={scriptId}
              />
            ) : shot.preview_fallback_url ? (
              <>
                <AssetImagePreview
                  url={shot.preview_fallback_url}
                  alt={t("storyboard.previewFallbackVideo")}
                  size="detail"
                  projectId={projectId}
                  scriptId={scriptId}
                />
                <span className="storyboard-preview-source-chip">
                  {t("storyboard.previewFallbackVideo")}
                </span>
              </>
            ) : shot.frame_asset_name ? (
              <p className="muted storyboard-shot-preview__placeholder">{shot.frame_asset_name}</p>
            ) : (
              <p className="muted storyboard-shot-preview__placeholder">
                {t("storyboard.noFrameYet")}
              </p>
            )}
          </div>

          <div className="storyboard-shot-card__copy">
            {shot.character_names.length > 0 ? (
              <p className="storyboard-table-characters">
                {t("storyboard.characters")}: {shot.character_names.join("、")}
              </p>
            ) : null}
            {shot.narration_text ? (
              <p className="storyboard-shot-narration">{shot.narration_text}</p>
            ) : (
              <p className="muted">—</p>
            )}
            {subtitleCount > 0 ? (
              <p className="muted storyboard-shot-summary">
                {t("storyboard.subtitleSummary", { count: subtitleCount })}
              </p>
            ) : null}
            <div className="storyboard-shot-card__footer">
              <span className="storyboard-motion-chip" title={shot.camera_motion_canonical}>
                {shot.camera_motion_label}
              </span>
              {shot.tts_audio_url ? (
                <div
                  className="storyboard-shot-tts"
                  onClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => e.stopPropagation()}
                >
                  <MediaPreview
                    kind="audio"
                    url={shot.tts_audio_url}
                    label={t("storyboard.previewTts")}
                    projectId={projectId}
                    scriptId={scriptId}
                    className="shot-tts-preview"
                  />
                </div>
              ) : (
                <span className="muted">{t("storyboard.noTts")}</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}
