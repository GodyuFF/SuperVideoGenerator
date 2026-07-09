/**
 * 从 SVF API 拉取剧本媒体并转为 Classic MediaAsset 索引。
 */

import type { MediaBinItem } from "../../edit/types";

const API = "/api";

/** SVF 媒体项 → Classic 可索引结构。 */
export interface SvfMediaRecord {
  id: string;
  name: string;
  type: string;
  url: string;
  link?: string;
  durationMs?: number;
  sourceAssetId?: string;
}

/** 拉取剧本媒体列表。 */
export async function fetchSvfScriptMedia(
  projectId: string,
  scriptId: string,
): Promise<SvfMediaRecord[]> {
  const res = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}/media`);
  if (!res.ok) return [];
  const items = (await res.json()) as MediaBinItem[];
  return items.map((m) => ({
    id: m.id,
    name: m.name,
    type: m.type,
    url: m.url || "",
    link: m.link,
    durationMs: m.duration_ms,
    sourceAssetId: m.source_asset_id,
  }));
}

/** 按 mediaId 查找 URL。 */
export function resolveSvfMediaUrl(
  records: SvfMediaRecord[],
  mediaId: string,
): string | undefined {
  return records.find((r) => r.id === mediaId)?.url;
}
