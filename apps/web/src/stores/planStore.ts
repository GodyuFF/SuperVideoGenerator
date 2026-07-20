/**
 * 工作台 Plan 视图 Zustand Store：非紧急 WS 更新走 startTransition。
 */

import { startTransition } from "react";
import { create } from "zustand";
import type { PlanDocument, PlanStep, PlanViewState } from "../types";
import {
  emptyPlanView,
  mergePlanDocument,
  patchPlanStep,
  planFromApi,
} from "../utils/planLabels";
import type { PlanUpdatedPayload } from "../lib/wsPlanThrottle";
import { applyPlanUpdatedPending } from "../lib/wsPlanThrottle";

interface PlanStoreState {
  planView: PlanViewState;
  setPlanView: (updater: PlanViewState | ((prev: PlanViewState) => PlanViewState)) => void;
  setPlanViewTransition: (
    updater: PlanViewState | ((prev: PlanViewState) => PlanViewState),
  ) => void;
  resetPlanView: () => void;
  loadPlanFromApi: (plan: PlanDocument) => void;
  mergePlan: (doc: Partial<PlanDocument>) => void;
  applyPlanUpdated: (payload: PlanUpdatedPayload) => void;
  patchStep: (stepId: string, patch: Partial<PlanStep>) => void;
}

/** 工作台 Plan 全局 Store。 */
export const usePlanStore = create<PlanStoreState>((set, get) => ({
  planView: emptyPlanView(),

  setPlanView(updater) {
    set((state) => ({
      planView: typeof updater === "function" ? updater(state.planView) : updater,
    }));
  },

  setPlanViewTransition(updater) {
    startTransition(() => {
      get().setPlanView(updater);
    });
  },

  resetPlanView() {
    set({ planView: emptyPlanView() });
  },

  loadPlanFromApi(plan) {
    set((state) => ({
      planView: {
        ...planFromApi(plan),
        plan_status_history: state.planView.plan_status_history,
        last_remaining_plan: state.planView.last_remaining_plan,
      },
    }));
  },

  mergePlan(doc) {
    set((state) => ({
      planView: mergePlanDocument(state.planView, doc),
    }));
  },

  applyPlanUpdated(payload) {
    set((state) => ({
      planView: applyPlanUpdatedPending(state.planView, payload),
    }));
  },

  patchStep(stepId, patch) {
    set((state) => ({
      planView: patchPlanStep(state.planView, stepId, patch),
    }));
  },
}));
