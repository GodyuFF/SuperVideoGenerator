/**
 * 原始 JSON Tab 切换展示。
 */

import { useState } from "react";

type JsonTab = "timeline" | "validate" | "analyze";

interface JsonPanelProps {
  timeline: unknown;
  validate: unknown;
  analyze: unknown;
}

/** 三份 API payload 的只读 JSON 视图。 */
export function JsonPanel({ timeline, validate, analyze }: JsonPanelProps) {
  const [tab, setTab] = useState<JsonTab>("timeline");

  const payloads: Record<JsonTab, unknown> = {
    timeline,
    validate,
    analyze,
  };

  return (
    <div className="etviz-json-panel">
      <div className="etviz-tab-bar" role="tablist">
        {(["timeline", "validate", "analyze"] as const).map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            className={`btn-secondary btn-sm${tab === key ? " active" : ""}`}
            onClick={() => setTab(key)}
          >
            {key}
          </button>
        ))}
      </div>
      <pre className="etviz-json-full">{JSON.stringify(payloads[tab], null, 2)}</pre>
    </div>
  );
}
