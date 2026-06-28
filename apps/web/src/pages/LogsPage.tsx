/**
 * 交互日志查看页：查询持久化 LLM / HTTP / Agent 动作记录。
 */

import { useCallback, useEffect, useState } from "react";

const API = "/api";

const KIND_OPTIONS = [
  { value: "", label: "全部类型" },
  { value: "llm_request", label: "LLM 请求" },
  { value: "llm_response", label: "LLM 响应" },
  { value: "llm_error", label: "LLM 错误" },
  { value: "agent_action", label: "Agent 动作" },
  { value: "api_request", label: "HTTP 请求" },
];

interface InteractionRecord {
  id: string;
  created_at: string;
  kind: string;
  source: string;
  agent_name: string;
  summary: string;
  request_body?: Record<string, unknown> | null;
  response_body?: Record<string, unknown> | string | null;
  error?: string | null;
}

interface LogFileInfo {
  date: string;
  path: string;
  size_bytes: number;
}

interface LogsPageProps {
  scriptId: string | null;
  projectId?: string | null;
  onBack: () => void;
}

export function LogsPage({ scriptId, projectId, onBack }: LogsPageProps) {
  const [records, setRecords] = useState<InteractionRecord[]>([]);
  const [kindFilter, setKindFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [logDir, setLogDir] = useState<string>("data/logs/interactions/");
  const [logFiles, setLogFiles] = useState<LogFileInfo[]>([]);
  const [llmCallCount, setLlmCallCount] = useState(0);

  const loadFiles = useCallback(async () => {
    const r = await fetch(`${API}/interactions/files`);
    if (!r.ok) return;
    const data = await r.json();
    setLogDir(String(data.log_dir ?? "data/logs/interactions/"));
    setLogFiles((data.files as LogFileInfo[]) ?? []);
  }, []);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (scriptId) params.set("script_id", scriptId);
      if (projectId) params.set("project_id", projectId);
      if (kindFilter) params.set("kind", kindFilter);
      const r = await fetch(`${API}/interactions?${params}`);
      if (!r.ok) {
        setError(`加载失败（${r.statusText}）`);
        setRecords([]);
        return;
      }
      const data = await r.json();
      setRecords((data.records as InteractionRecord[]) ?? []);
      setLlmCallCount(Number(data.llm_call_count ?? 0));
    } catch {
      setError("网络错误，请确认后端已启动。");
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, [scriptId, kindFilter]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  function formatTime(ts: string) {
    if (!ts) return "-";
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  }

  function formatBody(body: Record<string, unknown> | string | null | undefined) {
    if (body == null) return null;

    // 如果是对象，直接美化
    if (typeof body === "object") {
      return JSON.stringify(body, null, 2);
    }

    // 如果是字符串，尝试解析为 JSON
    if (typeof body === "string") {
      const trimmed = body.trim();
      // 尝试解析 JSON
      if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || 
          (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
        try {
          const parsed = JSON.parse(trimmed);
          return JSON.stringify(parsed, null, 2);
        } catch {
          // 解析失败，返回原字符串（保持原样）
          return trimmed;
        }
      }
      return trimmed;
    }

    return String(body);
  }

  /** 检测是否为 Claude Code 风格的结构化 payload */
  function isClaudePayload(body: any): boolean {
    return body && typeof body === "object" && body.model && Array.isArray(body.messages);
  }

  /** 渲染 Claude 风格的结构化日志 */
  function renderClaudePayload(payload: any) {
    return (
      <div className="claude-payload">
        <div className="payload-header">
          <span className="model-badge">{payload.model}</span>
          {payload.tools?.length > 0 && (
            <span className="tools-badge">{payload.tools.length} tools</span>
          )}
        </div>

        {payload.tools?.length > 0 && (
          <details className="tools-section">
            <summary>Tools ({payload.tools.length})</summary>
            <ul>
              {payload.tools.map((t: any, i: number) => (
                <li key={i}>
                  <strong>{t.function?.name}</strong>: {t.function?.description}
                  <pre>{JSON.stringify(t.function?.parameters, null, 2)}</pre>
                </li>
              ))}
            </ul>
          </details>
        )}

        <details className="messages-section" open>
          <summary>Messages ({payload.messages?.length || 0})</summary>
          {payload.messages?.map((msg: any, idx: number) => (
            <div key={idx} className={`message-block role-${msg.role}`}>
              <div className="message-role">{msg.role}</div>
              {Array.isArray(msg.content) ? (
                msg.content.map((c: any, cIdx: number) => (
                  <div key={cIdx} className="content-block">
                    <span className="content-type">{c.type}</span>
                    <pre className="content-text">{c.text}</pre>
                    {c.cache_control && (
                      <span className="cache-badge">{c.cache_control.type}</span>
                    )}
                  </div>
                ))
              ) : (
                <pre className="content-text">{JSON.stringify(msg.content)}</pre>
              )}
            </div>
          ))}
        </details>
      </div>
    );
  }

  return (
    <div className="logs-page">
      <header className="top-bar">
        <h1>交互日志</h1>
        <span className="status-badge">
          LLM 调用：{llmCallCount}
        </span>
        {scriptId && (
          <span className="status-badge muted-badge">剧本 {scriptId}</span>
        )}
        <div className="top-bar-spacer" />
        <button type="button" className="btn-secondary" onClick={onBack}>
          返回对话
        </button>
      </header>

      <div className="logs-content">
        <section className="logs-hint">
          <p className="muted">
            本地 JSONL 日志目录：<code>{logDir}</code>
          </p>
          {logFiles.length > 0 && (
            <ul className="log-files-list">
              {logFiles.slice(0, 5).map((f) => (
                <li key={f.date}>
                  <code>{f.date}.jsonl</code>
                  <span className="muted">（{f.size_bytes} 字节）</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="logs-toolbar">
          <label>
            类型筛选
            <select
              value={kindFilter}
              onChange={(e) => setKindFilter(e.target.value)}
            >
              {KIND_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>
          <button type="button" onClick={loadRecords} disabled={loading}>
            {loading ? "加载中…" : "刷新"}
          </button>
        </div>

        {error && <p className="settings-alert error">{error}</p>}

        {records.length === 0 && !loading && !error && (
          <p className="muted">暂无交互记录。发送对话后 LLM 请求/响应将写入此处。</p>
        )}

        <ul className="logs-list">
          {records.map((rec) => {
            const expanded = expandedId === rec.id;
            const reqText = formatBody(rec.request_body);
            const resText = formatBody(rec.response_body);
            return (
              <li key={rec.id} className={`log-item kind-${rec.kind}`}>
                <button
                  type="button"
                  className="log-item-header"
                  onClick={() => setExpandedId(expanded ? null : rec.id)}
                >
                  <span className="log-time">{formatTime(rec.created_at)}</span>
                  <span className="log-kind">{rec.kind}</span>
                  {rec.agent_name && (
                    <span className="log-agent">{rec.agent_name}</span>
                  )}
                  <span className="log-summary">{rec.summary || "-"}</span>
                  <span className="log-expand">{expanded ? "▲" : "▼"}</span>
                </button>
                {expanded && (
                  <div className="log-item-body">
                    {rec.error && (
                      <pre className="log-pre log-error">{rec.error}</pre>
                    )}
                    {reqText && (
                      <div>
                        <strong>request_body</strong>
                        {isClaudePayload(rec.request_body) ? (
                          renderClaudePayload(rec.request_body)
                        ) : (
                          <pre className="log-pre">{reqText}</pre>
                        )}
                      </div>
                    )}
                    {resText && (
                      <div>
                        <strong>response_body</strong>
                        {isClaudePayload(rec.response_body) ? (
                          renderClaudePayload(rec.response_body)
                        ) : (
                          <pre className="log-pre">{resText}</pre>
                        )}
                      </div>
                    )}
                    {!reqText && !resText && !rec.error && (
                      <p className="muted">无 request/response body</p>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
