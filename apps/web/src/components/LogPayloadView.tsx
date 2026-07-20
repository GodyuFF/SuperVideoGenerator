/**
 * 交互日志 payload 格式化展示：完整请求、消息分块、Token 与自动换行。
 */

import { useState, type ReactNode } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";

export interface TokenBreakdownItem {
  tokens?: number;
  pct_of_total?: number;
}

export interface TokenUsageMeta {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  estimated?: boolean;
  models?: {
    model?: string;
    total_tokens?: number;
    provider?: string;
    breakdown?: {
      system_tokens?: number;
      tools_tokens?: number;
      messages_tokens?: number;
    };
  }[];
  conversation_id?: string;
  system_tokens?: number;
  tools_tokens?: number;
  messages_tokens?: number;
  completion_budget_tokens?: number;
  total_estimated_tokens?: number;
  breakdown?: Record<string, TokenBreakdownItem>;
  finish_reason?: string;
  finish_reason_normalized?: string;
  truncated?: boolean;
  abort_reason?: string;
  actual_usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

export interface LogRecordFields {
  kind: string;
  provider?: string;
  model?: string;
  method?: string;
  url?: string;
  status_code?: number | null;
  duration_ms?: number | null;
  meta?: Record<string, unknown> | null;
  request_body?: Record<string, unknown> | string | null;
  response_body?: Record<string, unknown> | string | null;
  error?: string | null;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === "object" && !Array.isArray(v);
}

function isChatPayload(body: unknown): body is Record<string, unknown> & { messages: unknown[] } {
  return isRecord(body) && Array.isArray(body.messages);
}

export function formatJsonBody(body: unknown): string | null {
  if (body == null) return null;
  if (typeof body === "object") {
    return JSON.stringify(body, null, 2);
  }
  if (typeof body === "string") {
    const trimmed = body.trim();
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      try {
        return JSON.stringify(JSON.parse(trimmed), null, 2);
      } catch {
        return trimmed;
      }
    }
    return trimmed;
  }
  return String(body);
}

function formatMessageContent(content: unknown): string {
  if (content == null) return "";
  if (typeof content === "string") {
    const trimmed = content.trim();
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      try {
        return JSON.stringify(JSON.parse(trimmed), null, 2);
      } catch {
        return content;
      }
    }
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((part, i) => {
        if (isRecord(part) && typeof part.text === "string") {
          const type = part.type ? `[${String(part.type)}] ` : "";
          return `${type}${part.text}`;
        }
        return `块 ${i + 1}:\n${JSON.stringify(part, null, 2)}`;
      })
      .join("\n\n");
  }
  return JSON.stringify(content, null, 2);
}

function extractTokenUsage(meta: Record<string, unknown> | null | undefined): TokenUsageMeta | null {
  if (!meta) return null;
  const usage = meta.token_usage;
  if (!usage || typeof usage !== "object") return null;
  return usage as TokenUsageMeta;
}

function TokenBreakdownBar({ usage }: { usage: TokenUsageMeta }) {
  const items = usage.breakdown;
  if (!items || Object.keys(items).length === 0) return null;
  const labels: Record<string, string> = {
    system: "system",
    tools: "tools",
    messages: "messages",
    completion: "completion",
  };
  return (
    <div className="log-token-breakdown">
      {Object.entries(items).map(([key, item]) => (
        <div key={key} className="log-token-breakdown-row">
          <span className="log-token-breakdown-label">
            {labels[key] ?? key}
          </span>
          <span className="log-token-breakdown-bar-wrap">
            <span
              className={`log-token-breakdown-bar bar-${key}`}
              style={{ width: `${Math.min(100, item.pct_of_total ?? 0)}%` }}
            />
          </span>
          <span className="log-token-breakdown-pct">
            {item.tokens ?? 0} ({item.pct_of_total ?? 0}%)
          </span>
        </div>
      ))}
    </div>
  );
}

function FinishReasonBadge({ usage }: { usage: TokenUsageMeta }) {
  const reason = usage.finish_reason;
  if (!reason) return null;
  const truncated = usage.truncated === true;
  return (
    <div className="log-finish-reason">
      <span className={`log-meta-chip ${truncated ? "log-truncated" : ""}`}>
        finish: {reason}
        {usage.finish_reason_normalized &&
          usage.finish_reason_normalized !== reason &&
          ` → ${usage.finish_reason_normalized}`}
        {truncated && " · 截断"}
      </span>
      {usage.abort_reason && (
        <p className="log-abort-reason">{usage.abort_reason}</p>
      )}
    </div>
  );
}

function TokenUsageBar({ usage, label }: { usage: TokenUsageMeta; label?: string }) {
  const estimated = usage.estimated ? "（预估）" : "";
  const models = usage.models ?? [];
  return (
    <div className="log-token-bar">
      {label && <span className="log-token-label">{label}</span>}
      <span className="log-token-chip">
        prompt {usage.prompt_tokens ?? "-"}
      </span>
      <span className="log-token-chip">
        completion {usage.completion_tokens ?? "-"}
      </span>
      <span className="log-token-chip total">
        total {usage.total_tokens ?? "-"}{estimated}
      </span>
      <FinishReasonBadge usage={usage} />
      <TokenBreakdownBar usage={usage} />
      {models.length > 0 && (
        <details className="log-token-models">
          <summary>按模型</summary>
          <ul>
            {models.map((m, i) => (
              <li key={i}>
                {m.provider ? `${m.provider}/` : ""}
                {m.model ?? "?"}: {m.total_tokens ?? "-"} tokens
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function RequestParams({ payload }: { payload: Record<string, unknown> }) {
  const params: [string, unknown][] = [];
  for (const key of ["model", "temperature", "max_tokens", "stream", "response_format"]) {
    if (key in payload && payload[key] !== undefined) {
      params.push([key, payload[key]]);
    }
  }
  if (params.length === 0) return null;
  return (
    <dl className="log-params-dl">
      {params.map(([k, v]) => (
        <div key={k} className="log-params-row">
          <dt>{k}</dt>
          <dd>{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

function firstLine(text: string, maxLen: number = 200): string {
  const line = text.split("\n")[0].trim();
  if (!line) return "（空）";
  if (line.length <= maxLen) return line;
  return `${line.slice(0, maxLen)}…`;
}

function LogMessageItem({ role, text }: { role: string; text: string }) {
  const preview = firstLine(text, 100);
  return (
    <details className={`log-message log-message-collapsible role-${role}`}>
      <summary className="log-message-summary">
        <span className="log-message-role">{role}</span>
        <span className="log-message-preview">{preview}</span>
      </summary>
      <pre className="log-preformatted log-message-text">{text || "（空）"}</pre>
    </details>
  );
}

function ChatMessagesView({ messages }: { messages: unknown[] }) {
  return (
    <div className="log-messages">
      {messages.map((raw, idx) => {
        if (!isRecord(raw)) {
          return (
            <details key={idx} className="log-message log-message-collapsible">
              <summary className="log-message-summary">
                <span className="log-message-role">raw</span>
                <span className="log-message-preview">#{idx + 1}</span>
              </summary>
              <pre className="log-preformatted log-message-text">
                {JSON.stringify(raw, null, 2)}
              </pre>
            </details>
          );
        }
        const role = String(raw.role ?? "unknown");
        const text = formatMessageContent(raw.content);
        return <LogMessageItem key={idx} role={role} text={text} />;
      })}
    </div>
  );
}

function isStructuredLlmRequest(
  body: unknown,
): body is Record<string, unknown> & {
  system?: unknown;
  tools?: unknown[];
  messages?: unknown[];
} {
  return (
    isRecord(body) &&
    typeof body.system === "string" &&
    Array.isArray(body.messages)
  );
}

function CollapsibleLogSection({
  title,
  preview,
  children,
}: {
  title: string;
  preview?: string;
  children: ReactNode;
}) {
  return (
    <details className="log-collapsible-section">
      <summary className="log-collapsible-summary">
        <strong>{title}</strong>
        {preview && <span className="log-collapsible-preview">{preview}</span>}
      </summary>
      <div className="log-collapsible-body">{children}</div>
    </details>
  );
}

/** 渲染 tools 列表；每一项可单独折叠（默认收起）。 */
function ToolsView({ tools }: { tools: unknown[] }) {
  return (
    <div className="log-tools">
      {tools.map((raw, idx) => {
        if (!isRecord(raw)) {
          return (
            <details key={idx} className="log-tool-item log-tool-item-collapsible">
              <summary className="log-tool-header">
                <span className="log-tool-name">#{idx + 1}</span>
                <span className="log-meta-chip">raw</span>
              </summary>
              <div className="log-tool-body">
                <pre className="log-preformatted">
                  {JSON.stringify(raw, null, 2)}
                </pre>
              </div>
            </details>
          );
        }
        const fn = isRecord(raw.function) ? raw.function : undefined;
        const name = String(raw.name ?? fn?.name ?? "?");
        const kind = raw.kind ? String(raw.kind) : "function";
        const agentName = raw.agent_name ? String(raw.agent_name) : "";
        const schema = raw.input_schema ?? fn?.parameters;
        const hasBody =
          typeof raw.description === "string" || schema != null;
        return (
          <details key={idx} className="log-tool-item log-tool-item-collapsible">
            <summary className="log-tool-header">
              <span className="log-tool-name">{name}</span>
              <span className="log-meta-chip">{kind}</span>
              {agentName ? (
                <span className="log-meta-chip">agent: {agentName}</span>
              ) : null}
            </summary>
            {hasBody ? (
              <div className="log-tool-body">
                {typeof raw.description === "string" ? (
                  <p className="log-tool-desc">{raw.description}</p>
                ) : null}
                {schema != null ? (
                  <pre className="log-preformatted log-message-text">
                    {formatJsonBody(schema)}
                  </pre>
                ) : null}
              </div>
            ) : null}
          </details>
        );
      })}
    </div>
  );
}

function StructuredRequestView({ body }: { body: Record<string, unknown> }) {
  const tools = Array.isArray(body.tools) ? body.tools : [];
  const messages = Array.isArray(body.messages) ? body.messages : [];
  const systemText = String(body.system ?? "");
  return (
    <>
      <RequestParams payload={body} />
      <CollapsibleLogSection
        title="system"
        preview={`${systemText.length} 字符`}
      >
        <pre className="log-preformatted log-message-text">{systemText}</pre>
      </CollapsibleLogSection>
      {tools.length > 0 && (
        <CollapsibleLogSection
          title="tools"
          preview={`${tools.length} 项`}
        >
          <ToolsView tools={tools} />
        </CollapsibleLogSection>
      )}
      <CollapsibleLogSection
        title="messages"
        preview={`${messages.length} 条`}
      >
        <ChatMessagesView messages={messages} />
      </CollapsibleLogSection>
    </>
  );
}

function PayloadSection({
  title,
  body,
  defaultFormatted = true,
}: {
  title: string;
  body: unknown;
  defaultFormatted?: boolean;
}) {
  const { t } = useAppTranslation("common");
  const [showRaw, setShowRaw] = useState(false);
  const rawText = formatJsonBody(body);
  if (!rawText) return null;

  const structured = isStructuredLlmRequest(body);
  const chatRequest = !structured && isChatPayload(body);
  const formatted = structured || chatRequest;

  return (
    <section className="log-payload-section">
      <div className="log-payload-section-header">
        <strong>{title}</strong>
        {formatted && (
          <button
            type="button"
            className="btn-secondary btn-sm log-view-toggle"
            onClick={() => setShowRaw((v) => !v)}
          >
            {showRaw ? t("view.formatted") : t("view.rawJson")}
          </button>
        )}
      </div>
      {formatted && !showRaw ? (
        structured ? (
          <StructuredRequestView body={body} />
        ) : (
          <>
            <RequestParams payload={body} />
            <CollapsibleLogSection
              title="messages"
              preview={`${body.messages.length} 条`}
            >
              <ChatMessagesView messages={body.messages} />
            </CollapsibleLogSection>
          </>
        )
      ) : (
        <pre className="log-preformatted log-raw-json">{rawText}</pre>
      )}
    </section>
  );
}

function ResponseSection({ body }: { body: unknown }) {
  if (body == null) return null;
  if (typeof body === "string") {
    return (
      <section className="log-payload-section">
        <strong>response_body</strong>
        <pre className="log-preformatted log-message-text">{body}</pre>
      </section>
    );
  }
  if (isRecord(body) && typeof body.content === "string") {
    const content = body.content.trim();
    let display = content;
    if (
      (content.startsWith("{") && content.endsWith("}")) ||
      (content.startsWith("[") && content.endsWith("]"))
    ) {
      try {
        display = JSON.stringify(JSON.parse(content), null, 2);
      } catch {
        display = content;
      }
    }
    return (
      <section className="log-payload-section">
        <strong>response_body · content</strong>
        <pre className="log-preformatted log-message-text">{display}</pre>
        {Object.keys(body).length > 1 && (
          <details className="log-extra-raw">
            <summary>完整 response JSON</summary>
            <pre className="log-preformatted log-raw-json">
              {formatJsonBody(body)}
            </pre>
          </details>
        )}
      </section>
    );
  }
  return (
    <PayloadSection title="response_body" body={body} defaultFormatted={isChatPayload(body)} />
  );
}

export function LogRecordMeta({ rec }: { rec: LogRecordFields }) {
  const token = extractTokenUsage(rec.meta ?? undefined);
  const hasMeta =
    rec.provider ||
    rec.model ||
    rec.duration_ms != null ||
    rec.status_code != null ||
    rec.url ||
    token;

  if (!hasMeta) return null;

  return (
    <div className="log-record-meta">
      {rec.provider && (
        <span className="log-meta-chip">provider: {rec.provider}</span>
      )}
      {rec.model && <span className="log-meta-chip">model: {rec.model}</span>}
      {rec.status_code != null && (
        <span className="log-meta-chip">HTTP {rec.status_code}</span>
      )}
      {rec.duration_ms != null && (
        <span className="log-meta-chip">{rec.duration_ms.toFixed(0)} ms</span>
      )}
      {rec.method && rec.url && (
        <span className="log-meta-chip log-meta-url" title={rec.url}>
          {rec.method} {rec.url}
        </span>
      )}
      {token && <TokenUsageBar usage={token} />}
    </div>
  );
}

export function LogRecordBody({ rec }: { rec: LogRecordFields }) {
  if (rec.kind === "conversation_token_round") {
    const usage = extractTokenUsage(rec.meta ?? undefined);
    return (
      <div className="log-item-body">
        <LogRecordMeta rec={rec} />
        {usage && <TokenUsageBar usage={usage} label="本轮对话 Token" />}
        {rec.meta && (
          <pre className="log-preformatted log-raw-json">
            {formatJsonBody(rec.meta)}
          </pre>
        )}
      </div>
    );
  }

  return (
    <div className="log-item-body">
      <LogRecordMeta rec={rec} />
      {rec.error && <pre className="log-preformatted log-error">{rec.error}</pre>}
      <PayloadSection title="request_body" body={rec.request_body} />
      <ResponseSection body={rec.response_body} />
      {!rec.request_body && !rec.response_body && !rec.error && (
        <p className="muted">无 request/response body</p>
      )}
    </div>
  );
}

/** 列表行内简要 token 标签 */
export function LogTokenBadge({ meta }: { meta?: Record<string, unknown> | null }) {
  const usage = extractTokenUsage(meta ?? undefined);
  if (!usage?.total_tokens) return null;
  const suffix = usage.estimated ? "~" : "";
  return (
    <span className="log-token-inline">
      {suffix}
      {usage.total_tokens} tok
    </span>
  );
}
