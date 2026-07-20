/**
 * 从看板 API 拉取单个图文文字资产完整条目（含 images / variants / content）。
 */

import type { ImageTextAssetItem } from "../components/ImageTextAssetCard";
import type { BoardView } from "../types/board";

const API = "/api";

/** 可作为 board/{kind} 直接查询的图文类型。 */
const DIRECT_BOARD_KINDS = new Set([
  "character",
  "scene",
  "prop",
  "frame",
  "video_clip",
]);

/** 判断详情载荷是否缺少关联媒体/正文（谱系跳转常见桩数据）。 */
export function isSparseTextAssetItem(item: ImageTextAssetItem): boolean {
  const hasImages = (item.images?.length ?? 0) > 0 || (item.media?.length ?? 0) > 0;
  const hasVariants = (item.variants?.length ?? 0) > 0;
  const hasContent =
    Boolean(item.content && Object.keys(item.content).length > 0) ||
    Boolean((item.summary ?? "").trim()) ||
    Boolean((item.description ?? "").trim());
  return !hasImages && !hasVariants && !hasContent;
}

/**
 * 按资产类型从对应看板（失败再扫 knowledge）查找完整图文条目。
 * 找不到时返回 null。
 */
export async function fetchBoardTextAssetItem(
  projectId: string,
  scriptId: string,
  assetId: string,
  kindHint?: string,
): Promise<ImageTextAssetItem | null> {
  const hint = (kindHint ?? "").replace(/^text_/, "").trim();
  const boardKinds: string[] = [];
  if (DIRECT_BOARD_KINDS.has(hint)) boardKinds.push(hint);
  boardKinds.push("knowledge");

  const params = new URLSearchParams({ script_id: scriptId });
  for (const boardKind of boardKinds) {
    try {
      const r = await fetch(`${API}/projects/${projectId}/board/${boardKind}?${params}`);
      if (!r.ok) continue;
      const b = (await r.json()) as BoardView;
      const found = (b.items ?? []).find(
        (it) => String((it as Record<string, unknown>).id) === assetId,
      );
      if (found) return found as unknown as ImageTextAssetItem;
    } catch {
      // 尝试下一个看板
    }
  }
  return null;
}
