/**
 * 执行计划面板：展示 PlanDocument、AI 回写的 plan_status / remaining_plan 与步骤进度。
 */

import { memo, useEffect, useId, useState } from "react";
import { MediaPreview } from "./MediaPreview";
import { ImageGenProgressInline } from "./ImageGenProgressInline";
import { useAppTranslation } from "../i18n/useAppTranslation";
import type { PlanViewState, StepOutput } from "../types";
import { planProgress, scriptStatusLabel, stepStatusLabel, effectiveScriptStatus, displayStepStatus } from "../utils/planLabels";
import { resolveMediaPlayUrl } from "../utils/mediaUrl";
import { summarizePlanOutputs } from "../utils/planOutputSummary";

/** 单步产出：默认按状态折叠为一行摘要，可展开完整列表。 */
function PlanStepOutputs({
  outputs,
  shownStatus,
  stepId,
  projectId,
  scriptId,
}: {
  outputs: StepOutput[];
  shownStatus: string;
  stepId: string;
  projectId?: string | null;
  scriptId?: string | null;
}) {
  const { t } = useAppTranslation(["common", "plan"]);
  const listId = useId();
  const defaultExpanded =
    shownStatus === "running" || shownStatus === "awaiting_confirmation";
  const defaultKey = `${stepId}:${shownStatus}`;
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [boundKey, setBoundKey] = useState(defaultKey);

  useEffect(() => {
    if (boundKey !== defaultKey) {
      setBoundKey(defaultKey);
      setExpanded(defaultExpanded);
    }
  }, [boundKey, defaultKey, defaultExpanded]);

  if (!outputs.length) return null;

  const summary = summarizePlanOutputs(outputs, {
    kindImage: t("plan:outputsSummary.image"),
    kindVideo: t("plan:outputsSummary.video"),
    kindAudio: t("plan:outputsSummary.audio"),
    kindText: t("plan:outputsSummary.text"),
    labelNames: {
      character: t("plan:outputsSummary.labels.character"),
      prop: t("plan:outputsSummary.labels.prop"),
      scene: t("plan:outputsSummary.labels.scene"),
      plot: t("plan:outputsSummary.labels.plot"),
      video_plan: t("plan:outputsSummary.labels.video_plan"),
    },
  });

  const scrollable = outputs.length > 8;

  return (
    <div className="plan-step-outputs-wrap">
      <button
        type="button"
        className="plan-step-outputs-toggle"
        aria-expanded={expanded}
        aria-controls={listId}
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="plan-step-outputs-chevron" aria-hidden>
          {expanded ? "▼" : "▶"}
        </span>
        <span className="plan-step-outputs-summary">
          {summary || t("plan:outputsToggle")}
        </span>
      </button>
      {expanded && (
        <ul
          id={listId}
          className={`plan-step-outputs${scrollable ? " plan-step-outputs--scroll" : ""}`}
        >
          {outputs.map((o) => {
            const playUrl = resolveMediaPlayUrl(o.url, projectId, scriptId);
            return (
              <li key={o.asset_id} className={`plan-step-output kind-${o.kind}`}>
                <span className="plan-step-output-label">{o.label}</span>
                {o.kind === "audio" && playUrl ? (
                  <MediaPreview
                    kind="audio"
                    url={playUrl}
                    projectId={projectId}
                    scriptId={scriptId}
                    className="plan-step-audio-preview"
                  />
                ) : playUrl ? (
                  <a className="media-link" href={playUrl} target="_blank" rel="noreferrer">
                    {t("common:actions.open")}
                  </a>
                ) : o.url ? (
                  <span className="muted">{o.url}</span>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

interface PlanPanelProps {
  plan: PlanViewState;
  scriptStatus: string;
  projectId?: string | null;
  scriptId?: string | null;
  isRunning?: boolean;
  isAborting?: boolean;
  onAbort?: () => void;
}

/** 执行计划面板（memo 隔离 plan 更新与聊天流式重绘）。 */
export const PlanPanel = memo(function PlanPanel({
  plan,
  scriptStatus,
  projectId,
  scriptId,
  isRunning = false,
  isAborting = false,
  onAbort,
}: PlanPanelProps) {
  const { t } = useAppTranslation(["common", "nav", "plan"]);
  const { done, total, percent } = planProgress(plan.steps);
  const displayScriptStatus = effectiveScriptStatus(scriptStatus, plan.steps);
  const hasSteps = plan.steps.length > 0;
  const summary = plan.runtime_summary?.trim();
  const history = plan.plan_status_history.filter((h) => h.trim());
  const remaining = plan.last_remaining_plan.filter((r) => r.trim());
  const affected = new Set(plan.affected_step_ids ?? []);
  const replanReason = plan.last_replan_reason?.trim();

  return (
    <section className="plan-panel">
      <div className="plan-panel-header">
        <div>
          <h3>{t("plan:title")}</h3>
          <p className="plan-panel-meta muted">
            {plan.goal
              ? t("plan:goalPrefix", { goal: plan.goal })
              : t("plan:defaultHint")}
            {plan.version > 0 && ` · v${plan.version}`}
          </p>
        </div>
        <div className="plan-panel-header-actions">
          {isRunning && onAbort && (
            <button
              type="button"
              className="btn-secondary btn-sm plan-abort-btn"
              onClick={onAbort}
              disabled={isAborting}
            >
              {isAborting ? t("common:actions.aborting") : t("nav:abortExecution")}
            </button>
          )}
          <span className={`plan-script-badge status-${displayScriptStatus}`}>
            {scriptStatusLabel(displayScriptStatus)}
          </span>
        </div>
      </div>

      {hasSteps && (
        <div className="plan-progress-bar" aria-label={t("plan:progressAria")}>
          <div className="plan-progress-track">
            <div
              className="plan-progress-fill"
              style={{ width: `${percent}%` }}
            />
          </div>
          <span className="plan-progress-text muted">
            {t("plan:progressText", { done, total, percent })}
          </span>
        </div>
      )}

      {summary && (
        <div className="plan-status-card">
          <div className="plan-status-label">{t("plan:currentStatus")}</div>
          <p className="plan-status-text">{summary}</p>
        </div>
      )}

      {remaining.length > 0 && (
        <div className="plan-remaining-block">
          <div className="plan-block-title">{t("plan:remainingPlan")}</div>
          <ul className="plan-remaining-list">
            {remaining.map((item, i) => (
              <li key={`${i}-${item.slice(0, 24)}`}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {history.length > 0 && (
        <details className="plan-history-details">
          <summary>{t("plan:statusHistory", { count: history.length })}</summary>
          <ul className="plan-history-list">
            {history.map((item, i) => (
              <li key={`${i}-${item.slice(0, 16)}`}>{item}</li>
            ))}
          </ul>
        </details>
      )}

      {replanReason && (
        <div className="plan-status-card plan-replan-reason">
          <div className="plan-status-label">{t("plan:lastReplan")}</div>
          <p className="plan-status-text">{replanReason}</p>
        </div>
      )}

      {!hasSteps && !summary && (
        <p className="muted plan-empty-hint">{t("plan:pipelineHint")}</p>
      )}

      {hasSteps && (
        <ol className="plan-step-timeline">
          {plan.steps.map((step, index) => {
            const shownStatus = displayStepStatus(plan.steps, index);
            const isAffected = affected.has(step.id);
            return (
            <li
              key={step.id}
              className={`plan-step-card status-${shownStatus}${isAffected ? " plan-step--affected" : ""}`}
            >
              <div className="plan-step-index">{index + 1}</div>
              <div className="plan-step-body">
                <div className="plan-step-title-row">
                  <span className="plan-step-title">{step.title}</span>
                  <span className={`plan-step-badge status-${shownStatus}`}>
                    {stepStatusLabel(shownStatus)}
                  </span>
                </div>
                <div className="plan-step-meta muted">
                  <span className="step-type">{step.type}</span>
                  {step.agent && <span> · {step.agent}</span>}
                  {typeof step.progress === "number" && step.status === "running" && (
                    <span> · {step.progress}%</span>
                  )}
                </div>
                {step.description && (
                  <p className="plan-step-desc muted">{step.description}</p>
                )}
                {step.error && shownStatus !== "superseded" && (
                  <p className="plan-step-error">{step.error}</p>
                )}
                {step.error && shownStatus === "superseded" && (
                  <p className="plan-step-error muted">{t("plan:supersededStepNote")}</p>
                )}
                {step.image_gen_progress && step.image_gen_progress.total > 0 && (
                  <ImageGenProgressInline
                    total={step.image_gen_progress.total}
                    items={step.image_gen_progress.items}
                    projectId={projectId}
                    scriptId={scriptId}
                  />
                )}
                {(step.outputs?.length ?? 0) > 0 && (
                  <PlanStepOutputs
                    outputs={step.outputs!}
                    shownStatus={shownStatus}
                    stepId={step.id}
                    projectId={projectId}
                    scriptId={scriptId}
                  />
                )}
              </div>
            </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}, (prev, next) => {
  return (
    prev.plan.version === next.plan.version &&
    prev.plan.steps === next.plan.steps &&
    prev.plan.runtime_summary === next.plan.runtime_summary &&
    prev.plan.plan_status_history === next.plan.plan_status_history &&
    prev.plan.last_remaining_plan === next.plan.last_remaining_plan &&
    prev.scriptStatus === next.scriptStatus &&
    prev.isRunning === next.isRunning &&
    prev.isAborting === next.isAborting &&
    prev.projectId === next.projectId &&
    prev.scriptId === next.scriptId &&
    prev.onAbort === next.onAbort
  );
});
