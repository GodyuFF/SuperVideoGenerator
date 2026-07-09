/**
 * A2UI 内嵌卡片：在聊天流中展示确认表单，无全屏 overlay。
 */

import { useMemo, useState } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
import type { A2UIComponent, A2UIConfirmationRequest } from "../types";
import type { A2UIChatMessage } from "../types/chat";
import {
  initialA2UIValues,
  missingRequiredComponents,
} from "../utils/a2uiForm";

type ScriptIntent = "continue" | "regenerate" | "abort";

interface Props {
  message: A2UIChatMessage;
  sendConfirmation: (
    confirmationId: string,
    approved: boolean,
    values?: Record<string, unknown>
  ) => Promise<boolean>;
  onSubmitted: (
    messageId: string,
    values: Record<string, unknown>,
    approved: boolean
  ) => void;
}

function SubmittedSummary({
  request,
  values,
  approved,
}: {
  request: A2UIConfirmationRequest;
  values: Record<string, unknown>;
  approved: boolean;
}) {
  const entries = useMemo(() => {
    const rows: { label: string; value: string }[] = [];
    if (request.kind === "script_structure") {
      const intent = String(values.intent ?? "");
      const intentLabel =
        intent === "continue"
          ? "继续"
          : intent === "regenerate"
            ? "重新生成"
            : intent === "abort"
              ? "中止"
              : intent;
      rows.push({ label: "选择", value: intentLabel });
      if (values.feedback) {
        rows.push({ label: "修改意见", value: String(values.feedback) });
      }
      return rows;
    }
    for (const c of request.components) {
      const val = values[c.id];
      if (val === undefined || val === null || val === "") continue;
      if (c.component === "checkbox") {
        rows.push({ label: c.label, value: val ? "是" : "否" });
      } else {
        rows.push({ label: c.label, value: String(val) });
      }
    }
    if (request.kind === "video_generation_cost" && values.confirm_checkbox) {
      rows.push({ label: "费用确认", value: "已确认" });
    }
    return rows;
  }, [request, values]);

  return (
    <div className="a2ui-inline-summary">
      <span className={`a2ui-inline-status ${approved ? "approved" : "cancelled"}`}>
        {approved ? "已提交" : "已取消"}
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

/** 聊天内嵌 A2UI 确认卡片 */
export function A2UIInlineCard({
  message,
  sendConfirmation,
  onSubmitted,
}: Props) {
  const { request, status, submittedValues } = message;
  const readOnly = status !== "pending";
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const submit = async (
    approved: boolean,
    values: Record<string, unknown>
  ) => {
    if (readOnly || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const resolved = await sendConfirmation(
        message.confirmationId,
        approved,
        values
      );
      if (!resolved) {
        setError("提交失败，请重试");
        return;
      }
      onSubmitted(message.id, values, approved);
    } catch (e) {
      setError((e as Error).message || "提交失败，请重试");
    } finally {
      setSubmitting(false);
    }
  };

  if (status === "superseded") {
    return (
      <div className="a2ui-inline-card a2ui-inline-card-readonly">
        <header className="a2ui-inline-header">
          <span className="a2ui-badge">{request.kind}</span>
          <strong>{request.title}</strong>
        </header>
        <p className="a2ui-inline-muted">已被新的确认请求取代</p>
      </div>
    );
  }

  if (readOnly) {
    return (
      <div className="a2ui-inline-card a2ui-inline-card-readonly">
        <header className="a2ui-inline-header">
          <span className="a2ui-badge">{request.kind}</span>
          <strong>{request.title}</strong>
        </header>
        {status === "submitted" || status === "cancelled" ? (
          <SubmittedSummary
            request={request}
            values={submittedValues ?? {}}
            approved={status === "submitted"}
          />
        ) : (
          <p className="a2ui-inline-muted">未在历史中记录用户响应</p>
        )}
      </div>
    );
  }

  if (request.kind === "script_structure") {
    return (
      <ScriptStructureCard
        request={request}
        submitting={submitting}
        error={error}
        onSubmit={submit}
      />
    );
  }

  if (request.kind === "generic") {
    return (
      <GenericQuestionCard
        request={request}
        submitting={submitting}
        error={error}
        onSubmit={submit}
        onCancel={() => submit(false, { intent: "abort" })}
      />
    );
  }

  return (
    <CostConfirmCard
      request={request}
      submitting={submitting}
      error={error}
      onSubmit={submit}
      onCancel={() => submit(false, {})}
    />
  );
}

function ScriptStructureCard({
  request,
  submitting,
  error,
  onSubmit,
}: {
  request: A2UIConfirmationRequest;
  submitting: boolean;
  error: string;
  onSubmit: (approved: boolean, values: Record<string, unknown>) => void;
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
    <div className="a2ui-inline-card">
      <header className="a2ui-inline-header">
        <span className="a2ui-badge">{request.kind}</span>
        <strong>{request.title}</strong>
      </header>
      {request.description && <p className="a2ui-desc">{request.description}</p>}
      {summary && (
        <div className="a2ui-field a2ui-script-summary">
          <strong>{summary.label}</strong>
          <pre>{String(summary.value ?? "")}</pre>
        </div>
      )}
      <label className="a2ui-field">
        <strong>修改意见（重新生成时填写）</strong>
        <textarea
          className="a2ui-feedback"
          rows={3}
          value={feedback}
          disabled={submitting}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="如需调整剧本结构或内容，请在此说明…"
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
    </div>
  );
}

function GenericQuestionCard({
  request,
  submitting,
  error,
  onSubmit,
  onCancel,
}: {
  request: A2UIConfirmationRequest;
  submitting: boolean;
  error: string;
  onSubmit: (approved: boolean, values: Record<string, unknown>) => void;
  onCancel: () => void;
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
        `请填写必填项：${missingRequired.map((c) => c.label).join("、")}`
      );
      return;
    }
    setLocalError("");
    onSubmit(true, { ...values });
  };

  const displayError = localError || error;

  return (
    <div className="a2ui-inline-card">
      <header className="a2ui-inline-header">
        <span className="a2ui-badge">{request.kind}</span>
        <strong>{request.title}</strong>
      </header>
      {request.description && <p className="a2ui-desc">{request.description}</p>}
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
    </div>
  );
}

function CostConfirmCard({
  request,
  submitting,
  error,
  onSubmit,
  onCancel,
}: {
  request: A2UIConfirmationRequest;
  submitting: boolean;
  error: string;
  onSubmit: (approved: boolean, values: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const { t } = useAppTranslation(["common", "settings"]);
  const [checkbox, setCheckbox] = useState(false);

  return (
    <div className="a2ui-inline-card">
      <header className="a2ui-inline-header">
        <span className="a2ui-badge">{request.kind}</span>
        <strong>{request.title}</strong>
      </header>
      {request.description && <p className="a2ui-desc">{request.description}</p>}
      {request.estimated_cost_usd != null && (
        <div className="a2ui-cost">
          预估费用：<strong>${request.estimated_cost_usd.toFixed(2)} USD</strong>
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
          disabled={submitting || (request.kind === "video_generation_cost" && !checkbox)}
          onClick={() => onSubmit(true, { confirm_checkbox: checkbox })}
        >
          {submitting ? t("common:actions.submitting") : t("settings:a2ui.confirmContinue")}
        </button>
      </footer>
    </div>
  );
}

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
          {(component.options ?? []).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (component.component === "text") {
    return (
      <label className="a2ui-field">
        <strong>
          {component.label}
          {component.required && <span className="a2ui-required">*</span>}
        </strong>
        <input
          className="a2ui-input"
          type="text"
          value={String(value ?? "")}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    );
  }

  return null;
}

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
