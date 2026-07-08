/**
 * 图文资产卡片：角色 / 物品 / 场景 — 卡片仅展示摘要与预览，详情见弹窗。
 */

import { useState } from "react";
import { AssetImagePreview } from "./AssetImagePreview";
import { ImageTextAssetDetailModal } from "./ImageTextAssetDetailModal";
import {
  TYPE_LABEL,
  assetImages,
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
  preview?: string;
  images?: { id?: string; url?: string; name?: string; type?: string }[];
  media?: { id?: string; url?: string; name?: string; type?: string }[];
  status?: string;
  scope?: string;
  user_edited?: boolean;
  variants?: {
    id?: string;
    kind?: string;
    label?: string;
    meaning?: string;
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
}: {
  item: ImageTextAssetItem;
  onEdit?: (item: ImageTextAssetItem) => void;
  onDelete?: (item: ImageTextAssetItem) => void;
  manualEditEnabled?: boolean;
}) {
  const [detailOpen, setDetailOpen] = useState(false);
  const images = assetImages(item);
  const summary =
    fieldFromItem(item, "summary") ||
    fieldFromItem(item, "description").slice(0, 120);

  const openDetail = () => setDetailOpen(true);

  return (
    <>
      <article
        className="board-card image-text-asset-card image-text-asset-card--compact"
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
          {item.user_edited && <span className="meta-chip">已编辑</span>}
          <div
            className="image-text-asset-actions"
            onClick={(e) => e.stopPropagation()}
          >
            <button type="button" className="btn-secondary btn-sm" onClick={openDetail}>
              详情
            </button>
            {manualEditEnabled && onEdit && (
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => onEdit(item)}
              >
                编辑
              </button>
            )}
            {manualEditEnabled && onDelete && (
              <button
                type="button"
                className="btn-danger btn-sm"
                onClick={() => onDelete(item)}
              >
                删除
              </button>
            )}
          </div>
        </header>

        {summary && (
          <p className="image-text-summary image-text-summary--clamp">{summary}</p>
        )}

        {images.length > 0 ? (
          <div className="character-images">
            {images.slice(0, 2).map((img) =>
              img.url ? (
                <AssetImagePreview
                  key={img.url}
                  url={img.url}
                  name={images.length > 2 ? undefined : img.name}
                  size="card"
                  checkerboard={item.type === "character" || item.type === "prop"}
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
          onClose={() => setDetailOpen(false)}
          onEdit={
            onEdit
              ? (target) => {
                  setDetailOpen(false);
                  onEdit(target);
                }
              : undefined
          }
        />
      )}
    </>
  );
}

export function isImageTextAssetType(type: string): boolean {
  return type === "character" || type === "prop" || type === "scene";
}
