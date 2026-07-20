/**
 * 媒体资产详情弹窗：预览、来源文字资产与谱系关联。
 */

import { useCallback, useState } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
import { MediaPreview } from "./MediaPreview";
import { AssetImagePreview } from "./AssetImagePreview";
import { AssetLineagePanel } from "./AssetLineagePanel";
import { AssetRegenerateButton, type RegenerateKind } from "./AssetRegenerateButton";
import { AssetGeneratingBadge } from "./AssetGeneratingBadge";
import { useAssetGeneration } from "../context/AssetGenerationContext";
import { AssetDetailShell } from "./assetDetail/AssetDetailShell";
import { AssetDetailHeader } from "./assetDetail/AssetDetailHeader";
import { AssetDetailSection } from "./assetDetail/AssetDetailSection";
import { KIND_LABEL } from "../types/lineage";
import { parseMediaAssetFileRef } from "../utils/mediaUrl";
import { revealMediaAssetFromUrl } from "../utils/exportDownload";

export interface MediaAssetItem {
  id: string;
  type: string;
  name: string;
  url?: string;
  source_asset_id?: string | null;
  source_asset_name?: string | null;
  source_asset_type?: string | null;
  script_id?: string | null;
  shot_id?: string | null;
  duration_ms?: number | null;
  narration_text?: string | null;
  status?: string;
}

interface MediaAssetDetailModalProps {
  item: MediaAssetItem;
  projectId: string;
  scriptId?: string | null;
  onClose: () => void;
  onNavigateAsset?: (id: string, kind: string) => void;
  manualEditEnabled?: boolean;
  onRegenerated?: () => void;
}

/** 判断详情弹窗是否展示「打开文件夹」。 */
function supportsFolderReveal(type: string): boolean {
  return type === "video" || type === "final";
}

/** 按媒体类型映射二次生成按钮 kind。 */
function regenerateKindForMedia(type: string): RegenerateKind | null {
  if (type === "image") return "image";
  if (type === "audio" || type === "tts") return "tts";
  if (type === "video") return "video";
  return null;
}

/** 媒体资产只读详情弹窗。 */
export function MediaAssetDetailModal({
  item,
  projectId,
  scriptId,
  onClose,
  onNavigateAsset,
  manualEditEnabled = false,
  onRegenerated,
}: MediaAssetDetailModalProps) {
  const { t } = useAppTranslation("board");
  const { getEntryForTargets } = useAssetGeneration();
  const genEntry = getEntryForTargets([item.id, item.source_asset_id, item.shot_id]);

  const [revealing, setRevealing] = useState(false);
  const [revealError, setRevealError] = useState<string | null>(null);
  const [regenStatus, setRegenStatus] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);

  const typeLabel = KIND_LABEL[item.type] ?? item.type;
  const fileRef = parseMediaAssetFileRef(item.url, projectId, scriptId);
  const showFolder = supportsFolderReveal(item.type) && fileRef != null;
  const regenKind = regenerateKindForMedia(item.type);

  /** 缓存二次生成状态回调。 */
  const handleRegenStatus = useCallback(
    (status: { tone: "success" | "error"; text: string } | null) => {
      setRegenStatus(status);
    },
    [],
  );

  /** 在资源管理器中定位本地视频/成片文件。 */
  const handleReveal = useCallback(async () => {
    setRevealError(null);
    setRevealing(true);
    try {
      await revealMediaAssetFromUrl(item.url, projectId, scriptId);
    } catch (err) {
      setRevealError(err instanceof Error ? err.message : String(err));
    } finally {
      setRevealing(false);
    }
  }, [item.url, projectId, scriptId]);

  return (
    <AssetDetailShell titleId="media-detail-title" onClose={onClose}>
      <AssetDetailHeader
        typeLabel={typeLabel}
        title={item.name}
        titleId="media-detail-title"
        actions={
          <>
            {genEntry ? <AssetGeneratingBadge entry={genEntry} variant="inline" /> : null}
            {manualEditEnabled && scriptId && regenKind && (
              <AssetRegenerateButton
                projectId={projectId}
                scriptId={scriptId}
                assetId={item.id}
                kind={regenKind}
                layout="inline"
                onDone={onRegenerated}
                onStatusChange={handleRegenStatus}
              />
            )}
            <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
              {t("mediaPanel.close")}
            </button>
          </>
        }
        status={
          regenStatus ? (
            <p
              className={`asset-regenerate-status asset-regenerate-status--${regenStatus.tone}`}
              role={regenStatus.tone === "error" ? "alert" : "status"}
            >
              {regenStatus.text}
            </p>
          ) : null
        }
      />

      <div className="asset-detail-body">
        <AssetDetailSection title={t("mediaPanel.preview")}>
          {item.url ? (
            <div className="media-detail-preview-frame">
              {item.type === "image" ? (
                <AssetImagePreview
                  url={item.url}
                  name={item.name}
                  size="detail"
                  projectId={projectId}
                  scriptId={scriptId}
                  enableLightbox
                />
              ) : (
                <MediaPreview
                  kind={item.type}
                  url={item.url}
                  projectId={projectId}
                  scriptId={scriptId}
                  className="media-detail-preview"
                />
              )}
            </div>
          ) : (
            <p className="muted">{t("mediaPanel.noPreview")}</p>
          )}
          {showFolder ? (
            <div className="media-detail-actions">
              <button
                type="button"
                className="btn-secondary btn-sm"
                disabled={revealing}
                onClick={() => void handleReveal()}
              >
                {revealing ? t("mediaPanel.openingFolder") : t("openFolder")}
              </button>
              {revealError ? (
                <p className="asset-regenerate-status asset-regenerate-status--error" role="alert">
                  {revealError}
                </p>
              ) : null}
            </div>
          ) : null}
        </AssetDetailSection>

        <AssetDetailSection title={t("mediaPanel.metadata")}>
          <dl className="image-text-traits">
            <div className="trait-row">
              <dt>ID</dt>
              <dd>
                <code>{item.id}</code>
              </dd>
            </div>
            {item.shot_id && (
              <div className="trait-row">
                <dt>{t("mediaPanel.shot")}</dt>
                <dd>
                  {onNavigateAsset ? (
                    <button
                      type="button"
                      className="lineage-link-btn"
                      onClick={() => onNavigateAsset(item.shot_id!, "shot")}
                    >
                      {item.shot_id}
                    </button>
                  ) : (
                    item.shot_id
                  )}
                </dd>
              </div>
            )}
            {item.duration_ms != null && item.duration_ms > 0 && (
              <div className="trait-row">
                <dt>{t("mediaPanel.duration")}</dt>
                <dd>{(item.duration_ms / 1000).toFixed(2)}s</dd>
              </div>
            )}
            {item.source_asset_id && (
              <div className="trait-row">
                <dt>{t("mediaPanel.sourceAsset")}</dt>
                <dd>
                  {onNavigateAsset ? (
                    <button
                      type="button"
                      className="lineage-link-btn"
                      onClick={() =>
                        onNavigateAsset(
                          item.source_asset_id!,
                          item.source_asset_type ?? "character",
                        )
                      }
                    >
                      {item.source_asset_name ?? item.source_asset_id}
                    </button>
                  ) : (
                    item.source_asset_name ?? item.source_asset_id
                  )}
                </dd>
              </div>
            )}
            {item.narration_text && (
              <div className="trait-row">
                <dt>{t("mediaPanel.narration")}</dt>
                <dd>{item.narration_text}</dd>
              </div>
            )}
          </dl>
        </AssetDetailSection>

        <AssetDetailSection title={t("mediaPanel.related")}>
          <AssetLineagePanel
            projectId={projectId}
            assetId={item.id}
            onNavigateAsset={onNavigateAsset}
          />
        </AssetDetailSection>
      </div>
    </AssetDetailShell>
  );
}
