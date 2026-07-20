/**
 * validate API 结果展示。
 */

import type { EditTimelineValidateResponse } from "./types";

interface ValidatePanelProps {
  data: EditTimelineValidateResponse | null;
}

/** 校验结果面板。 */
export function ValidatePanel({ data }: ValidatePanelProps) {
  if (!data) {
    return <p className="muted">无校验数据</p>;
  }

  const missing = data.validation?.missing_items ?? [];
  const warnings = data.warnings ?? [];

  return (
    <div className="etviz-panel-section">
      <div className="etviz-stat-row">
        <span className={`etviz-badge${data.ready ? " etviz-badge--ok" : " etviz-badge--warn"}`}>
          {data.ready ? "ready" : "未就绪"}
        </span>
        {data.timeline_id ? (
          <span className="muted mono">timeline: {data.timeline_id}</span>
        ) : null}
        {data.revision != null ? (
          <span className="muted">rev {data.revision}</span>
        ) : null}
      </div>
      {warnings.length > 0 ? (
        <>
          <h4>warnings</h4>
          <ul className="etviz-list">
            {warnings.map((w, i) => (
              <li key={`w-${i}`}>{w}</li>
            ))}
          </ul>
        </>
      ) : null}
      {missing.length > 0 ? (
        <>
          <h4>missing_items ({missing.length})</h4>
          <div className="etviz-table-wrap">
            <table className="etviz-table">
              <thead>
                <tr>
                  <th>category</th>
                  <th>clip_id</th>
                  <th>reason</th>
                  <th>upstream</th>
                </tr>
              </thead>
              <tbody>
                {missing.map((item, i) => (
                  <tr key={`m-${i}`}>
                    <td>{String(item.category ?? "—")}</td>
                    <td className="mono">{String(item.clip_id ?? "—")}</td>
                    <td>{String(item.reason ?? "—")}</td>
                    <td>{String(item.suggested_upstream ?? "—")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p className="muted">无 missing_items</p>
      )}
    </div>
  );
}
