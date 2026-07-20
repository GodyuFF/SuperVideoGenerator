/**
 * 图文资产视觉选择器：缩略图 + 名称 + 摘要卡片，支持单选/多选与已选胶片条。
 * allowDuplicateSelection 时，同一资产可多次加入；胶片条按槽位点掉对应一次挂接。
 * 无可用预览时走纯文案卡片，加载失败不展示浏览器破图。
 */

import { useCallback, useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { looksLikeMediaUrl } from "../../utils/boardMediaPreview";
import { AssetImagePreview } from "../AssetImagePreview";

/** 可选资产摘要（含预览图）。 */
export interface AssetVisualOption {
  id: string;
  name: string;
  summary?: string;
  previewUrl?: string;
  /** 次要角标文案（如桶名）。 */
  badge?: string;
}

interface AssetVisualSelectProps {
  options: AssetVisualOption[];
  /**
   * 已选资产 ID 列表；允许重复（同一画面挂多次时同一 id 出现多次）。
   */
  selectedIds: string[];
  /** 点选候选卡片（或多选切换）时回调；单选清空时传空串。 */
  onToggle: (id: string) => void;
  /**
   * 允许重复挂接时，胶片条点击移除「第 index 次」挂接（相对 selectedIds）。
   */
  onDeselectAt?: (index: number) => void;
  mode?: "multi" | "single";
  /**
   * 为 true 时：点卡片始终追加（可重复）；取消只走胶片条 / 外部槽位删除。
   */
  allowDuplicateSelection?: boolean;
  loading?: boolean;
  emptyLabel?: string;
  projectId?: string | null;
  scriptId?: string | null;
  /** 顶部已选胶片条（默认开启）。 */
  showSelectedStrip?: boolean;
  /** 仅展示已选条，不渲染下方候选网格。 */
  stripOnly?: boolean;
  /** 透明底资产（角色/道具）用棋盘格。 */
  checkerboard?: boolean;
  /**
   * 无可用预览（空 URL / 非法 / 加载失败）时不渲染预览区与占位，改为纯文案卡片。
   */
  hideEmptyPreview?: boolean;
  className?: string;
}

/** 按 selectedIds 顺序展开已选项（含重复挂接）。 */
function orderedSelected(
  options: AssetVisualOption[],
  selectedIds: string[],
): Array<AssetVisualOption & { slotIndex: number }> {
  const byId = new Map(options.map((o) => [o.id, o]));
  const out: Array<AssetVisualOption & { slotIndex: number }> = [];
  selectedIds.forEach((id, slotIndex) => {
    const opt = byId.get(id);
    if (opt) out.push({ ...opt, slotIndex });
  });
  return out;
}

/** 候选项是否具备可尝试的预览 URL。 */
function hasAttemptablePreview(opt: AssetVisualOption): boolean {
  return Boolean(opt.previewUrl && looksLikeMediaUrl(opt.previewUrl));
}

/** 资产图文卡片选择网格。 */
export function AssetVisualSelect({
  options,
  selectedIds,
  onToggle,
  onDeselectAt,
  mode = "multi",
  allowDuplicateSelection = false,
  loading = false,
  emptyLabel,
  projectId,
  scriptId,
  showSelectedStrip = true,
  stripOnly = false,
  checkerboard = false,
  hideEmptyPreview = false,
  className,
}: AssetVisualSelectProps) {
  const { t } = useAppTranslation("board");
  const selectedSet = new Set(selectedIds);
  const selectedOrdered = orderedSelected(options, selectedIds);
  const showGrid = !stripOnly;
  const countById = selectedIds.reduce<Record<string, number>>((acc, id) => {
    acc[id] = (acc[id] ?? 0) + 1;
    return acc;
  }, {});
  /** 预览加载失败的资产 id（折叠预览区，避免破图）。 */
  const [failedPreviewIds, setFailedPreviewIds] = useState<Record<string, true>>({});

  /** 标记某资产预览不可用。 */
  const markPreviewFailed = useCallback((id: string) => {
    setFailedPreviewIds((prev) => (prev[id] ? prev : { ...prev, [id]: true }));
  }, []);

  /** 点击候选卡片。 */
  const handleCardPick = (id: string) => {
    if (mode === "single") {
      onToggle(selectedSet.has(id) ? "" : id);
      return;
    }
    if (allowDuplicateSelection) {
      onToggle(id);
      return;
    }
    // 默认多选：再点取消
    onToggle(id);
  };

  /** 胶片条点击：重复模式按槽位移除，否则走切换逻辑。 */
  const handleStripPick = (id: string, slotIndex: number) => {
    if (allowDuplicateSelection) {
      onDeselectAt?.(slotIndex);
      return;
    }
    handleCardPick(id);
  };

  /** 是否渲染媒体区（含占位）。 */
  const showMediaFor = (opt: AssetVisualOption): boolean => {
    const attemptable = hasAttemptablePreview(opt) && !failedPreviewIds[opt.id];
    if (attemptable) return true;
    return !hideEmptyPreview;
  };

  return (
    <div className={`asset-visual-select${className ? ` ${className}` : ""}`}>
      {showSelectedStrip ? (
        <div className="asset-visual-select__strip" aria-live="polite">
          {selectedOrdered.length === 0 ? (
            <p className="muted asset-visual-select__strip-empty">
              {t("storyboard.assetPicker.selectedEmpty")}
            </p>
          ) : (
            <ul className="asset-visual-select__strip-list">
              {selectedOrdered.map((opt, idx) => {
                const showThumb =
                  hasAttemptablePreview(opt) && !failedPreviewIds[opt.id];
                return (
                  <li key={`${opt.id}__${opt.slotIndex}`}>
                    <button
                      type="button"
                      className={`asset-visual-select__strip-chip${
                        showThumb ? "" : " asset-visual-select__strip-chip--text"
                      }`}
                      onClick={() => handleStripPick(opt.id, opt.slotIndex)}
                      title={
                        allowDuplicateSelection
                          ? t("storyboard.assetPicker.removeOneHint")
                          : t("storyboard.assetPicker.unselectHint")
                      }
                    >
                      <span className="asset-visual-select__strip-index">{idx + 1}</span>
                      {showThumb ? (
                        <AssetImagePreview
                          url={opt.previewUrl!}
                          name={opt.name}
                          size="card"
                          checkerboard={checkerboard}
                          projectId={projectId}
                          scriptId={scriptId}
                          hideWhenUnavailable={hideEmptyPreview}
                          onUnavailable={
                            hideEmptyPreview
                              ? () => markPreviewFailed(opt.id)
                              : undefined
                          }
                        />
                      ) : hideEmptyPreview ? null : (
                        <span className="asset-visual-select__thumb-fallback" aria-hidden>
                          {opt.name.slice(0, 1)}
                        </span>
                      )}
                      <span className="asset-visual-select__strip-meta">
                        {opt.badge ? (
                          <span className="asset-visual-select__strip-badge">{opt.badge}</span>
                        ) : null}
                        <span className="asset-visual-select__strip-name">{opt.name}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}

      {showGrid && loading ? (
        <p className="muted">{t("storyboard.assetPicker.loading")}</p>
      ) : null}

      {showGrid && !loading && options.length === 0 ? (
        <p className="muted">{emptyLabel ?? t("storyboard.assetPicker.none")}</p>
      ) : null}

      {showGrid && !loading && options.length > 0 ? (
        <ul
          className={`asset-visual-select__grid${
            hideEmptyPreview ? " asset-visual-select__grid--text-lean" : ""
          }`}
        >
          {options.map((opt) => {
            const count = countById[opt.id] ?? 0;
            const selected = count > 0;
            const withMedia = showMediaFor(opt);
            const attemptable =
              hasAttemptablePreview(opt) && !failedPreviewIds[opt.id];
            return (
              <li key={opt.id}>
                <button
                  type="button"
                  className={`asset-visual-select__card${selected ? " is-selected" : ""}${
                    withMedia ? "" : " asset-visual-select__card--text-only"
                  }`}
                  onClick={() => handleCardPick(opt.id)}
                  aria-pressed={selected}
                  title={
                    allowDuplicateSelection
                      ? t("storyboard.assetPicker.addAgainHint")
                      : undefined
                  }
                >
                  {withMedia ? (
                    <div className="asset-visual-select__card-media">
                      {count > 0 ? (
                        <span className="asset-visual-select__card-index">
                          {allowDuplicateSelection && count > 1 ? `×${count}` : count}
                        </span>
                      ) : null}
                      {selected ? (
                        <span className="asset-visual-select__card-check" aria-hidden>
                          ✓
                        </span>
                      ) : null}
                      {attemptable ? (
                        <AssetImagePreview
                          url={opt.previewUrl!}
                          name={opt.name}
                          size="card"
                          checkerboard={checkerboard}
                          projectId={projectId}
                          scriptId={scriptId}
                          unavailableLabel={t("storyboard.assetPicker.noPreview")}
                          onUnavailable={
                            hideEmptyPreview
                              ? () => markPreviewFailed(opt.id)
                              : undefined
                          }
                        />
                      ) : (
                        <div className="asset-visual-select__card-placeholder">
                          <span className="asset-visual-select__card-placeholder-mark" aria-hidden>
                            {opt.name.slice(0, 1)}
                          </span>
                          <span>{t("storyboard.assetPicker.noPreview")}</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <>
                      {count > 0 ? (
                        <span className="asset-visual-select__card-index asset-visual-select__card-index--floating">
                          {allowDuplicateSelection && count > 1 ? `×${count}` : count}
                        </span>
                      ) : null}
                      {selected ? (
                        <span
                          className="asset-visual-select__card-check asset-visual-select__card-check--floating"
                          aria-hidden
                        >
                          ✓
                        </span>
                      ) : null}
                    </>
                  )}
                  <div className="asset-visual-select__card-body">
                    {opt.badge ? (
                      <span className="meta-chip asset-visual-select__card-badge">{opt.badge}</span>
                    ) : null}
                    <span className="asset-visual-select__card-name">{opt.name}</span>
                    {opt.summary?.trim() ? (
                      <p className="asset-visual-select__card-summary">{opt.summary.trim()}</p>
                    ) : null}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
