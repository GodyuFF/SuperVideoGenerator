/** Plan 状态与步骤展示文案 */

import i18n from "../i18n/config";
import type { PlanDocument, PlanStep, PlanViewState } from "../types";

/** 步骤状态本地化标签。 */
export function stepStatusLabel(status: string): string {
  return i18n.t(`stepStatus.${status}`, {
    ns: "plan",
    defaultValue: status,
  });
}

export function emptyPlanView(): PlanViewState {
  return {
    version: 0,
    goal: "",
    constraints: {},
    steps: [],
    runtime_summary: "",
    plan_status_history: [],
    last_remaining_plan: [],
  };
}

export function planFromApi(data: Partial<PlanDocument> | null | undefined): PlanViewState {
  if (!data) return emptyPlanView();
  return {
    version: data.version ?? 0,
    goal: data.goal ?? "",
    constraints: data.constraints ?? {},
    steps: (data.steps ?? []) as PlanStep[],
    runtime_summary: data.runtime_summary ?? "",
    plan_status_history: [],
    last_remaining_plan: [],
  };
}

export function mergePlanDocument(
  prev: PlanViewState,
  doc: Partial<PlanDocument>
): PlanViewState {
  return {
    ...prev,
    version: doc.version ?? prev.version,
    goal: doc.goal ?? prev.goal,
    constraints: doc.constraints ?? prev.constraints,
    steps: (doc.steps as PlanStep[] | undefined) ?? prev.steps,
    runtime_summary: doc.runtime_summary ?? prev.runtime_summary,
  };
}

export function patchPlanStep(
  prev: PlanViewState,
  stepId: string,
  patch: Partial<PlanStep>
): PlanViewState {
  return {
    ...prev,
    steps: prev.steps.map((s) => (s.id === stepId ? { ...s, ...patch } : s)),
  };
}

export function planProgress(steps: PlanStep[]): { done: number; total: number; percent: number } {
  const total = steps.length;
  if (total === 0) return { done: 0, total: 0, percent: 0 };
  const done = steps.filter((s) =>
    ["completed", "skipped"].includes(s.status)
  ).length;
  const running = steps.some((s) => s.status === "running") ? 0.5 : 0;
  const percent = Math.min(100, Math.round(((done + running) / total) * 100));
  return { done, total, percent };
}

/** 剧本执行状态本地化标签。 */
export function scriptStatusLabel(status: string): string {
  return i18n.t(`scriptStatus.${status}`, {
    ns: "plan",
    defaultValue: status,
  });
}
