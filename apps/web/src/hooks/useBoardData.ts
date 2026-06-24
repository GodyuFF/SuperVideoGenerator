/** 看板数据 hook */

import { useCallback, useEffect, useState } from "react";
import type { BoardKind, BoardTabId, BoardView } from "../types/board";

const API = "/api";

export function useBoardData(
  projectId: string | null,
  scriptId: string | null,
  activeTab: BoardTabId
) {
  const [board, setBoard] = useState<BoardView | null>(null);
  const [kinds, setKinds] = useState<BoardKind[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/board/kinds`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setKinds)
      .catch(() => setKinds([]));
  }, []);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (scriptId) params.set("script_id", scriptId);
      const qs = params.toString();
      const r = await fetch(
        `${API}/projects/${projectId}/board/${activeTab}${qs ? `?${qs}` : ""}`
      );
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `加载看板失败 (${r.status})`);
      }
      setBoard(await r.json());
    } catch (err) {
      setError((err as Error).message);
      setBoard(null);
    } finally {
      setLoading(false);
    }
  }, [projectId, scriptId, activeTab]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { board, kinds, loading, error, refresh };
}
