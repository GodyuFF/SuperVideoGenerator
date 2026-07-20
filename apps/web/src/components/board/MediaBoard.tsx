/**
 * 看板媒体 Tab：图片/视频用缩略图网格；音频用紧凑播放条，避免 16:9 空框。
 */

import { useCallback, useState } from "react";
import { MediaPreview } from "../MediaPreview";
import type { MediaAssetItem } from "../MediaAssetDetailModal";
import { AssetGeneratingBadge } from "../AssetGeneratingBadge";
import { useAssetGeneration } from "../../context/AssetGenerationContext";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import type { BoardView } from "../../types/board";
import { parseMediaAssetFileRef, resolveMediaPlayUrl } from "../../utils/mediaUrl";
import { revealMediaAssetFromUrl } from "../../utils/exportDownload";

interface MediaBoardProps {
  board: BoardView;
  projectId?: string | null;
  scriptId?: string | null;
  onOpenMedia?: (item: MediaAssetItem) => void;
}

/** 判断媒体类型是否支持「打开文件夹」。 */
function supportsFolderReveal(type: string): boolean {
  return type === "video" || type === "final";
}

/** 是否按音频条目布局（紧凑条，而非 16:9 缩略图）。 */
function isAudioMediaType(type: string): boolean {
  return type === "audio" || type === "tts";
}

/** 将看板原始 item 转为 MediaAssetItem。 */
function toMediaAssetItem(raw: Record<string, unknown>): MediaAssetItem {
  const url = raw.url ? String(raw.url) : undefined;
  return {
    id: String(raw.id),
    type: String(raw.type),
    name: String(raw.name),
    url,
    source_asset_id: raw.source_asset_id ? String(raw.source_asset_id) : null,
    source_asset_name: raw.source_asset_name ? String(raw.source_asset_name) : null,
    source_asset_type: raw.source_asset_type ? String(raw.source_asset_type) : null,
    script_id: raw.script_id ? String(raw.script_id) : null,
    shot_id: raw.shot_id ? String(raw.shot_id) : null,
    duration_ms: raw.duration_ms != null ? Number(raw.duration_ms) : null,
    narration_text: raw.narration_text ? String(raw.narration_text) : null,
    status: raw.status ? String(raw.status) : undefined,
  };
}

/** 格式化毫秒时长为 mm:ss。 */
function formatDurationMs(ms: number | null | undefined): string | null {
  if (ms == null || !Number.isFinite(ms) || ms <= 0) return null;
  const totalSec = Math.round(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** 剧本媒体资产看板。 */
export function MediaBoard({ board, projectId, scriptId, onOpenMedia }: MediaBoardProps) {
  const { t } = useAppTranslation("board");
  const { getEntryForTargets } = useAssetGeneration();
  const [revealingId, setRevealingId] = useState<string | null>(null);
  const [revealError, setRevealError] = useState<string | null>(null);

  const items = board.items ?? [];
  const byType: Record<string, typeof items> = {};
  for (const raw of items) {
    const mediaType = String((raw as Record<string, unknown>).type);
    byType[mediaType] = byType[mediaType] ?? [];
    byType[mediaType].push(raw);
  }

  /** 在系统文件管理器中定位视频/成片文件。 */
  const handleReveal = useCallback(
    async (item: MediaAssetItem, e: React.MouseEvent) => {
      e.stopPropagation();
      e.preventDefault();
      setRevealError(null);
      setRevealingId(item.id);
      try {
        await revealMediaAssetFromUrl(item.url, projectId, scriptId);
      } catch (err) {
        setRevealError(err instanceof Error ? err.message : String(err));
      } finally {
        setRevealingId(null);
      }
    },
    [projectId, scriptId],
  );

  if (items.length === 0) {
    return <p className="muted">{t("noMediaYet")}</p>;
  }

  return (
    <div className="media-board-groups">
      {revealError ? <p className="board-error media-board-reveal-error">{revealError}</p> : null}
      {Object.entries(byType).map(([type, group]) => {
        const audioSection = isAudioMediaType(type);
        return (
          <section key={type} className="media-board-section">
            <h4 className="media-board-section-title">
              {t(`mediaPanel.types.${type}`, { defaultValue: type })}（{group.length}）
            </h4>
            <ul
              className={
                audioSection ? "media-board-grid media-board-grid--audio" : "media-board-grid"
              }
            >
              {group.map((raw) => {
                const m = raw as Record<string, unknown>;
                const item = toMediaAssetItem(m);
                const url = item.url ?? "";
                const fileRef = parseMediaAssetFileRef(url, projectId, scriptId);
                const showFolder = supportsFolderReveal(item.type) && fileRef != null;
                const genEntry = getEntryForTargets([
                  item.id,
                  item.source_asset_id,
                  item.shot_id,
                ]);
                const playUrl = resolveMediaPlayUrl(url, projectId, scriptId);
                const durationLabel = formatDurationMs(item.duration_ms);

                if (isAudioMediaType(item.type)) {
                  return (
                    <li
                      key={item.id}
                      className={`media-board-card media-board-card--audio${genEntry?.phase === "generating" ? " board-card--generating" : ""}`}
                    >
                      <div className="media-board-audio-row">
                        <button
                          type="button"
                          className="media-board-audio-hit"
                          onClick={onOpenMedia ? () => onOpenMedia(item) : undefined}
                          disabled={!onOpenMedia}
                        >
                          <span className="media-board-audio-glyph" aria-hidden="true">
                            <span className="media-board-audio-bar" />
                            <span className="media-board-audio-bar" />
                            <span className="media-board-audio-bar" />
                            <span className="media-board-audio-bar" />
                          </span>
                          <span className="media-board-card-meta">
                            <span className="media-board-card-name">{item.name}</span>
                            <span className="media-board-audio-sub muted">
                              {durationLabel ? (
                                <span className="tabular-nums">{durationLabel}</span>
                              ) : null}
                              {durationLabel && item.shot_id ? " · " : null}
                              {item.shot_id
                                ? t("mediaPanel.shotRef", { id: item.shot_id })
                                : null}
                            </span>
                            {genEntry ? (
                              <AssetGeneratingBadge entry={genEntry} variant="compact" />
                            ) : null}
                          </span>
                        </button>
                        {playUrl ? (
                          <audio
                            className="media-board-audio-player"
                            controls
                            preload="metadata"
                            src={playUrl}
                            onClick={(e) => e.stopPropagation()}
                          />
                        ) : (
                          <p className="muted media-board-audio-missing">
                            {t("mediaPanel.noPreview")}
                          </p>
                        )}
                      </div>
                    </li>
                  );
                }

                return (
                  <li
                    key={item.id}
                    className={`media-board-card${genEntry?.phase === "generating" ? " board-card--generating" : ""}`}
                  >
                    <button
                      type="button"
                      className="media-board-card-main"
                      onClick={onOpenMedia ? () => onOpenMedia(item) : undefined}
                      disabled={!onOpenMedia}
                    >
                      <div className="media-board-thumb">
                        <MediaPreview
                          kind={item.type}
                          url={url}
                          projectId={projectId}
                          scriptId={scriptId}
                          variant="thumb"
                          className="media-board-preview"
                        />
                      </div>
                      <div className="media-board-card-meta">
                        <span className="media-board-card-name">{item.name}</span>
                        {genEntry ? (
                          <AssetGeneratingBadge entry={genEntry} variant="compact" />
                        ) : null}
                        {item.shot_id ? (
                          <span className="media-board-card-shot muted">
                            {t("mediaPanel.shotRef", { id: item.shot_id })}
                          </span>
                        ) : null}
                      </div>
                    </button>
                    {showFolder ? (
                      <button
                        type="button"
                        className="btn-secondary btn-sm media-board-folder-btn"
                        disabled={revealingId === item.id}
                        onClick={(e) => void handleReveal(item, e)}
                      >
                        {revealingId === item.id
                          ? t("mediaPanel.openingFolder")
                          : t("openFolder")}
                      </button>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
