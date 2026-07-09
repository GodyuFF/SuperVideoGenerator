/**
 * SVF 剧本媒体 → OpenCut Classic MediaAsset 转换与缓存。
 */

import type { MediaBinItem } from "../../edit/types";
import { resolveMediaPlayUrl } from "../../utils/mediaUrl";
import type { SvfMediaRecord } from "./SvfMediaProvider";

/** 剧本媒体 URL 规范化上下文（project/script 用于相对路径转 API）。 */
export interface SvfMediaContext {
  projectId?: string;
  scriptId?: string;
}

/** Classic 侧可索引的媒体结构（与 MediaAsset 字段对齐，避免直接依赖 opencut 类型）。 */
export interface SvfClassicMediaAsset {
  id: string;
  name: string;
  type: "image" | "video" | "audio";
  size: number;
  lastModified: number;
  width?: number;
  height?: number;
  duration?: number;
  file: File;
  url?: string;
  thumbnailUrl?: string;
  ephemeral?: boolean;
  /** fetch 水合失败时为 true，供预览层展示错误提示。 */
  hydrationFailed?: boolean;
}

/** 媒体 ID 解析与类型查询（供 timeline 映射使用）。 */
export interface MediaIdLookup {
  /** 别名键 → 规范 mediaId */
  readonly index: Map<string, string>;
  /** 按 clip 字段解析稳定 mediaId。 */
  resolveMediaId(clip: { asset_ref?: string; preview_url?: string }): string | undefined;
  /** 按 mediaId 查询媒体类型。 */
  getMediaType(mediaId?: string): "image" | "video" | "audio" | undefined;
  /** 判断 mediaId 是否存在于当前剧本媒体列表。 */
  hasMediaId(mediaId?: string): boolean;
}

const mediaCache = new Map<string, SvfClassicMediaAsset[]>();
const hydratedBlobCache = new Map<string, File>();

function normalizeMediaType(type: string): "image" | "video" | "audio" {
  if (type === "video" || type === "audio") return type;
  return "image";
}

function resolveUrl(record: SvfMediaRecord | MediaBinItem): string {
  const url = "url" in record ? record.url : undefined;
  const link = "link" in record ? record.link : undefined;
  return link || url || "";
}

/** 将媒体原始 URL 转为可 fetch / 播放的 API 路径。 */
export function resolveAssetPlayUrl(
  rawUrl: string | undefined,
  context?: SvfMediaContext,
): string {
  return resolveMediaPlayUrl(rawUrl, context?.projectId, context?.scriptId);
}

/** 规范化 URL 以便跨相对/绝对路径匹配。 */
export function normalizeMediaUrl(url: string): string {
  const raw = (url || "").trim();
  if (!raw) return "";
  try {
    if (raw.startsWith("http://") || raw.startsWith("https://")) {
      const parsed = new URL(raw);
      return `${parsed.pathname}${parsed.search}`;
    }
  } catch {
    // 非标准 URL 走原样比较
  }
  return raw.replace(/\/+$/, "");
}

function placeholderFile(name: string, type: string): File {
  return new File([], name || "media", {
    type: type === "audio" ? "audio/mpeg" : "application/octet-stream",
  });
}

function mimeForAsset(type: "image" | "video" | "audio", blobType: string): string {
  if (blobType) return blobType;
  if (type === "video") return "video/mp4";
  if (type === "audio") return "audio/mpeg";
  return "image/jpeg";
}

/** 将 SVF 媒体记录转为 Classic MediaAsset 列表。 */
export function svfRecordsToMediaAssets(
  records: SvfMediaRecord[],
  context?: SvfMediaContext,
): SvfClassicMediaAsset[] {
  return records.map((r) => {
    const raw = r.url;
    const playUrl = resolveAssetPlayUrl(raw, context) || raw;
    return {
      id: r.id,
      name: r.name,
      type: normalizeMediaType(r.type),
      size: 0,
      lastModified: Date.now(),
      duration: r.durationMs ? r.durationMs / 1000 : undefined,
      file: placeholderFile(r.name, r.type),
      url: playUrl,
      ephemeral: false,
    };
  });
}

/** 将 MediaBinItem 转为 Classic MediaAsset 列表。 */
export function svfMediaItemsToAssets(
  items: MediaBinItem[],
  context?: SvfMediaContext,
): SvfClassicMediaAsset[] {
  return items.map((m) => {
    const raw = resolveUrl(m);
    const playUrl = resolveAssetPlayUrl(raw, context) || raw;
    return {
      id: m.id,
      name: m.name,
      type: normalizeMediaType(m.type),
      size: 0,
      lastModified: Date.now(),
      duration: m.duration_ms ? m.duration_ms / 1000 : undefined,
      file: placeholderFile(m.name, m.type),
      url: playUrl,
      ephemeral: false,
    };
  });
}

/** 构建媒体别名索引与类型表。 */
export function buildMediaIdLookup(items: MediaBinItem[]): MediaIdLookup {
  const index = new Map<string, string>();
  const typeById = new Map<string, "image" | "video" | "audio">();

  const addAlias = (alias: string, id: string) => {
    const key = (alias || "").trim();
    if (key) index.set(key, id);
  };

  for (const m of items) {
    const id = m.id;
    if (!id) continue;
    const url = resolveUrl(m);
    const normUrl = normalizeMediaUrl(url);
    const mediaType = normalizeMediaType(m.type);
    typeById.set(id, mediaType);
    addAlias(id, id);
    if (url) addAlias(url, id);
    if (normUrl) addAlias(normUrl, id);
    const sourceAssetId = (m as MediaBinItem & { source_asset_id?: string }).source_asset_id;
    if (sourceAssetId) addAlias(sourceAssetId, id);
  }

  return {
    index,
    resolveMediaId(clip) {
      if (clip.asset_ref) {
        if (index.has(clip.asset_ref)) return index.get(clip.asset_ref);
        if (typeById.has(clip.asset_ref)) return clip.asset_ref;
      }
      if (clip.preview_url) {
        const preview = clip.preview_url.trim();
        const normPreview = normalizeMediaUrl(preview);
        if (index.has(preview)) return index.get(preview);
        if (normPreview && index.has(normPreview)) return index.get(normPreview);
        for (const [key, mediaId] of index) {
          if (!key.startsWith("http") && !key.startsWith("/")) continue;
          if (normalizeMediaUrl(key) === normPreview) return mediaId;
        }
      }
      if (clip.asset_ref && typeById.has(clip.asset_ref)) return clip.asset_ref;
      return undefined;
    },
    getMediaType(mediaId) {
      return mediaId ? typeById.get(mediaId) : undefined;
    },
    hasMediaId(mediaId) {
      return mediaId ? typeById.has(mediaId) : false;
    },
  };
}

/** 构建 mediaId → url 索引（兼容旧调用方）。 */
export function buildMediaIdIndex(items: MediaBinItem[]): Map<string, string> {
  const lookup = buildMediaIdLookup(items);
  const out = new Map<string, string>();
  for (const [key, id] of lookup.index) {
    const url = resolveUrl(items.find((m) => m.id === id) || { id, name: "", type: "image" });
    out.set(key, url || id);
  }
  return out;
}

/** 按 URL / asset_ref 解析稳定 mediaId。 */
export function resolveMediaIdForClip(
  clip: { asset_ref?: string; preview_url?: string },
  mediaIndex: Map<string, string> | MediaIdLookup,
): string | undefined {
  if (typeof (mediaIndex as MediaIdLookup).resolveMediaId === "function") {
    return (mediaIndex as MediaIdLookup).resolveMediaId(clip);
  }
  const map = mediaIndex as Map<string, string>;
  if (clip.asset_ref && map.has(clip.asset_ref)) {
    return map.get(clip.asset_ref);
  }
  if (clip.preview_url) {
    const norm = normalizeMediaUrl(clip.preview_url);
    for (const [key, id] of map) {
      if (key === clip.preview_url || normalizeMediaUrl(key) === norm) return id;
    }
  }
  if (clip.asset_ref && [...map.values()].includes(clip.asset_ref)) return clip.asset_ref;
  return clip.asset_ref;
}

const VIDEO_URL_RE = /\.(mp4|webm|mov|m4v)(\?|$)/i;

/** 从 preview_url 扩展名推断是否为视频。 */
function inferTypeFromPreviewUrl(previewUrl?: string): "video" | undefined {
  const u = (previewUrl || "").trim();
  if (!u) return undefined;
  return VIDEO_URL_RE.test(u) ? "video" : undefined;
}

/** 推断 clip 对应的 Classic element 媒体类型。 */
export function inferClipMediaType(
  clip: { asset_ref?: string; preview_url?: string; preview_media_type?: string },
  lookup: MediaIdLookup,
  fallback: string,
): string {
  const mediaId = lookup.resolveMediaId(clip);
  if (mediaId) {
    const resolved = lookup.getMediaType(mediaId);
    if (resolved) return resolved;
  }
  if (clip.preview_media_type) return clip.preview_media_type;
  const fromUrl = inferTypeFromPreviewUrl(clip.preview_url);
  if (fromUrl) return fromUrl;
  return fallback;
}

/** 缓存某 SVF 项目的媒体列表。 */
export function setSvfProjectMediaCache(projectKey: string, assets: SvfClassicMediaAsset[]): void {
  mediaCache.set(projectKey, assets);
}

/** 读取缓存的 SVF 项目媒体。 */
export function getSvfProjectMediaCache(projectKey: string): SvfClassicMediaAsset[] {
  return mediaCache.get(projectKey) ?? [];
}

/** 清除 SVF 项目媒体缓存。 */
export function clearSvfProjectMediaCache(projectKey: string): void {
  mediaCache.delete(projectKey);
}

/** 将远程 URL 水合为可解码 File（视频 WASM 预览必需）。 */
export async function hydrateSvfMediaFiles(
  assets: SvfClassicMediaAsset[],
  context?: SvfMediaContext,
): Promise<void> {
  await Promise.all(
    assets.map(async (asset) => {
      if (!asset.url || asset.file.size > 0) return;

      const cached = hydratedBlobCache.get(asset.id);
      if (cached && cached.size > 0) {
        asset.file = cached;
        asset.size = cached.size;
        asset.hydrationFailed = false;
        return;
      }

      const fetchUrl = resolveAssetPlayUrl(asset.url, context) || asset.url;
      if (!fetchUrl) {
        asset.hydrationFailed = true;
        console.warn(`[SvfMediaBridge] 媒体 ${asset.id} 无可播放 URL`);
        return;
      }

      try {
        const res = await fetch(fetchUrl);
        if (!res.ok) {
          asset.hydrationFailed = true;
          console.warn(
            `[SvfMediaBridge] 媒体 ${asset.id} 水合失败: HTTP ${res.status} (${fetchUrl})`,
          );
          return;
        }
        const blob = await res.blob();
        if (blob.size === 0) {
          asset.hydrationFailed = true;
          console.warn(`[SvfMediaBridge] 媒体 ${asset.id} 水合为空 blob (${fetchUrl})`);
          return;
        }
        const file = new File([blob], asset.name || "media", {
          type: mimeForAsset(asset.type, blob.type),
        });
        asset.file = file;
        asset.size = file.size;
        asset.lastModified = Date.now();
        asset.hydrationFailed = false;
        asset.url = fetchUrl;
        hydratedBlobCache.set(asset.id, file);
      } catch (err) {
        asset.hydrationFailed = true;
        console.warn(`[SvfMediaBridge] 媒体 ${asset.id} 水合异常 (${fetchUrl})`, err);
      }
    }),
  );
}

/** 视频资产水合失败程度（供预览层展示提示）。 */
export type VideoHydrationState = "none" | "partial" | "all";

/** 统计视频资产水合失败状态。 */
export function getVideoHydrationState(assets: SvfClassicMediaAsset[]): VideoHydrationState {
  const videos = assets.filter((a) => a.type === "video");
  if (videos.length === 0) return "none";
  const failed = videos.filter((a) => a.hydrationFailed || a.file.size === 0);
  if (failed.length === 0) return "none";
  if (failed.length >= videos.length) return "all";
  return "partial";
}

/** 是否存在需解码但水合失败的视频/音频资产。 */
export function hasHydrationFailures(assets: SvfClassicMediaAsset[]): boolean {
  return assets.some(
    (a) =>
      (a.type === "video" || a.type === "audio") &&
      (a.hydrationFailed || a.file.size === 0),
  );
}

/** 异步为图片/视频生成缩略图（不阻塞首屏）。 */
export function enrichMediaThumbnailsAsync(assets: SvfClassicMediaAsset[]): void {
  for (const asset of assets) {
    if (!asset.url || asset.thumbnailUrl) continue;
    if (asset.type === "image") {
      void loadImageThumbnail(asset);
    }
  }
}

async function loadImageThumbnail(asset: SvfClassicMediaAsset): Promise<void> {
  try {
    const img = new Image();
    img.crossOrigin = "anonymous";
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error("thumbnail load failed"));
      img.src = asset.url!;
    });
    const canvas = document.createElement("canvas");
    const max = 120;
    const scale = Math.min(max / img.naturalWidth, max / img.naturalHeight, 1);
    canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    asset.thumbnailUrl = canvas.toDataURL("image/jpeg", 0.7);
    asset.width = img.naturalWidth;
    asset.height = img.naturalHeight;
  } catch {
    // 缩略图失败不影响编辑
  }
}
