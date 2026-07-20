/**
 * A2UI 内嵌卡片：在聊天流中展示确认表单，无全屏 overlay。
 * ask_user_question（generic）采用暗房胶片取景器样式。
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
import type { A2UIComponent, A2UIConfirmAck, A2UIConfirmationRequest } from "../types";
import type { A2UIChatMessage } from "../types/chat";
import {
  initialA2UIValues,
  missingRequiredComponents,
} from "../utils/a2uiForm";

type ScriptIntent = "continue" | "regenerate" | "abort";

const CHIP_OPTION_LIMIT = 6;

interface Props {
  message: A2UIChatMessage;
  sendConfirmation: (
    confirmationId: string,
    approved: boolean,
    values?: Record<string, unknown>
  ) => Promise<A2UIConfirmAck>;
  onSubmitted: (
    messageId: string,
    values: Record<string, unknown>,
    approved: boolean
  ) => void;
  /** 本地倒计时到期时通知父级将消息标为 expired。 */
  onExpired?: (messageId: string) => void;
}

/** 将剩余秒数格式化为 mm:ss 或纯秒。 */
function formatRemainSec(sec: number): string {
  if (sec <= 0) return "0s";
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** 已提交答案摘要。 */
function SubmittedSummary({
  request,
  values,
  approved,
}: {
  request: A2UIConfirmationRequest;
  values: Record<string, unknown>;
  approved: boolean;
}) {
  const { t } = useAppTranslation(["settings"]);
  const entries = useMemo(() => {
    const rows: { label: string; value: string }[] = [];
    if (request.kind === "script_structure") {
      const intent = String(values.intent ?? "");
      const intentLabel =
        intent === "continue"
          ? t("settings:a2ui.intentContinue")
          : intent === "regenerate"
            ? t("settings:a2ui.intentRegenerate")
            : intent === "abort"
              ? t("settings:a2ui.intentAbort")
              : intent;
      rows.push({ label: t("settings:a2ui.choiceLabel"), value: intentLabel });
      if (values.feedback) {
        rows.push({
          label: t("settings:a2ui.feedbackLabel"),
          value: String(values.feedback),
        });
      }
      return rows;
    }
    for (const c of request.components) {
      const val = values[c.id];
      if (val === undefined || val === null || val === "") continue;
      if (c.component === "checkbox") {
        rows.push({
          label: c.label,
          value: val ? t("settings:a2ui.costConfirmed") : "—",
        });
      } else {
        rows.push({ label: c.label, value: String(val) });
      }
    }
    if (request.kind === "video_generation_cost" && values.confirm_checkbox) {
      rows.push({
        label: t("settings:a2ui.costConfirmed"),
        value: t("settings:a2ui.costConfirmed"),
      });
    }
    return rows;
  }, [request, values, t]);

  const statusLabel =
    request.kind === "generic" || request.kind === "script_requirements"
      ? t("settings:a2ui.answered")
      : approved
        ? t("settings:a2ui.submitted")
        : t("settings:a2ui.cancelled");

  return (
    <div className="a2ui-inline-summary">
      <span className={`a2ui-inline-status ${approved ? "approved" : "cancelled"}`}>
        {statusLabel}
      </span>
      {entries.length > 0 && (
        <dl className="a2ui-inline-summary-list">
          {entries.map((row) => (
            <div key={row.label} className="a2ui-inline-summary-row">
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

/** 卡片眉标：等待回答 / 等待确认，不暴露原始 kind。 */
function A2UIEyebrow({ kind }: { kind: string }) {
  const { t } = useAppTranslation(["settings"]);
  const label =
    kind === "generic" || kind === "script_requirements"
      ? t("settings:a2ui.awaitingReply")
      : t("settings:a2ui.awaitingConfirm");
  return <span className="a2ui-eyebrow">{label}</span>;
}

/** 聊天内嵌 A2UI 确认卡片 */
export function A2UIInlineCard({
  message,
  sendConfirmation,
  onSubmitted,
  onExpired,
}: Props) {
  const { t } = useAppTranslation(["common", "settings"]);
  const { request, status, submittedValues } = message;
  const cardRef = useRef<HTMLDivElement>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [remainSec, setRemainSec] = useState<number | null>(null);

  const readOnly = status !== "pending";
  const expiresIn = request.expires_in_sec;

  useEffect(() => {
    if (status !== "pending") return;
    cardRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [status, message.confirmationId]);

  useEffect(() => {
    if (status !== "pending" || expiresIn == null || expiresIn <= 0) {
      setRemainSec(null);
      return;
    }
    const started = Date.now();
    let fired = false;
    const tick = () => {
      const left = Math.max(0, expiresIn - Math.floor((Date.now() - started) / 1000));
      setRemainSec(left);
      if (left <= 0 && !fired) {
        fired = true;
        onExpired?.(message.id);
      }
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [status, expiresIn, message.id, onExpired]);

  const submit = async (
    approved: boolean,
    values: Record<string, unknown>
  ) => {
    if (readOnly || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const ack = await sendConfirmation(
        message.confirmationId,
        approved,
        values
      );
      if (!ack.resolved) {
        if (ack.reason === "expired") {
          setError(t("settings:a2ui.submitExpired"));
          onExpired?.(message.id);
        } else if (ack.reason === "already_resolved") {
          setError(t("settings:a2ui.submitAlreadyResolved"));
        } else {
          setError(t("settings:a2ui.submitFailed"));
        }
        return;
      }
      onSubmitted(message.id, values, approved);
    } catch (e) {
      setError((e as Error).message || t("settings:a2ui.submitFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  const shellClass =
    status === "pending"
      ? "a2ui-inline-card a2ui-inline-card--live"
      : "a2ui-inline-card a2ui-inline-card-readonly";

  if (status === "superseded") {
    return (
      <div className={shellClass} ref={cardRef}>
        <div className="a2ui-viewfinder-bar" aria-hidden />
        <header className="a2ui-inline-header">
          <A2UIEyebrow kind={request.kind} />
          <strong className="a2ui-inline-title">{request.title}</strong>
        </header>
        <p className="a2ui-inline-muted">{t("settings:a2ui.superseded")}</p>
      </div>
    );
  }

  if (status === "expired") {
    return (
      <div className={shellClass} ref={cardRef}>
        <div className="a2ui-viewfinder-bar" aria-hidden />
        <header className="a2ui-inline-header">
          <A2UIEyebrow kind={request.kind} />
          <strong className="a2ui-inline-title">{request.title}</strong>
        </header>
        <span className="a2ui-inline-status cancelled">
          {t("settings:a2ui.expired")}
        </span>
        <p className="a2ui-inline-muted">{t("settings:a2ui.expiredHint")}</p>
      </div>
    );
  }

  if (readOnly) {
    return (
      <div className={shellClass} ref={cardRef}>
        <div className="a2ui-viewfinder-bar" aria-hidden />
        <header className="a2ui-inline-header">
          <A2UIEyebrow kind={request.kind} />
          <strong className="a2ui-inline-title">{request.title}</strong>
        </header>
        {status === "submitted" || status === "cancelled" ? (
          <SubmittedSummary
            request={request}
            values={submittedValues ?? {}}
            approved={status === "submitted"}
          />
        ) : (
          <p className="a2ui-inline-muted">{t("settings:a2ui.noHistoryResponse")}</p>
        )}
      </div>
    );
  }

  const expiryHint =
    remainSec != null ? (
      <p className="a2ui-expiry-hint">
        {t("settings:a2ui.expiresIn", { time: formatRemainSec(remainSec) })}
      </p>
    ) : null;

  if (request.kind === "script_structure") {
    return (
      <div className={shellClass} ref={cardRef}>
        <div className="a2ui-viewfinder-bar a2ui-viewfinder-bar--pulse" aria-hidden />
        <ScriptStructureCard
          request={request}
          submitting={submitting}
          error={error}
          onSubmit={submit}
          expiryHint={expiryHint}
        />
      </div>
    );
  }

  if (
    request.kind === "generic" ||
    request.kind === "script_requirements" ||
    request.kind === "plan_approval"
  ) {
    return (
      <div className={shellClass} ref={cardRef}>
        <div className="a2ui-viewfinder-bar a2ui-viewfinder-bar--pulse" aria-hidden />
        <GenericQuestionCard
          request={request}
          submitting={submitting}
          error={error}
          onSubmit={submit}
          onCancel={() => submit(false, { intent: "abort" })}
          expiryHint={expiryHint}
        />
      </div>
    );
  }

  return (
    <div className={shellClass} ref={cardRef}>
      <div className="a2ui-viewfinder-bar a2ui-viewfinder-bar--pulse" aria-hidden />
      <CostConfirmCard
        request={request}
        submitting={submitting}
        error={error}
        onSubmit={submit}
        onCancel={() => submit(false, {})}
        expiryHint={expiryHint}
      />
    </div>
  );
}

/** 剧本结构确认卡。 */
function ScriptStructureCard({
  request,
  submitting,
  error,
  onSubmit,
  expiryHint,
}: {
  request: A2UIConfirmationRequest;
  submitting: boolean;
  error: string;
  onSubmit: (approved: boolean, values: Record<string, unknown>) => void;
  expiryHint: ReactNode;
}) {
  const { t } = useAppTranslation(["common", "settings"]);
  const [feedback, setFeedback] = useState("");
  const summary = request.components.find(
    (c) => c.component === "markdown" || c.component === "text"
  );

  const submitIntent = (intent: ScriptIntent) => {
    onSubmit(intent === "continue", { intent, feedback: feedback.trim() });
  };

  return (
    <>
      <header className="a2ui-inline-header">
        <A2UIEyebrow kind={request.kind} />
        <strong className="a2ui-inline-title">{request.title}</strong>
      </header>
      {request.description && <p className="a2ui-desc">{request.description}</p>}
      {expiryHint}
      {summary && (
        <div className="a2ui-field a2ui-script-summary">
          <strong>{summary.label}</strong>
          <pre>{String(summary.value ?? "")}</pre>
        </div>
      )}
      <label className="a2ui-field">
        <strong>{t("settings:a2ui.feedbackLabel")}</strong>
        <textarea
          className="a2ui-feedback a2ui-input"
          rows={3}
          value={feedback}
          disabled={submitting}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder={t("settings:a2ui.feedbackPlaceholder")}
        />
      </label>
      {error && <p className="a2ui-error">{error}</p>}
      <footer className="a2ui-actions a2ui-actions-three">
        <button
          type="button"
          className="btn-secondary"
          disabled={submitting}
          onClick={() => submitIntent("abort")}
        >
          {t("settings:a2ui.abort")}
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={submitting}
          onClick={() => submitIntent("regenerate")}
        >
          {t("settings:a2ui.regenerate")}
        </button>
        <button
          type="button"
          className="btn-primary"
          disabled={submitting}
          onClick={() => submitIntent("continue")}
        >
          {submitting ? t("common:actions.submitting") : t("settings:a2ui.continue")}
        </button>
      </footer>
    </>
  );
}

/** ask_user_question 动态提问卡。 */
function GenericQuestionCard({
  request,
  submitting,
  error,
  onSubmit,
  onCancel,
  expiryHint,
}: {
  request: A2UIConfirmationRequest;
  submitting: boolean;
  error: string;
  onSubmit: (approved: boolean, values: Record<string, unknown>) => void;
  onCancel: () => void;
  expiryHint: ReactNode;
}) {
  const { t } = useAppTranslation(["common", "settings"]);
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    initialA2UIValues(request.components)
  );
  const [localError, setLocalError] = useState("");

  const missingRequired = useMemo(
    () => missingRequiredComponents(request.components, values),
    [request.components, values]
  );

  const submit = () => {
    if (missingRequired.length > 0) {
      setLocalError(
        t("settings:a2ui.missingRequired", {
          fields: missingRequired.map((c) => c.label).join("、"),
        })
      );
      return;
    }
    setLocalError("");
    onSubmit(true, { ...values });
  };

  const displayError = localError || error;

  return (
    <>
      <header className="a2ui-inline-header">
        <A2UIEyebrow kind={request.kind} />
        <strong className="a2ui-inline-title">{request.title}</strong>
      </header>
      {request.description && <p className="a2ui-desc">{request.description}</p>}
      {expiryHint}
      <div className="a2ui-components">
        {request.components.map((c) => (
          <GenericQuestionField
            key={c.id}
            component={c}
            value={values[c.id]}
            disabled={submitting}
            onChange={(next) =>
              setValues((prev) => ({ ...prev, [c.id]: next }))
            }
          />
        ))}
      </div>
      {displayError && <p className="a2ui-error">{displayError}</p>}
      <footer className="a2ui-actions">
        <button
          type="button"
          className="btn-secondary"
          disabled={submitting}
          onClick={onCancel}
        >
          {t("common:actions.cancel")}
        </button>
        <button
          type="button"
          className="btn-primary"
          disabled={submitting}
          onClick={submit}
        >
          {submitting ? t("common:actions.submitting") : t("common:actions.submit")}
        </button>
      </footer>
    </>
  );
}

/** 费用确认卡。 */
function CostConfirmCard({
  request,
  submitting,
  error,
  onSubmit,
  onCancel,
  expiryHint,
}: {
  request: A2UIConfirmationRequest;
  submitting: boolean;
  error: string;
  onSubmit: (approved: boolean, values: Record<string, unknown>) => void;
  onCancel: () => void;
  expiryHint: ReactNode;
}) {
  const { t } = useAppTranslation(["common", "settings"]);
  const [checkbox, setCheckbox] = useState(false);

  return (
    <>
      <header className="a2ui-inline-header">
        <A2UIEyebrow kind={request.kind} />
        <strong className="a2ui-inline-title">{request.title}</strong>
      </header>
      {request.description && <p className="a2ui-desc">{request.description}</p>}
      {expiryHint}
      {request.estimated_cost_usd != null && (
        <div className="a2ui-cost">
          {t("settings:a2ui.estimatedCost")}
          <strong>${request.estimated_cost_usd.toFixed(2)} USD</strong>
        </div>
      )}
      <div className="a2ui-components">
        {request.components.map((c) => (
          <A2UIField
            key={c.id}
            component={c}
            checkbox={checkbox}
            onCheckbox={setCheckbox}
          />
        ))}
      </div>
      {error && <p className="a2ui-error">{error}</p>}
      <footer className="a2ui-actions">
        <button
          type="button"
          className="btn-secondary"
          disabled={submitting}
          onClick={onCancel}
        >
          {t("common:actions.cancel")}
        </button>
        <button
          type="button"
          className="btn-primary"
          disabled={
            submitting ||
            (request.kind === "video_generation_cost" && !checkbox)
          }
          onClick={() => onSubmit(true, { confirm_checkbox: checkbox })}
        >
          {submitting
            ? t("common:actions.submitting")
            : t("settings:a2ui.confirmContinue")}
        </button>
      </footer>
    </>
  );
}

/** ask_user 单个表单字段（含 chip 单选）。 */
function GenericQuestionField({
  component,
  value,
  disabled,
  onChange,
}: {
  component: A2UIComponent;
  value: unknown;
  disabled?: boolean;
  onChange: (next: unknown) => void;
}) {
  if (component.component === "checkbox") {
    return (
      <label className="a2ui-field checkbox">
        <input
          type="checkbox"
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
        {component.label}
        {component.required && <span className="a2ui-required">*</span>}
      </label>
    );
  }

  if (component.component === "select") {
    const options = component.options ?? [];
    const useChips = options.length > 0 && options.length <= CHIP_OPTION_LIMIT;
    if (useChips) {
      return (
        <fieldset className="a2ui-field a2ui-chip-field">
          <legend>
            {component.label}
            {component.required && <span className="a2ui-required">*</span>}
          </legend>
          <div
            className="a2ui-option-chips"
            role="radiogroup"
            aria-label={component.label}
          >
            {options.map((opt) => {
              const selected = String(value ?? "") === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  className={`a2ui-option-chip${selected ? " is-selected" : ""}`}
                  disabled={disabled}
                  onClick={() => onChange(opt.value)}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </fieldset>
      );
    }
    return (
      <label className="a2ui-field">
        <strong>
          {component.label}
          {component.required && <span className="a2ui-required">*</span>}
        </strong>
        <select
          className="a2ui-input"
          value={String(value ?? "")}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (component.component === "text") {
    const isDuration =
      component.id === "duration_sec" || /时长|秒/.test(component.label);
    if (isDuration) {
      return (
        <label className="a2ui-field">
          <strong>
            {component.label}
            {component.required && <span className="a2ui-required">*</span>}
          </strong>
          <input
            className="a2ui-input"
            type="number"
            min={1}
            value={String(value ?? "")}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value)}
          />
        </label>
      );
    }
    return (
      <label className="a2ui-field">
        <strong>
          {component.label}
          {component.required && <span className="a2ui-required">*</span>}
        </strong>
        <textarea
          className="a2ui-input a2ui-feedback"
          rows={3}
          value={String(value ?? "")}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    );
  }

  return null;
}

/** 费用卡内字段渲染。 */
function A2UIField({
  component,
  checkbox,
  onCheckbox,
}: {
  component: A2UIComponent;
  checkbox: boolean;
  onCheckbox: (v: boolean) => void;
}) {
  if (component.component === "cost_summary") {
    const v = component.value as Record<string, unknown>;
    return (
      <div className="a2ui-field cost-summary">
        <div>{component.label}</div>
        <ul>
          <li>镜头数：{String(v?.shots ?? "")}</li>
          <li>预估：${Number(v?.estimated_usd ?? 0).toFixed(2)}</li>
          <li>{String(v?.description ?? "")}</li>
        </ul>
      </div>
    );
  }
  if (component.component === "checkbox") {
    return (
      <label className="a2ui-field checkbox">
        <input
          type="checkbox"
          checked={checkbox}
          onChange={(e) => onCheckbox(e.target.checked)}
        />
        {component.label}
      </label>
    );
  }
  if (component.component === "markdown" || component.component === "text") {
    return (
      <div className="a2ui-field">
        <strong>{component.label}</strong>
        <pre>{String(component.value ?? "")}</pre>
      </div>
    );
  }
  return null;
}
