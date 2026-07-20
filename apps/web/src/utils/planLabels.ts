/** Plan 状态与步骤展示文案 */

import i18n from "../i18n/config";
import type { PlanDocument, PlanStep, PlanViewState } from "../types";

const TERMINAL_OK = new Set(["completed", "skipped"]);

/** 判断失败步骤是否已被后续同类型成功步骤覆盖。 */
export function isStepSuperseded(steps: PlanStep[], index: number): boolean {
  const step = steps[index];
  if (!step || step.status !== "failed") return false;
  for (let i = index + 1; i < steps.length; i += 1) {
    const later = steps[i];
    if (later.type === step.type && TERMINAL_OK.has(later.status)) {
      return true;
    }
  }
  return false;
}

/** 各 step type 最后一次出现的状态是否均为终态成功。 */
export function isPlanEffectivelyComplete(steps: PlanStep[]): boolean {
  if (steps.length === 0) return false;
  const lastByType = new Map<string, string>();
  for (const step of steps) {
    lastByType.set(step.type, step.status);
  }
  return [...lastByType.values()].every((status) => TERMINAL_OK.has(status));
}

/** 展示用剧本状态：历史 failed 但计划已实质完成时按 completed 展示。 */
export function effectiveScriptStatus(
  scriptStatus: string,
  steps: PlanStep[],
): string {
  if (scriptStatus === "failed" && isPlanEffectivelyComplete(steps)) {
    return "completed";
  }
  return scriptStatus;
}

/** 步骤展示状态：已恢复的失败步骤显示为 superseded。 */
export function displayStepStatus(
  steps: PlanStep[],
  index: number,
): string {
  const step = steps[index];
  if (!step) return "pending";
  if (isStepSuperseded(steps, index)) return "superseded";
  return step.status;
}

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
  const done = steps.filter(
    (step, index) =>
      TERMINAL_OK.has(step.status) || isStepSuperseded(steps, index),
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
