/**
 * 交互日志查看页：查询持久化 LLM / HTTP / Agent 动作记录。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  LogRecordBody,
  LogTokenBadge,
  type LogRecordFields,
} from "../components/LogPayloadView";
import { LocaleSwitcher } from "../i18n/LocaleSwitcher";
import { ThemeToggle } from "../components/theme/ThemeToggle";
import { AppTopBar } from "../components/layout/AppTopBar";

const API = "/api";

const KIND_VALUES = [
  "",
  "llm_request",
  "llm_response",
  "llm_error",
  "agent_action",
  "conversation_token_round",
  "api_request",
] as const;

interface InteractionRecord extends LogRecordFields {
  id: string;
  created_at: string;
  source: string;
  agent_name: string;
  summary: string;
  project_id?: string;
  script_id?: string;
}

interface LogFileInfo {
  project_id?: string;
  date: string;
  path: string;
  size_bytes: number;
}

interface LogsPageProps {
  scriptId: string | null;
  projectId?: string | null;
  onBack: () => void;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function LogsPage({ scriptId, projectId, onBack }: LogsPageProps) {
  const { t } = useTranslation();
  const [records, setRecords] = useState<InteractionRecord[]>([]);
  const [kindFilter, setKindFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [logDir, setLogDir] = useState<string>("data/logs/interactions/");
  const [logFiles, setLogFiles] = useState<LogFileInfo[]>([]);
  const [llmCallCount, setLlmCallCount] = useState(0);
  const [selectedDate, setSelectedDate] = useState("");
  const [deleteProjectId, setDeleteProjectId] = useState("");
  const [deleting, setDeleting] = useState(false);

  const effectiveProjectId = projectId ?? deleteProjectId;

  const projectOptions = useMemo(() => {
    const ids = new Set<string>();
    for (const f of logFiles) {
      const pid = (f.project_id ?? "").trim();
      if (pid && pid !== "_unknown") ids.add(pid);
    }
    if (projectId) ids.add(projectId);
    return [...ids].sort();
  }, [logFiles, projectId]);

  const scopeLabel = useMemo(() => {
    if (scriptId) return `剧本 ${scriptId}`;
    if (projectId) return `项目 ${projectId}`;
    return "全部项目";
  }, [projectId, scriptId]);

  const projectLogFiles = useMemo(() => {
    if (!projectId) return logFiles;
    return logFiles.filter(
      (f) => !f.project_id || f.project_id === projectId || f.project_id === "_unknown"
    );
  }, [logFiles, projectId]);

  const loadFiles = useCallback(async () => {
    const params = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    const r = await fetch(`${API}/interactions/files${params}`);
    if (!r.ok) return;
    const data = await r.json();
    setLogDir(String(data.log_dir ?? "data/logs/interactions/"));
    const files = (data.files as LogFileInfo[]) ?? [];
    setLogFiles(files);
    setSelectedDate((prev) => prev || (files[0]?.date ?? ""));
  }, [projectId]);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "200" });
      if (scriptId) params.set("script_id", scriptId);
      else if (projectId) params.set("project_id", projectId);
      if (kindFilter) params.set("kind", kindFilter);
      const r = await fetch(`${API}/interactions?${params}`);
      if (!r.ok) {
        setError(`加载失败（${r.statusText}）`);
        setRecords([]);
        return;
      }
      const data = await r.json();
      let rows = (data.records as InteractionRecord[]) ?? [];
      if (selectedDate) {
        rows = rows.filter((rec) => rec.created_at?.startsWith(selectedDate));
      }
      setRecords(rows);
      setLlmCallCount(Number(data.llm_call_count ?? 0));
    } catch {
      setError("网络错误，请确认后端已启动。");
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, [scriptId, projectId, kindFilter, selectedDate]);

  useEffect(() => {
    void loadFiles();
  }, [loadFiles]);

  useEffect(() => {
    void loadRecords();
  }, [loadRecords]);

  useEffect(() => {
    if (projectId) {
      setDeleteProjectId(projectId);
      return;
    }
    if (!deleteProjectId && projectOptions.length > 0) {
      setDeleteProjectId(projectOptions[0]);
    }
  }, [projectId, projectOptions, deleteProjectId]);

  async function handleDeleteLogs() {
    if (!effectiveProjectId || !selectedDate) {
      setError("请先选择项目和日期后再删除。");
      return;
    }
    const scope = scriptId
      ? `项目 ${effectiveProjectId} · 剧本 ${scriptId} · ${selectedDate}`
      : `项目 ${effectiveProjectId} · ${selectedDate}`;
    if (
      !window.confirm(
        `确定删除 ${scope} 的交互日志？\n将同时清理 SQLite 与 JSONL 文件，且不可恢复。`
      )
    ) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        project_id: effectiveProjectId,
        date: selectedDate,
      });
      if (scriptId) params.set("script_id", scriptId);
      const r = await fetch(`${API}/interactions?${params}`, { method: "DELETE" });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        const detail =
          typeof body.detail === "string"
            ? body.detail
            : `删除失败（${r.statusText}）`;
        setError(detail);
        return;
      }
      setExpandedId(null);
      await loadFiles();
      await loadRecords();
    } catch {
      setError("删除失败：网络错误，请确认后端已启动。");
    } finally {
      setDeleting(false);
    }
  }

  function formatTime(ts: string) {
    if (!ts) return "-";
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  }

  const backLabel = projectId
    ? scriptId
      ? t("backToScript", { ns: "nav" })
      : t("backToProject", { ns: "nav" })
    : t("backHome", { ns: "nav" });

  /** 将日志类型值映射为 i18n 键名。 */
  function kindLabel(value: string): string {
    const key = value || "all";
    return t(`logs.kinds.${key}`, { ns: "settings" });
  }

  return (
    <div className="logs-page">
      <AppTopBar
        title={t("logs.title", { ns: "settings" })}
        center={
          <>
            <span className="status-badge">LLM 调用：{llmCallCount}</span>
            <span className="status-badge muted-badge">{scopeLabel}</span>
          </>
        }
        trail={
          <>
            <ThemeToggle />
            <LocaleSwitcher />
            <button type="button" className="btn-secondary" onClick={onBack}>
              {backLabel}
            </button>
          </>
        }
      />

      <div className="logs-content">
        <section className="logs-hint">
          <p className="muted">
            JSONL 落盘目录：<code>{logDir}</code>
            {projectId ? (
              <>
                {" "}
                · 当前项目子目录 <code>{projectId}/</code>
              </>
            ) : null}
          </p>
          <p className="muted logs-scope-note">
            默认展示当前{scriptId ? "剧本" : projectId ? "项目" : ""}的交互记录；新建项目不会清空历史日志。
          </p>
          {projectLogFiles.length > 0 && (
            <ul className="log-files-list">
              {projectLogFiles.map((f) => (
                <li key={`${f.project_id ?? ""}-${f.date}`}>
                  <button
                    type="button"
                    className={
                      selectedDate === f.date
                        ? "log-file-btn active"
                        : "log-file-btn"
                    }
                    onClick={() => setSelectedDate(f.date)}
                  >
                    <code>
                      {f.project_id ? `${f.project_id}/` : ""}
                      {f.date}.jsonl
                    </code>
                    <span className="muted">（{formatBytes(f.size_bytes)}）</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="logs-toolbar">
          {!projectId && projectOptions.length > 0 && (
            <label>
              {t("logs.projectLabel", { ns: "settings" })}
              <select
                value={deleteProjectId}
                onChange={(e) => setDeleteProjectId(e.target.value)}
              >
                {projectOptions.map((pid) => (
                  <option key={pid} value={pid}>
                    {pid}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            {t("logs.dateLabel", { ns: "settings" })}
            <select
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
            >
              <option value="">{t("logs.allDates", { ns: "settings" })}</option>
              {projectLogFiles.map((f) => (
                <option key={`${f.project_id ?? ""}-${f.date}`} value={f.date}>
                  {f.date}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("logs.kindFilter", { ns: "settings" })}
            <select
              value={kindFilter}
              onChange={(e) => setKindFilter(e.target.value)}
            >
              {KIND_VALUES.map((value) => (
                <option key={value || "all"} value={value}>
                  {kindLabel(value)}
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={loadRecords} disabled={loading}>
            {loading
              ? t("actions.loading", { ns: "common" })
              : t("logs.loadRecords", { ns: "settings" })}
          </button>
          <button
            type="button"
            className="btn-danger btn-sm"
            disabled={deleting || !effectiveProjectId || !selectedDate}
            onClick={() => void handleDeleteLogs()}
          >
            {deleting
              ? t("actions.deleting", { ns: "common" })
              : t("logs.deleteSelected", { ns: "settings" })}
          </button>
          <span className="muted logs-count">共 {records.length} 条</span>
        </div>

        {error && <p className="settings-alert error">{error}</p>}

        {records.length === 0 && !loading && !error && (
          <p className="muted">
            暂无交互记录。发送对话后 LLM 请求/响应将写入 SQLite 与项目 JSONL 文件。
          </p>
        )}

        <ul className="logs-list">
          {records.map((rec) => {
            const expanded = expandedId === rec.id;
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
                  {rec.model && (
                    <span className="log-model">{rec.model}</span>
                  )}
                  <LogTokenBadge meta={rec.meta} />
                  <span className="log-summary">{rec.summary || "-"}</span>
                  <span className="log-expand">{expanded ? "▲" : "▼"}</span>
                </button>
                {expanded && <LogRecordBody rec={rec} />}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
