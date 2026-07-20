/**
 * 生成队列快照：解析与合并 WebSocket / HTTP 载荷。
 */

import type { GenerationQueueJob, GenerationQueueSnapshot } from "../types";

/** 空快照，用于切换剧本或尚无数据时。 */
export function emptyGenerationQueueSnapshot(scriptId: string): GenerationQueueSnapshot {
  return {
    type: "generation_queue_snapshot",
    script_id: scriptId,
    active: null,
    queued: [],
    recent: [],
    counts: { queued: 0, running: 0 },
  };
}

/** 默认计数（无快照时）。 */
export function emptyGenerationQueueCounts(): GenerationQueueSnapshot["counts"] {
  return { queued: 0, running: 0 };
}

const JOB_STATUSES = new Set(["queued", "running", "done", "failed"]);
const JOB_KINDS = new Set(["image", "video"]);

/** 将未知对象规范为单条队列任务。 */
export function normalizeGenerationQueueJob(raw: unknown): GenerationQueueJob | null {
  if (!raw || typeof raw !== "object") return null;
  const rec = raw as Record<string, unknown>;
  const id = String(rec.id ?? "").trim();
  const assetId = String(rec.asset_id ?? "").trim();
  const label = String(rec.label ?? "").trim();
  const kind = String(rec.kind ?? "");
  const status = String(rec.status ?? "");
  if (!id || !assetId || !JOB_KINDS.has(kind) || !JOB_STATUSES.has(status)) {
    return null;
  }
  return {
    id,
    kind: kind as GenerationQueueJob["kind"],
    asset_id: assetId,
    label: label || assetId,
    status: status as GenerationQueueJob["status"],
    error: rec.error != null ? String(rec.error) : null,
    variant_id: rec.variant_id != null ? String(rec.variant_id) : null,
    source: rec.source != null ? String(rec.source) : undefined,
  };
}

/** 解析 HTTP / WS 载荷为队列快照。 */
export function parseGenerationQueueSnapshot(raw: unknown): GenerationQueueSnapshot | null {
  if (!raw || typeof raw !== "object") return null;
  const rec = raw as Record<string, unknown>;
  if (rec.type !== "generation_queue_snapshot") return null;
  const scriptId = String(rec.script_id ?? "").trim();
  if (!scriptId) return null;

  const activeRaw = rec.active;
  const active =
    activeRaw == null ? null : normalizeGenerationQueueJob(activeRaw);

  const queued: GenerationQueueJob[] = [];
  if (Array.isArray(rec.queued)) {
    for (const item of rec.queued) {
      const job = normalizeGenerationQueueJob(item);
      if (job) queued.push(job);
    }
  }

  const recent: GenerationQueueJob[] = [];
  if (Array.isArray(rec.recent)) {
    for (const item of rec.recent) {
      const job = normalizeGenerationQueueJob(item);
      if (job) recent.push(job);
    }
  }

  const countsRaw = rec.counts;
  let counts = emptyGenerationQueueCounts();
  if (countsRaw && typeof countsRaw === "object") {
    const c = countsRaw as Record<string, unknown>;
    counts = {
      queued: Number(c.queued ?? queued.length) || 0,
      running: Number(c.running ?? (active ? 1 : 0)) || 0,
    };
  } else {
    counts = {
      queued: queued.length,
      running: active ? 1 : 0,
    };
  }

  const projectId =
    rec.project_id != null ? String(rec.project_id) : undefined;

  return {
    type: "generation_queue_snapshot",
    script_id: scriptId,
    project_id: projectId,
    active,
    queued,
    recent,
    counts,
  };
}

/** 判断 WS 事件是否为当前剧本的队列快照。 */
export function generationQueueEventMatchesScript(
  event: Record<string, unknown>,
  scriptId: string | null,
): boolean {
  if (!scriptId) return true;
  const evScript = String(event.script_id ?? "");
  if (!evScript) return true;
  return evScript === scriptId;
}

/** 用新快照替换状态；非当前剧本事件时保留原快照。 */
export function applyGenerationQueueSnapshot(
  prev: GenerationQueueSnapshot | null,
  incoming: GenerationQueueSnapshot,
  scriptId: string | null,
): GenerationQueueSnapshot {
  if (scriptId && incoming.script_id !== scriptId) {
    return prev ?? emptyGenerationQueueSnapshot(incoming.script_id);
  }
  return incoming;
}

/** 从 WebSocket 事件合并队列快照。 */
export function reduceGenerationQueueFromWs(
  prev: GenerationQueueSnapshot | null,
  event: Record<string, unknown>,
  scriptId: string | null,
): GenerationQueueSnapshot | null {
  if (event.type !== "generation_queue_snapshot") return prev;
  if (!generationQueueEventMatchesScript(event, scriptId)) return prev;
  const parsed = parseGenerationQueueSnapshot(event);
  if (!parsed) return prev;
  return applyGenerationQueueSnapshot(prev, parsed, scriptId);
}

/** 读取快照计数，缺省时返回零值。 */
export function getGenerationQueueCounts(
  snapshot: GenerationQueueSnapshot | null,
): GenerationQueueSnapshot["counts"] {
  return snapshot?.counts ?? emptyGenerationQueueCounts();
}

/** 判断资产是否仍在队列 active 或 queued 中。 */
export function isAssetInQueueActiveOrQueued(
  snapshot: GenerationQueueSnapshot,
  assetId: string,
): boolean {
  const id = assetId.trim();
  if (!id) return false;
  if (snapshot.active?.asset_id === id) return true;
  return snapshot.queued.some((job) => job.asset_id === id);
}

/** 从 recent 中取该资产最近一条终态（done/failed）。 */
export function getAssetQueueRecentTerminalStatus(
  snapshot: GenerationQueueSnapshot,
  assetId: string,
): "done" | "failed" | null {
  const id = assetId.trim();
  if (!id) return null;
  for (const job of snapshot.recent) {
    if (job.asset_id !== id) continue;
    if (job.status === "done" || job.status === "failed") return job.status;
  }
  return null;
}

/** 从 recent 中取该资产最近一条失败任务的错误文案。 */
export function getAssetQueueRecentError(
  snapshot: GenerationQueueSnapshot,
  assetId: string,
): string | null {
  const id = assetId.trim();
  if (!id) return null;
  for (const job of snapshot.recent) {
    if (job.asset_id !== id) continue;
    if (job.status === "failed" && job.error) return job.error;
  }
  return null;
}

/** 单资产队列等待状态（轮询间累积）。 */
export interface AssetQueueWaitState {
  /** 本轮等待中是否曾见过该资产在 active/queued。 */
  sawInQueue: boolean;
  /** 入队 API 返回的 job_id（优先用于终态匹配，避免陈旧 recent）。 */
  jobId?: string | null;
}

/** 单次快照轮询的等待判定结果。 */
export interface AssetQueueWaitTickResult {
  state: AssetQueueWaitState;
  complete: boolean;
  outcome?: "done" | "failed";
  error?: string | null;
}

/** 判断指定 job 是否仍在 active 或 queued。 */
export function isJobInQueueActiveOrQueued(
  snapshot: GenerationQueueSnapshot,
  jobId: string,
): boolean {
  const id = jobId.trim();
  if (!id) return false;
  if (snapshot.active?.id === id) return true;
  return snapshot.queued.some((job) => job.id === id);
}

/** 从 recent 中按 job id 取终态（done/failed）。 */
export function getJobQueueTerminalStatus(
  snapshot: GenerationQueueSnapshot,
  jobId: string,
): "done" | "failed" | null {
  const id = jobId.trim();
  if (!id) return null;
  for (const job of snapshot.recent) {
    if (job.id !== id) continue;
    if (job.status === "done" || job.status === "failed") return job.status;
  }
  return null;
}

/** 从 recent 中按 job id 取失败错误文案。 */
export function getJobQueueRecentError(
  snapshot: GenerationQueueSnapshot,
  jobId: string,
): string | null {
  const id = jobId.trim();
  if (!id) return null;
  for (const job of snapshot.recent) {
    if (job.id !== id) continue;
    if (job.status === "failed" && job.error) return job.error;
  }
  return null;
}

/**
 * 单次快照轮询：更新等待状态并判定是否可收尾。
 * 有 job_id 时仅匹配该 job 的 recent 终态；否则需先见过 queued/running 再认 recent 终态。
 */
export function tickAssetQueueWait(
  snapshot: GenerationQueueSnapshot,
  assetId: string,
  prev: AssetQueueWaitState,
): AssetQueueWaitTickResult {
  const id = assetId.trim();
  const jobId = String(prev.jobId ?? "").trim();
  let sawInQueue = prev.sawInQueue;

  if (jobId) {
    if (isJobInQueueActiveOrQueued(snapshot, jobId)) {
      return { state: { sawInQueue: true, jobId }, complete: false };
    }
    const terminal = getJobQueueTerminalStatus(snapshot, jobId);
    if (terminal === "failed") {
      return {
        state: { sawInQueue: true, jobId },
        complete: true,
        outcome: "failed",
        error: getJobQueueRecentError(snapshot, jobId),
      };
    }
    if (terminal === "done") {
      return {
        state: { sawInQueue: true, jobId },
        complete: true,
        outcome: "done",
      };
    }
    if (id && isAssetInQueueActiveOrQueued(snapshot, id)) {
      sawInQueue = true;
    }
    return { state: { sawInQueue, jobId }, complete: false };
  }

  if (isAssetInQueueActiveOrQueued(snapshot, id)) {
    return { state: { sawInQueue: true, jobId: null }, complete: false };
  }

  if (!sawInQueue) {
    return { state: { sawInQueue: false, jobId: null }, complete: false };
  }

  const terminal = getAssetQueueRecentTerminalStatus(snapshot, id);
  if (terminal === "failed") {
    return {
      state: { sawInQueue, jobId: null },
      complete: true,
      outcome: "failed",
      error: getAssetQueueRecentError(snapshot, id),
    };
  }
  if (terminal === "done") {
    return {
      state: { sawInQueue, jobId: null },
      complete: true,
      outcome: "done",
    };
  }

  return { state: { sawInQueue, jobId: null }, complete: false };
}

/** 从入队响应提取 job_id / job_ids。 */
export function extractEnqueueJobIds(data: Record<string, unknown>): string[] {
  const ids: string[] = [];
  const single = String(data.job_id ?? "").trim();
  if (single) ids.push(single);
  if (Array.isArray(data.job_ids)) {
    for (const raw of data.job_ids) {
      const id = String(raw ?? "").trim();
      if (id) ids.push(id);
    }
  }
  return [...new Set(ids)];
}

/** 判定一组 job_id 是否均已到达 recent 终态。 */
export function areEnqueueJobsTerminal(
  snapshot: GenerationQueueSnapshot,
  jobIds: Iterable<string>,
): { complete: boolean; anyFailed: boolean; error: string | null } {
  const ids = [...jobIds].map((j) => String(j ?? "").trim()).filter(Boolean);
  if (ids.length === 0) {
    return { complete: false, anyFailed: false, error: null };
  }
  let anyFailed = false;
  let error: string | null = null;
  for (const jobId of ids) {
    if (isJobInQueueActiveOrQueued(snapshot, jobId)) {
      return { complete: false, anyFailed: false, error: null };
    }
    const terminal = getJobQueueTerminalStatus(snapshot, jobId);
    if (!terminal) {
      return { complete: false, anyFailed: false, error: null };
    }
    if (terminal === "failed") {
      anyFailed = true;
      error = getJobQueueRecentError(snapshot, jobId) ?? error;
    }
  }
  return { complete: true, anyFailed, error };
}

/** 解析资产在快照中的行状态（批量 UI 与轮询用）。 */
export function resolveAssetQueueRowStatus(
  snapshot: GenerationQueueSnapshot,
  assetId: string,
): "queued" | "running" | "done" | "failed" | null {
  if (isAssetInQueueActiveOrQueued(snapshot, assetId)) {
    return snapshot.active?.asset_id === assetId ? "running" : "queued";
  }
  return getAssetQueueRecentTerminalStatus(snapshot, assetId);
}

/** 在快照中查找任一关注资产是否已到达终态（需曾出现在 active/queued）。 */
export function findQueueTerminalAmongAssets(
  snapshot: GenerationQueueSnapshot,
  assetIds: Iterable<string>,
): { assetId: string; status: "done" | "failed"; error: string | null } | null {
  for (const raw of assetIds) {
    const assetId = String(raw ?? "").trim();
    if (!assetId) continue;
    const tick = tickAssetQueueWait(snapshot, assetId, {
      sawInQueue: isAssetInQueueActiveOrQueued(snapshot, assetId),
      jobId: null,
    });
    if (tick.complete && tick.outcome) {
      return {
        assetId,
        status: tick.outcome,
        error: tick.error ?? null,
      };
    }
  }
  return null;
}
