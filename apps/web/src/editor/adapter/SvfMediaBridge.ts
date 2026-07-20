/**
 * SVF 剧本媒体 → OpenCut Classic MediaAsset 转换与缓存。
 */

import type { MediaBinItem } from "../../edit/types";
import { resolveMediaPlayUrl } from "../../utils/mediaUrl";
import { getSvfDesktop } from "../../desktop/svfDesktop";
import type { SvfMediaRecord } from "./SvfMediaProvider";
import { probeMediaDuration } from "./probeMediaDuration";

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
  /** 按 mediaId 查询媒体源时长（秒）。 */
  getMediaDurationSec(mediaId?: string): number | undefined;
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

/** 将水合探测后的时长回灌 mediaItems，供 loadFromSvf lookup 使用。 */
export function mergeHydratedDurationsIntoMediaItems<
  T extends { id: string; duration_ms?: number; type?: string },
>(mediaItems: T[], hydratedAssets: SvfClassicMediaAsset[]): T[] {
  const durationById = new Map<string, number>();
  for (const asset of hydratedAssets) {
    if (asset.duration != null && asset.duration > 0) {
      durationById.set(asset.id, Math.round(asset.duration * 1000));
    }
  }
  if (durationById.size === 0) return mediaItems;
  return mediaItems.map((item) => {
    const probedMs = durationById.get(item.id);
    if (probedMs == null || probedMs <= 0) return item;
    const apiMs = item.duration_ms ?? 0;
    // TTS 槽位常长于浏览器探测；探测偏短时不覆盖 API/metadata 时长。
    if (item.type === "audio" && apiMs > probedMs + 50) {
      return item;
    }
    return { ...item, duration_ms: probedMs };
  });
}

/** 用 API duration_ms 校正水合资产时长，避免 probe 偏短污染 mediaCache。 */
export function syncHydratedAssetDurationsFromApi<
  T extends { id: string; duration_ms?: number; type?: string },
>(mediaItems: T[], hydratedAssets: SvfClassicMediaAsset[]): void {
  const apiById = new Map(mediaItems.map((m) => [m.id, m]));
  for (const asset of hydratedAssets) {
    const api = apiById.get(asset.id);
    if (!api?.duration_ms || api.duration_ms <= 0) continue;
    const apiSec = api.duration_ms / 1000;
    const probedSec = asset.duration ?? 0;
    if (api.type === "audio" && probedSec > 0 && probedSec + 0.05 < apiSec) {
      asset.duration = apiSec;
      continue;
    }
    if (!asset.duration || asset.duration <= 0) {
      asset.duration = apiSec;
    }
  }
}

/** 清除指定媒体 ID 的 blob 水合缓存（force 刷新时避免复用偏短探测文件）。 */
export function clearHydratedBlobCacheForIds(mediaIds: string[]): void {
  for (const id of mediaIds) {
    hydratedBlobCache.delete(id);
  }
}

/** 构建媒体别名索引与类型表。 */
export function buildMediaIdLookup(items: MediaBinItem[]): MediaIdLookup {
  const index = new Map<string, string>();
  const typeById = new Map<string, "image" | "video" | "audio">();
  const durationById = new Map<string, number>();

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
    if (m.duration_ms != null && m.duration_ms > 0) {
      durationById.set(id, m.duration_ms / 1000);
    }
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
    getMediaDurationSec(mediaId) {
      return mediaId ? durationById.get(mediaId) : undefined;
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
  const assets = mediaCache.get(projectKey) ?? [];
  clearHydratedBlobCacheForIds(assets.map((a) => a.id));
  mediaCache.delete(projectKey);
}

/** 限制并发执行异步任务。 */
async function mapWithConcurrency<T>(
  items: T[],
  limit: number,
  worker: (item: T) => Promise<void>,
): Promise<void> {
  const executing = new Set<Promise<void>>();
  for (const item of items) {
    const task = worker(item).finally(() => {
      executing.delete(task);
    });
    executing.add(task);
    if (executing.size >= limit) {
      await Promise.race(executing);
    }
  }
  await Promise.all(executing);
}

/**
 * 将已取得的 File 写入资产并可选探测音视频时长。
 */
async function applyHydratedFile(
  asset: SvfClassicMediaAsset,
  file: File,
  fetchUrl: string,
): Promise<void> {
  asset.file = file;
  asset.size = file.size;
  asset.lastModified = Date.now();
  asset.hydrationFailed = false;
  asset.url = fetchUrl;
  hydratedBlobCache.set(asset.id, file);

  if (asset.type !== "audio" && asset.type !== "video") return;
  try {
    const probedSec = await probeMediaDuration(file);
    if (!(probedSec > 0 && Number.isFinite(probedSec))) return;
    const apiSec = asset.duration != null && asset.duration > 0 ? asset.duration : null;
    if (apiSec != null) {
      const drift = Math.abs(apiSec - probedSec) / Math.max(probedSec, 0.001);
      if (drift > 0.05) {
        console.warn(
          `[SvfMediaBridge] 媒体 ${asset.id} 时长偏差: api=${apiSec}s probe=${probedSec}s`,
        );
      }
      // TTS 槽位常长于浏览器探测值；探测偏短时不覆盖 API/metadata 时长。
      if (asset.type === "audio" && probedSec + 0.05 < apiSec) {
        return;
      }
    }
    asset.duration = probedSec;
  } catch (err) {
    console.warn(`[SvfMediaBridge] 媒体 ${asset.id} 时长探测失败`, err);
  }
}

/** 单条媒体资产水合：桌面 IPC 读盘优先，否则 HTTP fetch。 */
async function hydrateSingleAsset(
  asset: SvfClassicMediaAsset,
  context?: SvfMediaContext,
): Promise<void> {
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

  const desktop = getSvfDesktop();
  if (desktop) {
    try {
      const local = await desktop.readLocalMedia(fetchUrl);
      const file = new File([local.data], local.name || asset.name || "media", {
        type: local.mime || mimeForAsset(asset.type, ""),
      });
      if (file.size === 0) {
        asset.hydrationFailed = true;
        console.warn(`[SvfMediaBridge] 媒体 ${asset.id} 本地读盘为空 (${fetchUrl})`);
        return;
      }
      await applyHydratedFile(asset, file, fetchUrl);
      return;
    } catch (err) {
      console.warn(
        `[SvfMediaBridge] 媒体 ${asset.id} 桌面读盘失败，回退 HTTP (${fetchUrl})`,
        err,
      );
    }
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
    await applyHydratedFile(asset, file, fetchUrl);
  } catch (err) {
    asset.hydrationFailed = true;
    console.warn(`[SvfMediaBridge] 媒体 ${asset.id} 水合异常 (${fetchUrl})`, err);
  }
}

const HYDRATE_CONCURRENCY = 4;

/** 将远程 URL 水合为可解码 File（视频 WASM 预览必需）。 */
export async function hydrateSvfMediaFiles(
  assets: SvfClassicMediaAsset[],
  context?: SvfMediaContext,
): Promise<void> {
  await mapWithConcurrency(assets, HYDRATE_CONCURRENCY, (asset) =>
    hydrateSingleAsset(asset, context),
  );
}

/** 视频资产水合失败程度（供预览层展示提示）。 */
export type VideoHydrationState = "none" | "partial" | "all";

/** 单类媒体（video/audio）水合失败程度。 */
export type MediaHydrationSeverity = VideoHydrationState;

export interface MediaHydrationIssues {
  video: MediaHydrationSeverity;
  audio: MediaHydrationSeverity;
}

function getHydrationStateForType(
  assets: SvfClassicMediaAsset[],
  mediaType: "video" | "audio",
): MediaHydrationSeverity {
  const items = assets.filter((a) => a.type === mediaType);
  if (items.length === 0) return "none";
  const failed = items.filter((a) => a.hydrationFailed || a.file.size === 0);
  if (failed.length === 0) return "none";
  if (failed.length >= items.length) return "all";
  return "partial";
}

/** 统计视频与音频资产水合失败状态。 */
export function getMediaHydrationIssues(assets: SvfClassicMediaAsset[]): MediaHydrationIssues {
  return {
    video: getHydrationStateForType(assets, "video"),
    audio: getHydrationStateForType(assets, "audio"),
  };
}

/** 返回需展示的 editor i18n 键列表（video + audio）。 */
export function listMediaHydrationMessageKeys(issues: MediaHydrationIssues): string[] {
  const keys: string[] = [];
  if (issues.video === "all") keys.push("mediaHydrationFailedAll");
  else if (issues.video === "partial") keys.push("mediaHydrationFailedPartial");
  if (issues.audio === "all") keys.push("audioHydrationFailedAll");
  else if (issues.audio === "partial") keys.push("audioHydrationFailedPartial");
  return keys;
}

/** 统计视频资产水合失败状态。 */
export function getVideoHydrationState(assets: SvfClassicMediaAsset[]): VideoHydrationState {
  return getHydrationStateForType(assets, "video");
}

/** 是否存在需解码但水合失败的视频/音频资产。 */
export function hasHydrationFailures(assets: SvfClassicMediaAsset[]): boolean {
  return assets.some(
    (a) =>
      (a.type === "video" || a.type === "audio") &&
      (a.hydrationFailed || a.file.size === 0),
  );
}

/** 视频/音频是否已全部水合完成，可供预览解码与导出混音。 */
export function isSvfMediaReadyForDecode(assets: SvfClassicMediaAsset[]): boolean {
  const decodable = assets.filter((a) => a.type === "video" || a.type === "audio");
  if (decodable.length === 0) return true;
  return decodable.every((a) => a.file.size > 0 && !a.hydrationFailed);
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
