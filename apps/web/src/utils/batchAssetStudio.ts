/**
 * 资源列表：聚合五类看板资产、缺媒体判定、异步队列 regenerate 批量编排。
 */

import { formatApiError } from "../hooks/useApi";
import type { GenerationQueueSnapshot } from "../types";
import type { AssetGenerationKind } from "./assetGenerationStatus";
import { pickBoardMediaPreviewUrl } from "./boardMediaPreview";
import {
  parseGenerationQueueSnapshot,
  resolveAssetQueueRowStatus,
  tickAssetQueueWait,
  type AssetQueueWaitState,
} from "./generationQueueStatus";

const API = "/api";

/** 轮询间隔默认毫秒。 */
const DEFAULT_QUEUE_POLL_MS = 1500;

/** 休眠指定毫秒（队列轮询用）。 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 拉取当前剧本生成队列快照。 */
async function fetchGenerationQueueSnapshot(
  projectId: string,
  scriptId: string,
): Promise<GenerationQueueSnapshot | null> {
  const res = await fetch(
    `${API}/projects/${projectId}/scripts/${scriptId}/generation-queue`,
  );
  if (!res.ok) return null;
  const data: unknown = await res.json().catch(() => null);
  return parseGenerationQueueSnapshot(data);
}

/** 印样台支持的文字资产类型。 */
export const BATCH_STUDIO_KINDS = [
  "character",
  "scene",
  "prop",
  "frame",
  "video_clip",
] as const;

export type BatchStudioKind = (typeof BATCH_STUDIO_KINDS)[number];

/** 单行队列状态。 */
export type BatchStudioRowStatus = "idle" | "queued" | "running" | "done" | "error";

/** 印样台列表行。 */
export interface BatchStudioAssetRow {
  id: string;
  type: BatchStudioKind;
  name: string;
  summary: string;
  previewUrl: string;
  primaryMediaId: string;
  missingMedia: boolean;
}

/** 拉取并规范化五类看板后的整表。 */
export interface BatchStudioCatalog {
  rows: BatchStudioAssetRow[];
  missingCount: number;
  totalCount: number;
}

/** markGenerating / clearGenerating 命令接口（与 AssetGenerationContext 对齐）。 */
export interface BatchStudioGenerationHooks {
  markGenerating: (opts: {
    targetId: string;
    kind: AssetGenerationKind;
    scriptId: string;
  }) => void;
  clearGenerating: (...targetIds: string[]) => void;
}

/** 判断看板条目是否缺可展示媒体。 */
export function isBatchStudioMissingMedia(item: Record<string, unknown>): boolean {
  const type = String(item.type ?? item.kind ?? "").trim();
  const previewUrl = pickBoardMediaPreviewUrl(item);
  if (previewUrl) return false;
  const primary = String(item.primary_media_id ?? "").trim();
  if (primary) return false;
  if (type === "video_clip") {
    const videos = Array.isArray(item.videos) ? item.videos : [];
    for (const row of videos) {
      if (!row || typeof row !== "object") continue;
      const url = String((row as { url?: unknown }).url ?? "").trim();
      if (url) return false;
    }
    return true;
  }
  const images = Array.isArray(item.images) ? item.images : [];
  for (const row of images) {
    if (!row || typeof row !== "object") continue;
    const url = String((row as { url?: unknown }).url ?? "").trim();
    if (url) return false;
  }
  return true;
}

/** 将看板 raw item 规范为印样台行。 */
export function normalizeBatchStudioRow(
  item: Record<string, unknown>,
  fallbackType: BatchStudioKind,
): BatchStudioAssetRow | null {
  const id = String(item.id ?? "").trim();
  if (!id) return null;
  const rawType = String(item.type ?? fallbackType).trim() as BatchStudioKind;
  const type = (BATCH_STUDIO_KINDS as readonly string[]).includes(rawType)
    ? rawType
    : fallbackType;
  const name = String(item.name ?? id).trim() || id;
  const summary = String(item.summary ?? item.description ?? item.preview ?? "").trim();
  return {
    id,
    type,
    name,
    summary,
    previewUrl: pickBoardMediaPreviewUrl(item),
    primaryMediaId: String(item.primary_media_id ?? "").trim(),
    missingMedia: isBatchStudioMissingMedia({ ...item, type }),
  };
}

/** 并行拉取五类 board 并去重聚合。 */
export async function fetchBatchStudioCatalog(
  projectId: string,
  scriptId: string,
): Promise<BatchStudioCatalog> {
  const params = new URLSearchParams({ script_id: scriptId });
  const results = await Promise.all(
    BATCH_STUDIO_KINDS.map(async (kind) => {
      const res = await fetch(`${API}/projects/${projectId}/board/${kind}?${params}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(formatApiError(body, `加载 ${kind} 看板失败 (${res.status})`));
      }
      const data = (await res.json()) as { items?: Record<string, unknown>[] };
      return { kind, items: data.items ?? [] };
    }),
  );

  const seen = new Set<string>();
  const rows: BatchStudioAssetRow[] = [];
  for (const { kind, items } of results) {
    for (const raw of items) {
      const row = normalizeBatchStudioRow(raw, kind);
      if (!row || seen.has(row.id)) continue;
      seen.add(row.id);
      rows.push(row);
    }
  }

  rows.sort((a, b) => {
    const ti = BATCH_STUDIO_KINDS.indexOf(a.type) - BATCH_STUDIO_KINDS.indexOf(b.type);
    if (ti !== 0) return ti;
    return a.name.localeCompare(b.name, "zh");
  });

  const missingCount = rows.filter((r) => r.missingMedia).length;
  return { rows, missingCount, totalCount: rows.length };
}

/** 资产类型 → regenerate 生成 kind。 */
export function regenerateKindForStudioType(type: BatchStudioKind): AssetGenerationKind {
  return type === "video_clip" ? "video" : "image";
}

/** 单条 regenerate 入队结果（HTTP 成功仅表示已接受，不代表生成完成）。 */
export interface RegenerateStudioAssetResult {
  message: string;
  jobId: string | null;
}

/** 单条 regenerate 入队请求。 */
export async function regenerateStudioAsset(
  projectId: string,
  scriptId: string,
  assetId: string,
): Promise<RegenerateStudioAssetResult> {
  const url = `${API}/projects/${projectId}/scripts/${scriptId}/assets/${assetId}/regenerate`;
  const res = await fetch(url, { method: "POST" });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    throw new Error(formatApiError(data, "二次生成失败"));
  }
  const jobId = String(data.job_id ?? "").trim() || null;
  return {
    message: typeof data.message === "string" ? data.message : "已加入生成队列",
    jobId,
  };
}

export interface WaitForGenerationJobsOptions {
  pollMs?: number;
  shouldCancel?: () => boolean;
  /** 入队响应中的 asset_id → job_id，优先用于终态匹配。 */
  jobIdsByAsset?: Map<string, string>;
  /** 每次轮询拿到快照时回调，供批量 UI 刷新行状态。 */
  onSnapshot?: (snapshot: GenerationQueueSnapshot) => void;
}

/** 等待指定资产离开队列的 active/queued，并返回终态。 */
export async function waitForGenerationJobs(
  projectId: string,
  scriptId: string,
  assetIds: Set<string>,
  opts?: WaitForGenerationJobsOptions,
): Promise<Map<string, "done" | "failed" | string>> {
  const pollMs = opts?.pollMs ?? DEFAULT_QUEUE_POLL_MS;
  const results = new Map<string, "done" | "failed" | string>();
  const pending = new Set(
    [...assetIds].map((id) => id.trim()).filter(Boolean),
  );
  if (pending.size === 0) return results;

  const waitStates = new Map<string, AssetQueueWaitState>();
  for (const assetId of pending) {
    waitStates.set(assetId, {
      sawInQueue: false,
      jobId: opts?.jobIdsByAsset?.get(assetId) ?? null,
    });
  }

  while (pending.size > 0) {
    if (opts?.shouldCancel?.()) break;

    const snapshot = await fetchGenerationQueueSnapshot(projectId, scriptId);
    if (snapshot) {
      opts?.onSnapshot?.(snapshot);
      for (const assetId of [...pending]) {
        const prev = waitStates.get(assetId) ?? { sawInQueue: false, jobId: null };
        const tick = tickAssetQueueWait(snapshot, assetId, prev);
        waitStates.set(assetId, tick.state);
        if (!tick.complete || !tick.outcome) continue;
        if (tick.outcome === "failed") {
          results.set(assetId, tick.error ?? "failed");
        } else {
          results.set(assetId, "done");
        }
        pending.delete(assetId);
      }
    }

    if (pending.size > 0) {
      await sleep(pollMs);
    }
  }

  return results;
}

export interface RunBatchRegenerateOptions {
  projectId: string;
  scriptId: string;
  rows: BatchStudioAssetRow[];
  concurrency?: number;
  hooks: BatchStudioGenerationHooks;
  onRowStatus: (
    assetId: string,
    status: BatchStudioRowStatus,
    error?: string | null,
  ) => void;
  /** 单条完成后节流刷新看板。 */
  onItemDone?: () => void;
  shouldCancel?: () => boolean;
}

/** 批量入队并等待服务端串行队列完成；返回成功/失败计数。 */
export async function runBatchRegenerate(
  opts: RunBatchRegenerateOptions,
): Promise<{ ok: number; failed: number }> {
  const concurrency = Math.max(
    1,
    Math.min(4, opts.concurrency ?? Math.min(opts.rows.length, 4)),
  );
  const queue = [...opts.rows];
  let ok = 0;
  let failed = 0;
  let cursor = 0;
  const enqueuedIds = new Set<string>();
  const jobIdsByAsset = new Map<string, string>();
  const markedIds = new Set<string>();

  for (const row of queue) {
    opts.onRowStatus(row.id, "queued");
  }

  const worker = async () => {
    while (cursor < queue.length) {
      if (opts.shouldCancel?.()) return;
      const idx = cursor;
      cursor += 1;
      const row = queue[idx];
      if (!row) continue;

      const genKind = regenerateKindForStudioType(row.type);
      opts.hooks.markGenerating({
        targetId: row.id,
        kind: genKind,
        scriptId: opts.scriptId,
      });
      markedIds.add(row.id);

      try {
        const { jobId } = await regenerateStudioAsset(opts.projectId, opts.scriptId, row.id);
        enqueuedIds.add(row.id);
        if (jobId) jobIdsByAsset.set(row.id, jobId);
        opts.onRowStatus(row.id, "queued");
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        opts.onRowStatus(row.id, "error", msg);
        failed += 1;
        opts.hooks.clearGenerating(row.id);
        markedIds.delete(row.id);
      }
    }
  };

  await Promise.all(
    Array.from({ length: Math.min(concurrency, queue.length) }, () => worker()),
  );

  if (enqueuedIds.size > 0 && !opts.shouldCancel?.()) {
    const outcomes = await waitForGenerationJobs(
      opts.projectId,
      opts.scriptId,
      enqueuedIds,
      {
        shouldCancel: opts.shouldCancel,
        jobIdsByAsset,
        onSnapshot: (snapshot) => {
          for (const assetId of enqueuedIds) {
            const rowStatus = resolveAssetQueueRowStatus(snapshot, assetId);
            if (rowStatus === "running") {
              opts.onRowStatus(assetId, "running");
            } else if (rowStatus === "queued") {
              opts.onRowStatus(assetId, "queued");
            }
          }
        },
      },
    );

    for (const assetId of enqueuedIds) {
      const outcome = outcomes.get(assetId) ?? "done";
      if (outcome === "done") {
        opts.onRowStatus(assetId, "done");
        ok += 1;
        opts.onItemDone?.();
      } else {
        const errMsg = outcome === "failed" ? "生成失败" : outcome;
        opts.onRowStatus(assetId, "error", errMsg);
        failed += 1;
      }
      opts.hooks.clearGenerating(assetId);
      markedIds.delete(assetId);
    }
  }

  for (const assetId of markedIds) {
    opts.hooks.clearGenerating(assetId);
  }

  return { ok, failed };
}

/** 按类型与缺媒体状态筛选行。 */
export function filterBatchStudioRows(
  rows: BatchStudioAssetRow[],
  typeFilter: BatchStudioKind | "all",
  mediaFilter: "all" | "missing" | "ready",
): BatchStudioAssetRow[] {
  return rows.filter((row) => {
    if (typeFilter !== "all" && row.type !== typeFilter) return false;
    if (mediaFilter === "missing" && !row.missingMedia) return false;
    if (mediaFilter === "ready" && row.missingMedia) return false;
    return true;
  });
}
