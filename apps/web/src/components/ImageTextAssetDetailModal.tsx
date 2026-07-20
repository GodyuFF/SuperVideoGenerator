/**
 * 图文资产详情弹窗：只读展示 + 二次生成（未执行态）。
 *
 * 「关联图片/视频」来自看板 item.images|media|variants；「资产谱系」是引用边列表，二者独立。
 */

import { useCallback, useEffect, useState } from "react";
import {
  TYPE_LABEL,
  TRAIT_LABEL,
  assetImages,
  assetVideos,
  elementRefsFromItem,
  fieldFromItem,
  isSimplifiedClipAssetType,
  promptFieldKeyForClipType,
  traitEntries,
  variantRefsFromItem,
} from "./imageTextAssetShared";
import { useAppTranslation } from "../i18n/useAppTranslation";
import { AssetImagePreview } from "./AssetImagePreview";
import { MediaPreview } from "./MediaPreview";
import { AssetLineagePanel } from "./AssetLineagePanel";
import { AssetRegenerateButton } from "./AssetRegenerateButton";
import { AssetGeneratingBadge } from "./AssetGeneratingBadge";
import { useAssetGeneration } from "../context/AssetGenerationContext";
import { AssetDetailShell } from "./assetDetail/AssetDetailShell";
import { AssetDetailHeader } from "./assetDetail/AssetDetailHeader";
import { AssetDetailSection } from "./assetDetail/AssetDetailSection";
import { ResolvedPromptPreview } from "./assetDetail/ResolvedPromptPreview";
import { LinkedAssetRefsSection } from "./LinkedAssetRefsSection";
import type { ImageTextAssetItem } from "./ImageTextAssetCard";
import {
  fetchBoardTextAssetItem,
  isSparseTextAssetItem,
} from "../lib/fetchBoardTextAsset";

interface ImageTextAssetDetailModalProps {
  item: ImageTextAssetItem;
  projectId?: string | null;
  scriptId?: string | null;
  onClose: () => void;
  onEdit?: (item: ImageTextAssetItem) => void;
  onNavigateAsset?: (id: string, kind: string) => void;
  manualEditEnabled?: boolean;
  onRegenerated?: () => void;
}

/** 图文 / video_clip 文字资产只读详情弹窗。 */
export function ImageTextAssetDetailModal({
  item,
  projectId,
  scriptId,
  onClose,
  onEdit,
  onNavigateAsset,
  manualEditEnabled = false,
  onRegenerated,
}: ImageTextAssetDetailModalProps) {
  const { t } = useAppTranslation("common");
  const { getEntry } = useAssetGeneration();
  const [resolved, setResolved] = useState(item);
  const [hydrating, setHydrating] = useState(false);
  const [regenStatus, setRegenStatus] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);

  /** 谱系跳转常只带 id/name：从看板补全 images / content。 */
  useEffect(() => {
    setResolved(item);
    setRegenStatus(null);
    if (!projectId || !scriptId || !isSparseTextAssetItem(item)) return;
    let cancelled = false;
    setHydrating(true);
    void fetchBoardTextAssetItem(projectId, scriptId, item.id, item.type)
      .then((full) => {
        if (!cancelled && full) setResolved(full);
      })
      .finally(() => {
        if (!cancelled) setHydrating(false);
      });
    return () => {
      cancelled = true;
    };
  }, [item, projectId, scriptId]);

  /** 缓存回调，避免二次生成按钮 effect 循环。 */
  const handleRegenStatus = useCallback(
    (status: { tone: "success" | "error"; text: string } | null) => {
      setRegenStatus(status);
    },
    [],
  );

  const genEntry = getEntry(resolved.id);

  const isVideoClip = resolved.type === "video_clip";
  const isSimplifiedClip = isSimplifiedClipAssetType(resolved.type);
  const promptFieldKey = promptFieldKeyForClipType(resolved.type);
  const images = assetImages(resolved);
  const videos = assetVideos(resolved);
  const useCheckerboard = resolved.type === "character" || resolved.type === "prop";
  const desc =
    fieldFromItem(resolved, "description") || String(resolved.preview ?? "").trim();
  const summary = fieldFromItem(resolved, "summary");
  const traits = isSimplifiedClip ? [] : traitEntries(resolved);
  const tags = resolved.tags ?? [];
  const displayMode =
    resolved.display_mode ?? String(resolved.content?.display_mode ?? "static_image");
  const colorPalette = fieldFromItem(resolved, "color_palette");
  const notes = fieldFromItem(resolved, "notes");
  const promptHint = fieldFromItem(resolved, "prompt_hint");
  const imagePrompt = fieldFromItem(resolved, "image_prompt");
  const negativePrompt = fieldFromItem(resolved, "negative_prompt");
  const videoPrompt = fieldFromItem(resolved, "video_prompt");
  const clipPrompt =
    promptFieldKey === "video_prompt"
      ? videoPrompt
      : promptFieldKey === "image_prompt"
        ? imagePrompt
        : "";
  const typeLabel = TYPE_LABEL[resolved.type] ?? resolved.type;
  const elementRefs = elementRefsFromItem(resolved);
  const variantRefs = variantRefsFromItem(resolved);
  const hasElementRefs = Object.values(elementRefs).some((ids) => (ids ?? []).length > 0);
  const regenerateKind = isVideoClip ? "video" : "image";
  const canPreviewResolvedPrompt = Boolean(
    projectId && (clipPrompt || imagePrompt || hasElementRefs),
  );
  const resolvedPromptActions = canPreviewResolvedPrompt ? (
    <ResolvedPromptPreview
      projectId={projectId}
      assetId={resolved.id}
      enabled={canPreviewResolvedPrompt}
    />
  ) : null;

  return (
    <AssetDetailShell titleId="asset-detail-title" onClose={onClose}>
      <AssetDetailHeader
        typeLabel={typeLabel}
        title={resolved.name}
        titleId="asset-detail-title"
        actions={
          <>
            {genEntry ? <AssetGeneratingBadge entry={genEntry} variant="inline" /> : null}
            {manualEditEnabled && projectId && scriptId && (
              <AssetRegenerateButton
                projectId={projectId}
                scriptId={scriptId}
                assetId={resolved.id}
                kind={regenerateKind}
                layout="inline"
                disabled={!manualEditEnabled}
                onDone={onRegenerated}
                onStatusChange={handleRegenStatus}
              />
            )}
            {onEdit && (
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => onEdit(resolved)}
              >
                {t("actions.edit")}
              </button>
            )}
            <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
              {t("actions.close")}
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
        {summary && (
          <AssetDetailSection title="摘要">
            <p>{summary}</p>
          </AssetDetailSection>
        )}

        {isSimplifiedClip ? (
          <>
            <AssetDetailSection title="关联资产">
              {hasElementRefs ? (
                <LinkedAssetRefsSection
                  elementRefs={elementRefs}
                  variantRefs={variantRefs}
                  projectId={projectId}
                  scriptId={scriptId}
                  onNavigateAsset={onNavigateAsset}
                />
              ) : (
                <p className="muted">尚未关联资产</p>
              )}
            </AssetDetailSection>

            <AssetDetailSection title="提示词" actions={resolvedPromptActions}>
              {clipPrompt ? (
                <pre className="prompt-pre">{clipPrompt}</pre>
              ) : (
                <p className="muted">尚未填写提示词</p>
              )}
            </AssetDetailSection>

            {notes ? (
              <AssetDetailSection title="备注">
                <p className="image-text-notes muted">{notes}</p>
              </AssetDetailSection>
            ) : null}
          </>
        ) : (
          <>
            {desc && (
              <AssetDetailSection title="主视觉描述">
                <p className="image-text-description">{desc}</p>
              </AssetDetailSection>
            )}

            {traits.length > 0 && (
              <AssetDetailSection title="类型属性">
                <dl className="image-text-traits">
                  {traits.map(([key, value]) => (
                    <div key={key} className="trait-row">
                      <dt>{TRAIT_LABEL[key] ?? key}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
              </AssetDetailSection>
            )}

            {hasElementRefs ? (
              <AssetDetailSection title="关联资产">
                <LinkedAssetRefsSection
                  elementRefs={elementRefs}
                  variantRefs={variantRefs}
                  projectId={projectId}
                  scriptId={scriptId}
                  onNavigateAsset={onNavigateAsset}
                />
              </AssetDetailSection>
            ) : null}

            <div className="image-text-meta">
              {resolved.scope && <span className="meta-chip">范围：{resolved.scope}</span>}
              {resolved.source_script_id && (
                <span className="meta-chip">来源剧本：{resolved.source_script_id}</span>
              )}
              {resolved.user_edited && <span className="meta-chip">已编辑</span>}
              {resolved.visual_style && (
                <span className="meta-chip">风格：{resolved.visual_style}</span>
              )}
              {colorPalette && <span className="meta-chip">色调：{colorPalette}</span>}
              {displayMode === "dynamic_image" && <span className="meta-chip">动态图</span>}
              {tags.map((tag) => (
                <span key={tag} className="meta-chip tag">
                  {tag}
                </span>
              ))}
            </div>

            {notes && (
              <AssetDetailSection title="备注">
                <p className="image-text-notes muted">{notes}</p>
              </AssetDetailSection>
            )}

            {(promptHint || imagePrompt || negativePrompt || canPreviewResolvedPrompt) && (
              <AssetDetailSection title="生图提示词" actions={resolvedPromptActions}>
                <div className="prompt-block">
                  {promptHint && (
                    <p>
                      <strong>增强：</strong>
                      {promptHint}
                    </p>
                  )}
                  {imagePrompt && <pre className="prompt-pre">{imagePrompt}</pre>}
                  {negativePrompt && (
                    <p className="muted">
                      <strong>负向：</strong>
                      {negativePrompt}
                    </p>
                  )}
                </div>
              </AssetDetailSection>
            )}

            {(resolved.variants?.length ?? 0) > 0 && (
              <AssetDetailSection title="图片变体">
                <ul className="variant-list">
                  {resolved.variants!.map((v) => (
                    <li key={v.id ?? v.label} className="variant-list-item">
                      <span className="meta-chip">
                        {v.is_primary ? "主形象" : v.kind ?? "变体"}
                      </span>
                      <strong>{v.label}</strong>
                      {v.meaning && (
                        <span className="muted"> — {v.meaning.slice(0, 80)}</span>
                      )}
                      {v.variant_prompt ? (
                        <p className="variant-list-prompt muted">{v.variant_prompt}</p>
                      ) : null}
                      {v.preview_url && (
                        <AssetImagePreview
                          url={v.preview_url}
                          name={v.label}
                          size="card"
                          checkerboard={useCheckerboard}
                          projectId={projectId}
                          scriptId={scriptId}
                        />
                      )}
                      {manualEditEnabled && projectId && scriptId && v.id && (
                        <AssetRegenerateButton
                          projectId={projectId}
                          scriptId={scriptId}
                          assetId={resolved.id}
                          variantId={v.id}
                          kind="image"
                          layout="compact"
                          onDone={onRegenerated}
                        />
                      )}
                    </li>
                  ))}
                </ul>
              </AssetDetailSection>
            )}
          </>
        )}

        {isVideoClip ? (
          videos.length > 0 ? (
            <AssetDetailSection title="关联视频">
              <div className="character-images character-images--detail">
                {videos.map((vid) =>
                  vid.url ? (
                    <div key={vid.id ?? vid.url} className="lineage-media-thumb">
                      <MediaPreview
                        kind="video"
                        url={vid.url}
                        label={vid.name}
                        projectId={projectId}
                        scriptId={scriptId}
                      />
                      {vid.id && <code className="lineage-id">{vid.id}</code>}
                    </div>
                  ) : null,
                )}
              </div>
            </AssetDetailSection>
          ) : null
        ) : (
          images.length > 0 ? (
            <AssetDetailSection title="关联图片">
              <div className="character-images character-images--detail">
                {images.map((img) =>
                  img.url ? (
                    <div key={img.id ?? img.url} className="lineage-media-thumb">
                      <AssetImagePreview
                        url={img.url}
                        name={img.name}
                        size="detail"
                        checkerboard={useCheckerboard}
                        projectId={projectId}
                        scriptId={scriptId}
                        enableLightbox
                      />
                      {img.id && <code className="lineage-id">{img.id}</code>}
                    </div>
                  ) : null,
                )}
              </div>
            </AssetDetailSection>
          ) : hydrating ? (
            <AssetDetailSection title="关联图片">
              <p className="muted">加载关联图片…</p>
            </AssetDetailSection>
          ) : null
        )}

        {projectId && (
          <AssetDetailSection title="资产谱系">
            <AssetLineagePanel
              projectId={projectId}
              assetId={resolved.id}
              onNavigateAsset={onNavigateAsset}
            />
          </AssetDetailSection>
        )}
      </div>
    </AssetDetailShell>
  );
}
