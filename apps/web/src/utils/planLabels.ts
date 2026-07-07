/** Plan 状态与步骤展示文案 */

import type { PlanDocument, PlanStep, PlanViewState } from "../types";

const STEP_STATUS_LABEL: Record<string, string> = {
  pending: "待执行",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
  paused: "已暂停",
  skipped: "已跳过",
  awaiting_confirmation: "待确认",
};

export function stepStatusLabel(status: string): string {
  return STEP_STATUS_LABEL[status] ?? status;
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
