/**
 * 执行计划面板：展示 PlanDocument、AI 回写的 plan_status / remaining_plan 与步骤进度。
 */

import { MediaPreview } from "./MediaPreview";
import type { PlanViewState } from "../types";
import { planProgress, stepStatusLabel } from "../utils/planLabels";
import { resolveMediaPlayUrl } from "../utils/mediaUrl";

interface PlanPanelProps {
  plan: PlanViewState;
  scriptStatus: string;
  projectId?: string | null;
  scriptId?: string | null;
  isRunning?: boolean;
  isAborting?: boolean;
  onAbort?: () => void;
}

const SCRIPT_STATUS_LABEL: Record<string, string> = {
  draft: "草稿",
  planned: "已规划",
  executing: "执行中",
  completed: "已完成",
  failed: "失败",
};

function scriptStatusLabel(status: string): string {
  return SCRIPT_STATUS_LABEL[status] ?? status;
}

export function PlanPanel({
  plan,
  scriptStatus,
  projectId,
  scriptId,
  isRunning = false,
  isAborting = false,
  onAbort,
}: PlanPanelProps) {
  const { done, total, percent } = planProgress(plan.steps);
  const hasSteps = plan.steps.length > 0;
  const summary = plan.runtime_summary?.trim();
  const history = plan.plan_status_history.filter((h) => h.trim());
  const remaining = plan.last_remaining_plan.filter((r) => r.trim());

  return (
    <section className="plan-panel">
      <div className="plan-panel-header">
        <div>
          <h3>执行计划</h3>
          <p className="plan-panel-meta muted">
            {plan.goal ? `目标：${plan.goal}` : "发送对话后按流水线顺序执行"}
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
              {isAborting ? "中止中…" : "中止执行"}
            </button>
          )}
          <span className={`plan-script-badge status-${scriptStatus}`}>
            {scriptStatusLabel(scriptStatus)}
          </span>
        </div>
      </div>

      {hasSteps && (
        <div className="plan-progress-bar" aria-label="计划进度">
          <div className="plan-progress-track">
            <div
              className="plan-progress-fill"
              style={{ width: `${percent}%` }}
            />
          </div>
          <span className="plan-progress-text muted">
            {done}/{total} 步完成 · {percent}%
          </span>
        </div>
      )}

      {summary && (
        <div className="plan-status-card">
          <div className="plan-status-label">当前状态（AI）</div>
          <p className="plan-status-text">{summary}</p>
        </div>
      )}

      {remaining.length > 0 && (
        <div className="plan-remaining-block">
          <div className="plan-block-title">后续计划</div>
          <ul className="plan-remaining-list">
            {remaining.map((item, i) => (
              <li key={`${i}-${item.slice(0, 24)}`}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {history.length > 0 && (
        <details className="plan-history-details">
          <summary>状态历史（{history.length}）</summary>
          <ul className="plan-history-list">
            {history.map((item, i) => (
              <li key={`${i}-${item.slice(0, 16)}`}>{item}</li>
            ))}
          </ul>
        </details>
      )}

      {!hasSteps && !summary && (
        <p className="muted plan-empty-hint">
          剧本 → 图片 → 分镜 → [视频] → 配音 → 剪辑
        </p>
      )}

      {hasSteps && (
        <ol className="plan-step-timeline">
          {plan.steps.map((step, index) => (
            <li
              key={step.id}
              className={`plan-step-card status-${step.status}`}
            >
              <div className="plan-step-index">{index + 1}</div>
              <div className="plan-step-body">
                <div className="plan-step-title-row">
                  <span className="plan-step-title">{step.title}</span>
                  <span className={`plan-step-badge status-${step.status}`}>
                    {stepStatusLabel(step.status)}
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
                {step.error && (
                  <p className="plan-step-error">{step.error}</p>
                )}
                {(step.outputs?.length ?? 0) > 0 && (
                  <ul className="plan-step-outputs">
                    {step.outputs!.map((o) => {
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
                            <a
                              className="media-link"
                              href={playUrl}
                              target="_blank"
                              rel="noreferrer"
                            >
                              打开
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
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
