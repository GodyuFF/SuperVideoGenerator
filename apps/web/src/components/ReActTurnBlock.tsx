/**
 * 单轮 ReAct 展示：思考（默认收起）+ 行动 pill + 可折叠参数区 + 可折叠观察。
 * 参数和观察默认折叠，点击箭头展开/收起。
 */

import { memo, useState } from "react";
import type { ActionKind, ReactTurnMessage } from "../types/chat";

interface ReActTurnBlockProps {
  turn: ReactTurnMessage;
  /** false 时仅展示工具名称 */
  showDetails?: boolean;
}

function inferActionKind(action: string): ActionKind {
  if (action === "delegate_agent" || action.startsWith("delegate_")) return "delegate";
  if (action.startsWith("tool_")) return "tool";
  if (action === "finish") return "finish";
  if (action === "ask_user_question") return "ask_user";
  return "unknown";
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

/** 取文本的首行（截断至 maxLen） */
function firstLine(text: string, maxLen: number = 200): string {
  const line = text.split("\n")[0].trim();
  if (line.length <= maxLen) return line;
  return line.slice(0, maxLen) + "…";
}

/** 折叠箭头（▲/▼），仅在有需要折叠的内容时渲染 */
function ToggleArrow({ expanded, onClick }: { expanded: boolean; onClick: () => void }) {
  return (
    <span className="toggle-arrow" onClick={onClick} title={expanded ? "收起" : "展开"}>
      {expanded ? "▲" : "▼"}
    </span>
  );
}

function CollapsibleSection({
  label,
  preview,
  full,
  defaultExpanded = false,
  alwaysCollapsible = false,
  bodyClassName = "",
}: {
  label: string;
  preview: string;
  full: string;
  defaultExpanded?: boolean;
  alwaysCollapsible?: boolean;
  bodyClassName?: string;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const needsToggle =
    alwaysCollapsible ||
    full.includes("\n") ||
    full.length > 250 ||
    full !== preview;

  if (!needsToggle) {
    return (
      <div className="collapsible-section">
        <div className="react-section-label">{label}</div>
        <div className={`react-section-body ${bodyClassName}`.trim()}>{full}</div>
      </div>
    );
  }

  return (
    <div className="collapsible-section">
      <div className="react-section-label">
        <span>{label}</span>
        <ToggleArrow expanded={expanded} onClick={() => setExpanded((v) => !v)} />
      </div>
      <div className={`react-section-body ${bodyClassName}`.trim()}>
        {expanded ? full : preview}
      </div>
    </div>
  );
}

/** 单轮 ReAct 展示块（memo 避免流式更新时重绘全部历史轮次）。 */
export const ReActTurnBlock = memo(function ReActTurnBlock({
  turn,
  showDetails = true,
}: ReActTurnBlockProps) {
  const batchActions = turn.actions && turn.actions.length > 1 ? turn.actions : undefined;
  const inputEntries = turn.actionInput
    ? Object.entries(turn.actionInput).filter(([, v]) => v.trim())
    : [];
  const toolLabel = turn.actionLabel ?? turn.action;

  if (!showDetails) {
    if (batchActions) {
      return (
        <div className="react-turn react-turn-compact">
          <div className="react-action-batch">
            {batchActions.map((a) => (
              <div key={a.action} className={actionKindClass(inferActionKind(a.action))}>
                {a.action}
              </div>
            ))}
          </div>
        </div>
      );
    }
    if (!turn.action) return null;
    return (
      <div className="react-turn react-turn-compact">
        <div className={actionKindClass(turn.actionKind)}>{toolLabel}</div>
      </div>
    );
  }

  const obs = turn.observation ?? "";

  // 构建 action_input 的预览（仅显示 key 列表）和完整内容
  const inputPreview = inputEntries.length > 0
    ? inputEntries.map(([k]) => k).join("、")
    : "";
  const inputFull = inputEntries.length > 0
    ? inputEntries.map(([k, v]) => `${k}: ${v}`).join("\n")
    : "";

  const thoughtText =
    turn.thought || (turn.thoughtStreaming ? "" : "（无思考内容）");
  const thoughtPreview = turn.thoughtStreaming
    ? "思考中…"
    : firstLine(thoughtText || "（无思考内容）", 120);

  return (
    <div className="react-turn">
      <div className="react-turn-header">
        <span className="react-turn-badge">ReAct #{turn.iteration}</span>
      </div>

      <div className="react-thought">
        <CollapsibleSection
          label="思考"
          preview={thoughtPreview}
          full={thoughtText}
          defaultExpanded={Boolean(turn.thoughtStreaming)}
          alwaysCollapsible
          bodyClassName={`react-thought-body${turn.thoughtStreaming ? " streaming" : ""}`}
        />
      </div>

      {batchActions ? (
        <div className="react-action">
          <div className="react-section-label">行动（{batchActions.length} 个并行）</div>
          <div className="react-action-batch">
            {batchActions.map((a) => (
              <div key={a.action} className={actionKindClass(inferActionKind(a.action))}>
                {a.action}
              </div>
            ))}
          </div>
        </div>
      ) : turn.action ? (
        <div className="react-action">
          <div className="react-section-label">行动</div>
          <div className={actionKindClass(turn.actionKind)}>
            {turn.actionLabel ?? turn.action}
          </div>
          {turn.action !== turn.actionLabel && (
            <code className="react-action-code">{turn.action}</code>
          )}
          {inputEntries.length > 0 && (
            <CollapsibleSection
              label="参数"
              preview={inputPreview}
              full={inputFull}
              defaultExpanded={false}
            />
          )}
        </div>
      ) : null}

      {obs && (
        <CollapsibleSection
          label="观察"
          preview={firstLine(obs)}
          full={obs}
          defaultExpanded={false}
        />
      )}
    </div>
  );
}, (prev, next) => {
  const a = prev.turn;
  const b = next.turn;
  if (prev.showDetails !== next.showDetails) return false;
  return (
    a.id === b.id &&
    a.thought === b.thought &&
    a.thoughtStreaming === b.thoughtStreaming &&
    a.action === b.action &&
    a.observation === b.observation &&
    JSON.stringify(a.actions ?? null) === JSON.stringify(b.actions ?? null) &&
    a.iteration === b.iteration &&
    a.round === b.round
  );
});
