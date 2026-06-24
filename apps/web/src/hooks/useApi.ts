/**
 * API 与 WebSocket 钩子：项目/剧本初始化、切换与本地记录。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { A2UIConfirmationRequest, WsEvent } from "../types";
import {
  loadActiveSession,
  saveActiveSession,
  saveRecentProject,
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

async function validateSession(projectId: string, scriptId: string): Promise<boolean> {
  const r = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}`);
  return r.ok;
}

function persistSession(
  projectId: string,
  scriptId: string,
  projectTitle = "我的视频项目",
  scriptTitle = "默认剧本"
) {
  saveActiveSession({ projectId, scriptId });
  saveRecentProject({ projectId, projectTitle, scriptId, scriptTitle });
}

/** 项目与剧本：恢复、新建、切换 */
export function useProject(scriptTitle = "默认剧本") {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [scriptId, setScriptId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [initError, setInitError] = useState<string | null>(null);
  const initStarted = useRef(false);

  const applySession = useCallback(
    (pid: string, sid: string, meta?: { projectTitle?: string; scriptTitle?: string }) => {
      setProjectId(pid);
      setScriptId(sid);
      persistSession(pid, sid, meta?.projectTitle, meta?.scriptTitle);
    },
    []
  );

  const bootstrap = useCallback(async () => {
    setInitError(null);
    setLoading(true);

    const cached = loadActiveSession();
    if (cached && (await validateSession(cached.projectId, cached.scriptId))) {
      applySession(cached.projectId, cached.scriptId);
      setLoading(false);
      return cached;
    }

    const created = await createProjectAndScript("我的视频项目", scriptTitle);
    applySession(created.projectId, created.scriptId, {
      projectTitle: created.projectTitle,
      scriptTitle: created.scriptTitle,
    });
    setLoading(false);
    return { projectId: created.projectId, scriptId: created.scriptId };
  }, [applySession, scriptTitle]);

  const switchProject = useCallback(
    (pid: string, sid: string) => {
      applySession(pid, sid);
    },
    [applySession]
  );

  const createNewProject = useCallback(async () => {
    setLoading(true);
    setInitError(null);
    try {
      const n = Date.now();
      const created = await createProjectAndScript(
        `视频项目 ${new Date(n).toLocaleDateString()}`,
        `剧本 ${n.toString().slice(-4)}`
      );
      applySession(created.projectId, created.scriptId, {
        projectTitle: created.projectTitle,
        scriptTitle: created.scriptTitle,
      });
    } catch (e) {
      setInitError((e as Error).message);
      throw e;
    } finally {
      setLoading(false);
    }
  }, [applySession]);

  useEffect(() => {
    if (initStarted.current) return;
    initStarted.current = true;
    bootstrap().catch((e: Error) => {
      setInitError(e.message || "初始化失败");
      setLoading(false);
      initStarted.current = false;
    });
  }, [bootstrap]);

  return {
    projectId,
    scriptId,
    loading,
    initError,
    bootstrap,
    switchProject,
    createNewProject,
  };
}

/** 连接 WebSocket，收集事件并处理 A2UI 确认弹窗 */
export function useWebSocket(projectId: string | null, scriptId: string | null) {
  const [events, setEvents] = useState<WsEvent[]>([]);
  const [pendingConfirmation, setPendingConfirmation] =
    useState<A2UIConfirmationRequest | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const sendConfirmation = useCallback(
    (confirmationId: string, approved: boolean, values: Record<string, unknown> = {}) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({
            type: "a2ui_confirmation_response",
            confirmation_id: confirmationId,
            approved,
            values,
          })
        );
      }
      setPendingConfirmation(null);
    },
    []
  );

  useEffect(() => {
    if (!projectId || !scriptId) return;

    const ws = new WebSocket(
      `ws://${window.location.host}/ws/projects/${projectId}/scripts/${scriptId}`
    );
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data) as WsEvent;
      setEvents((prev) => [...prev, data]);
      if (data.type === "a2ui_confirmation_required") {
        setPendingConfirmation(data as unknown as A2UIConfirmationRequest);
      }
    };

    return () => ws.close();
  }, [projectId, scriptId]);

  return { events, pendingConfirmation, sendConfirmation };
}
