/**
 * A2UI 确认模态框：展示服务端推送的表单组件，用户确认或取消后继续/中断流水线。
 */

import { useState } from "react";
import type { A2UIComponent, A2UIConfirmationRequest } from "../types";

interface Props {
  request: A2UIConfirmationRequest;
  onConfirm: (values: Record<string, unknown>) => void;
  onCancel: () => void;
}

/** A2UI 确认弹窗根组件 */
export function A2UIModal({ request, onConfirm, onCancel }: Props) {
  const [checkbox, setCheckbox] = useState(false);

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
            取消
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={
              request.kind === "video_generation_cost" && !checkbox
            }
            onClick={() => onConfirm({ confirm_checkbox: checkbox })}
          >
            确认并继续
          </button>
        </footer>
      </div>
    </div>
  );
}

/** 根据组件类型渲染单个 A2UI 字段 */
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
