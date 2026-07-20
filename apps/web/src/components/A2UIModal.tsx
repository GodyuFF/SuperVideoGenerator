/**
 * A2UI 确认模态框：展示服务端推送的表单组件，用户确认或取消后继续/中断流水线。
 */

import { useMemo, useState } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
import type { A2UIComponent, A2UIConfirmationRequest } from "../types";
import {
  initialA2UIValues,
  missingRequiredComponents,
} from "../utils/a2uiForm";

interface Props {
  request: A2UIConfirmationRequest;
  onConfirm: (values: Record<string, unknown>) => void;
  onCancel: () => void;
}

type ScriptIntent = "continue" | "regenerate" | "abort";

/** A2UI 确认弹窗根组件 */
export function A2UIModal({ request, onConfirm, onCancel }: Props) {
  const { t } = useAppTranslation(["common", "settings"]);
  const [checkbox, setCheckbox] = useState(false);
  const [feedback, setFeedback] = useState("");

  if (request.kind === "script_structure") {
    const summary = request.components.find(
      (c) => c.component === "markdown" || c.component === "text"
    );

    const submit = (intent: ScriptIntent) => {
      onConfirm({
        intent,
        feedback: feedback.trim(),
      });
    };

    return (
      <div className="a2ui-overlay">
        <div className="a2ui-modal a2ui-modal-wide">
          <header>
            <span className="a2ui-badge">{request.kind}</span>
            <h2>{request.title}</h2>
          </header>
          {request.description && (
            <p className="a2ui-desc">{request.description}</p>
          )}
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
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="如需调整剧本结构或内容，请在此说明…"
            />
          </label>
          <footer className="a2ui-actions a2ui-actions-three">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => submit("abort")}
            >
              {t("settings:a2ui.abort")}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => submit("regenerate")}
            >
              {t("settings:a2ui.regenerate")}
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => submit("continue")}
            >
              {t("settings:a2ui.continue")}
            </button>
          </footer>
        </div>
      </div>
    );
  }

  if (
    request.kind === "generic" ||
    request.kind === "script_requirements" ||
    request.kind === "plan_approval"
  ) {
    return (
      <GenericQuestionModal
        request={request}
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    );
  }

  return (
    <div className="a2ui-overlay">
      <div className="a2ui-modal">
        <header>
          <span className="a2ui-badge">{request.kind}</span>
          <h2>{request.title}</h2>
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
        <footer className="a2ui-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            {t("common:actions.cancel")}
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={
              request.kind === "video_generation_cost" && !checkbox
            }
            onClick={() => onConfirm({ confirm_checkbox: checkbox })}
          >
            {t("settings:a2ui.confirmContinue")}
          </button>
        </footer>
      </div>
    </div>
  );
}

function GenericQuestionModal({
  request,
  onConfirm,
  onCancel,
}: Props) {
  const { t } = useAppTranslation(["common", "settings"]);
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    initialA2UIValues(request.components)
  );
  const [error, setError] = useState("");

  const missingRequired = useMemo(
    () => missingRequiredComponents(request.components, values),
    [request.components, values]
  );

  const submit = () => {
    if (missingRequired.length > 0) {
      setError(`请填写必填项：${missingRequired.map((c) => c.label).join("、")}`);
      return;
    }
    setError("");
    onConfirm({ ...values });
  };

  return (
    <div className="a2ui-overlay">
      <div className="a2ui-modal">
        <header>
          <span className="a2ui-badge">{request.kind}</span>
          <h2>{request.title}</h2>
        </header>
        {request.description && <p className="a2ui-desc">{request.description}</p>}
        <div className="a2ui-components">
          {request.components.map((c) => (
            <GenericQuestionField
              key={c.id}
              component={c}
              value={values[c.id]}
              onChange={(next) =>
                setValues((prev) => ({ ...prev, [c.id]: next }))
              }
            />
          ))}
        </div>
        {error && <p className="a2ui-error">{error}</p>}
        <footer className="a2ui-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            {t("common:actions.cancel")}
          </button>
          <button type="button" className="btn-primary" onClick={submit}>
            {t("common:actions.submit")}
          </button>
        </footer>
      </div>
    </div>
  );
}

function GenericQuestionField({
  component,
  value,
  onChange,
}: {
  component: A2UIComponent;
  value: unknown;
  onChange: (next: unknown) => void;
}) {
  if (component.component === "checkbox") {
    return (
      <label className="a2ui-field checkbox">
        <input
          type="checkbox"
          checked={Boolean(value)}
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
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    );
  }

  return null;
}

/** 根据组件类型渲染单个 A2UI 字段（只读展示，用于费用确认等） */
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
