/**
 * 工作台：对话 + 剧本资产（主页）。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChatPanel } from "../components/ChatPanel";
import { SkillPicker } from "../components/SkillPicker";
import { PlanPanel } from "../components/PlanPanel";
import { BoardPanel } from "../components/board/BoardPanel";
import { ProjectSwitcher } from "../components/ProjectSwitcher";
import {
  IMAGE_STYLE_HINT_OPTIONS,
  MASTER_AGENT_NAME,
  TARGET_DURATION_HINT_OPTIONS,
  buildStyleHintsPayload,
  coerceStyleMode,
  styleModeLabel,
  type StyleHints,
  type StyleMode,
} from "../constants";
import { useStyleModes } from "../hooks/useAgentConfig";
import { useBoardData } from "../hooks/useBoardData";
import { formatApiError, useProject, useWebSocket } from "../hooks/useApi";
import {
  getLastConversationId,
  setLastConversationId,
} from "../lib/localProjects";
import { logPerf, logPerfBetween, logPerfMark, perfMeasure } from "../lib/perfLog";
import type { BoardTabId } from "../types/board";
import type { ChatMessage } from "../types/chat";
import type { AiConfig, PlanDocument, WsEvent } from "../types";
import { createDebouncedAsyncTask } from "../lib/asyncRefresh";
import { apiFetch } from "../lib/apiFetch";
import {
  AssetGenerationProvider,
  useAssetGenerationController,
} from "../context/AssetGenerationContext";
import {
  GenerationQueueProvider,
  useGenerationQueueController,
} from "../context/GenerationQueueContext";
import { useChatStore } from "../stores/chatStore";
import { usePlanStore } from "../stores/planStore";
import { useWorkbenchWs } from "../hooks/useWorkbenchWs";
import type { ConversationSummary } from "../types/conversation";
import {
  isTimelineResponse,
  timelineToChatMessages,
  dedupeChatMessages,
  earliestCreatedAtFromTimeline,
  reassignChatRounds,
} from "../utils/conversationTimeline";
import {
  applySkillSelection,
  filterSkills,
  getSkillPickerQuery,
  parseSkillCommand,
  type SkillOption,
} from "../utils/skillCommand";
import { AppTopBar } from "../components/layout/AppTopBar";
import { AppNavTrail } from "../components/layout/AppNavTrail";

const API = "/api";

/** 生图完成后需刷新的看板 Tab（按 kind 增量刷新，避免无关 Tab 重绘）。 */
const IMAGE_BOARD_TABS: BoardTabId[] = [
  "character",
  "scene",
  "prop",
  "frame",
  "video_clip",
  "storyboard",
  "media",
];

type ExecutionMode = "interactive" | "goal";

interface SkillMeta extends SkillOption {}

interface ScriptMeta {
  style_mode?: string;
  style_locked?: boolean;
  style_hints?: StyleHints;
  status?: string;
  title?: string;
  content_md?: string;
}

interface WorkbenchProps {
  routeProjectId: string;
  routeScriptId?: string | null;
  aiConfig: AiConfig | null;
  llmLoading: boolean;
  needsAiConfig: boolean;
  onOpenSettings: () => void;
  onOpenAgents: () => void;
  onOpenLogs: () => void;
  onBackHome: () => void;
  onNavigateToProject: (projectId: string, scriptId?: string | null) => void;
}

export function Workbench(props: WorkbenchProps) {
  return (
    <AssetGenerationProvider>
      <GenerationQueueProvider>
        <WorkbenchPage {...props} />
      </GenerationQueueProvider>
    </AssetGenerationProvider>
  );
}

function WorkbenchPage({
  routeProjectId,
  routeScriptId = null,
  aiConfig,
  llmLoading,
  needsAiConfig,
  onOpenSettings,
  onOpenAgents,
  onOpenLogs,
  onBackHome,
  onNavigateToProject,
}: WorkbenchProps) {
  const { t } = useTranslation();
  const assetGenerationController = useAssetGenerationController();
  const generationQueueController = useGenerationQueueController();
  const {
    projectId,
    scriptId,
    workspaceMode,
    loading,
    initError,
    bootstrap,
    enterScript,
    exitToProject,
    createScriptInProject,
    createNewProject,
    deleteScript,
  } = useProject({
    routeProjectId,
    routeScriptId,
    onInvalidRoute: onBackHome,
  });

  useEffect(() => {
    logPerfMark("workbench", "Workbench 挂载", "workbench-mount");
  }, []);
  const isScriptMode = workspaceMode === "script" && !!scriptId;
  const showReactDetails = aiConfig?.llm.show_react_details ?? true;
  const [boardTab, setBoardTab] = useState<BoardTabId>("overview");
  const isEditTab = isScriptMode && boardTab === "edit";
  const [activeScriptTitle, setActiveScriptTitle] = useState("");
  const { board, scriptMeta, loading: boardLoading, error: boardError, refresh: refreshBoard } =
    useBoardData(projectId, scriptId, boardTab, workspaceMode);
  const wsEventHandlerRef = useRef<((event: WsEvent) => void) | null>(null);
  const { sendConfirmation } = useWebSocket(
    projectId,
    scriptId,
    isScriptMode,
    wsEventHandlerRef
  );
  const messages = useChatStore((s) => s.messages);
  const setMessages = useChatStore((s) => s.setMessages);
  const appendMessage = useChatStore((s) => s.appendMessage);
  const resetChatMessages = useChatStore((s) => s.resetMessages);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [conversationList, setConversationList] = useState<ConversationSummary[]>([]);
  const [input, setInput] = useState("");
  const [skillPickerIndex, setSkillPickerIndex] = useState(0);
  const chatInputRef = useRef<HTMLInputElement>(null);
  const chatAbortRef = useRef<AbortController | null>(null);
  const planView = usePlanStore((s) => s.planView);
  const resetPlanView = usePlanStore((s) => s.resetPlanView);
  const loadPlanFromStore = usePlanStore((s) => s.loadPlanFromApi);
  const [scriptStatus, setScriptStatus] = useState("draft");
  const [styleMode, setStyleMode] = useState<StyleMode>("storybook");
  const [styleLocked, setStyleLocked] = useState(false);
  const [styleHints, setStyleHints] = useState<StyleHints>({});
  const { modes: styleModeOptions } = useStyleModes();
  const styleLabelMap = useMemo(
    () => Object.fromEntries(styleModeOptions.map((m) => [m.id, m.label])),
    [styleModeOptions],
  );

  useEffect(() => {
    if (styleLocked) return;
    setStyleMode((current) => coerceStyleMode(current, styleModeOptions));
  }, [styleModeOptions, styleLocked]);
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("interactive");
  const [skills, setSkills] = useState<SkillMeta[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isAborting, setIsAborting] = useState(false);
  const [loadingEarlierMessages, setLoadingEarlierMessages] = useState(false);
  const [hasMoreMessages, setHasMoreMessages] = useState(false);
  const earliestMessageAtRef = useRef<string | null>(null);
  const abortSlowTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const activeConversationIdRef = useRef(activeConversationId);
  activeConversationIdRef.current = activeConversationId;
  const streamMessageIds = useRef<Map<string, string>>(new Map());
  const chatRoundRef = useRef(0);
  const stepMasterIteration = useRef<Map<string, number>>(new Map());
  const stepMasterRound = useRef<Map<string, number>>(new Map());
  const conversationHydratedRef = useRef(false);
  const pendingWsEventsRef = useRef<WsEvent[]>([]);
  const wsChatReplayRef = useRef(false);
  const handleWsEventRef = useRef<(e: WsEvent) => void>(() => {});

  const awaitingConfirmation = useMemo(
    () =>
      messages.some(
        (m) => m.kind === "a2ui_confirmation" && m.status === "pending"
      ),
    [messages]
  );

  const inputBlocked = isRunning || awaitingConfirmation;
  const manualEditEnabled =
    isScriptMode &&
    !isRunning &&
    !awaitingConfirmation &&
    scriptStatus !== "executing";

  const skillPickerQuery = useMemo(
    () => (inputBlocked ? null : getSkillPickerQuery(input)),
    [input, inputBlocked]
  );
  const filteredSkills = useMemo(
    () =>
      skillPickerQuery === null ? [] : filterSkills(skills, skillPickerQuery),
    [skills, skillPickerQuery]
  );
  const skillPickerOpen =
    skillPickerQuery !== null && skills.length > 0 && !inputBlocked;

  useEffect(() => {
    setSkillPickerIndex(0);
  }, [skillPickerQuery, filteredSkills.length]);

  const selectSkill = useCallback((skill: SkillOption) => {
    setInput(applySkillSelection(skill.id));
    setSkillPickerIndex(0);
    requestAnimationFrame(() => chatInputRef.current?.focus());
  }, []);

  const appendSystemMessage = useCallback(
    (text: string) => {
      appendMessage({
        kind: "system",
        id: `sys-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        text,
      });
    },
    [appendMessage]
  );

  const clearAborting = useCallback(() => {
    if (abortSlowTimerRef.current) {
      clearTimeout(abortSlowTimerRef.current);
      abortSlowTimerRef.current = null;
    }
    setIsAborting(false);
  }, []);

  const beginAborting = useCallback(() => {
    setIsAborting(true);
    if (abortSlowTimerRef.current) {
      clearTimeout(abortSlowTimerRef.current);
    }
    abortSlowTimerRef.current = setTimeout(() => {
      appendSystemMessage(
        "中止仍在进行中，当前步骤可能在收尾；若长时间无响应可刷新页面或重启 API 服务。"
      );
      abortSlowTimerRef.current = null;
    }, 30_000);
  }, [appendSystemMessage]);

  const loadConversations = useCallback(async (): Promise<ConversationSummary[]> => {
    if (!projectId) return [];
    const q = scriptId ? `?script_id=${encodeURIComponent(scriptId)}` : "";
    const r = await apiFetch(`${API}/projects/${projectId}/conversations${q}`);
    if (!r.ok) return [];
    const items = (await r.json()) as ConversationSummary[];
    setConversationList(items);
    return items;
  }, [projectId, scriptId]);

  const loadConversationMessages = useCallback(
    async (conversationId: string, loadSeq?: number) => {
      if (!projectId) return;
      conversationHydratedRef.current = false;
      pendingWsEventsRef.current = [];
      const seq = loadSeq ?? ++conversationLoadSeqRef.current;
      const isStale = () => seq !== conversationLoadSeqRef.current;
      const msgStart = performance.now();
      const r = await fetch(
        `${API}/projects/${projectId}/conversations/${conversationId}/messages?view=full&limit=80`
      );
      logPerf("workbench", "loadConversationMessages", {
        duration_ms: Math.round(performance.now() - msgStart),
        project_id: projectId,
        script_id: scriptId,
        conversation_id: conversationId,
        view: "full",
        status: r.status,
      });
      if (isStale()) return;
      if (!r.ok) {
        if (!isStale()) {
          conversationHydratedRef.current = true;
        }
        return;
      }
      const data = await r.json();
      if (isTimelineResponse(data)) {
        const timeline = data.timeline;
        const mapped = reassignChatRounds(timelineToChatMessages(timeline));
        setMessages(mapped);
        setHasMoreMessages(Boolean(data.has_more));
        earliestMessageAtRef.current =
          (data.oldest_created_at ? String(data.oldest_created_at) : null) ??
          earliestCreatedAtFromTimeline(timeline);
        chatRoundRef.current = mapped.filter((item) => item.kind === "user").length;
      } else {
        const records = data as { role: string; content: string }[];
        setMessages(
          dedupeChatMessages(
            records.map((m, i) =>
              m.role === "user"
                ? { kind: "user" as const, id: `hist-user-${i}`, text: String(m.content) }
                : {
                    kind: "assistant" as const,
                    id: `hist-master-${i}`,
                    text: String(m.content),
                  }
            )
          )
        );
      }
      if (isStale()) return;
      setActiveConversationId(conversationId);
      if (scriptId) {
        setLastConversationId(projectId, scriptId, conversationId);
      }
      streamMessageIds.current.clear();
      stepMasterIteration.current.clear();
      stepMasterRound.current.clear();
      conversationHydratedRef.current = true;
      const pending = pendingWsEventsRef.current.splice(0);
      wsChatReplayRef.current = true;
      for (const ev of pending) {
        handleWsEventRef.current(ev);
      }
      wsChatReplayRef.current = false;
      logPerfMark("workbench", "对话加载完成", "workbench-ready");
      logPerfBetween(
        "workbench",
        "工作台首屏就绪",
        "workbench-mount",
        "workbench-ready",
        {
          project_id: projectId,
          script_id: scriptId,
          conversation_id: conversationId,
        },
      );
    },
    [projectId, scriptId, setMessages]
  );

  const loadEarlierMessages = useCallback(async () => {
    if (!projectId || !activeConversationId || loadingEarlierMessages) return;
    const beforeRaw = earliestMessageAtRef.current;
    if (!beforeRaw) return;
    setLoadingEarlierMessages(true);
    try {
      const before = encodeURIComponent(beforeRaw);
      const r = await fetch(
        `${API}/projects/${projectId}/conversations/${activeConversationId}/messages?view=full&limit=80&before=${before}`,
      );
      if (!r.ok) return;
      const data = await r.json();
      if (!isTimelineResponse(data)) return;
      const older = timelineToChatMessages(data.timeline);
      setHasMoreMessages(Boolean(data.has_more));
      const nextCursor =
        (data.oldest_created_at ? String(data.oldest_created_at) : null) ??
        earliestCreatedAtFromTimeline(data.timeline);
      // 游标必须前进：否则同一 before 反复请求，表现为「点击无效」
      if (nextCursor && nextCursor < beforeRaw) {
        earliestMessageAtRef.current = nextCursor;
      } else {
        setHasMoreMessages(false);
      }
      setMessages((prev) => {
        const merged = reassignChatRounds(dedupeChatMessages([...older, ...prev]));
        chatRoundRef.current = merged.filter((m) => m.kind === "user").length;
        return merged;
      });
    } finally {
      setLoadingEarlierMessages(false);
    }
  }, [projectId, activeConversationId, loadingEarlierMessages, setMessages]);

  const startNewConversation = useCallback(async () => {
    if (!projectId || !scriptId) return;
    const r = await fetch(
      `${API}/projects/${projectId}/scripts/${scriptId}/conversations`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "新对话" }),
      }
    );
    if (!r.ok) return;
    const data = (await r.json()) as { conversation_id: string };
    setActiveConversationId(data.conversation_id);
    resetChatMessages();
    chatRoundRef.current = 0;
    conversationHydratedRef.current = true;
    pendingWsEventsRef.current = [];
    stepMasterIteration.current.clear();
    stepMasterRound.current.clear();
    await loadConversations();
  }, [projectId, scriptId, loadConversations]);

  const loadProjectConfig = useCallback(async () => {
    if (!projectId) return;
    const r = await fetch(`${API}/projects/${projectId}`);
    if (!r.ok) return;
    const project = (await r.json()) as {
      config?: { generation?: { execution_mode?: ExecutionMode } };
    };
    const mode = project.config?.generation?.execution_mode;
    if (mode === "goal" || mode === "interactive") {
      setExecutionMode(mode);
    }
  }, [projectId]);

  const loadSkills = useCallback(async () => {
    const r = await fetch(`${API}/skills`);
    if (!r.ok) return;
    const list = (await r.json()) as SkillMeta[];
    setSkills(Array.isArray(list) ? list : []);
  }, []);

  const handleExecutionModeChange = useCallback(
    async (mode: ExecutionMode) => {
      setExecutionMode(mode);
      if (!projectId) return;
      await fetch(`${API}/projects/${projectId}/config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ execution_mode: mode }),
      });
    },
    [projectId]
  );

  const loadScriptMeta = useCallback(async () => {
    if (!projectId || !scriptId) return;
    const r = await apiFetch(`${API}/projects/${projectId}/scripts/${scriptId}`);
    if (!r.ok) return;
    const script = (await r.json()) as ScriptMeta;
    if (script.title) setActiveScriptTitle(script.title);
    if (script.status) setScriptStatus(script.status);
    if (script.style_mode) {
      setStyleMode(coerceStyleMode(script.style_mode, styleModeOptions));
    }
    setStyleHints(script.style_hints ?? {});
    setStyleLocked(Boolean(script.style_locked));
  }, [projectId, scriptId, styleModeOptions]);

  /** 看板 scriptMeta 刷新时同步顶栏标题，始终以 Script.title 为准。 */
  useEffect(() => {
    if (scriptMeta?.title) {
      setActiveScriptTitle(scriptMeta.title);
    }
  }, [scriptMeta?.title]);

  const loadPlan = useCallback(async () => {
    if (!projectId || !scriptId) return;
    const r = await apiFetch(`${API}/projects/${projectId}/scripts/${scriptId}/plan`);
    if (!r.ok) return;
    const plan = (await r.json()) as PlanDocument;
    loadPlanFromStore(plan);
  }, [projectId, scriptId, loadPlanFromStore]);

  /** 刷新剧本元数据与 Plan；看板由 useBoardData 独立加载，默认不重复拉 board。 */
  const refreshWorkspace = useCallback(
    async (options?: { includeBoard?: boolean }) => {
      const includeBoard = options?.includeBoard ?? false;
      if (workspaceMode === "script" && scriptId) {
        await Promise.all([loadScriptMeta(), loadPlan()]);
      }
      if (includeBoard) {
        await refreshBoard();
      }
    },
    [workspaceMode, scriptId, loadScriptMeta, loadPlan, refreshBoard],
  );

  /** 稳定引用，避免 BoardPanel memo 因内联回调失效。 */
  const handleBoardRefresh = useCallback(() => {
    void refreshWorkspace({ includeBoard: true });
  }, [refreshWorkspace]);

  const refreshBoardRef = useRef(refreshBoard);
  refreshBoardRef.current = refreshBoard;
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;
  const scriptIdRef = useRef(scriptId);
  scriptIdRef.current = scriptId;
  const boardTabRef = useRef(boardTab);
  boardTabRef.current = boardTab;

  useEffect(() => {
    assetGenerationController.setScriptId(scriptId ?? null);
  }, [scriptId, assetGenerationController.setScriptId]);

  useEffect(() => {
    generationQueueController.setScope(projectId ?? null, scriptId ?? null);
  }, [projectId, scriptId, generationQueueController.setScope]);

  useEffect(() => {
    if (!board || !scriptId) return;
    assetGenerationController.pruneFromBoard(board);
  }, [board, scriptId, assetGenerationController.pruneFromBoard]);

  const handleRefreshError = useCallback(
    (err: unknown) => {
      const message =
        err instanceof Error ? err.message : "工作区刷新失败，请稍后重试。";
      appendSystemMessage(message);
    },
    [appendSystemMessage]
  );

  const debouncedRefreshWorkspace = useRef(
    createDebouncedAsyncTask(
      async () => {
        await refreshWorkspaceRef.current({ includeBoard: false });
      },
      400,
      { onError: handleRefreshError }
    )
  ).current;
  const debouncedRefreshWorkspaceFull = useRef(
    createDebouncedAsyncTask(
      async () => {
        await refreshWorkspaceRef.current({ includeBoard: true });
      },
      400,
      { onError: handleRefreshError }
    )
  ).current;
  const debouncedRefreshBoard = useRef(
    createDebouncedAsyncTask(
      async () => {
        await refreshBoardRef.current();
      },
      400,
      { onError: handleRefreshError }
    )
  ).current;

  /** 当前看板 Tab 与资产/分镜相关时调度看板刷新。 */
  const scheduleBoardRefreshIfRelevant = useCallback(() => {
    const tab = boardTabRef.current;
    if (IMAGE_BOARD_TABS.includes(tab) || tab === "storyboard") {
      debouncedRefreshBoard.schedule();
    }
  }, [debouncedRefreshBoard]);

  const debouncedAssetsChanged = useRef(
    createDebouncedAsyncTask(
      async () => {
        const tab = boardTabRef.current;
        if (IMAGE_BOARD_TABS.includes(tab) || tab === "storyboard") {
          await refreshBoardRef.current();
        }
        const pid = projectIdRef.current;
        const sid = scriptIdRef.current;
        if (pid && sid && boardTabRef.current === "edit") {
          const { reloadFromApi } = await import("../editor/agentBridge");
          await reloadFromApi(pid, sid);
        }
      },
      400,
      { onError: handleRefreshError }
    )
  ).current;

  const prevScriptIdRef = useRef<string | null>(null);
  const conversationLoadSeqRef = useRef(0);
  const loadConversationsRef = useRef(loadConversations);
  loadConversationsRef.current = loadConversations;
  const loadConversationMessagesRef = useRef(loadConversationMessages);
  loadConversationMessagesRef.current = loadConversationMessages;
  const refreshWorkspaceRef = useRef(refreshWorkspace);
  refreshWorkspaceRef.current = refreshWorkspace;

  const { handleWsEvent, flushPlanThrottle, disposePlanThrottle } = useWorkbenchWs({
    showReactDetails,
    activeConversationId,
    assetGeneration: assetGenerationController,
    generationQueue: generationQueueController,
    boardTabRef,
    chatRoundRef,
    stepMasterIteration,
    stepMasterRound,
    streamMessageIds,
    conversationHydratedRef,
    pendingWsEventsRef,
    wsChatReplayRef,
    debouncedRefreshWorkspace,
    debouncedRefreshWorkspaceFull,
    debouncedRefreshBoard,
    debouncedAssetsChanged,
    scheduleBoardRefreshIfRelevant,
    appendSystemMessage,
    beginAborting,
    clearAborting,
    setScriptStatus,
    setIsRunning,
    setStyleMode,
    setStyleHints,
    setStyleLocked,
    chatAbortRef,
  });

  useEffect(() => () => disposePlanThrottle(), [disposePlanThrottle]);

  wsEventHandlerRef.current = handleWsEvent;
  handleWsEventRef.current = handleWsEvent;

  useEffect(() => {
    if (!projectId || !scriptId || workspaceMode !== "script") return;
    let cancelled = false;
    void (async () => {
      try {
        const r = await apiFetch(
          `${API}/projects/${projectId}/scripts/${scriptId}/executions/active`
        );
        if (!r.ok || cancelled) return;
        const data = (await r.json()) as {
          active?: boolean;
          conversation_id?: string | null;
        };
        if (data.active) {
          setIsRunning(true);
          if (data.conversation_id) {
            setActiveConversationId(String(data.conversation_id));
          }
        }
      } catch {
        /* 恢复执行态失败不阻断页面 */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, scriptId, workspaceMode]);

  useEffect(() => {
    void loadSkills();
  }, [loadSkills]);

  useEffect(() => {
    if (projectId) {
      void loadProjectConfig();
    }
  }, [projectId, loadProjectConfig]);

  useEffect(() => {
    if (workspaceMode === "project") {
      setBoardTab((tab) =>
        tab === "overview" || tab === "knowledge" ? tab : "overview"
      );
    } else {
      setBoardTab((tab) =>
        tab === "overview" || tab === "knowledge" ? "script_details" : tab
      );
    }
  }, [workspaceMode]);

  useEffect(() => {
    if (!(projectId && workspaceMode === "script" && scriptId)) return;

    const scriptChanged = prevScriptIdRef.current !== scriptId;
    prevScriptIdRef.current = scriptId;

    if (scriptChanged) {
      flushPlanThrottle();
      conversationLoadSeqRef.current += 1;
      conversationHydratedRef.current = false;
      pendingWsEventsRef.current = [];
      resetPlanView();
      resetChatMessages();
      setActiveConversationId(null);
      chatRoundRef.current = 0;
      stepMasterIteration.current.clear();
      stepMasterRound.current.clear();
    }

    let cancelled = false;
    const loadSeq = ++conversationLoadSeqRef.current;

    void (async () => {
      const [, items] = await Promise.all([
        perfMeasure(
          "workbench",
          "refreshWorkspace",
          () => refreshWorkspaceRef.current({ includeBoard: false }),
          { project_id: projectId, script_id: scriptId },
        ),
        perfMeasure(
          "workbench",
          "loadConversations",
          () => loadConversationsRef.current(),
          { project_id: projectId, script_id: scriptId },
        ),
      ]);
      if (cancelled || loadSeq !== conversationLoadSeqRef.current) return;

      if (items.length === 0) {
        if (scriptChanged) {
          resetChatMessages();
          setActiveConversationId(null);
        }
        conversationHydratedRef.current = true;
        pendingWsEventsRef.current = [];
        logPerfMark("workbench", "工作台就绪（无对话）", "workbench-ready");
        logPerfBetween(
          "workbench",
          "工作台首屏就绪（无对话）",
          "workbench-mount",
          "workbench-ready",
          { project_id: projectId, script_id: scriptId },
        );
        return;
      }

      const storedId = getLastConversationId(projectId, scriptId);
      const preferred =
        activeConversationIdRef.current ?? storedId ?? items[0].id;
      const targetId = items.some((c) => c.id === preferred)
        ? preferred
        : items[0].id;

      const skipReload =
        !scriptChanged &&
        messagesRef.current.length > 0 &&
        activeConversationIdRef.current === targetId;
      if (skipReload) return;

      await loadConversationMessagesRef.current(targetId, loadSeq);
    })();

    return () => {
      cancelled = true;
    };
  }, [projectId, scriptId, workspaceMode]);

  const handleEnterScript = useCallback(
    (sid: string) => {
      if (!projectId) return;
      if (sid === scriptId && workspaceMode === "script") return;
      enterScript(projectId, sid);
      onNavigateToProject(projectId, sid);
      setBoardTab("script_details");
    },
    [projectId, scriptId, workspaceMode, enterScript, onNavigateToProject]
  );

  const handleBackToOverview = useCallback(() => {
    if (!projectId) return;
    exitToProject(projectId);
    onNavigateToProject(projectId, null);
    setBoardTab("overview");
    resetChatMessages();
    setActiveConversationId(null);
    chatRoundRef.current = 0;
    conversationHydratedRef.current = false;
    pendingWsEventsRef.current = [];
    stepMasterIteration.current.clear();
    stepMasterRound.current.clear();
    resetPlanView();
    setIsRunning(false);
    setActiveScriptTitle("");
  }, [projectId, exitToProject, onNavigateToProject]);

  const handleCreateScript = useCallback(
    async (title: string) => {
      if (!projectId) return;
      const sid = await createScriptInProject(projectId, title);
      handleEnterScript(sid);
    },
    [projectId, createScriptInProject, handleEnterScript]
  );

  const handleDeleteScript = useCallback(
    async (sid: string) => {
      if (!projectId) return;
      if (
        !window.confirm("确定删除该剧本？将删除对应目录、资产与对话数据，且不可恢复。")
      ) {
        return;
      }
      await deleteScript(projectId, sid);
      if (scriptId === sid) {
        handleBackToOverview();
      }
      refreshBoard();
    },
    [projectId, scriptId, deleteScript, handleBackToOverview, refreshBoard]
  );

  function promptConfigureAi() {
    appendSystemMessage("请先配置 AI 模型与 API Key 后再开始对话。");
    onOpenSettings();
  }

  async function abortExecution() {
    // 允许中止：isRunning 或 scriptStatus === "executing"（生图中断但 isRunning 仍为 true）
    const isActive = isRunning || scriptStatus === "executing";
    if (!projectId || !scriptId || !isActive || isAborting) return;
    chatAbortRef.current?.abort();
    try {
      const r = await fetch(
        `${API}/projects/${projectId}/scripts/${scriptId}/chat/abort`,
        { method: "POST" }
      );
      if (!r.ok && r.status !== 409) {
        const err = (await r.json().catch(() => null)) as Record<string, unknown> | null;
        appendSystemMessage(`中止失败（${formatApiError(err, r.statusText)}）`);
        // 即使 API 返回错误，也允许本地恢复状态
        setIsRunning(false);
        setScriptStatus("draft");
      } else if (r.status === 409) {
        setIsRunning(false);
        setScriptStatus("draft");
        clearAborting();
        appendSystemMessage("当前没有正在执行的主编排。");
      } else {
        beginAborting();
        appendSystemMessage("正在中止执行…");
      }
    } catch {
      // 网络错误时允许本地恢复
      setIsRunning(false);
      setScriptStatus("draft");
      clearAborting();
      appendSystemMessage("中止请求失败，已恢复对话状态。");
    }
  }

  async function sendChat() {
    const text = input.trim();
    if (!text || inputBlocked) return;

    if (needsAiConfig) {
      promptConfigureAi();
      return;
    }

    let pid = projectId;
    let sid = scriptId;
    if (!pid || !sid) {
      appendSystemMessage("请先从整体看板进入某个剧本后再开始对话。");
      return;
    }

    const parsed = parseSkillCommand(text);

    chatRoundRef.current += 1;
    appendMessage({
      kind: "user",
      id: `user-${Date.now()}`,
      text,
      ...(parsed.skillId ? { skillId: parsed.skillId } : {}),
    });
    setInput("");
    setIsRunning(true);
    streamMessageIds.current.clear();
    stepMasterIteration.current.clear();
    stepMasterRound.current.clear();

    const postChat = async (p: string, s: string, convId: string | null) => {
      const controller = new AbortController();
      chatAbortRef.current = controller;
      return fetch(`${API}/projects/${p}/scripts/${s}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          message: text,
          ...(convId ? { conversation_id: convId } : {}),
          ...(styleLocked
            ? {}
            : {
                style_mode: styleMode,
                ...(buildStyleHintsPayload(styleHints)
                  ? { style_hints: buildStyleHintsPayload(styleHints) }
                  : {}),
              }),
          execution_mode: executionMode,
          ...(parsed.skillId ? { skill_id: parsed.skillId } : {}),
        }),
      });
    };

    try {
      let convId = activeConversationId;
      if (!convId) {
        const cr = await fetch(
          `${API}/projects/${pid}/scripts/${sid}/conversations`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: text.slice(0, 48) }),
          }
        );
        if (cr.ok) {
          const created = (await cr.json()) as { conversation_id: string };
          convId = created.conversation_id;
          setActiveConversationId(convId);
          setLastConversationId(pid, sid, convId);
        }
      }

      const r = await postChat(pid, sid, convId);

      if (r.status === 202) {
        const data = (await r.json()) as { conversation_id?: string };
        if (data.conversation_id) {
          const acceptedConvId = String(data.conversation_id);
          setActiveConversationId(acceptedConvId);
          setLastConversationId(pid, sid, acceptedConvId);
        }
        void loadConversations();
        return;
      }

      if (r.status === 404) {
        appendSystemMessage(
          "剧本或项目不存在（后端可能已重启）。请点击页面刷新或重新初始化后再发送。"
        );
        setIsRunning(false);
        return;
      }

      if (!r.ok) {
        const err = (await r.json().catch(() => null)) as Record<string, unknown> | null;
        appendSystemMessage(`执行失败（${formatApiError(err, r.statusText)}）`);
        setIsRunning(false);
        return;
      }
      const data = await r.json();
      if (data.conversation_id) {
        const convIdFromResponse = String(data.conversation_id);
        setActiveConversationId(convIdFromResponse);
        setLastConversationId(pid, sid, convIdFromResponse);
      }
      if (data.script?.status) setScriptStatus(data.script.status);
      if (data.script?.style_locked) setStyleLocked(true);
      if (data.script?.style_mode) {
        setStyleMode(coerceStyleMode(data.script.style_mode, styleModeOptions));
      }
      if (data.script?.style_hints && Object.keys(data.script.style_hints).length > 0) {
        setStyleHints(data.script.style_hints as StyleHints);
      }
      if (data.plan) {
        loadPlanFromStore(data.plan as PlanDocument);
      }
      const convIdToReload =
        data.conversation_id != null
          ? String(data.conversation_id)
          : convId;
      if (convIdToReload) {
        const wsBuiltRound =
          messagesRef.current.length > 0 &&
          !messagesRef.current.some(
            (msg) =>
              (msg.kind === "assistant" && msg.streaming) ||
              (msg.kind === "react_turn" && msg.thoughtStreaming)
          );
        if (!wsBuiltRound) {
          await loadConversationMessages(convIdToReload);
        }
      } else if (data.summary) {
        const summaryText = String(data.summary);
        setMessages((m) => {
          if (
            m.some(
              (msg) =>
                msg.kind === "assistant" && msg.text.trim() === summaryText.trim()
            )
          ) {
            return m;
          }
          return [
            ...m,
            {
              kind: "assistant" as const,
              id: `summary-api-${Date.now()}`,
              text: summaryText,
            },
          ];
        });
      }
      void loadConversations();
      setIsRunning(false);
      chatAbortRef.current = null;
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setIsRunning(false);
        chatAbortRef.current = null;
        return;
      }
      appendSystemMessage("网络错误，请确认后端已启动（端口 8000）。");
      setIsRunning(false);
      chatAbortRef.current = null;
    }
  }

  if (loading) return <div className="loading">{t("actions.loading", { ns: "common" })}</div>;

  if (initError) {
    return (
      <div className="loading">
        <p>初始化失败：{initError}</p>
        <p className="muted">请先启动后端：<code>uvicorn apps.api.main:app --port 8000</code></p>
        <button type="button" onClick={() => bootstrap()}>{t("actions.retry", { ns: "common" })}</button>
      </div>
    );
  }

  const aiBadgeClass = needsAiConfig ? "ai-missing" : "ai-ready";
  const aiBadgeText = llmLoading
    ? "AI 检查中…"
    : needsAiConfig
      ? "未配置 AI"
      : aiConfig?.llm.llm_active
        ? `AI: ${aiConfig.llm.provider_label}`
        : "规则模式";

  return (
    <div className={`workbench ${isScriptMode ? "workbench--script" : "workbench--project"}`}>
      <AppTopBar
        lead={
          <button type="button" className="btn-secondary btn-sm board-back-link" onClick={onBackHome}>
            {t("backToProjectList", { ns: "nav" })}
          </button>
        }
        center={
          <>
            <span className={`status-badge ${aiBadgeClass}`}>{aiBadgeText}</span>
            {isScriptMode && (
              <>
                <span className="status-badge">{scriptStatus}</span>
                {activeScriptTitle && (
                  <span className="status-badge muted-badge">{activeScriptTitle}</span>
                )}
                {styleLocked && (
                  <span className="status-badge style-locked">
                    风格：{styleModeLabel(styleMode, styleLabelMap)}（已锁定）
                  </span>
                )}
                {styleLocked && styleHints.image_style && (
                  <span className="status-badge muted-badge">
                    图片风格：{styleHints.image_style}
                  </span>
                )}
                {styleLocked && styleHints.target_duration && (
                  <span className="status-badge muted-badge">
                    预计时长：{styleHints.target_duration}
                  </span>
                )}
                {awaitingConfirmation && (
                  <span className="status-badge awaiting">等待您确认剧本结构…</span>
                )}
                {(isRunning || isAborting) && !awaitingConfirmation && (
                  <>
                    <span className="status-badge running">
                      {isAborting
                        ? `${MASTER_AGENT_NAME} 中止中…`
                        : `${MASTER_AGENT_NAME} 执行中…`}
                    </span>
                    <button
                      type="button"
                      className="btn-secondary btn-sm plan-abort-btn"
                      onClick={() => void abortExecution()}
                      disabled={isAborting}
                    >
                      {isAborting
                        ? t("actions.aborting", { ns: "common" })
                        : t("abortExecution", { ns: "nav" })}
                    </button>
                  </>
                )}
              </>
            )}
            <ProjectSwitcher
              projectId={projectId}
              scriptId={scriptId}
              onSwitchProject={(pid) => {
                chatAbortRef.current?.abort();
                onNavigateToProject(pid, null);
                exitToProject(pid);
                setBoardTab("overview");
                resetChatMessages();
                setActiveConversationId(null);
                resetPlanView();
                setIsRunning(false);
                setActiveScriptTitle("");
              }}
              onEnterScript={(pid, sid, meta) => {
                if (pid === projectId && sid === scriptId && workspaceMode === "script") {
                  return;
                }
                chatAbortRef.current?.abort();
                enterScript(pid, sid, meta);
                onNavigateToProject(pid, sid);
                setBoardTab("script_details");
              }}
              onCreateNew={async () => {
                const pid = await createNewProject();
                if (pid) onNavigateToProject(pid);
              }}
              disabled={inputBlocked}
            />
          </>
        }
        trail={
          <AppNavTrail
            onOpenAgents={onOpenAgents}
            onOpenLogs={onOpenLogs}
            onOpenSettings={onOpenSettings}
          />
        }
      />

      {needsAiConfig && !llmLoading && (
        <div className="ai-config-banner">
          <p>
            尚未配置 AI 模型与 API Key，无法使用 ReAct 智能编排。
            请填写 API Key 后点击<strong>「保存配置」</strong>或<strong>「保存并返回对话」</strong>。
          </p>
          <button type="button" onClick={onOpenSettings}>{t("configureAi", { ns: "nav" })}</button>
        </div>
      )}

      {llmLoading && (
        <div className="ai-config-banner loading-banner">
          <p>正在检查 AI 配置…</p>
        </div>
      )}

      <div className="main-split">
        {isScriptMode && (
        <aside className="chat-panel">
          <h2>{isEditTab ? t("editAssistant", { ns: "editor" }) : t("chatPanel", { ns: "editor" })}</h2>
          <div className="conversation-toolbar">
            <button
              type="button"
              className="btn-secondary"
              disabled={inputBlocked || !projectId || !scriptId}
              onClick={() => void startNewConversation()}
            >
              {t("newConversation", { ns: "nav" })}
            </button>
          </div>
          {conversationList.length > 0 && (
            <ul className="conversation-list">
              {conversationList.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    className={
                      c.id === activeConversationId
                        ? "conversation-item active"
                        : "conversation-item"
                    }
                    disabled={inputBlocked}
                    onClick={() => void loadConversationMessages(c.id)}
                  >
                    <span className="conversation-title">{c.title || "新对话"}</span>
                    {c.last_summary && (
                      <span className="conversation-summary muted">{c.last_summary}</span>
                    )}
                    {c.last_round_token_usage?.total_tokens ? (
                      <span className="conversation-summary muted">
                        本轮约 {c.last_round_token_usage.total_tokens} tokens
                      </span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="muted chat-hint">
            首次发送将绑定视频风格并生成剧本；风格锁定后不可更改。
            {skills.length > 0 && (
              <> 输入 <code>/</code> 可选择 Skill，或 <code>/skillId 你的需求</code>（如 /thriller）。</>
            )}
          </p>
          <div className="config-bar">
            <label className="goal-mode-toggle">
              <input
                type="checkbox"
                checked={executionMode === "goal"}
                disabled={inputBlocked}
                onChange={(e) =>
                  void handleExecutionModeChange(e.target.checked ? "goal" : "interactive")
                }
              />
              目标模式（AI 自主执行，不弹出确认）
            </label>
            <label>
              视频风格
              {styleLocked ? (
                <span className="locked-style">{styleModeLabel(styleMode, styleLabelMap)}（已锁定）</span>
              ) : (
                <select
                  value={styleMode}
                  disabled={inputBlocked}
                  onChange={(e) => setStyleMode(e.target.value)}
                >
                  {(styleModeOptions.length > 0
                    ? styleModeOptions
                    : [
                        { id: "storybook", label: "故事书模式" },
                        { id: "ai_video", label: "AI 视频模式" },
                      ]
                  ).map((opt) => (
                    <option key={opt.id} value={opt.id}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              )}
            </label>
            <label>
              图片风格
              {styleLocked ? (
                <span className="locked-style">
                  {styleHints.image_style ? `${styleHints.image_style}（已锁定）` : "未指定"}
                </span>
              ) : (
                <select
                  value={styleHints.image_style ?? ""}
                  disabled={inputBlocked}
                  onChange={(e) =>
                    setStyleHints((prev) => ({
                      ...prev,
                      image_style: e.target.value || undefined,
                    }))
                  }
                >
                  <option value="">不指定</option>
                  {IMAGE_STYLE_HINT_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              )}
            </label>
            <label>
              预计时长
              {styleLocked ? (
                <span className="locked-style">
                  {styleHints.target_duration
                    ? `${styleHints.target_duration}（已锁定）`
                    : "未指定"}
                </span>
              ) : (
                <select
                  value={styleHints.target_duration ?? ""}
                  disabled={inputBlocked}
                  onChange={(e) =>
                    setStyleHints((prev) => ({
                      ...prev,
                      target_duration: e.target.value || undefined,
                    }))
                  }
                >
                  <option value="">不指定</option>
                  {TARGET_DURATION_HINT_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              )}
            </label>
          </div>
          <div className="chat-log">
            <ChatPanel
              showReactDetails={showReactDetails}
              sendConfirmation={sendConfirmation}
              hasMoreMessages={hasMoreMessages}
              loadingEarlier={loadingEarlierMessages}
              onLoadEarlier={() => void loadEarlierMessages()}
            />
          </div>
          <div className="chat-input-wrap">
          <div className="chat-input-row">
            <input
              ref={chatInputRef}
              value={input}
              disabled={inputBlocked || needsAiConfig || llmLoading}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                needsAiConfig
                  ? "请先配置 AI 模型…"
                  : skills.length > 0
                    ? "描述创意，或输入 / 选择 Skill…"
                    : "描述你的视频创意…"
              }
              onKeyDown={(e) => {
                if (skillPickerOpen && filteredSkills.length > 0) {
                  if (e.key === "ArrowDown") {
                    e.preventDefault();
                    setSkillPickerIndex((i) =>
                      Math.min(i + 1, filteredSkills.length - 1)
                    );
                    return;
                  }
                  if (e.key === "ArrowUp") {
                    e.preventDefault();
                    setSkillPickerIndex((i) => Math.max(i - 1, 0));
                    return;
                  }
                  if (e.key === "Enter" || e.key === "Tab") {
                    e.preventDefault();
                    selectSkill(filteredSkills[skillPickerIndex]);
                    return;
                  }
                }
                if (e.key === "Escape" && skillPickerOpen) {
                  e.preventDefault();
                  setInput((prev) => prev.replace(/^\//, ""));
                  return;
                }
                if (e.key === "Enter" && !inputBlocked) {
                  if (needsAiConfig) promptConfigureAi();
                  else void sendChat();
                }
              }}
            />
            <button
              type="button"
              onClick={
                (isRunning || scriptStatus === "executing")
                  ? () => void abortExecution()
                  : needsAiConfig
                    ? promptConfigureAi
                    : () => void sendChat()
              }
              disabled={
                (isRunning || scriptStatus === "executing")
                  ? false
                  : inputBlocked || llmLoading || (!needsAiConfig && !input.trim())
              }
            >
              {awaitingConfirmation
                ? t("waitingConfirm", { ns: "chat" })
                : (isRunning || scriptStatus === "executing")
                  ? t("abortExecution", { ns: "chat" })
                  : needsAiConfig
                    ? t("configureAiFirst", { ns: "chat" })
                    : t("send", { ns: "chat" })}
            </button>
          </div>
          {skillPickerOpen && (
            <SkillPicker
              skills={filteredSkills}
              activeIndex={Math.min(skillPickerIndex, Math.max(filteredSkills.length - 1, 0))}
              onSelect={selectSkill}
              onHover={setSkillPickerIndex}
            />
          )}
          </div>
        </aside>
        )}

        <main className="script-panel">
          <h2>{isScriptMode ? t("scriptWorkbench", { ns: "editor" }) : t("tabs.overview", { ns: "board" })}</h2>
          <div className="script-panel-scroll">
            {isScriptMode && (
              <PlanPanel
                plan={planView}
                scriptStatus={scriptStatus}
                projectId={projectId}
                scriptId={scriptId}
                isRunning={isRunning}
                isAborting={isAborting}
                onAbort={() => void abortExecution()}
              />
            )}
            <BoardPanel
              workspaceMode={workspaceMode}
              activeTab={boardTab}
              onTabChange={setBoardTab}
              board={board}
              loading={boardLoading}
              error={boardError}
              onRefresh={handleBoardRefresh}
              onEnterScript={handleEnterScript}
              onCreateScript={handleCreateScript}
              onDeleteScript={handleDeleteScript}
              onBackToOverview={handleBackToOverview}
              projectId={projectId}
              scriptId={scriptId}
              scriptMeta={scriptMeta}
              manualEditEnabled={manualEditEnabled}
            />
          </div>
        </main>
      </div>
    </div>
  );
}
