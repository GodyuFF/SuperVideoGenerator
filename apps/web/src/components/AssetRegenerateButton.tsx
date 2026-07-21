/**
 * 详情页二次生成按钮：调用 regenerate API 并展示进度/错误。
 * 图片/视频入队后保持生成态，直至 assets_changed 或队列终态。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
import { formatApiError } from "../hooks/useApi";
import { useAssetGeneration } from "../context/AssetGenerationContext";
import { useGenerationQueue } from "../context/GenerationQueueContext";
import type { AssetGenerationKind } from "../utils/assetGenerationStatus";
import {
  areEnqueueJobsTerminal,
  extractEnqueueJobIds,
  isAssetInQueueActiveOrQueued,
  isJobInQueueActiveOrQueued,
  parseGenerationQueueSnapshot,
  tickAssetQueueWait,
} from "../utils/generationQueueStatus";
import {
  emptyVideoGenSource,
  videoGenSourceToApiBody,
  type VideoGenSourceSelection,
} from "../utils/videoGenSource";

const API = "/api";

export type RegenerateKind = "image" | "tts" | "video" | "frame" | "auto";

export type RegenerateLayout = "inline" | "card" | "compact";

interface AssetRegenerateButtonProps {
  projectId: string;
  scriptId: string;
  /** 单资产二次生成时使用。 */
  assetId?: string;
  /** 分镜级二次生成时使用。 */
  shotId?: string;
  /** 分镜级 kinds，默认 tts。 */
  shotKinds?: Array<"tts" | "frame" | "video">;
  /** 图文变体 ID（可选）。 */
  variantId?: string | null;
  /** 按钮文案类型。 */
  kind?: RegenerateKind;
  /** 展示布局：顶栏 inline、分镜 card、变体 compact。 */
  layout?: RegenerateLayout;
  /** 分镜 AI 视频生成参考源（kinds 含 video 时写入 body.video）。 */
  videoOptions?: VideoGenSourceSelection;
  disabled?: boolean;
  className?: string;
  onDone?: () => void;
  /** 将成功/失败文案上抛给详情顶栏独占行展示。 */
  onStatusChange?: (status: { tone: "success" | "error"; text: string } | null) => void;
}

/** 将 RegenerateKind 映射为生成状态 kind。 */
function generationKindFromRegenerate(
  kind: RegenerateKind,
  shotKinds: Array<"tts" | "frame" | "video">,
  hasShotId: boolean,
): AssetGenerationKind {
  if (hasShotId) {
    if (shotKinds[0] === "tts") return "tts";
    if (shotKinds[0] === "frame") return "frame";
    if (shotKinds[0] === "video") return "video";
  }
  if (kind === "tts") return "tts";
  if (kind === "video") return "video";
  if (kind === "frame") return "frame";
  return "image";
}

/** 判断 HTTP 响应是否为异步入队（202 / accepted）。 */
function isAsyncQueueAccepted(
  data: Record<string, unknown>,
  status: number,
): boolean {
  return status === 202 || data.accepted === true;
}

/** 收集队列监听用的资产 ID 集合。 */
function collectQueueWatchIds(
  data: Record<string, unknown>,
  targetId: string,
): Set<string> {
  const ids = new Set<string>([targetId]);
  const assetId = String(data.asset_id ?? "").trim();
  if (assetId) ids.add(assetId);
  if (Array.isArray(data.asset_ids)) {
    for (const raw of data.asset_ids) {
      const id = String(raw ?? "").trim();
      if (id) ids.add(id);
    }
  }
  const snapshotRaw = data.snapshot;
  if (snapshotRaw && typeof snapshotRaw === "object") {
    const snap = parseGenerationQueueSnapshot(snapshotRaw);
    if (snap) {
      const jobs = [
        snap.active,
        ...snap.queued,
        ...snap.recent,
      ].filter(Boolean);
      for (const job of jobs) {
        if (job?.asset_id) ids.add(job.asset_id);
      }
    }
  }
  return ids;
}

/** 详情页资产二次生成按钮。 */
export function AssetRegenerateButton({
  projectId,
  scriptId,
  assetId,
  shotId,
  shotKinds = ["tts"],
  variantId,
  kind = "auto",
  layout = "inline",
  videoOptions,
  disabled = false,
  className,
  onDone,
  onStatusChange,
}: AssetRegenerateButtonProps) {
  const { t } = useAppTranslation("common");
  const { markGenerating, clearGenerating, getEntry } = useAssetGeneration();
  const { snapshot } = useGenerationQueue();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [asyncWait, setAsyncWait] = useState<{
    watchIds: Set<string>;
    targetId: string;
    jobIds: Set<string>;
  } | null>(null);
  const hadGeneratingEntryRef = useRef(false);
  const sawInQueueRef = useRef(false);

  useEffect(() => {
    if (!onStatusChange) return;
    if (error) onStatusChange({ tone: "error", text: error });
    else if (message) onStatusChange({ tone: "success", text: message });
    else onStatusChange(null);
  }, [error, message, onStatusChange]);

  /** 异步入队完成后收尾：清 busy、生成态与回调。 */
  const finishAsyncWait = useCallback(
    (targetId: string, outcome: { tone: "success" | "error"; text: string }) => {
      clearGenerating(targetId);
      setAsyncWait(null);
      hadGeneratingEntryRef.current = false;
      sawInQueueRef.current = false;
      setBusy(false);
      if (outcome.tone === "success") {
        setError(null);
        setMessage(outcome.text);
        onDone?.();
      } else {
        setMessage(null);
        setError(outcome.text);
      }
    },
    [clearGenerating, onDone],
  );

  /** 监听队列快照与 assets_changed，判定异步入队何时结束。 */
  useEffect(() => {
    if (!asyncWait || !busy) return;

    const { watchIds, targetId, jobIds } = asyncWait;
    const entry = getEntry(targetId);
    if (entry?.phase === "generating") {
      hadGeneratingEntryRef.current = true;
    }

    if (snapshot) {
      if (jobIds.size > 0) {
        for (const jobId of jobIds) {
          if (isJobInQueueActiveOrQueued(snapshot, jobId)) {
            sawInQueueRef.current = true;
          }
        }
        const jobsDone = areEnqueueJobsTerminal(snapshot, jobIds);
        if (jobsDone.complete) {
          if (jobsDone.anyFailed) {
            finishAsyncWait(targetId, {
              tone: "error",
              text: jobsDone.error ?? t("regenerate.failed"),
            });
          } else {
            finishAsyncWait(targetId, { tone: "success", text: t("regenerate.success") });
          }
          return;
        }
      } else {
        for (const id of watchIds) {
          if (isAssetInQueueActiveOrQueued(snapshot, id)) {
            sawInQueueRef.current = true;
          }
        }
        if (sawInQueueRef.current) {
          for (const id of watchIds) {
            const tick = tickAssetQueueWait(snapshot, id, {
              sawInQueue: true,
              jobId: null,
            });
            if (!tick.complete || !tick.outcome) continue;
            if (tick.outcome === "failed") {
              finishAsyncWait(targetId, {
                tone: "error",
                text: tick.error ?? t("regenerate.failed"),
              });
              return;
            }
            finishAsyncWait(targetId, { tone: "success", text: t("regenerate.success") });
            return;
          }
        }
      }
    }

    if (entry?.phase === "failed") {
      finishAsyncWait(targetId, { tone: "error", text: t("regenerate.failed") });
      return;
    }

    if (hadGeneratingEntryRef.current && !entry) {
      finishAsyncWait(targetId, { tone: "success", text: t("regenerate.success") });
    }
  }, [asyncWait, busy, finishAsyncWait, getEntry, snapshot, t]);

  const labelKey = (() => {
    if (kind === "auto") return "regenerate.default";
    if (kind === "image") return "regenerate.image";
    if (kind === "tts") return "regenerate.tts";
    if (kind === "video") return "regenerate.video";
    if (kind === "frame") return "regenerate.frame";
    return "regenerate.default";
  })();

  /** 解析本次操作对应的状态追踪目标。 */
  const resolveGenerationTarget = useCallback((): {
    targetId: string;
    genKind: AssetGenerationKind;
  } | null => {
    if (shotId) {
      return {
        targetId: shotId,
        genKind: generationKindFromRegenerate(kind, shotKinds, true),
      };
    }
    if (assetId) {
      return {
        targetId: assetId,
        genKind: generationKindFromRegenerate(kind, shotKinds, false),
      };
    }
    return null;
  }, [assetId, kind, shotId, shotKinds]);

  /** 发起二次生成请求。 */
  const handleClick = useCallback(async () => {
    if (disabled || busy) return;
    if (!assetId && !shotId) return;

    const genTarget = resolveGenerationTarget();
    if (genTarget) {
      markGenerating({
        targetId: genTarget.targetId,
        kind: genTarget.genKind,
        scriptId,
      });
    }

    setBusy(true);
    setError(null);
    setMessage(null);
    setAsyncWait(null);
    hadGeneratingEntryRef.current = false;
    sawInQueueRef.current = false;
    let deferBusyClear = false;
    try {
      let url: string;
      let body: Record<string, unknown> | undefined;
      if (shotId) {
        url = `${API}/projects/${projectId}/scripts/${scriptId}/shots/${shotId}/regenerate`;
        body = { kinds: shotKinds };
        if (shotKinds.includes("video")) {
          const videoBody = videoGenSourceToApiBody(
            videoOptions ?? emptyVideoGenSource(0),
          );
          if (videoBody) {
            body.video = videoBody;
          }
        }
      } else {
        url = `${API}/projects/${projectId}/scripts/${scriptId}/assets/${assetId}/regenerate`;
        if (variantId) {
          body = { variant_id: variantId };
        }
      }
      const r = await fetch(url, {
        method: "POST",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = (await r.json().catch(() => ({}))) as Record<string, unknown>;
      if (!r.ok) {
        throw new Error(formatApiError(data, t("regenerate.failed")));
      }
      const msg = typeof data.message === "string" ? data.message : t("regenerate.success");
      if (isAsyncQueueAccepted(data, r.status) && genTarget) {
        const watchIds = collectQueueWatchIds(data, genTarget.targetId);
        const jobIds = new Set(extractEnqueueJobIds(data));
        const responseSnap = parseGenerationQueueSnapshot(data.snapshot);
        if (responseSnap) {
          sawInQueueRef.current = [...watchIds].some((id) =>
            isAssetInQueueActiveOrQueued(responseSnap, id),
          );
          if (jobIds.size > 0) {
            const jobsDone = areEnqueueJobsTerminal(responseSnap, jobIds);
            if (jobsDone.complete) {
              setMessage(msg);
              if (jobsDone.anyFailed) {
                setError(jobsDone.error ?? t("regenerate.failed"));
                clearGenerating(genTarget.targetId);
                setBusy(false);
                return;
              }
              clearGenerating(genTarget.targetId);
              setBusy(false);
              onDone?.();
              return;
            }
          }
        }
        setMessage(msg);
        setAsyncWait({ watchIds, targetId: genTarget.targetId, jobIds });
        deferBusyClear = true;
        return;
      }
      setMessage(msg);
      if (genTarget) {
        clearGenerating(genTarget.targetId);
      }
      onDone?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      if (genTarget) {
        clearGenerating(genTarget.targetId);
      }
    } finally {
      if (!deferBusyClear) {
        setBusy(false);
      }
    }
  }, [
    assetId,
    busy,
    clearGenerating,
    disabled,
    markGenerating,
    onDone,
    projectId,
    resolveGenerationTarget,
    scriptId,
    shotId,
    shotKinds,
    t,
    variantId,
    videoOptions,
  ]);

  const wrapClass = [
    "asset-regenerate-wrap",
    layout === "inline" ? "asset-regenerate-wrap--inline" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const btnClass = [
    "asset-regenerate-btn",
    "btn-sm",
    layout === "compact" ? "asset-regenerate-btn--compact" : "",
    busy ? "asset-regenerate-btn--busy" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  /** inline 布局由顶栏 status 区展示，避免挤乱按钮行。 */
  const showInlineStatus = layout !== "inline" || !onStatusChange;

  return (
    <span className={wrapClass}>
      <button
        type="button"
        className={btnClass}
        disabled={disabled || busy}
        aria-busy={busy}
        onClick={() => void handleClick()}
      >
        {busy ? t("regenerate.inProgress") : t(labelKey)}
      </button>
      {showInlineStatus && message ? (
        <p className="asset-regenerate-status asset-regenerate-status--success" role="status">
          {message}
        </p>
      ) : null}
      {showInlineStatus && error ? (
        <p className="asset-regenerate-status asset-regenerate-status--error" role="alert">
          {error}
        </p>
      ) : null}
    </span>
  );
}
