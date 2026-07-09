/**
 * 从 SVF REST API 加载剧本媒体资产列表。
 */

import { apiMediaToEditor } from "./timelineMapper";
import type { MediaAsset } from "../types";

const API = "/api";

/** 拉取指定剧本的全部可编辑媒体。 */
export async function fetchScriptMedia(
  projectId: string,
  scriptId: string,
): Promise<MediaAsset[]> {
  const res = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}/media`);
  if (!res.ok) return [];
  const items = (await res.json()) as Array<{
    id: string;
    name: string;
    type: string;
    url: string;
    is_accessible?: boolean;
    duration_ms?: number;
    source_asset_id?: string;
  }>;
  return apiMediaToEditor(items);
}

/** 解析媒体文件代理 URL（项目/剧本相对路径）。 */
export function mediaFileUrl(
  projectId: string,
  scriptId: string,
  filename: string,
): string {
  return `${API}/projects/${projectId}/scripts/${scriptId}/assets/media/${encodeURIComponent(filename)}`;
}
