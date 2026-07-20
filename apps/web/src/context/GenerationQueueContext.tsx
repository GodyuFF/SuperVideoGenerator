/**
 * 生成队列：Context + HTTP 拉取 + WebSocket 快照合并。
 * Dispatch 与 State 分离，避免 Workbench WS 路径订阅抽屉开关导致重渲染。
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { apiFetch } from "../lib/apiFetch";
import type { GenerationQueueSnapshot, WsEvent } from "../types";
import {
  getGenerationQueueCounts,
  parseGenerationQueueSnapshot,
  reduceGenerationQueueFromWs,
} from "../utils/generationQueueStatus";

const API = "/api";

/** 命令式 API：Workbench WebSocket 与作用域切换使用。 */
export interface GenerationQueueController {
  applyWsEvent: (event: WsEvent) => void;
  applySnapshot: (snapshot: GenerationQueueSnapshot) => void;
  setScope: (projectId: string | null, scriptId: string | null) => void;
  refresh: () => Promise<void>;
}

interface GenerationQueueStateValue {
  snapshot: GenerationQueueSnapshot | null;
  open: boolean;
  setOpen: (open: boolean) => void;
  refresh: () => Promise<void>;
  counts: GenerationQueueSnapshot["counts"];
}

const GenerationQueueDispatchContext =
  createContext<GenerationQueueController | null>(null);
const GenerationQueueStateContext =
  createContext<GenerationQueueStateValue | null>(null);

interface GenerationQueueProviderProps {
  children: ReactNode;
}

/** 提供生成队列快照与抽屉开关（抽屉 UI 由 Task 7 挂载）。 */
export function GenerationQueueProvider({ children }: GenerationQueueProviderProps) {
  const [snapshot, setSnapshot] = useState<GenerationQueueSnapshot | null>(null);
  const [open, setOpen] = useState(false);
  const projectIdRef = useRef<string | null>(null);
  const scriptIdRef = useRef<string | null>(null);

  /** 从 API 拉取当前剧本队列快照。 */
  const refresh = useCallback(async () => {
    const projectId = projectIdRef.current;
    const scriptId = scriptIdRef.current;
    if (!projectId || !scriptId) {
      setSnapshot(null);
      return;
    }
    try {
      const response = await apiFetch(
        `${API}/projects/${projectId}/scripts/${scriptId}/generation-queue`,
      );
      if (!response.ok) return;
      const data: unknown = await response.json();
      const parsed = parseGenerationQueueSnapshot(data);
      if (parsed) {
        setSnapshot(parsed);
      }
    } catch {
      /* 队列拉取失败不阻断工作台 */
    }
  }, []);

  /** 更新项目/剧本作用域；切换时先清空快照再 refresh，避免展示旧剧本队列。 */
  const setScope = useCallback(
    (projectId: string | null, scriptId: string | null) => {
      const scopeChanged =
        projectId !== projectIdRef.current || scriptId !== scriptIdRef.current;

      projectIdRef.current = projectId;
      scriptIdRef.current = scriptId;

      if (!projectId || !scriptId) {
        setSnapshot(null);
        return;
      }

      if (scopeChanged) {
        setSnapshot(null);
      }
      void refresh();
    },
    [refresh],
  );

  /** 直接应用已解析快照（HTTP 或 WS 共用）。 */
  const applySnapshot = useCallback((incoming: GenerationQueueSnapshot) => {
    const scriptId = scriptIdRef.current;
    if (scriptId && incoming.script_id !== scriptId) return;
    setSnapshot(incoming);
  }, []);

  /** 合并 WebSocket generation_queue_snapshot 事件。 */
  const applyWsEvent = useCallback((event: WsEvent) => {
    setSnapshot((prev) =>
      reduceGenerationQueueFromWs(
        prev,
        event as Record<string, unknown>,
        scriptIdRef.current,
      ),
    );
  }, []);

  const dispatch = useMemo(
    () => ({ applyWsEvent, applySnapshot, setScope, refresh }),
    [applyWsEvent, applySnapshot, setScope, refresh],
  );

  const counts = useMemo(() => getGenerationQueueCounts(snapshot), [snapshot]);

  const state = useMemo(
    () => ({
      snapshot,
      open,
      setOpen,
      refresh,
      counts,
    }),
    [snapshot, open, refresh, counts],
  );

  return (
    <GenerationQueueDispatchContext.Provider value={dispatch}>
      <GenerationQueueStateContext.Provider value={state}>
        {children}
      </GenerationQueueStateContext.Provider>
    </GenerationQueueDispatchContext.Provider>
  );
}

/** 命令式控制器：Workbench WS 使用，不订阅 snapshot。 */
export function useGenerationQueueController(): GenerationQueueController {
  const ctx = useContext(GenerationQueueDispatchContext);
  if (ctx) return ctx;
  return {
    applyWsEvent: () => {},
    applySnapshot: () => {},
    setScope: () => {},
    refresh: async () => {},
  };
}

/** 读取生成队列状态；抽屉与角标（Task 7）使用。 */
export function useGenerationQueue(): GenerationQueueStateValue {
  const ctx = useContext(GenerationQueueStateContext);
  if (ctx) return ctx;
  return {
    snapshot: null,
    open: false,
    setOpen: () => {},
    refresh: async () => {},
    counts: getGenerationQueueCounts(null),
  };
}
