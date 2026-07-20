/**
 * 剧本视频片段看板选项加载（分镜子镜视频选择器共用）。
 */

import { pickBoardMediaPreviewUrl } from "./boardMediaPreview";

const API = "/api";

/** 看板 video_clip 条目摘要。 */
export interface VideoClipBoardOption {
  id: string;
  name: string;
  summary: string;
  previewUrl?: string;
  primaryMediaId?: string;
  elementRefs: Record<string, string[]>;
}

/** 解析看板 video_clip 条目的 element_refs。 */
export function parseVideoClipElementRefs(content: unknown): Record<string, string[]> {
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

/** 从 video_clip 看板 API 拉取可选列表。 */
export async function fetchVideoClipBoardOptions(
  projectId: string,
  scriptId: string,
): Promise<VideoClipBoardOption[]> {
  const params = new URLSearchParams({ script_id: scriptId });
  const res = await fetch(`${API}/projects/${projectId}/board/video_clip?${params}`);
  if (!res.ok) return [];
  const data = (await res.json()) as { items?: Record<string, unknown>[] };
  return (data.items ?? [])
    .map((item) => {
      const content = item.content;
      const media = Array.isArray(item.media) ? item.media : [];
      const firstVideo = media.find(
        (m) =>
          (m as { type?: string }).type === "video" ||
          (m as { type?: string }).type === "final",
      ) as { id?: string; url?: string } | undefined;
      const images = Array.isArray(item.images) ? item.images : [];
      const firstImage = images[0] as { id?: string; url?: string } | undefined;
      return {
        id: String(item.id ?? item.asset_id ?? ""),
        name: String(item.name ?? item.id ?? ""),
        summary: String(item.summary ?? item.description ?? ""),
        previewUrl: pickBoardMediaPreviewUrl(item) || undefined,
        primaryMediaId: String(
          item.primary_media_id ?? firstVideo?.id ?? firstImage?.id ?? "",
        ),
        elementRefs: parseVideoClipElementRefs(content),
      } satisfies VideoClipBoardOption;
    })
    .filter((o) => o.id);
}

/** 将看板 video_clip 项转为子镜视频视图字段。 */
export function videoClipViewFromBoardOption(
  opt: VideoClipBoardOption,
  slotId: string,
  startMs: number,
  endMs: number,
): {
  id: string;
  videoClipAssetId: string;
  videoClipName?: string;
  mediaId?: string;
  url?: string;
  startMs: number;
  endMs: number;
  sourceKind: string;
} {
  return {
    id: slotId,
    videoClipAssetId: opt.id,
    videoClipName: opt.name,
    mediaId: opt.primaryMediaId || undefined,
    url: opt.previewUrl || undefined,
    startMs,
    endMs,
    sourceKind: "video",
  };
}
