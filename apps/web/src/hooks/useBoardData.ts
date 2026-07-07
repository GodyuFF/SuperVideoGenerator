/** 看板数据 hook */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { BoardKind, BoardTabId, BoardView, ScriptBoardMeta } from "../types/board";
import type { WorkspaceMode } from "../lib/localProjects";

const API = "/api";

const PROJECT_TABS: BoardTabId[] = ["overview", "knowledge"];
const SCRIPT_TABS: BoardTabId[] = [
  "script_details",
  "script",
  "character",
  "scene",
  "prop",
  "storyboard",
  "edit",
  "media",
  "pipeline",
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

  const effectiveTab = useMemo(
    () => resolveBoardTab(workspaceMode, activeTab),
    [workspaceMode, activeTab]
  );

  useEffect(() => {
    fetch(`${API}/board/kinds`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setKinds)
      .catch(() => setKinds([]));
  }, []);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    if (workspaceMode === "script" && !scriptId) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (scriptId) params.set("script_id", scriptId);
      const qs = params.toString();
      const mainUrl = `${API}/projects/${projectId}/board/${effectiveTab}${qs ? `?${qs}` : ""}`;
      const metaUrl =
        workspaceMode === "script" &&
        scriptId &&
        effectiveTab !== "script_details"
          ? `${API}/projects/${projectId}/board/script_details?${params}`
          : null;

      const [mainRes, metaRes] = await Promise.all([
        fetch(mainUrl),
        metaUrl ? fetch(metaUrl) : Promise.resolve(null),
      ]);

      if (!mainRes.ok) {
        const body = await mainRes.json().catch(() => ({}));
        throw new Error(body.detail || `加载看板失败 (${mainRes.status})`);
      }
      const mainBoard = (await mainRes.json()) as BoardView;
      setBoard(mainBoard);

      if (workspaceMode === "script" && scriptId) {
        if (effectiveTab === "script_details") {
          setScriptMeta((mainBoard.stats ?? {}) as ScriptBoardMeta);
        } else if (metaRes) {
          if (metaRes.ok) {
            const metaBoard = (await metaRes.json()) as BoardView;
            setScriptMeta((metaBoard.stats ?? {}) as ScriptBoardMeta);
          }
        }
      } else {
        setScriptMeta(null);
      }
    } catch (err) {
      setError((err as Error).message);
      setBoard(null);
    } finally {
      setLoading(false);
    }
  }, [projectId, scriptId, effectiveTab, workspaceMode]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { board, scriptMeta, kinds, loading, error, refresh, effectiveTab };
}
