/**
 * analyze API 结果展示。
 */

import type { EditTimelineAnalyzeResponse } from "./types";
import { formatMsPrecise } from "./formatMs";

interface AnalyzePanelProps {
  data: EditTimelineAnalyzeResponse | null;
}

/** 将分析条目渲染为列表。 */
function ItemList({ title, items }: { title: string; items: Array<Record<string, unknown>> }) {
  if (!items.length) return null;
  return (
    <div className="etviz-analyze-block">
      <h4>
        {title} ({items.length})
      </h4>
      <ul className="etviz-list etviz-list--compact">
        {items.map((item, i) => (
          <li key={`${title}-${i}`}>
            <pre className="etviz-json-snippet etviz-json-snippet--inline">
              {JSON.stringify(item, null, 2)}
            </pre>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** 分析结果面板。 */
export function AnalyzePanel({ data }: AnalyzePanelProps) {
  if (!data) {
    return <p className="muted">无分析数据</p>;
  }

  const range = data.range ?? {};
  const start = Number(range.start_ms ?? 0);
  const end = Number(range.end_ms ?? 0);

  return (
    <div className="etviz-panel-section">
      <p className="muted etviz-range-label">
        分析区间：{formatMsPrecise(start)} – {formatMsPrecise(end)}
      </p>
      {(data.warnings ?? []).length > 0 ? (
        <ul className="etviz-list">
          {(data.warnings ?? []).map((w, i) => (
            <li key={`aw-${i}`}>{w}</li>
          ))}
        </ul>
      ) : null}
      <ItemList title="gaps" items={(data.gaps ?? []) as Array<Record<string, unknown>>} />
      <ItemList title="overlaps" items={(data.overlaps ?? []) as Array<Record<string, unknown>>} />
      <ItemList
        title="missing_assets"
        items={(data.missing_assets ?? []) as Array<Record<string, unknown>>}
      />
      <ItemList
        title="shot_alignment"
        items={(data.shot_alignment ?? []) as Array<Record<string, unknown>>}
      />
      <ItemList
        title="optimization_hints"
        items={(data.optimization_hints ?? []) as Array<Record<string, unknown>>}
      />
      {(data.clips_in_range ?? []).length > 0 ? (
        <details className="etviz-details">
          <summary>clips_in_range ({data.clips_in_range!.length})</summary>
          <pre className="etviz-json-snippet">
            {JSON.stringify(data.clips_in_range, null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
