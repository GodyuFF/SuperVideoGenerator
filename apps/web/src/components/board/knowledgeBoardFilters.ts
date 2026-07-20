/**
 * 项目级图文资产看板：剧本/类型筛选与分组工具。
 */

import type { ImageTextAssetItem } from "../ImageTextAssetCard";

/** 剧本关联范围：引用（含来源可见）或仅来源剧本。 */
export type KnowledgeScope = "referenced" | "source";

/** 图文资产类型筛选。 */
export type KnowledgeTypeFilter =
  | "all"
  | "character"
  | "scene"
  | "prop"
  | "frame"
  | "video_clip";

/** 筛选状态。 */
export interface KnowledgeFilters {
  scriptId: string | "all";
  scope: KnowledgeScope;
  type: KnowledgeTypeFilter;
}

/** 看板条目扩展字段（后端 knowledge 看板富化）。 */
export interface KnowledgeAssetItem extends ImageTextAssetItem {
  referenced_script_ids?: string[];
  source_script_title?: string | null;
}

/** 剧本元信息（按创建顺序带编号）。 */
export interface KnowledgeScriptMeta {
  id: string;
  title: string;
  script_index?: number;
}

export const KNOWLEDGE_FILTER_STORAGE_KEY = "svg.knowledge.filters";

/** 类型 chip 展示顺序。 */
export const KNOWLEDGE_TYPE_ORDER = [
  "character",
  "scene",
  "prop",
  "frame",
  "video_clip",
] as const;

const DEFAULT_FILTERS: KnowledgeFilters = {
  scriptId: "all",
  scope: "referenced",
  type: "all",
};

/** 从 localStorage 读取筛选偏好。 */
export function loadKnowledgeFilters(): KnowledgeFilters {
  if (typeof window === "undefined") return { ...DEFAULT_FILTERS };
  try {
    const raw = window.localStorage.getItem(KNOWLEDGE_FILTER_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_FILTERS };
    const parsed = JSON.parse(raw) as Partial<KnowledgeFilters>;
    return {
      scriptId:
        parsed.scriptId === "all" || typeof parsed.scriptId === "string"
          ? parsed.scriptId
          : DEFAULT_FILTERS.scriptId,
      scope: parsed.scope === "source" ? "source" : "referenced",
      type:
        parsed.type === "all" ||
        KNOWLEDGE_TYPE_ORDER.includes(parsed.type as (typeof KNOWLEDGE_TYPE_ORDER)[number])
          ? (parsed.type as KnowledgeTypeFilter)
          : DEFAULT_FILTERS.type,
    };
  } catch {
    return { ...DEFAULT_FILTERS };
  }
}

/** 持久化筛选偏好。 */
export function saveKnowledgeFilters(filters: KnowledgeFilters): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KNOWLEDGE_FILTER_STORAGE_KEY, JSON.stringify(filters));
  } catch {
    /* ignore quota */
  }
}

/** 解析 knowledge 看板 stats（兼容旧版扁平结构）。 */
export function parseKnowledgeStats(stats: Record<string, unknown> | undefined): {
  byType: Record<string, number>;
  scripts: KnowledgeScriptMeta[];
} {
  if (!stats) return { byType: {}, scripts: [] };
  const byTypeRaw = stats.by_type;
  if (byTypeRaw && typeof byTypeRaw === "object" && !Array.isArray(byTypeRaw)) {
    const byType: Record<string, number> = {};
    for (const [key, value] of Object.entries(byTypeRaw)) {
      if (typeof value === "number") byType[key] = value;
    }
    const scripts = Array.isArray(stats.scripts)
      ? (stats.scripts as KnowledgeScriptMeta[]).filter(
          (s) => s && typeof s.id === "string" && typeof s.title === "string",
        )
      : [];
    return { byType, scripts };
  }
  const byType: Record<string, number> = {};
  for (const [key, value] of Object.entries(stats)) {
    if (key !== "scripts" && typeof value === "number") byType[key] = value;
  }
  const scripts = Array.isArray(stats.scripts)
    ? (stats.scripts as KnowledgeScriptMeta[]).filter(
        (s) => s && typeof s.id === "string" && typeof s.title === "string",
      )
    : [];
  return { byType, scripts };
}

/** 判断资产是否匹配所选剧本与范围。 */
export function matchesKnowledgeScript(
  item: KnowledgeAssetItem,
  scriptId: string,
  scope: KnowledgeScope,
): boolean {
  if (scope === "source") {
    return item.source_script_id === scriptId;
  }
  const refs = item.referenced_script_ids ?? [];
  return refs.includes(scriptId) || item.source_script_id === scriptId;
}

/** 按剧本、范围与类型过滤资产列表。 */
export function filterKnowledgeItems(
  items: KnowledgeAssetItem[],
  filters: KnowledgeFilters,
): KnowledgeAssetItem[] {
  return items.filter((item) => {
    if (filters.type !== "all" && item.type !== filters.type) return false;
    if (
      filters.scriptId !== "all" &&
      !matchesKnowledgeScript(item, filters.scriptId, filters.scope)
    ) {
      return false;
    }
    return true;
  });
}

/** 在「全部类型」视图下按类型分区（区内按名称排序）。 */
export function groupKnowledgeByType(
  items: KnowledgeAssetItem[],
): { type: string; items: KnowledgeAssetItem[] }[] {
  const groups: { type: string; items: KnowledgeAssetItem[] }[] = [];
  for (const kind of KNOWLEDGE_TYPE_ORDER) {
    const bucket = items
      .filter((item) => item.type === kind)
      .sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
    if (bucket.length > 0) groups.push({ type: kind, items: bucket });
  }
  return groups;
}

/** 生成卡片上的剧本关联说明行。 */
export function knowledgeScriptLine(
  item: KnowledgeAssetItem,
  scope: KnowledgeScope,
  titleById: Record<string, string>,
  labels: {
    sourceLine: (title: string) => string;
    referencedOne: (title: string) => string;
    referencedMany: (count: number) => string;
    createdUnused: (title: string) => string;
    unreferenced: string;
  },
): string | undefined {
  if (scope === "source") {
    const title =
      item.source_script_title ||
      (item.source_script_id ? titleById[item.source_script_id] : undefined);
    return title ? labels.sourceLine(title) : undefined;
  }
  const refs = item.referenced_script_ids ?? [];
  if (refs.length === 1) {
    const title = titleById[refs[0]] ?? refs[0];
    return labels.referencedOne(title);
  }
  if (refs.length > 1) {
    return labels.referencedMany(refs.length);
  }
  const sourceTitle =
    item.source_script_title ||
    (item.source_script_id ? titleById[item.source_script_id] : undefined);
  if (sourceTitle) return labels.createdUnused(sourceTitle);
  return labels.unreferenced;
}
