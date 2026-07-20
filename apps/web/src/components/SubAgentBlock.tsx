/**
 * 子 Agent ReAct 过程展示：某 Plan 步骤下的多轮思考/行动/可折叠参数/可折叠观察。
 * 思考、参数和观察默认折叠，点击箭头展开/收起。
 */

import { memo, useState } from "react";
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

/** 子 Agent ReAct 块（默认折叠，减少执行期 DOM 压力）。 */
export const SubAgentBlock = memo(function SubAgentBlock({
  block,
  showDetails = true,
}: SubAgentBlockProps) {
  const [expanded, setExpanded] = useState(false);
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
            const batchActions = it.actions && it.actions.length > 1 ? it.actions : undefined;
            if (!showDetails) {
              if (batchActions) {
                return (
                  <div key={it.iteration} className="sub-agent-iteration sub-agent-iteration-compact">
                    <div className="react-action-batch">
                      {batchActions.map((a) => (
                        <code key={a.action} className="react-action-code">{a.action}</code>
                      ))}
                    </div>
                  </div>
                );
              }
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
                    <CollapsibleSection
                      label="思考"
                      preview={firstLine(it.thought, 120)}
                      full={it.thought}
                      defaultExpanded={false}
                      alwaysCollapsible
                      bodyClassName="react-thought-body"
                    />
                  </div>
                )}
                {batchActions ? (
                  <div className="react-action">
                    <div className="react-section-label">行动（{batchActions.length} 个并行）</div>
                    <div className="react-action-batch">
                      {batchActions.map((a) => (
                        <code key={a.action} className="react-action-code">{a.action}</code>
                      ))}
                    </div>
                  </div>
                ) : it.action ? (
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
          })}
        </div>
      )}
    </div>
  );
}, (prev, next) => {
  const a = prev.block;
  const b = next.block;
  if (prev.showDetails !== next.showDetails) return false;
  return (
    a.id === b.id &&
    a.iterations.length === b.iterations.length &&
    a.finished?.iterations === b.finished?.iterations &&
    a.finished?.outputCount === b.finished?.outputCount &&
    a.iterations.every((it, i) => {
      const other = b.iterations[i];
      return (
        other &&
        it.iteration === other.iteration &&
        it.thought === other.thought &&
        it.action === other.action &&
        it.observation === other.observation &&
        JSON.stringify(it.actions ?? null) === JSON.stringify(other.actions ?? null)
      );
    })
  );
});

/** 从 WS 事件 payload 解析 action_input */
export function subAgentActionInput(raw: unknown): Record<string, string> | undefined {
  return normalizeActionInput(raw);
}
