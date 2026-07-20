/**
 * 图文资产卡片：角色 / 物品 / 场景 — 卡片仅展示摘要与预览，详情见弹窗。
 */

import { useState } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
import { AssetImagePreview } from "./AssetImagePreview";
import { MediaPreview } from "./MediaPreview";
import { AssetGeneratingBadge } from "./AssetGeneratingBadge";
import { useAssetGeneration } from "../context/AssetGenerationContext";
import { ImageTextAssetDetailModal } from "./ImageTextAssetDetailModal";
import {
  TYPE_LABEL,
  assetImages,
  assetVideos,
  fieldFromItem,
} from "./imageTextAssetShared";

export interface ImageTextAssetItem {
  id: string;
  type: string;
  name: string;
  summary?: string;
  description?: string;
  visual_style?: string;
  color_palette?: string;
  prompt_hint?: string;
  image_prompt?: string;
  negative_prompt?: string;
  notes?: string;
  tags?: string[];
  display_mode?: string;
  traits?: Record<string, string>;
  content?: Record<string, unknown>;
  /** 摘要/提示词摘录等文案，不是媒体 URL。 */
  preview?: string;
  /** 主预览媒体可播放链路（与 media[] 同源）。 */
  preview_url?: string;
  images?: { id?: string; url?: string; name?: string; type?: string }[];
  media?: { id?: string; url?: string; name?: string; type?: string }[];
  /** video_clip 看板下发的视频子集（与 media 中 type=video 一致）。 */
  videos?: { id?: string; url?: string; name?: string; type?: string }[];
  scope?: string;
  source_script_id?: string | null;
  user_edited?: boolean;
  variants?: {
    id?: string;
    kind?: string;
    label?: string;
    meaning?: string;
    variant_prompt?: string;
    image_prompt?: string;
    media_id?: string | null;
    status?: string;
    is_primary?: boolean;
    preview_url?: string;
  }[];
}

export function ImageTextAssetCard({
  item,
  onEdit,
  onDelete,
  manualEditEnabled = true,
  projectId,
  scriptId,
  scriptLine,
  onNavigateAsset,
  onRegenerated,
}: {
  item: ImageTextAssetItem;
  onEdit?: (item: ImageTextAssetItem) => void;
  onDelete?: (item: ImageTextAssetItem) => void;
  manualEditEnabled?: boolean;
  projectId?: string | null;
  scriptId?: string | null;
  /** 项目看板：来源/引用剧本说明行。 */
  scriptLine?: string;
  onNavigateAsset?: (id: string, kind: string) => void;
  onRegenerated?: () => void;
}) {
  const { t } = useAppTranslation("common");
  const { getEntry } = useAssetGeneration();
  const [detailOpen, setDetailOpen] = useState(false);
  const genEntry = getEntry(item.id);
  const isGenerating = genEntry?.phase === "generating";
  const isVideoClip = item.type === "video_clip";
  const images = assetImages(item);
  const videos = assetVideos(item);
  const summary =
    fieldFromItem(item, "summary") ||
    fieldFromItem(item, "description").slice(0, 120);

  const openDetail = () => setDetailOpen(true);

  return (
    <>
      <article
        className={`board-card image-text-asset-card image-text-asset-card--compact${
          isGenerating ? " board-card--generating" : ""
        }`}
        role="button"
        tabIndex={0}
        onClick={openDetail}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            openDetail();
          }
        }}
      >
        <header className="image-text-asset-header">
          <span className="asset-type-badge">{TYPE_LABEL[item.type] ?? item.type}</span>
          <h4>{item.name}</h4>
          {genEntry ? <AssetGeneratingBadge entry={genEntry} /> : null}
          {item.user_edited && <span className="meta-chip">已编辑</span>}
          <div
            className="image-text-asset-actions"
            onClick={(e) => e.stopPropagation()}
          >
            <button type="button" className="btn-secondary btn-sm" onClick={openDetail}>
              {t("actions.details")}
            </button>
            {manualEditEnabled && onEdit && (
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => onEdit(item)}
              >
                {t("actions.edit")}
              </button>
            )}
            {manualEditEnabled && onDelete && (
              <button
                type="button"
                className="btn-danger btn-sm"
                onClick={() => onDelete(item)}
              >
                {t("actions.delete")}
              </button>
            )}
          </div>
        </header>

        {summary && (
          <p className="image-text-summary image-text-summary--clamp">{summary}</p>
        )}

        {scriptLine ? (
          <p className="knowledge-script-meta muted">{scriptLine}</p>
        ) : null}

        {isVideoClip ? (
          videos.some((vid) => Boolean(vid.url)) ? (
            <div className="character-images">
              {videos.slice(0, 1).map((vid) =>
                vid.url ? (
                  <MediaPreview
                    key={vid.url}
                    kind="video"
                    url={vid.url}
                    label={vid.name}
                    projectId={projectId}
                    scriptId={scriptId}
                  />
                ) : null,
              )}
            </div>
          ) : null
        ) : images.length > 0 ? (
          <div className="character-images">
            {images.slice(0, 2).map((img) =>
              img.url ? (
                <AssetImagePreview
                  key={img.url}
                  url={img.url}
                  name={images.length > 2 ? undefined : img.name}
                  size="card"
                  checkerboard={item.type === "character" || item.type === "prop"}
                  projectId={projectId}
                  scriptId={scriptId}
                />
              ) : null
            )}
            {images.length > 2 && (
              <span className="muted image-text-more-images">+{images.length - 2} 张</span>
            )}
          </div>
        ) : (
          <p className="muted image-text-no-image">尚未生成关联图片</p>
        )}
      </article>

      {detailOpen && (
        <ImageTextAssetDetailModal
          item={item}
          projectId={projectId}
          scriptId={scriptId}
          onClose={() => setDetailOpen(false)}
          onEdit={
            onEdit
              ? (target) => {
                  setDetailOpen(false);
                  onEdit(target);
                }
              : undefined
          }
          onNavigateAsset={onNavigateAsset}
          manualEditEnabled={manualEditEnabled}
          onRegenerated={onRegenerated}
        />
      )}
    </>
  );
}

export function isImageTextAssetType(type: string): boolean {
  return (
    type === "character" ||
    type === "prop" ||
    type === "scene" ||
    type === "frame" ||
    type === "video_clip"
  );
}
