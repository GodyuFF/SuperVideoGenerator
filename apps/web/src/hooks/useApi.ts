/**
 * API 与 WebSocket 钩子：项目/剧本初始化、切换与本地记录。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { WsEvent } from "../types";
import {
  clearActiveSessionIfMatches,
  removeRecentProjectsByIds,
  saveRecentProject,
  saveWorkspaceSession,
  type WorkspaceMode,
} from "../lib/localProjects";

const API = "/api";

/** 解析 FastAPI 错误体 */
export function formatApiError(
  err: Record<string, unknown> | null,
  statusText: string
): string {
  if (!err) return statusText;
  const detail = err.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => String((d as { msg?: string }).msg ?? d)).join("; ");
  }
  if (typeof err.message === "string" && err.message.trim()) {
    return err.message;
  }
  return statusText;
}

async function createProjectOnly(title: string): Promise<{ projectId: string; projectTitle: string }> {
  const pr = await fetch(`${API}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!pr.ok) {
    const body = await pr.json().catch(() => ({}));
    throw new Error(formatApiError(body, `创建项目失败 (${pr.status})`));
  }
  const project = await pr.json();
  if (!project?.id) throw new Error("创建项目失败：未返回项目 ID");
  return {
    projectId: String(project.id),
    projectTitle: String(project.title ?? title),
  };
}

async function createProjectAndScript(
  projectTitle: string,
  scriptTitle: string
): Promise<{ projectId: string; scriptId: string; projectTitle: string; scriptTitle: string }> {
  const pr = await fetch(`${API}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: projectTitle }),
  });
  if (!pr.ok) throw new Error(`创建项目失败 (${pr.status})`);
  const project = await pr.json();
  if (!project?.id) throw new Error("创建项目失败：未返回项目 ID");

  const sr = await fetch(`${API}/projects/${project.id}/scripts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: scriptTitle, duration_sec: 60 }),
  });
  if (!sr.ok) throw new Error(`创建剧本失败 (${sr.status})`);
  const script = await sr.json();
  if (!script?.id) throw new Error("创建剧本失败：未返回剧本 ID");

  return {
    projectId: project.id,
    scriptId: script.id,
    projectTitle: project.title ?? projectTitle,
    scriptTitle: script.title ?? scriptTitle,
  };
}

async function validateProject(projectId: string): Promise<boolean> {
  const r = await fetch(`${API}/projects/${projectId}`);
  return r.ok;
}

async function validateScript(projectId: string, scriptId: string): Promise<boolean> {
  const r = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}`);
  return r.ok;
}

function persistScriptSession(
  projectId: string,
  scriptId: string,
  projectTitle = "我的视频项目",
  scriptTitle = "默认剧本"
) {
  saveWorkspaceSession(projectId, scriptId, "script");
  saveRecentProject({ projectId, projectTitle, scriptId, scriptTitle });
}

export interface ProjectListItem {
  id: string;
  title: string;
  created_at?: string;
  script_count?: number;
  scripts?: Array<{ id: string; title: string; status: string }>;
}

export async function fetchProjectList(): Promise<ProjectListItem[]> {
  const r = await fetch(`${API}/projects`);
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(formatApiError(body, `加载项目列表失败 (${r.status})`));
  }
  const data = await r.json();
  return Array.isArray(data) ? data : [];
}

export async function createProject(title: string) {
  return createProjectOnly(title);
}

export async function deleteProjectApi(projectId: string) {
  const r = await fetch(`${API}/projects/${projectId}`, { method: "DELETE" });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(formatApiError(body, `删除项目失败 (${r.status})`));
  }
  removeRecentProjectsByIds([projectId]);
  clearActiveSessionIfMatches([projectId]);
}

export async function deleteProjectsBatchApi(projectIds: string[]) {
  const r = await fetch(`${API}/projects/batch-delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_ids: projectIds }),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(formatApiError(body, `批量删除失败 (${r.status})`));
  }
  removeRecentProjectsByIds(projectIds);
  clearActiveSessionIfMatches(projectIds);
}

export async function deleteScriptApi(projectId: string, scriptId: string) {
  const r = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}`, {
    method: "DELETE",
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(formatApiError(body, `删除剧本失败 (${r.status})`));
  }
}

export interface UseProjectOptions {
  routeProjectId?: string | null;
  routeScriptId?: string | null;
  onInvalidRoute?: () => void;
}

/** 项目与剧本：路由驱动初始化、切换与删除 */
export function useProject(options: UseProjectOptions = {}) {
  const { routeProjectId, routeScriptId, onInvalidRoute } = options;
  const [projectId, setProjectId] = useState<string | null>(routeProjectId ?? null);
  const [scriptId, setScriptId] = useState<string | null>(routeScriptId ?? null);
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>(
    routeScriptId ? "script" : "project"
  );
  const [loading, setLoading] = useState(!!routeProjectId);
  const [initError, setInitError] = useState<string | null>(null);

  const applyProjectMode = useCallback((pid: string) => {
    setProjectId(pid);
    setScriptId(null);
    setWorkspaceMode("project");
    saveWorkspaceSession(pid, null, "project");
  }, []);

  const enterScript = useCallback(
    (
      pid: string,
      sid: string,
      meta?: { projectTitle?: string; scriptTitle?: string }
    ) => {
      setProjectId(pid);
      setScriptId(sid);
      setWorkspaceMode("script");
      persistScriptSession(pid, sid, meta?.projectTitle, meta?.scriptTitle);
    },
    []
  );

  const exitToProject = useCallback(
    (pid: string) => {
      applyProjectMode(pid);
    },
    [applyProjectMode]
  );

  const initFromRoute = useCallback(async () => {
    if (!routeProjectId) {
      setLoading(false);
      return;
    }
    setInitError(null);
    setLoading(true);
    try {
      if (!(await validateProject(routeProjectId))) {
        throw new Error("项目不存在或已被删除");
      }
      if (routeScriptId && (await validateScript(routeProjectId, routeScriptId))) {
        setProjectId(routeProjectId);
        setScriptId(routeScriptId);
        setWorkspaceMode("script");
        saveWorkspaceSession(routeProjectId, routeScriptId, "script");
      } else {
        applyProjectMode(routeProjectId);
      }
    } catch (e) {
      setInitError((e as Error).message);
      onInvalidRoute?.();
    } finally {
      setLoading(false);
    }
  }, [routeProjectId, routeScriptId, applyProjectMode, onInvalidRoute]);

  useEffect(() => {
    if (!routeProjectId) {
      setLoading(false);
      return;
    }
    void initFromRoute();
  }, [initFromRoute, routeProjectId, routeScriptId]);

  const createScriptInProject = useCallback(async (pid: string, title: string) => {
    const sr = await fetch(`${API}/projects/${pid}/scripts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, duration_sec: 60 }),
    });
    if (!sr.ok) {
      const body = await sr.json().catch(() => ({}));
      throw new Error(formatApiError(body, `创建剧本失败 (${sr.status})`));
    }
    const script = await sr.json();
    if (!script?.id) throw new Error("创建剧本失败：未返回剧本 ID");
    return String(script.id);
  }, []);

  const createNewProject = useCallback(async () => {
    setLoading(true);
    setInitError(null);
    try {
      const n = Date.now();
      const created = await createProjectAndScript(
        `视频项目 ${new Date(n).toLocaleDateString()}`,
        `剧本 ${n.toString().slice(-4)}`
      );
      applyProjectMode(created.projectId);
      return created.projectId;
    } catch (e) {
      setInitError((e as Error).message);
      throw e;
    } finally {
      setLoading(false);
    }
  }, [applyProjectMode]);

  return {
    projectId,
    scriptId,
    workspaceMode,
    loading,
    initError,
    bootstrap: initFromRoute,
    enterScript,
    exitToProject,
    createScriptInProject,
    createNewProject,
    deleteScript: deleteScriptApi,
  };
}

const WS_EVENT_RING_MAX = 200;

/** 连接 WebSocket，收集事件并处理 A2UI 确认回传 */
export function useWebSocket(
  projectId: string | null,
  scriptId: string | null,
  enabled = true
) {
  const [events, setEvents] = useState<WsEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const ackResolvers = useRef<
    Map<string, { resolve: (resolved: boolean) => void; reject: (err: Error) => void }>
  >(new Map());

  const sendConfirmation = useCallback(
    (
      confirmationId: string,
      approved: boolean,
      values: Record<string, unknown> = {}
    ): Promise<boolean> => {
      return new Promise((resolve, reject) => {
        if (wsRef.current?.readyState !== WebSocket.OPEN) {
          reject(new Error("WebSocket 未连接，无法提交"));
          return;
        }
        ackResolvers.current.set(confirmationId, { resolve, reject });
        wsRef.current.send(
          JSON.stringify({
            type: "a2ui_confirmation_response",
            confirmation_id: confirmationId,
            approved,
            values,
          })
        );
      });
    },
    []
  );

  useEffect(() => {
    if (!enabled || !projectId || !scriptId) {
      setEvents([]);
      return;
    }

    const ws = new WebSocket(
      `ws://${window.location.host}/ws/projects/${projectId}/scripts/${scriptId}`
    );
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data) as WsEvent;
      setEvents((prev) => {
        const next = [...prev, data];
        if (next.length <= WS_EVENT_RING_MAX) return next;
        return next.slice(next.length - WS_EVENT_RING_MAX);
      });

      if (data.type === "a2ui_confirmation_ack") {
        const confirmationId = String(data.confirmation_id ?? "");
        const pending = ackResolvers.current.get(confirmationId);
        if (pending) {
          ackResolvers.current.delete(confirmationId);
          pending.resolve(Boolean(data.resolved));
        }
      }
    };

    return () => {
      ackResolvers.current.forEach(({ reject }) =>
        reject(new Error("WebSocket 已断开"))
      );
      ackResolvers.current.clear();
      ws.close();
    };
  }, [enabled, projectId, scriptId]);

  return { events, sendConfirmation };
}
