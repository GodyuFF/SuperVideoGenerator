/**
 * 关联资产只读展示：缩略图 + 名称 + 可选子形象标签，支持点击跳转。
 */

import { useEffect, useMemo, useState } from "react";
import { AssetImagePreview } from "./AssetImagePreview";
import type { ImageTextAssetItem } from "./ImageTextAssetCard";
import { resolveLinkedAssetPreview } from "./imageTextAssetShared";
import { fetchBoardTextAssetItem } from "../lib/fetchBoardTextAsset";

const REF_KIND_LABEL: Record<string, string> = {
  character: "角色",
  scene: "空镜",
  prop: "物品",
  frame: "画面",
  video_clip: "视频片段",
};

interface LinkedRefRow {
  kind: string;
  assetId: string;
  name: string;
  previewUrl: string;
  variantLabel?: string;
  checkerboard: boolean;
}

interface LinkedAssetRefsSectionProps {
  elementRefs: Record<string, string[]>;
  variantRefs?: Record<string, string>;
  projectId?: string | null;
  scriptId?: string | null;
  onNavigateAsset?: (id: string, kind: string) => void;
}

/** 将 element_refs / variant_refs 展平为带预览的关联卡片列表。 */
export function LinkedAssetRefsSection({
  elementRefs,
  variantRefs = {},
  projectId,
  scriptId,
  onNavigateAsset,
}: LinkedAssetRefsSectionProps) {
  const flat = useMemo(() => {
    const rows: { kind: string; assetId: string }[] = [];
    for (const [kind, ids] of Object.entries(elementRefs)) {
      for (const assetId of ids ?? []) {
        if (assetId) rows.push({ kind, assetId });
      }
    }
    return rows;
  }, [elementRefs]);

  const [resolved, setResolved] = useState<LinkedRefRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (flat.length === 0) {
      setResolved([]);
      return;
    }
    if (!projectId || !scriptId) {
      setResolved(
        flat.map(({ kind, assetId }) => ({
          kind,
          assetId,
          name: assetId,
          previewUrl: "",
          variantLabel: undefined,
          checkerboard: kind === "character" || kind === "prop",
        })),
      );
      return;
    }
    let cancelled = false;
    setLoading(true);
    void Promise.all(
      flat.map(async ({ kind, assetId }) => {
        const item = await fetchBoardTextAssetItem(projectId, scriptId, assetId, kind);
        const variantId = variantRefs[assetId];
        if (!item) {
          return {
            kind,
            assetId,
            name: assetId,
            previewUrl: "",
            variantLabel: undefined,
            checkerboard: kind === "character" || kind === "prop",
          } satisfies LinkedRefRow;
        }
        const preview = resolveLinkedAssetPreview(item as ImageTextAssetItem, variantId);
        let variantLabel = preview.variantLabel;
        if (variantId && !variantLabel && item.variants?.length) {
          const hit = item.variants.find((v) => String(v.id ?? "") === variantId);
          variantLabel = hit?.label || hit?.kind || undefined;
        }
        return {
          kind,
          assetId,
          name: item.name || assetId,
          previewUrl: preview.url,
          variantLabel,
          checkerboard: kind === "character" || kind === "prop",
        } satisfies LinkedRefRow;
      }),
    )
      .then((rows) => {
        if (!cancelled) setResolved(rows);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [flat, projectId, scriptId, variantRefs]);

  if (flat.length === 0) {
    return <p className="muted">尚未关联资产</p>;
  }

  return (
    <div className="linked-asset-refs">
      {loading && resolved.length === 0 ? (
        <p className="muted">加载关联资产…</p>
      ) : (
        <ul className="linked-asset-refs__list">
          {resolved.map((row) => {
            const body = (
              <>
                {row.previewUrl ? (
                  <AssetImagePreview
                    url={row.previewUrl}
                    name={row.name}
                    size="card"
                    checkerboard={row.checkerboard}
                    projectId={projectId}
                    scriptId={scriptId}
                  />
                ) : (
                  <span className="linked-asset-refs__thumb-fallback" aria-hidden>
                    {row.name.slice(0, 1)}
                  </span>
                )}
                <span className="linked-asset-refs__meta">
                  <span className="meta-chip">{REF_KIND_LABEL[row.kind] ?? row.kind}</span>
                  <strong className="linked-asset-refs__name">{row.name}</strong>
                  {row.variantLabel ? (
                    <span className="linked-asset-refs__variant muted">
                      子形象：{row.variantLabel}
                    </span>
                  ) : null}
                </span>
              </>
            );
            return (
              <li key={`${row.kind}-${row.assetId}`} className="linked-asset-refs__item">
                {onNavigateAsset ? (
                  <button
                    type="button"
                    className="linked-asset-refs__card"
                    onClick={() => onNavigateAsset(row.assetId, row.kind)}
                  >
                    {body}
                  </button>
                ) : (
                  <div className="linked-asset-refs__card linked-asset-refs__card--static">
                    {body}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
