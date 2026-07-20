/**
 * 生图进度 WS 事件合并到 Plan 步骤状态。
 */

import type { ImageGenProgressItem } from "../components/ImageGenProgressInline";
import type { ImageGenProgressEvent, PlanViewState } from "../types";
import { patchPlanStep } from "./planLabels";

/** 将 image_gen_progress 事件合并进对应 Plan 步骤。 */
export function mergeImageGenProgressIntoPlan(
  prev: PlanViewState,
  ev: ImageGenProgressEvent,
): PlanViewState {
  const stepId = String(ev.step_id ?? "");
  if (!stepId) return prev;

  const index = Number(ev.index ?? 0);
  const total = Number(ev.total ?? 0);
  const status = String(ev.status ?? "started");
  const step = prev.steps.find((s) => s.id === stepId);
  const prevItems = step?.image_gen_progress?.items ?? [];

  const items = [...prevItems];
  const existingIdx = items.findIndex((item) => item.index === index);
  const entry: ImageGenProgressItem = {
    index,
    sourceTextAssetId: String(ev.source_text_asset_id ?? ""),
    name: String(ev.name ?? ""),
    status:
      status === "completed"
        ? "completed"
        : status === "failed"
          ? "failed"
          : "started",
    url: ev.url ? String(ev.url) : undefined,
    error: ev.error ? String(ev.error) : undefined,
  };

  if (existingIdx >= 0) {
    items[existingIdx] = { ...items[existingIdx], ...entry };
  } else {
    items.push(entry);
  }
  items.sort((a, b) => a.index - b.index);

  const resolvedTotal = total || step?.image_gen_progress?.total || 0;
  const finished = items.filter(
    (i) => i.status === "completed" || i.status === "failed",
  ).length;
  const progress =
    resolvedTotal > 0 ? Math.min(100, Math.round((finished / resolvedTotal) * 100)) : undefined;

  return patchPlanStep(prev, stepId, {
    status: step?.status === "completed" ? step.status : "running",
    progress,
    image_gen_progress: {
      total: resolvedTotal,
      items,
    },
  });
}
