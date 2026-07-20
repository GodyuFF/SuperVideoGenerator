/**
 * 资产生成中状态：Context + WS 合并，供看板卡片与二次生成按钮共享。
 * Dispatch 与 State 分离，避免 Workbench 订阅 map 导致整页重渲染。
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
import type { WsEvent } from "../types";
import type { BoardView } from "../types/board";
import {
  clearAssetGeneratingMany,
  emptyAssetGenerationMap,
  getAssetGenerationEntry,
  getFirstGeneratingEntry,
  getShotGenerationEntry,
  reduceAssetGenerationFromWs,
  setAssetGenerating,
  pruneAssetGenerationFromBoard,
  type AssetGenerationEntry,
  type AssetGenerationKind,
  type AssetGenerationMap,
} from "../utils/assetGenerationStatus";

interface MarkGeneratingOptions {
  targetId: string;
  kind: AssetGenerationKind;
  scriptId: string;
  label?: string;
  alsoTargetIds?: string[];
}

/** 命令式 API：不触发订阅方重渲染。 */
export interface AssetGenerationController {
  applyWsEvent: (event: WsEvent) => void;
  setScriptId: (id: string | null) => void;
  pruneFromBoard: (board: BoardView | null) => void;
}

interface AssetGenerationStateValue {
  scriptId: string | null;
  getEntry: (targetId: string | null | undefined) => AssetGenerationEntry | null;
  getEntryForTargets: (targetIds: Array<string | null | undefined>) => AssetGenerationEntry | null;
  getShotEntry: (shot: { id: string; asset_refs?: Record<string, string[]> }) => AssetGenerationEntry | null;
  markGenerating: (opts: MarkGeneratingOptions) => void;
  clearGenerating: (...targetIds: string[]) => void;
}

const AssetGenerationDispatchContext = createContext<AssetGenerationController | null>(null);
const AssetGenerationStateContext = createContext<AssetGenerationStateValue | null>(null);

interface AssetGenerationProviderProps {
  children: ReactNode;
  initialScriptId?: string | null;
}

/** 提供资产生成进度上下文。 */
export function AssetGenerationProvider({
  children,
  initialScriptId = null,
}: AssetGenerationProviderProps) {
  const [scriptId, setScriptIdState] = useState<string | null>(initialScriptId ?? null);
  const [map, setMap] = useState<AssetGenerationMap>(emptyAssetGenerationMap);
  const scriptIdRef = useRef(scriptId);
  scriptIdRef.current = scriptId;

  /** 合并 WebSocket 事件到生成状态表。 */
  const applyWsEvent = useCallback((event: WsEvent) => {
    setMap((prev) => reduceAssetGenerationFromWs(prev, event, scriptIdRef.current));
  }, []);

  const setScriptId = useCallback((id: string | null) => {
    setScriptIdState(id);
  }, []);

  /** 标记目标为生成中（二次生成按钮乐观更新）。 */
  const markGenerating = useCallback(
    ({ targetId, kind, scriptId: sid, label, alsoTargetIds }: MarkGeneratingOptions) => {
      setMap((prev) => {
        let next = setAssetGenerating(prev, {
          scriptId: sid,
          targetId,
          kind,
          label,
        });
        for (const extra of alsoTargetIds ?? []) {
          if (extra && extra !== targetId) {
            next = setAssetGenerating(next, {
              scriptId: sid,
              targetId: extra,
              kind,
              label,
            });
          }
        }
        return next;
      });
    },
    [],
  );

  /** 清除指定目标的生成状态。 */
  const clearGenerating = useCallback((...targetIds: string[]) => {
    setMap((prev) => clearAssetGeneratingMany(prev, targetIds));
  }, []);

  /** 看板数据落盘后同步清除过期的生成中标记。 */
  const pruneFromBoard = useCallback((board: BoardView | null) => {
    setMap((prev) => pruneAssetGenerationFromBoard(prev, scriptIdRef.current, board));
  }, []);

  const dispatch = useMemo(
    () => ({ applyWsEvent, setScriptId, pruneFromBoard }),
    [applyWsEvent, setScriptId, pruneFromBoard],
  );

  const state = useMemo(
    () => ({
      scriptId,
      markGenerating,
      clearGenerating,
      getEntry: (targetId: string | null | undefined) =>
        getAssetGenerationEntry(map, targetId, scriptId),
      getEntryForTargets: (targetIds: Array<string | null | undefined>) =>
        getFirstGeneratingEntry(map, targetIds, scriptId),
      getShotEntry: (shot: { id: string; asset_refs?: Record<string, string[]> }) =>
        getShotGenerationEntry(map, shot, scriptId),
    }),
    [scriptId, map, markGenerating, clearGenerating],
  );

  return (
    <AssetGenerationDispatchContext.Provider value={dispatch}>
      <AssetGenerationStateContext.Provider value={state}>
        {children}
      </AssetGenerationStateContext.Provider>
    </AssetGenerationDispatchContext.Provider>
  );
}

/** 命令式控制器：Workbench WS 路径使用，不订阅 map。 */
export function useAssetGenerationController(): AssetGenerationController {
  const ctx = useContext(AssetGenerationDispatchContext);
  if (ctx) return ctx;
  return {
    applyWsEvent: () => {},
    setScriptId: () => {},
    pruneFromBoard: () => {},
  };
}

/** 读取资产生成状态；看板卡片与二次生成按钮使用。 */
export function useAssetGeneration(): AssetGenerationStateValue & AssetGenerationController {
  const dispatch = useAssetGenerationController();
  const state = useContext(AssetGenerationStateContext);
  if (state) {
    return { ...dispatch, ...state };
  }
  return {
    ...dispatch,
    scriptId: null,
    markGenerating: () => {},
    clearGenerating: () => {},
    getEntry: () => null,
    getEntryForTargets: () => null,
    getShotEntry: () => null,
  };
}

/** 按 targetId 订阅单条生成状态，减少无关卡片重渲染。 */
export function useAssetGenerationEntry(
  targetId: string | null | undefined,
): AssetGenerationEntry | null {
  const { scriptId, getEntry } = useAssetGeneration();
  return getEntry(targetId);
}
