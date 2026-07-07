/**
 * 子 Agent ReAct 过程展示：某 Plan 步骤下的多轮思考/行动/观察。
 */

import { useState } from "react";
import type { SubAgentTurnMessage } from "../types/chat";
import { normalizeActionInput } from "../types/chat";

interface SubAgentBlockProps {
  block: SubAgentTurnMessage;
  /** false 时仅展示各轮工具名称 */
  showDetails?: boolean;
}

export function SubAgentBlock({ block, showDetails = true }: SubAgentBlockProps) {
  const [expanded, setExpanded] = useState(true);
  const title = block.displayName || block.agentName;

  return (
    <div className="sub-agent-block">
      <button
        type="button"
        className="sub-agent-header"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className="sub-agent-badge">子 Agent</span>
        <span className="sub-agent-title">{title}</span>
        {block.finished && (
          <span className="sub-agent-meta muted">
            {block.finished.iterations} 轮 · {block.finished.outputCount} 产出
          </span>
        )}
        <span className="sub-agent-toggle">{expanded ? "收起" : "展开"}</span>
      </button>

      {expanded && (
        <div className="sub-agent-body">
          {block.iterations.map((it) => {
            if (!showDetails) {
              if (!it.action) return null;
              return (
                <div key={it.iteration} className="sub-agent-iteration sub-agent-iteration-compact">
                  <code className="react-action-code">{it.action}</code>
                </div>
              );
            }
            const inputEntries = it.actionInput
              ? Object.entries(it.actionInput).filter(([, v]) => v.trim())
              : [];
            return (
              <div key={it.iteration} className="sub-agent-iteration">
                <div className="react-turn-badge">#{it.iteration}</div>
                {it.thought && (
                  <div className="react-thought">
                    <div className="react-section-label">思考</div>
                    <div className="react-thought-body">{it.thought}</div>
                  </div>
                )}
                {it.action && (
                  <div className="react-action">
                    <div className="react-section-label">行动</div>
                    <code className="react-action-code">{it.action}</code>
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
                {it.observation && (
                  <div className="react-observation">
                    <div className="react-section-label">观察</div>
                    <div className="react-observation-body">{it.observation}</div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** 从 WS 事件 payload 解析 action_input */
export function subAgentActionInput(raw: unknown): Record<string, string> | undefined {
  return normalizeActionInput(raw);
}
