/**
 * 项目级图文资产看板：按剧本与类型筛选，网格展示共享池资产。
 */

import { useEffect, useMemo, useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { ImageTextAssetCard } from "../ImageTextAssetCard";
import type { BoardView } from "../../types/board";
import {
  filterKnowledgeItems,
  groupKnowledgeByType,
  knowledgeScriptLine,
  KNOWLEDGE_TYPE_ORDER,
  loadKnowledgeFilters,
  parseKnowledgeStats,
  saveKnowledgeFilters,
  type KnowledgeAssetItem,
  type KnowledgeFilters,
  type KnowledgeScope,
  type KnowledgeTypeFilter,
} from "./knowledgeBoardFilters";

interface KnowledgeBoardProps {
  board: BoardView;
  projectId?: string | null;
  scriptId?: string | null;
  onEdit?: (item: KnowledgeAssetItem) => void;
  onDelete?: (item: KnowledgeAssetItem) => void;
  manualEditEnabled?: boolean;
  onNavigateAsset?: (id: string, kind: string) => void;
  onRegenerated?: () => void;
}

/** 项目共享图文资产看板主体。 */
export function KnowledgeBoard({
  board,
  projectId,
  scriptId,
  onEdit,
  onDelete,
  manualEditEnabled,
  onNavigateAsset,
  onRegenerated,
}: KnowledgeBoardProps) {
  const { t } = useAppTranslation("board");
  const [filters, setFilters] = useState<KnowledgeFilters>(() => loadKnowledgeFilters());

  useEffect(() => {
    saveKnowledgeFilters(filters);
  }, [filters]);

  const rawItems = (board.items ?? []) as unknown as KnowledgeAssetItem[];
  const { byType, scripts } = useMemo(
    () => parseKnowledgeStats(board.stats as Record<string, unknown> | undefined),
    [board.stats],
  );
  const titleById = useMemo(
    () => Object.fromEntries(scripts.map((s) => [s.id, s.title])),
    [scripts],
  );

  const filtered = useMemo(
    () => filterKnowledgeItems(rawItems, filters),
    [rawItems, filters],
  );

  const grouped = useMemo(
    () => (filters.type === "all" ? groupKnowledgeByType(filtered) : null),
    [filtered, filters.type],
  );

  const scriptLabels = useMemo(
    () => ({
      sourceLine: (title: string) => t("knowledge.sourceLine", { title }),
      referencedOne: (title: string) => t("knowledge.referencedOne", { title }),
      referencedMany: (count: number) => t("knowledge.referencedMany", { count }),
      createdUnused: (title: string) => t("knowledge.createdUnused", { title }),
      unreferenced: t("knowledge.unreferenced"),
    }),
    [t],
  );

  /** 更新单项筛选并写回状态。 */
  const patchFilters = (patch: Partial<KnowledgeFilters>) => {
    setFilters((prev) => ({ ...prev, ...patch }));
  };

  /** 渲染单张资产卡片。 */
  const renderCard = (item: KnowledgeAssetItem) => (
    <ImageTextAssetCard
      key={item.id}
      item={item}
      projectId={projectId}
      scriptId={scriptId}
      scriptLine={knowledgeScriptLine(item, filters.scope, titleById, scriptLabels)}
      onEdit={projectId && manualEditEnabled ? onEdit : undefined}
      onDelete={projectId && manualEditEnabled ? onDelete : undefined}
      manualEditEnabled={manualEditEnabled}
      onNavigateAsset={onNavigateAsset}
      onRegenerated={onRegenerated}
    />
  );

  const typeChips: KnowledgeTypeFilter[] = ["all", ...KNOWLEDGE_TYPE_ORDER];

  return (
    <div className="knowledge-board">
      <div className="knowledge-board__toolbar board-toolbar">
        <label className="knowledge-board__field">
          <span className="knowledge-board__eyebrow">{t("knowledge.scriptFilter")}</span>
          <select
            className="knowledge-board__select"
            value={filters.scriptId}
            onChange={(e) =>
              patchFilters({
                scriptId: e.target.value === "all" ? "all" : e.target.value,
              })
            }
          >
            <option value="all">{t("knowledge.allScripts")}</option>
            {scripts.map((s) => (
              <option key={s.id} value={s.id}>
                {s.script_index != null
                  ? t("scriptIndex", { index: s.script_index }) + ` · ${s.title}`
                  : s.title}
              </option>
            ))}
          </select>
        </label>

        <div className="knowledge-board__scope" role="group" aria-label={t("knowledge.scopeLabel")}>
          {(["referenced", "source"] as KnowledgeScope[]).map((scope) => (
            <button
              key={scope}
              type="button"
              className={`batch-studio-chip${filters.scope === scope ? " is-active" : ""}`}
              onClick={() => patchFilters({ scope })}
            >
              {scope === "referenced" ? t("knowledge.scopeReferenced") : t("knowledge.scopeSource")}
            </button>
          ))}
        </div>
      </div>

      <div className="knowledge-board__chips batch-studio-drawer__chips" role="group" aria-label={t("knowledge.typeFilter")}>
        {typeChips.map((kind) => {
          const count = kind === "all" ? rawItems.length : (byType[kind] ?? 0);
          if (kind !== "all" && count === 0) return null;
          return (
            <button
              key={kind}
              type="button"
              className={`batch-studio-chip${filters.type === kind ? " is-active" : ""}`}
              onClick={() => patchFilters({ type: kind })}
            >
              {kind === "all" ? t("knowledge.typeAll") : t(`tabs.${kind}`)}
              <span className="knowledge-board__chip-count">{count}</span>
            </button>
          );
        })}
      </div>

      {rawItems.length === 0 ? (
        <p className="muted knowledge-board__empty">{t("knowledge.emptyPool")}</p>
      ) : filtered.length === 0 ? (
        <div className="knowledge-board__empty-wrap">
          <p className="muted">{t("knowledge.emptyFilter")}</p>
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={() => setFilters({ scriptId: "all", scope: "referenced", type: "all" })}
          >
            {t("knowledge.clearFilters")}
          </button>
        </div>
      ) : grouped ? (
        grouped.map((section) => (
          <section key={section.type} className="knowledge-board__section">
            <header className="knowledge-board__section-head">
              <span className="knowledge-board__eyebrow">{t(`tabs.${section.type}`)}</span>
              <span className="muted knowledge-board__section-count">
                {t("knowledge.sectionCount", { count: section.items.length })}
              </span>
            </header>
            <div className="board-cards character-cards knowledge-board__grid">
              {section.items.map(renderCard)}
            </div>
          </section>
        ))
      ) : (
        <div className="board-cards character-cards knowledge-board__grid">
          {filtered.map(renderCard)}
        </div>
      )}
    </div>
  );
}
