/**
 * 图文资产详情弹窗（只读）。
 */

import {
  TYPE_LABEL,
  TRAIT_LABEL,
  assetImages,
  fieldFromItem,
  traitEntries,
} from "./imageTextAssetShared";
import { AssetImagePreview } from "./AssetImagePreview";
import type { ImageTextAssetItem } from "./ImageTextAssetCard";

interface ImageTextAssetDetailModalProps {
  item: ImageTextAssetItem;
  onClose: () => void;
  onEdit?: (item: ImageTextAssetItem) => void;
}

export function ImageTextAssetDetailModal({
  item,
  onClose,
  onEdit,
}: ImageTextAssetDetailModalProps) {
  const images = assetImages(item);
  const desc =
    fieldFromItem(item, "description") || String(item.preview ?? "").trim();
  const summary = fieldFromItem(item, "summary");
  const traits = traitEntries(item);
  const tags = item.tags ?? [];
  const displayMode =
    item.display_mode ?? String(item.content?.display_mode ?? "static_image");
  const colorPalette = fieldFromItem(item, "color_palette");
  const notes = fieldFromItem(item, "notes");
  const promptHint = fieldFromItem(item, "prompt_hint");
  const imagePrompt = fieldFromItem(item, "image_prompt");
  const negativePrompt = fieldFromItem(item, "negative_prompt");
  const typeLabel = TYPE_LABEL[item.type] ?? item.type;

  return (
    <div
      className="asset-editor-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="asset-detail-title"
      onClick={onClose}
    >
      <div
        className="asset-editor-panel asset-detail-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="asset-editor-header">
          <div>
            <span className="asset-type-badge">{typeLabel}</span>
            <h3 id="asset-detail-title">{item.name}</h3>
          </div>
          <div className="asset-detail-actions">
            {onEdit && (
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => onEdit(item)}
              >
                编辑
              </button>
            )}
            <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
              关闭
            </button>
          </div>
        </header>

        <div className="asset-detail-body">
          {summary && (
            <section className="asset-detail-section">
              <h4>摘要</h4>
              <p>{summary}</p>
            </section>
          )}

          {desc && (
            <section className="asset-detail-section">
              <h4>主视觉描述</h4>
              <p className="image-text-description">{desc}</p>
            </section>
          )}

          {traits.length > 0 && (
            <section className="asset-detail-section">
              <h4>类型属性</h4>
              <dl className="image-text-traits">
                {traits.map(([key, value]) => (
                  <div key={key} className="trait-row">
                    <dt>{TRAIT_LABEL[key] ?? key}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          <div className="image-text-meta">
            {item.user_edited && <span className="meta-chip">已编辑</span>}
            {item.visual_style && (
              <span className="meta-chip">风格：{item.visual_style}</span>
            )}
            {colorPalette && (
              <span className="meta-chip">色调：{colorPalette}</span>
            )}
            {displayMode === "dynamic_image" && (
              <span className="meta-chip">动态图</span>
            )}
            {tags.map((tag) => (
              <span key={tag} className="meta-chip tag">
                {tag}
              </span>
            ))}
          </div>

          {notes && (
            <section className="asset-detail-section">
              <h4>备注</h4>
              <p className="image-text-notes muted">{notes}</p>
            </section>
          )}

          {(promptHint || imagePrompt || negativePrompt) && (
            <section className="asset-detail-section">
              <h4>生图提示词</h4>
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
            </section>
          )}

          {(item.variants?.length ?? 0) > 0 && (
            <section className="asset-detail-section">
              <h4>图片变体</h4>
              <ul className="variant-list">
                {item.variants!.map((v) => (
                  <li key={v.id ?? v.label} className="variant-list-item">
                    <span className="meta-chip">
                      {v.is_primary ? "主形象" : v.kind ?? "变体"}
                    </span>
                    <strong>{v.label}</strong>
                    {v.meaning && (
                      <span className="muted"> — {v.meaning.slice(0, 80)}</span>
                    )}
                    {v.preview_url && (
                      <AssetImagePreview
                        url={v.preview_url}
                        name={v.label}
                        size="thumb"
                      />
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="asset-detail-section">
            <h4>关联图片</h4>
            {images.length > 0 ? (
              <div className="character-images character-images--detail">
                {images.map((img) =>
                  img.url ? (
                    <AssetImagePreview
                      key={img.url}
                      url={img.url}
                      name={img.name}
                      size="detail"
                    />
                  ) : null
                )}
              </div>
            ) : (
              <p className="muted">尚未生成关联图片</p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
