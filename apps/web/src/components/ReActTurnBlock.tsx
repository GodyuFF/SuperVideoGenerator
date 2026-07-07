/**
 * 单轮 ReAct 展示：思考（默认展开）+ 行动 pill + action_input 参数区。
 */

import type { ActionKind, ReactTurnMessage } from "../types/chat";

interface ReActTurnBlockProps {
  turn: ReactTurnMessage;
  /** false 时仅展示工具名称 */
  showDetails?: boolean;
}

function actionKindClass(kind?: ActionKind): string {
  switch (kind) {
    case "delegate":
      return "react-action-pill delegate";
    case "tool":
      return "react-action-pill tool";
    case "finish":
      return "react-action-pill finish";
    case "ask_user":
      return "react-action-pill ask-user";
    default:
      return "react-action-pill";
  }
}

export function ReActTurnBlock({ turn, showDetails = true }: ReActTurnBlockProps) {
  const inputEntries = turn.actionInput
    ? Object.entries(turn.actionInput).filter(([, v]) => v.trim())
    : [];
  const toolLabel = turn.actionLabel ?? turn.action;

  if (!showDetails) {
    if (!turn.action) return null;
    return (
      <div className="react-turn react-turn-compact">
        <div className={actionKindClass(turn.actionKind)}>{toolLabel}</div>
      </div>
    );
  }

  return (
    <div className="react-turn">
      <div className="react-turn-header">
        <span className="react-turn-badge">ReAct #{turn.iteration}</span>
      </div>

      <div className="react-thought">
        <div className="react-section-label">思考</div>
        <div
          className={`react-thought-body${turn.thoughtStreaming ? " streaming" : ""}`}
        >
          {turn.thought || (turn.thoughtStreaming ? "" : "（无思考内容）")}
        </div>
      </div>

      {turn.action && (
        <div className="react-action">
          <div className="react-section-label">行动</div>
          <div className={actionKindClass(turn.actionKind)}>
            {turn.actionLabel ?? turn.action}
          </div>
          {turn.action !== turn.actionLabel && (
            <code className="react-action-code">{turn.action}</code>
          )}
          {inputEntries.length > 0 && (
            <dl className="react-action-input">
              {inputEntries.map(([key, value]) => (
                <div key={key} className="react-action-input-row">
                  <dt>{key}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}

      {turn.observation && (
        <div className="react-observation">
          <div className="react-section-label">观察</div>
          <div className="react-observation-body">{turn.observation}</div>
        </div>
      )}
    </div>
  );
}
