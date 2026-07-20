/**
 * Plan / 生图 WebSocket 事件防抖合并，降低执行期 setPlanView 频率。
 */

import type { ImageGenProgressEvent, PlanDocument, PlanViewState } from "../types";
import { mergeImageGenProgressIntoPlan } from "../utils/imageGenProgress";
import { mergePlanDocument } from "../utils/planLabels";

export interface PlanUpdatedPayload {
  plan?: PlanDocument;
  runtime_summary?: string;
  plan_status_history?: string[];
  last_remaining_plan?: string[];
  version?: number;
}

interface PendingPlanUpdated {
  plan?: PlanDocument;
  runtime_summary?: string;
  plan_status_history?: string[];
  last_remaining_plan?: string[];
  version?: number;
}

/** 合并 plan_updated 防抖缓冲。 */
export function mergePlanUpdatedPending(
  prev: PendingPlanUpdated | null,
  payload: PlanUpdatedPayload,
): PendingPlanUpdated {
  const next: PendingPlanUpdated = { ...prev };
  if (payload.plan) {
    next.plan = payload.plan;
  }
  if (payload.runtime_summary !== undefined) {
    next.runtime_summary = payload.runtime_summary;
  }
  if (Array.isArray(payload.plan_status_history)) {
    next.plan_status_history = payload.plan_status_history;
  }
  if (Array.isArray(payload.last_remaining_plan)) {
    next.last_remaining_plan = payload.last_remaining_plan;
  }
  if (payload.version !== undefined) {
    next.version = payload.version;
  }
  return next;
}

/** 将缓冲的 plan_updated 合并进 PlanViewState。 */
export function applyPlanUpdatedPending(
  prev: PlanViewState,
  pending: PendingPlanUpdated,
): PlanViewState {
  let next = pending.plan
    ? mergePlanDocument(prev, pending.plan)
    : { ...prev };
  if (pending.runtime_summary !== undefined) {
    next = { ...next, runtime_summary: pending.runtime_summary };
  }
  if (Array.isArray(pending.plan_status_history)) {
    next = { ...next, plan_status_history: pending.plan_status_history };
  }
  if (Array.isArray(pending.last_remaining_plan)) {
    next = { ...next, last_remaining_plan: pending.last_remaining_plan };
  }
  if (pending.version !== undefined) {
    next = { ...next, version: pending.version };
  }
  return next;
}

export interface WsPlanThrottleOptions {
  planDebounceMs?: number;
  imageGenDebounceMs?: number;
  onPlanApply: (updater: (prev: PlanViewState) => PlanViewState) => void;
}

/** 创建 plan_updated / image_gen_progress 防抖调度器。 */
export function createWsPlanThrottle(options: WsPlanThrottleOptions) {
  const planMs = options.planDebounceMs ?? 150;
  const imageMs = options.imageGenDebounceMs ?? 100;

  let planPending: PendingPlanUpdated | null = null;
  let planTimer: ReturnType<typeof setTimeout> | null = null;

  let imagePending: ImageGenProgressEvent[] = [];
  let imageTimer: ReturnType<typeof setTimeout> | null = null;

  const flushPlan = () => {
    planTimer = null;
    if (!planPending) return;
    const pending = planPending;
    planPending = null;
    options.onPlanApply((prev) => applyPlanUpdatedPending(prev, pending));
  };

  const flushImage = () => {
    imageTimer = null;
    if (imagePending.length === 0) return;
    const events = imagePending;
    imagePending = [];
    options.onPlanApply((prev) => {
      let next = prev;
      for (const ev of events) {
        next = mergeImageGenProgressIntoPlan(next, ev);
      }
      return next;
    });
  };

  return {
    /** 调度 plan_updated 合并（trailing debounce）。 */
    schedulePlanUpdated(payload: PlanUpdatedPayload) {
      planPending = mergePlanUpdatedPending(planPending, payload);
      if (!planTimer) {
        planTimer = setTimeout(flushPlan, planMs);
      }
    },

    /** 调度 image_gen_progress 合并。 */
    scheduleImageGenProgress(ev: ImageGenProgressEvent) {
      imagePending.push(ev);
      if (!imageTimer) {
        imageTimer = setTimeout(flushImage, imageMs);
      }
    },

    /** 组件卸载或剧本切换时立即刷出缓冲。 */
    flush() {
      if (planTimer) {
        clearTimeout(planTimer);
        planTimer = null;
      }
      if (imageTimer) {
        clearTimeout(imageTimer);
        imageTimer = null;
      }
      flushPlan();
      flushImage();
    },

    dispose() {
      if (planTimer) clearTimeout(planTimer);
      if (imageTimer) clearTimeout(imageTimer);
      planTimer = null;
      imageTimer = null;
      planPending = null;
      imagePending = [];
    },
  };
}

export type WsPlanThrottle = ReturnType<typeof createWsPlanThrottle>;
