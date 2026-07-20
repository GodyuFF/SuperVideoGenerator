/**
 * 画面资产 element_refs 选择器（角色/场景/道具/画面桶）：图文卡片点选，支持挂接子形象。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import {
  ELEMENT_REF_BUCKETS,
  type ElementRefBucket,
  wouldCreateElementRefCycle,
} from "../../utils/elementRefUtils";
import { pickBoardMediaPreviewUrl } from "../../utils/boardMediaPreview";
import {
  AssetVisualSelect,
  type AssetVisualOption,
} from "./AssetVisualSelect";
import { AssetImagePreview } from "../AssetImagePreview";

const API = "/api";

/** 关联资产可选的子形象摘要。 */
interface VariantOption {
  id: string;
  label: string;
  kind?: string;
  previewUrl?: string;
  isPrimary?: boolean;
}

interface AssetOption extends AssetVisualOption {
  elementRefs: Record<string, string[]>;
  variants: VariantOption[];
}

interface AssetRefPickerProps {
  projectId: string;
  scriptId: string;
  value: Record<string, string[]>;
  onChange: (refs: Record<string, string[]>) => void;
  /** 关联资产 → 子形象 id；未传则不展示子形象选择。 */
  variantRefs?: Record<string, string>;
  onVariantRefsChange?: (refs: Record<string, string>) => void;
  className?: string;
  /** 当前编辑的资产 ID，不可选自身且用于环检测。 */
  ownerAssetId?: string;
  /** 展示的桶；默认四类全开。画面编辑可传全量，角色编辑仅 character。 */
  kinds?: ElementRefBucket[];
  /** 内嵌在画面卡片内时使用紧凑布局。 */
  variant?: "default" | "inline";
  /** 全剧本 element_refs 索引（用于环检测），可选。 */
  refsIndex?: Record<string, Record<string, string[]>>;
}

/** 从看板条目解析摘要。 */
function summaryFromBoardItem(item: Record<string, unknown>): string {
  return String(item.summary ?? item.description ?? item.preview ?? "").trim();
}

/** 从看板条目解析子形象列表。 */
function variantsFromBoardItem(item: Record<string, unknown>): VariantOption[] {
  const raw = Array.isArray(item.variants) ? item.variants : [];
  return raw
    .map((row) => {
      if (!row || typeof row !== "object") return null;
      const v = row as Record<string, unknown>;
      const id = String(v.id ?? "").trim();
      if (!id) return null;
      const preview = String(v.preview_url ?? "").trim();
      return {
        id,
        label: String(v.label ?? v.kind ?? id),
        kind: String(v.kind ?? "") || undefined,
        previewUrl: preview || undefined,
        isPrimary: Boolean(v.is_primary) || String(v.kind ?? "") === "base",
      } satisfies VariantOption;
    })
    .filter((v): v is VariantOption => v != null);
}

/** 裁剪 variant_refs，仅保留当前仍被 element_refs 引用的资产。 */
function pruneVariantRefs(
  refs: Record<string, string>,
  elementRefs: Record<string, string[]>,
): Record<string, string> {
  const alive = new Set<string>();
  for (const ids of Object.values(elementRefs)) {
    for (const id of ids ?? []) {
      if (id) alive.add(id);
    }
  }
  const next: Record<string, string> = {};
  for (const [aid, vid] of Object.entries(refs)) {
    if (alive.has(aid) && vid) next[aid] = vid;
  }
  return next;
}

/** 按 variant 覆盖胶片条预览图。 */
function withVariantPreview(
  opt: AssetOption,
  variantId?: string,
): AssetVisualOption {
  if (!variantId || !opt.variants.length) return opt;
  const hit = opt.variants.find((v) => v.id === variantId);
  if (!hit?.previewUrl) return opt;
  return {
    ...opt,
    previewUrl: hit.previewUrl,
    name: hit.label && hit.label !== opt.name ? `${opt.name} · ${hit.label}` : opt.name,
  };
}

/** 关联资产：分类 Tab + 图文卡片多选 + 可选子形象。 */
export function AssetRefPicker({
  projectId,
  scriptId,
  value,
  onChange,
  variantRefs = {},
  onVariantRefsChange,
  className,
  ownerAssetId,
  kinds = [...ELEMENT_REF_BUCKETS],
  variant = "default",
  refsIndex = {},
}: AssetRefPickerProps) {
  const { t } = useAppTranslation("board");
  const [options, setOptions] = useState<Record<ElementRefBucket, AssetOption[]>>({
    scene: [],
    character: [],
    prop: [],
    frame: [],
  });
  const [loading, setLoading] = useState(false);
  const [cycleError, setCycleError] = useState<string | null>(null);
  const [activeKind, setActiveKind] = useState<ElementRefBucket>(kinds[0] ?? "character");
  const enableVariants = typeof onVariantRefsChange === "function";

  useEffect(() => {
    if (!kinds.includes(activeKind)) {
      setActiveKind(kinds[0] ?? "character");
    }
  }, [kinds, activeKind]);

  /** 拉取各桶可选资产（含预览、摘要与子形象）。 */
  const loadOptions = useCallback(async () => {
    setLoading(true);
    try {
      const next: Record<ElementRefBucket, AssetOption[]> = {
        scene: [],
        character: [],
        prop: [],
        frame: [],
      };
      await Promise.all(
        kinds.map(async (kind) => {
          const params = new URLSearchParams({ script_id: scriptId });
          const res = await fetch(
            `${API}/projects/${projectId}/board/${kind}?${params}`,
          );
          if (!res.ok) return;
          const data = (await res.json()) as { items?: Record<string, unknown>[] };
          next[kind] = (data.items ?? [])
            .map((item) => {
              const content = item.content as
                | { element_refs?: Record<string, string[]> }
                | undefined;
              const rawRefs = content?.element_refs ?? {};
              const elementRefs: Record<string, string[]> = {};
              for (const b of ELEMENT_REF_BUCKETS) {
                const arr = rawRefs[b];
                if (Array.isArray(arr)) {
                  elementRefs[b] = arr.map(String).filter(Boolean);
                }
              }
              const id = String(item.asset_id ?? item.id ?? "");
              return {
                id,
                name: String(item.name ?? item.title ?? id),
                summary: summaryFromBoardItem(item),
                previewUrl: pickBoardMediaPreviewUrl(item) || undefined,
                badge: t(`storyboard.ref.${kind}`),
                elementRefs,
                variants: variantsFromBoardItem(item),
              } satisfies AssetOption;
            })
            .filter((o) => o.id && o.id !== ownerAssetId);
        }),
      );
      setOptions(next);
    } finally {
      setLoading(false);
    }
  }, [projectId, scriptId, kinds, ownerAssetId, t]);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  const mergedIndex = useMemo(() => {
    const idx = { ...refsIndex };
    if (ownerAssetId) {
      idx[ownerAssetId] = value;
    }
    for (const kind of kinds) {
      for (const opt of options[kind] ?? []) {
        if (!idx[opt.id]) {
          idx[opt.id] = opt.elementRefs;
        }
      }
    }
    return idx;
  }, [refsIndex, ownerAssetId, value, kinds, options]);

  /** 提交 element_refs，并同步裁剪 variant_refs。 */
  const commitRefs = (next: Record<string, string[]>) => {
    onChange(next);
    if (enableVariants && onVariantRefsChange) {
      onVariantRefsChange(pruneVariantRefs(variantRefs, next));
    }
  };

  /** 切换当前桶内某资产选中态。 */
  const toggle = (kind: ElementRefBucket, assetId: string) => {
    if (!assetId) return;
    const current = value[kind] ?? [];
    const exists = current.includes(assetId);
    const nextIds = exists
      ? current.filter((id) => id !== assetId)
      : [...current, assetId];
    const next = { ...value, [kind]: nextIds };
    if (ownerAssetId && wouldCreateElementRefCycle(ownerAssetId, next, mergedIndex)) {
      setCycleError(t("storyboard.assetPicker.cycleError"));
      return;
    }
    setCycleError(null);
    commitRefs(next);
  };

  /** 为已选资产指定子形象（再点同一子形象可回到主形象）。 */
  const selectVariant = (assetId: string, variantId: string, isPrimary: boolean) => {
    if (!onVariantRefsChange) return;
    const next = { ...variantRefs };
    if (isPrimary || next[assetId] === variantId) {
      delete next[assetId];
    } else {
      next[assetId] = variantId;
    }
    onVariantRefsChange(pruneVariantRefs(next, value));
  };

  const activeOptions = options[activeKind] ?? [];
  const activeSelected = value[activeKind] ?? [];
  const checkerboard = activeKind === "character" || activeKind === "prop";

  /** 按 id 查找已加载选项。 */
  const findOption = useCallback(
    (assetId: string): AssetOption | undefined => {
      for (const kind of kinds) {
        const hit = (options[kind] ?? []).find((o) => o.id === assetId);
        if (hit) return hit;
      }
      return undefined;
    },
    [kinds, options],
  );

  /** 跨桶已选汇总条（名称带桶徽章；预览跟随子形象）。 */
  const crossSelected = useMemo(() => {
    const rows: AssetVisualOption[] = [];
    const ids: string[] = [];
    for (const kind of kinds) {
      for (const id of value[kind] ?? []) {
        const opt = (options[kind] ?? []).find((o) => o.id === id);
        if (opt) {
          rows.push(withVariantPreview(opt, variantRefs[id]));
          ids.push(id);
        }
      }
    }
    return { rows, ids };
  }, [kinds, value, options, variantRefs]);

  /** 已选中且含多个子形象的条目（供子形象条）。 */
  const selectedWithVariants = useMemo(() => {
    if (!enableVariants) return [];
    const out: Array<{ assetId: string; name: string; variants: VariantOption[] }> = [];
    for (const kind of kinds) {
      for (const id of value[kind] ?? []) {
        const opt = findOption(id);
        if (opt && opt.variants.length > 1) {
          out.push({ assetId: id, name: opt.name, variants: opt.variants });
        }
      }
    }
    return out;
  }, [enableVariants, kinds, value, findOption]);

  return (
    <div
      className={`shot-editor-block asset-ref-picker asset-ref-picker--visual${variant === "inline" ? " asset-ref-picker--inline" : ""}${className ? ` ${className}` : ""}`}
    >
      {variant === "default" ? (
        <>
          <h4>{t("storyboard.assetPicker.title")}</h4>
          <p className="muted asset-ref-picker__hint">
            {enableVariants
              ? t("storyboard.assetPicker.visualHintWithVariant")
              : t("storyboard.assetPicker.visualHint")}
          </p>
        </>
      ) : (
        <p className="asset-ref-picker__inline-label">{t("storyboard.subShot.frameRefsTitle")}</p>
      )}

      {cycleError ? <p className="form-error">{cycleError}</p> : null}

      {crossSelected.rows.length > 0 ? (
        <AssetVisualSelect
          options={crossSelected.rows}
          selectedIds={crossSelected.ids}
          onToggle={(id) => {
            for (const kind of kinds) {
              if ((value[kind] ?? []).includes(id)) {
                toggle(kind, id);
                return;
              }
            }
          }}
          mode="multi"
          projectId={projectId}
          scriptId={scriptId}
          showSelectedStrip
          stripOnly
        />
      ) : (
        <p className="muted asset-visual-select__strip-empty">
          {t("storyboard.assetPicker.selectedEmpty")}
        </p>
      )}

      {selectedWithVariants.length > 0 ? (
        <div className="asset-ref-picker__variants">
          <p className="asset-ref-picker__variants-hint muted">
            {t("storyboard.assetPicker.variantHint")}
          </p>
          {selectedWithVariants.map((row) => (
            <div key={row.assetId} className="asset-ref-picker__variant-row">
              <span className="asset-ref-picker__variant-asset">{row.name}</span>
              <ul className="asset-ref-picker__variant-chips">
                {row.variants.map((v) => {
                  const selected =
                    (!variantRefs[row.assetId] && Boolean(v.isPrimary)) ||
                    variantRefs[row.assetId] === v.id;
                  return (
                    <li key={v.id}>
                      <button
                        type="button"
                        className={`asset-ref-picker__variant-chip${selected ? " is-selected" : ""}`}
                        onClick={() => selectVariant(row.assetId, v.id, Boolean(v.isPrimary))}
                        title={v.label}
                      >
                        {v.previewUrl ? (
                          <AssetImagePreview
                            url={v.previewUrl}
                            name={v.label}
                            size="card"
                            checkerboard
                            projectId={projectId}
                            scriptId={scriptId}
                          />
                        ) : (
                          <span className="asset-ref-picker__variant-fallback" aria-hidden>
                            {v.label.slice(0, 1)}
                          </span>
                        )}
                        <span className="asset-ref-picker__variant-label">{v.label}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      ) : null}

      {kinds.length > 1 ? (
        <div className="asset-ref-picker__tabs" role="tablist" aria-label={t("storyboard.assetPicker.title")}>
          {kinds.map((kind) => {
            const count = (value[kind] ?? []).length;
            return (
              <button
                key={kind}
                type="button"
                role="tab"
                aria-selected={activeKind === kind}
                className={`asset-ref-picker__tab${activeKind === kind ? " is-active" : ""}`}
                onClick={() => setActiveKind(kind)}
              >
                <span>{t(`storyboard.ref.${kind}`)}</span>
                {count > 0 ? (
                  <span className="asset-ref-picker__tab-count">{count}</span>
                ) : null}
              </button>
            );
          })}
        </div>
      ) : null}

      <AssetVisualSelect
        options={activeOptions}
        selectedIds={activeSelected}
        onToggle={(id) => {
          if (!id) return;
          toggle(activeKind, id);
        }}
        mode="multi"
        loading={loading}
        projectId={projectId}
        scriptId={scriptId}
        showSelectedStrip={false}
        checkerboard={checkerboard}
      />
    </div>
  );
}

