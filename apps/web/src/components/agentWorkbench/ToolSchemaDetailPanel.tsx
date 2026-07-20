/**
 * 工具 Schema 详情侧栏：展示 action 元信息与入参/出参 JSON Schema。
 */

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { AgentToolOption } from "../../types/agentConfig";
import {
  flattenSchemaProperties,
  formatSchemaJson,
  type JsonSchemaObject,
} from "../../lib/toolSchemaView";

interface ToolSchemaDetailPanelProps {
  tool: AgentToolOption;
  onClose: () => void;
  translateScope: (scope: string) => string;
  translateOperation: (operation: string) => string;
}

/** 渲染 Schema 字段表格与原始 JSON。 */
function SchemaBlock({
  title,
  schema,
  emptyLabel,
}: {
  title: string;
  schema?: JsonSchemaObject;
  emptyLabel: string;
}) {
  const rows = useMemo(() => flattenSchemaProperties(schema), [schema]);
  const raw = useMemo(() => formatSchemaJson(schema), [schema]);

  return (
    <section className="aw-tool-schema-block">
      <header className="aw-tool-schema-head">
        <span className="aw-tool-schema-eyebrow">{title}</span>
        {rows.length > 0 && <span className="aw-tool-schema-count">{rows.length}</span>}
      </header>
      {rows.length > 0 ? (
        <div className="aw-tool-schema-table-wrap">
          <table className="aw-tool-schema-table">
            <thead>
              <tr>
                <th scope="col">field</th>
                <th scope="col">type</th>
                <th scope="col">req</th>
                <th scope="col">desc</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.name}>
                  <td>
                    <code>{row.name}</code>
                  </td>
                  <td>{row.type}</td>
                  <td>{row.required ? "✓" : ""}</td>
                  <td>{row.description || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="aw-tool-schema-empty">{emptyLabel}</p>
      )}
      {raw && (
        <details className="aw-tool-schema-raw">
          <summary>JSON</summary>
          <pre className="aw-tool-schema-pre">{raw}</pre>
        </details>
      )}
    </section>
  );
}

/** 工具入参/出参详情侧栏。 */
export function ToolSchemaDetailPanel({
  tool,
  onClose,
  translateScope,
  translateOperation,
}: ToolSchemaDetailPanelProps) {
  const { t } = useTranslation();

  return (
    <aside className="aw-tool-detail-panel" aria-labelledby="aw-tool-detail-title">
      <header className="aw-tool-detail-head">
        <div>
          <p className="aw-modal-eyebrow">{t("agent.workbench.toolDetailEyebrow", { ns: "settings" })}</p>
          <h3 id="aw-tool-detail-title" className="aw-tool-detail-title">
            {tool.action}
          </h3>
          {tool.agent && <p className="aw-tool-detail-agent">{tool.agent}</p>}
        </div>
        <button
          type="button"
          className="aw-btn-ghost aw-tool-detail-close"
          onClick={onClose}
          aria-label={t("agent.workbench.toolDetailClose", { ns: "settings" })}
        >
          ×
        </button>
      </header>

      <div className="aw-tool-detail-body">
        {tool.description && tool.description !== tool.name && (
          <p className="aw-tool-detail-desc">{tool.description}</p>
        )}

        <div className="aw-tool-detail-meta">
          <span className="aw-badge">{tool.kind}</span>
          {tool.read_only && <span className="aw-badge aw-tool-read">read_only</span>}
          {(tool.scopes ?? []).map((scope) => (
            <span key={scope} className="aw-badge aw-tool-scope">
              {translateScope(scope)}
            </span>
          ))}
          {(tool.operations ?? []).map((op) => (
            <span key={op} className="aw-badge aw-tool-operation">
              {translateOperation(op)}
            </span>
          ))}
        </div>

        {(tool.affected_data_read?.length ?? 0) > 0 && (
          <p className="aw-tool-detail-range">
            {t("agent.workbench.toolQueryRange", { ns: "settings" })}：
            {tool.affected_data_read?.join("、")}
          </p>
        )}
        {(tool.affected_data_write?.length ?? 0) > 0 && (
          <p className="aw-tool-detail-range aw-tool-detail-range-write">
            {t("agent.workbench.toolDetailWriteRange", { ns: "settings" })}：
            {tool.affected_data_write?.join("、")}
          </p>
        )}

        <SchemaBlock
          title={t("agent.workbench.toolInputSchema", { ns: "settings" })}
          schema={tool.input_schema}
          emptyLabel={t("agent.workbench.toolSchemaEmpty", { ns: "settings" })}
        />
        <SchemaBlock
          title={t("agent.workbench.toolOutputSchema", { ns: "settings" })}
          schema={tool.output_schema}
          emptyLabel={t("agent.workbench.toolSchemaEmpty", { ns: "settings" })}
        />
      </div>
    </aside>
  );
}
