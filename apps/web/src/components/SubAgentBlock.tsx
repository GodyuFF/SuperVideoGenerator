/**
 * 子 Agent ReAct 过程展示：某 Plan 步骤下的多轮思考/行动/可折叠参数/可折叠观察。
 * 参数和观察默认折叠，点击箭头展开/收起。
 */

import { useState } from "react";
import type { SubAgentTurnMessage } from "../types/chat";
import { normalizeActionInput } from "../types/chat";

interface SubAgentBlockProps {
  block: SubAgentTurnMessage;
  /** false 时仅展示各轮工具名称 */
  showDetails?: boolean;
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
}: {
  label: string;
  preview: string;
  full: string;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const needsToggle = full.includes("\n") || full.length > 250 || full !== preview;

  if (!needsToggle) {
    return (
      <div className="collapsible-section">
        <div className="react-section-label">{label}</div>
        <div className="react-section-body">{full}</div>
      </div>
    );
  }

  return (
    <div className="collapsible-section">
      <div className="react-section-label">
        <span>{label}</span>
        <ToggleArrow expanded={expanded} onClick={() => setExpanded((v) => !v)} />
      </div>
      <div className="react-section-body">
        {expanded ? full : preview}
      </div>
    </div>
  );
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
            const inputPreview = inputEntries.length > 0
              ? inputEntries.map(([k]) => k).join("、")
              : "";
            const inputFull = inputEntries.length > 0
              ? inputEntries.map(([k, v]) => `${k}: ${v}`).join("\n")
              : "";
            const obs = it.observation ?? "";

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
                      <CollapsibleSection
                        label="参数"
                        preview={inputPreview}
                        full={inputFull}
                        defaultExpanded={false}
                      />
                    )}
                  </div>
                )}
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
