/**
 * API 与 WebSocket 钩子：初始化项目/剧本、订阅实时事件、回传 A2UI 确认。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { A2UIConfirmationRequest, WsEvent } from "../types";

const API = "/api";
const SESSION_KEY = "svg_session";

interface SessionIds {
  projectId: string;
  scriptId: string;
}

function saveSession(ids: SessionIds) {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(ids));
  } catch {
    /* ignore */
  }
}

function loadSession(): SessionIds | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SessionIds;
    if (parsed.projectId && parsed.scriptId) return parsed;
  } catch {
    /* ignore */
  }
  return null;
}

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

async function createProjectAndScript(scriptTitle: string): Promise<SessionIds> {
  const pr = await fetch(`${API}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "我的视频项目" }),
  });
  if (!pr.ok) {
    throw new Error(`创建项目失败 (${pr.status})`);
  }
  const project = await pr.json();
  if (!project?.id) {
    throw new Error("创建项目失败：未返回项目 ID");
  }

  const sr = await fetch(`${API}/projects/${project.id}/scripts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: scriptTitle, duration_sec: 60 }),
  });
  if (!sr.ok) {
    throw new Error(`创建剧本失败 (${sr.status})`);
  }
  const script = await sr.json();
  if (!script?.id) {
    throw new Error("创建剧本失败：未返回剧本 ID");
  }

  const ids = { projectId: project.id, scriptId: script.id };
  saveSession(ids);
  return ids;
}

async function validateSession(ids: SessionIds): Promise<boolean> {
  const r = await fetch(
    `${API}/projects/${ids.projectId}/scripts/${ids.scriptId}`
  );
  return r.ok;
}

/** 自动创建或恢复项目与剧本 */
export function useProject(scriptTitle = "默认剧本") {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [scriptId, setScriptId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [initError, setInitError] = useState<string | null>(null);
  const initStarted = useRef(false);

  const bootstrap = useCallback(async () => {
    setInitError(null);
    setLoading(true);

    // 优先恢复会话（避免后端重启后仍用失效 ID）
    const cached = loadSession();
    if (cached && await validateSession(cached)) {
      setProjectId(cached.projectId);
      setScriptId(cached.scriptId);
      setLoading(false);
      return cached;
    }

    const ids = await createProjectAndScript(scriptTitle);
    setProjectId(ids.projectId);
    setScriptId(ids.scriptId);
    setLoading(false);
    return ids;
  }, [scriptTitle]);

  useEffect(() => {
    // 避免 React StrictMode 重复创建多个项目
    if (initStarted.current) return;
    initStarted.current = true;

    bootstrap().catch((e: Error) => {
      setInitError(e.message || "初始化失败");
      setLoading(false);
      initStarted.current = false;
    });
  }, [bootstrap]);

  return { projectId, scriptId, loading, initError, bootstrap };
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
