/**
 * 剧本画面看板选项加载（分镜子镜画面选择器与单镜绑定共用）。
 */

import { pickBoardMediaPreviewUrl } from "./boardMediaPreview";

const API = "/api";

/** 看板画面项摘要。 */
export interface FrameBoardOption {
  id: string;
  name: string;
  description: string;
  previewUrl?: string;
  primaryMediaId?: string;
  elementRefs: Record<string, string[]>;
}

/** 解析看板 frame 条目的 element_refs。 */
export function parseFrameElementRefs(content: unknown): Record<string, string[]> {
  if (!content || typeof content !== "object") return {};
  const raw = (content as { element_refs?: Record<string, unknown> }).element_refs;
  if (!raw || typeof raw !== "object") return {};
  const out: Record<string, string[]> = {};
  for (const [key, val] of Object.entries(raw)) {
    if (Array.isArray(val)) {
      out[key] = val.map(String).filter(Boolean);
    }
  }
  return out;
}

/** 从画面看板 API 拉取可选 frame 列表。 */
export async function fetchFrameBoardOptions(
  projectId: string,
  scriptId: string,
): Promise<FrameBoardOption[]> {
  const params = new URLSearchParams({ script_id: scriptId });
  const res = await fetch(`${API}/projects/${projectId}/board/frame?${params}`);
  if (!res.ok) return [];
  const data = (await res.json()) as { items?: Record<string, unknown>[] };
  return (data.items ?? [])
    .map((item) => {
      const content = item.content;
      const images = Array.isArray(item.images) ? item.images : [];
      const firstImage = images[0] as { id?: string; url?: string } | undefined;
      return {
        id: String(item.id ?? item.asset_id ?? ""),
        name: String(item.name ?? item.id ?? ""),
        description: String(item.description ?? item.summary ?? ""),
        // preview 字段多为摘要文案，须用真实媒体 URL
        previewUrl: pickBoardMediaPreviewUrl(item) || undefined,
        primaryMediaId: String(item.primary_media_id ?? firstImage?.id ?? ""),
        elementRefs: parseFrameElementRefs(content),
      } satisfies FrameBoardOption;
    })
    .filter((o) => o.id);
}

/** 将看板画面项转为子镜画面视图字段。 */
export function frameViewFromBoardOption(
  opt: FrameBoardOption,
  slotId: string,
): {
  id: string;
  frameAssetId: string;
  frameName?: string;
  imageMediaId?: string;
  imageUrl?: string;
  sourceMediaIds: string[];
  elementRefs?: Record<string, string[]>;
} {
  return {
    id: slotId,
    frameAssetId: opt.id,
    frameName: opt.name,
    imageMediaId: opt.primaryMediaId || undefined,
    imageUrl: opt.previewUrl || undefined,
    sourceMediaIds: [],
    elementRefs: { ...opt.elementRefs },
  };
}
