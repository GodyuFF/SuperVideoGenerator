/** 看板数据 hook */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { BoardKind, BoardTabId, BoardView, ScriptBoardMeta } from "../types/board";
import type { WorkspaceMode } from "../lib/localProjects";
import { apiFetch } from "../lib/apiFetch";

const API = "/api";

const PROJECT_TABS: BoardTabId[] = ["overview", "knowledge"];
const SCRIPT_TABS: BoardTabId[] = [
  "script_details",
  "character",
  "scene",
  "prop",
  "frame",
  "video_clip",
  "storyboard",
  "edit",
  "media",
  "pipeline",
  "graph",
];

export function resolveBoardTab(
  workspaceMode: WorkspaceMode,
  activeTab: BoardTabId
): BoardTabId {
  if (workspaceMode === "project") {
    return PROJECT_TABS.includes(activeTab) ? activeTab : "overview";
  }
  if (activeTab === "overview" || activeTab === "knowledge") {
    return "script_details";
  }
  if (activeTab === "script") {
    return "script_details";
  }
  return SCRIPT_TABS.includes(activeTab) ? activeTab : "script_details";
}

export function useBoardData(
  projectId: string | null,
  scriptId: string | null,
  activeTab: BoardTabId,
  workspaceMode: WorkspaceMode
) {
  const [board, setBoard] = useState<BoardView | null>(null);
  const [scriptMeta, setScriptMeta] = useState<ScriptBoardMeta | null>(null);
  const [kinds, setKinds] = useState<BoardKind[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeqRef = useRef(0);

  const effectiveTab = useMemo(
    () => resolveBoardTab(workspaceMode, activeTab),
    [workspaceMode, activeTab]
  );

  /** 项目/剧本/Tab 切换时立即清空看板内容，避免展示上一剧本残留数据。 */
  useEffect(() => {
    requestSeqRef.current += 1;
    setBoard(null);
    setError(null);
    if (projectId && (workspaceMode !== "script" || scriptId)) {
      setLoading(true);
    }
  }, [projectId, scriptId, effectiveTab, workspaceMode]);

  /** 仅项目/剧本切换时清空 scriptMeta；Tab 切换须保留 meta 以维持二级 Tab 可见性。 */
  useEffect(() => {
    setScriptMeta(null);
  }, [projectId, scriptId, workspaceMode]);

  useEffect(() => {
    fetch(`${API}/board/kinds`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setKinds)
      .catch(() => setKinds([]));
  }, []);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    if (workspaceMode === "script" && !scriptId) return;
    const seq = ++requestSeqRef.current;
    const isStale = () => seq !== requestSeqRef.current;
    if (effectiveTab === "edit") {
      if (isStale()) return;
      setLoading(false);
      setError(null);
      setBoard({
        kind: "edit",
        title: "剪辑",
        description: "简易预览与专业剪辑入口",
        items: [],
        stats: {},
      });
      if (workspaceMode === "script" && scriptId) {
        const params = new URLSearchParams({ script_id: scriptId });
        const metaUrl = `${API}/projects/${projectId}/board/script_details?${params}`;
        try {
          const metaRes = await apiFetch(metaUrl);
          if (isStale()) return;
          if (metaRes.ok) {
            const metaBoard = (await metaRes.json()) as BoardView;
            setScriptMeta((metaBoard.stats ?? {}) as ScriptBoardMeta);
          }
        } catch {
          // meta 拉取失败不阻断剪辑 Tab
        }
      }
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (scriptId) params.set("script_id", scriptId);
      const qs = params.toString();
      const boardKind = effectiveTab === "graph" ? "project_graph" : effectiveTab;
      const mainUrl = `${API}/projects/${projectId}/board/${boardKind}${qs ? `?${qs}` : ""}`;
      const metaUrl =
        workspaceMode === "script" &&
        scriptId &&
        effectiveTab !== "script_details"
          ? `${API}/projects/${projectId}/board/script_details?${params}`
          : null;

      const [mainRes, metaRes] = await Promise.all([
        apiFetch(mainUrl),
        metaUrl ? apiFetch(metaUrl) : Promise.resolve(null),
      ]);

      if (isStale()) return;

      if (!mainRes.ok) {
        const body = await mainRes.json().catch(() => ({}));
        throw new Error(body.detail || `加载看板失败 (${mainRes.status})`);
      }
      const mainBoard = (await mainRes.json()) as BoardView;
      if (isStale()) return;
      setBoard(mainBoard);

      if (workspaceMode === "script" && scriptId) {
        if (effectiveTab === "script_details") {
          setScriptMeta((mainBoard.stats ?? {}) as ScriptBoardMeta);
        } else if (metaRes) {
          if (metaRes.ok) {
            const metaBoard = (await metaRes.json()) as BoardView;
            if (isStale()) return;
            setScriptMeta((metaBoard.stats ?? {}) as ScriptBoardMeta);
          }
        }
      } else {
        setScriptMeta(null);
      }
    } catch (err) {
      if (isStale()) return;
      setError((err as Error).message);
      setBoard(null);
    } finally {
      if (!isStale()) {
        setLoading(false);
      }
    }
  }, [projectId, scriptId, effectiveTab, workspaceMode]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { board, scriptMeta, kinds, loading, error, refresh, effectiveTab };
}
