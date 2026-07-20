/** planLabels 自测：中间失败但后续同类型成功时应视为完成。 */

import {
  effectiveScriptStatus,
  isPlanEffectivelyComplete,
  isStepSuperseded,
  planProgress,
} from "./planLabels";
import type { PlanStep } from "../types";

function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error(msg);
}

function step(type: string, status: PlanStep["status"]): PlanStep {
  return {
    id: `${type}-${status}`,
    type,
    title: type,
    agent: "agent",
    status,
    progress: status === "completed" ? 100 : 0,
    outputs: [],
  };
}

const steps: PlanStep[] = [
  step("script_design", "completed"),
  step("image_gen", "failed"),
  step("image_gen", "completed"),
  step("edit_compose", "completed"),
];

assert(isStepSuperseded(steps, 1), "failed image_gen should be superseded");
assert(isPlanEffectivelyComplete(steps), "plan should be effectively complete");
assert(
  effectiveScriptStatus("failed", steps) === "completed",
  "failed script should display as completed",
);
const progress = planProgress(steps);
assert(progress.done === progress.total, "progress should count superseded as done");

console.log("planLabels.selftest ok");
