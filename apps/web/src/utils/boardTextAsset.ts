/**
 * 从剧本看板 API 拉取单个文字资产完整项，供子镜挂接区打开编辑弹窗。
 */

import type { ImageTextAssetItem } from "../components/ImageTextAssetCard";

const API = "/api";

/** 看板 kind → 文字资产 type。 */
export type BoardTextAssetKind = "frame" | "video_clip";

/** 按 kind 与 assetId 从看板列表解析文字资产项。 */
export async function fetchBoardTextAssetItem(
  projectId: string,
  scriptId: string,
  kind: BoardTextAssetKind,
  assetId: string,
): Promise<ImageTextAssetItem | null> {
  const id = assetId.trim();
  if (!id) return null;
  const params = new URLSearchParams({ script_id: scriptId });
  const res = await fetch(`${API}/projects/${projectId}/board/${kind}?${params}`);
  if (!res.ok) return null;
  const data = (await res.json()) as { items?: ImageTextAssetItem[] };
  const found = (data.items ?? []).find((item) => item.id === id);
  if (!found) return null;
  return { ...found, type: found.type || kind };
}
