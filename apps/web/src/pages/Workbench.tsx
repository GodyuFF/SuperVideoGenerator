/**
 * 工作台：对话 + 剧本资产（主页）。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChatMessageList } from "../components/ChatMessageList";
import { ImageGenProgressModal, type ImageGenProgressItem } from "../components/ImageGenProgressModal";
import { SkillPicker } from "../components/SkillPicker";
import { PlanPanel } from "../components/PlanPanel";
import { BoardPanel } from "../components/board/BoardPanel";
import { ProjectSwitcher } from "../components/ProjectSwitcher";
import { MASTER_AGENT_NAME, styleModeLabel, type StyleMode, imageTextPresetLabel, comicPresetLabel } from "../constants";
import { useBoardData } from "../hooks/useBoardData";
import { formatApiError, useProject, useWebSocket } from "../hooks/useApi";
import {
  getLastConversationId,
  setLastConversationId,
} from "../lib/localProjects";
import type { BoardTabId } from "../types/board";
import type {
  ActionKind,
  ChatMessage,
  SubAgentTurnMessage,
} from "../types/chat";
import { normalizeActionInput } from "../types/chat";
import type { AiConfig, ImageGenProgressEvent, PlanDocument, PlanViewState, StepOutput, A2UIConfirmationRequest } from "../types";
import {
  emptyPlanView,
  mergePlanDocument,
  patchPlanStep,
  planFromApi,
} from "../utils/planLabels";
import type { ConversationSummary } from "../types/conversation";
import { isTimelineResponse, timelineToChatMessages } from "../utils/conversationTimeline";
import {
  applySkillSelection,
  filterSkills,
  getSkillPickerQuery,
  parseSkillCommand,
  type SkillOption,
} from "../utils/skillCommand";

const API = "/api";

type ExecutionMode = "interactive" | "goal";

interface SkillMeta extends SkillOption {}

interface ScriptMeta {
  style_mode?: string;
  style_locked?: boolean;
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

export function Workbench({
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
  const isScriptMode = workspaceMode === "script" && !!scriptId;
  const showReactDetails = aiConfig?.llm.show_react_details ?? true;
  const [boardTab, setBoardTab] = useState<BoardTabId>("overview");
  const [activeScriptTitle, setActiveScriptTitle] = useState("");
  const { board, scriptMeta, loading: boardLoading, error: boardError, refresh: refreshBoard } =
    useBoardData(projectId, scriptId, boardTab, workspaceMode);
  const { events, sendConfirmation } = useWebSocket(
    projectId,
    scriptId,
    isScriptMode
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [conversationList, setConversationList] = useState<ConversationSummary[]>([]);
  const [input, setInput] = useState("");
  const [skillPickerIndex, setSkillPickerIndex] = useState(0);
  const chatInputRef = useRef<HTMLInputElement>(null);
  const chatAbortRef = useRef<AbortController | null>(null);
  const [planView, setPlanView] = useState<PlanViewState>(emptyPlanView);
  const [scriptStatus, setScriptStatus] = useState("draft");
  const [styleMode, setStyleMode] = useState<StyleMode>("dynamic_image");
  const [styleLocked, setStyleLocked] = useState(false);
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("interactive");
  const [skills, setSkills] = useState<SkillMeta[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isAborting, setIsAborting] = useState(false);
  const abortSlowTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastEventIndex = useRef(0);
  const eventsRef = useRef(events);
  eventsRef.current = events;
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const activeConversationIdRef = useRef(activeConversationId);
  activeConversationIdRef.current = activeConversationId;
  const streamMessageIds = useRef<Map<string, string>>(new Map());
  const chatRoundRef = useRef(0);
  const stepMasterIteration = useRef<Map<string, number>>(new Map());
  const stepMasterRound = useRef<Map<string, number>>(new Map());
  const [imageGenProgress, setImageGenProgress] = useState<{
    open: boolean;
    stepId: string;
    total: number;
    items: ImageGenProgressItem[];
  }>({ open: false, stepId: "", total: 0, items: [] });

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

  const appendMessage = useCallback((message: ChatMessage) => {
    setMessages((m) => [...m, message]);
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

  const updateMessage = useCallback(
    (id: string, updater: (msg: ChatMessage) => ChatMessage) => {
      setMessages((m) => m.map((msg) => (msg.id === id ? updater(msg) : msg)));
    },
    []
  );

  const upsertReactAction = useCallback(
    (
      round: number,
      iteration: number,
      action: string,
      actionLabel: string | undefined,
      actionKind: ActionKind | undefined,
      actionInput: Record<string, string> | undefined
    ) => {
      setMessages((m) => {
        const idx = m.findIndex(
          (msg) =>
            msg.kind === "react_turn" &&
            msg.round === round &&
            msg.iteration === iteration
        );
        if (idx === -1) {
          return [
            ...m,
            {
              kind: "react_turn" as const,
              id: `turn-${round}-${iteration}-${Date.now()}`,
              round,
              iteration,
              thought: "",
              action,
              actionLabel,
              actionKind,
              actionInput,
            },
          ];
        }
        return m.map((msg, i) =>
          i === idx && msg.kind === "react_turn"
            ? {
                ...msg,
                action,
                actionLabel,
                actionKind,
                actionInput,
              }
            : msg
        );
      });
    },
    []
  );

  const handleA2uiSubmitted = useCallback(
    (messageId: string, values: Record<string, unknown>, approved: boolean) => {
      updateMessage(messageId, (msg) => {
        if (msg.kind !== "a2ui_confirmation") return msg;
        return {
          ...msg,
          status: approved ? "submitted" : "cancelled",
          submittedValues: values,
        };
      });
    },
    [updateMessage]
  );

  const upsertSubAgentEvent = useCallback((e: Record<string, unknown>) => {
    const stepId = e.step_id ? String(e.step_id) : "";
    if (!stepId) return;
    const eventType = String(e.type ?? "");
    const iteration = Number(e.iteration ?? 0);
    const round = chatRoundRef.current;

    setMessages((m) => {
      let idx = m.findIndex(
        (msg) =>
          msg.kind === "sub_agent" &&
          msg.stepId === stepId &&
          msg.round === round
      );

      if (idx === -1) {
        const masterIter = stepMasterIteration.current.get(stepId);
        const masterRound = stepMasterRound.current.get(stepId);
        const insertAt =
          masterIter !== undefined && masterRound !== undefined
            ? m.findIndex(
                (msg) =>
                  msg.kind === "react_turn" &&
                  msg.round === masterRound &&
                  msg.iteration === masterIter
              ) + 1
            : m.length;
        const newBlock: SubAgentTurnMessage = {
          kind: "sub_agent",
          id: `sub-${round}-${stepId}`,
          stepId,
          round,
          agentName: String(e.agent_name ?? ""),
          displayName: String(e.agent_display_name ?? e.agent_name ?? ""),
          iterations: [],
        };
        const next = [...m];
        next.splice(insertAt < 0 ? m.length : insertAt, 0, newBlock);
        idx = insertAt < 0 ? next.length - 1 : insertAt;
        m = next;
      }

      const block = m[idx];
      if (block.kind !== "sub_agent") return m;

      const updated: SubAgentTurnMessage = { ...block };

      if (eventType === "agent_react_finished") {
        updated.finished = {
          iterations: Number(e.iterations ?? iteration),
          outputCount: Number(e.output_count ?? 0),
        };
        return m.map((msg, i) => (i === idx ? updated : msg));
      }

      const iterIdx = updated.iterations.findIndex(
        (it) => it.iteration === iteration
      );
      const iter =
        iterIdx >= 0
          ? { ...updated.iterations[iterIdx] }
          : { iteration };

      if (eventType === "agent_react_thought" && e.thought) {
        iter.thought = String(e.thought);
      }
      if (eventType === "agent_react_action") {
        iter.action = String(e.action ?? "");
        const rawInput = e.action_input;
        if (rawInput) {
          iter.actionInput = normalizeActionInput(rawInput);
        }
      }
      if (eventType === "agent_react_observation" && e.observation) {
        iter.observation = String(e.observation);
        if (String(e.action ?? "") === "generate_images") {
          setImageGenProgress((prev) => ({ ...prev, open: false }));
        }
      }

      if (iterIdx >= 0) {
        updated.iterations = updated.iterations.map((it, i) =>
          i === iterIdx ? iter : it
        );
      } else {
        updated.iterations = [...updated.iterations, iter];
      }

      if (e.agent_name) updated.agentName = String(e.agent_name);
      if (e.agent_display_name) {
        updated.displayName = String(e.agent_display_name);
      }

      return m.map((msg, i) => (i === idx ? updated : msg));
    });
  }, []);

  const loadConversations = useCallback(async (): Promise<ConversationSummary[]> => {
    if (!projectId) return [];
    const q = scriptId ? `?script_id=${encodeURIComponent(scriptId)}` : "";
    const r = await fetch(`${API}/projects/${projectId}/conversations${q}`);
    if (!r.ok) return [];
    const items = (await r.json()) as ConversationSummary[];
    setConversationList(items);
    return items;
  }, [projectId, scriptId]);

  const loadConversationMessages = useCallback(
    async (conversationId: string) => {
      if (!projectId) return;
      const r = await fetch(
        `${API}/projects/${projectId}/conversations/${conversationId}/messages?view=full`
      );
      if (!r.ok) return;
      const data = await r.json();
      if (isTimelineResponse(data)) {
        setMessages(timelineToChatMessages(data.timeline));
        chatRoundRef.current = data.timeline.filter(
          (item) => item.type === "user"
        ).length;
      } else {
        const records = data as { role: string; content: string }[];
        setMessages(
          records.map((m, i) =>
            m.role === "user"
              ? { kind: "user" as const, id: `hist-user-${i}`, text: String(m.content) }
              : {
                  kind: "assistant" as const,
                  id: `hist-master-${i}`,
                  text: String(m.content),
                }
          )
        );
      }
      setActiveConversationId(conversationId);
      if (scriptId) {
        setLastConversationId(projectId, scriptId, conversationId);
      }
      lastEventIndex.current = eventsRef.current.length;
      streamMessageIds.current.clear();
      stepMasterIteration.current.clear();
      stepMasterRound.current.clear();
    },
    [projectId, scriptId]
  );

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
    setMessages([]);
    chatRoundRef.current = 0;
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
    const r = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}`);
    if (!r.ok) return;
    const script = (await r.json()) as ScriptMeta;
    if (script.title) setActiveScriptTitle(script.title);
    if (script.status) setScriptStatus(script.status);
    if (
      script.style_mode === "dynamic_image" ||
      script.style_mode === "dynamic_comic" ||
      script.style_mode === "ai_video"
    ) {
      setStyleMode(script.style_mode);
    }
    setStyleLocked(Boolean(script.style_locked));
  }, [projectId, scriptId]);

  const loadPlan = useCallback(async () => {
    if (!projectId || !scriptId) return;
    const r = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}/plan`);
    if (r.ok) {
      const plan = (await r.json()) as PlanDocument;
      setPlanView((prev) => ({
        ...planFromApi(plan),
        plan_status_history: prev.plan_status_history,
        last_remaining_plan: prev.last_remaining_plan,
      }));
    }
  }, [projectId, scriptId]);

  const refreshWorkspace = useCallback(async () => {
    if (workspaceMode === "script" && scriptId) {
      await loadScriptMeta();
      await loadPlan();
    }
    await refreshBoard();
  }, [workspaceMode, scriptId, loadScriptMeta, loadPlan, refreshBoard]);

  const prevScriptIdRef = useRef<string | null>(null);
  const loadConversationsRef = useRef(loadConversations);
  loadConversationsRef.current = loadConversations;
  const loadConversationMessagesRef = useRef(loadConversationMessages);
  loadConversationMessagesRef.current = loadConversationMessages;
  const refreshWorkspaceRef = useRef(refreshWorkspace);
  refreshWorkspaceRef.current = refreshWorkspace;

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
      setPlanView(emptyPlanView());
      setMessages([]);
      setActiveConversationId(null);
      chatRoundRef.current = 0;
      stepMasterIteration.current.clear();
      stepMasterRound.current.clear();
    }

    let cancelled = false;

    void (async () => {
      await refreshWorkspaceRef.current();
      if (cancelled) return;

      const items = await loadConversationsRef.current();
      if (cancelled) return;

      if (items.length === 0) {
        if (scriptChanged) {
          setMessages([]);
          setActiveConversationId(null);
        }
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

      await loadConversationMessagesRef.current(targetId);
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
    setMessages([]);
    setActiveConversationId(null);
    chatRoundRef.current = 0;
    stepMasterIteration.current.clear();
    stepMasterRound.current.clear();
    setPlanView(emptyPlanView());
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

  useEffect(() => {
    const newEvents = events.slice(lastEventIndex.current);
    lastEventIndex.current = events.length;

    newEvents.forEach((e) => {
      const eventConvId = e.conversation_id ? String(e.conversation_id) : null;
      if (
        eventConvId &&
        activeConversationId &&
        eventConvId !== activeConversationId
      ) {
        return;
      }
      const streamKind = e.kind ? String(e.kind) : "";

      if (e.type === "llm_stream_start" && e.stream_id) {
        const streamId = String(e.stream_id);
        const messageId = `stream-${streamId}`;

        if (streamKind === "react_thought" && showReactDetails) {
          streamMessageIds.current.set(streamId, messageId);
          const iteration = Number(e.iteration ?? 0);
          const round = chatRoundRef.current;
          appendMessage({
            kind: "react_turn",
            id: messageId,
            round,
            iteration,
            thought: "",
            thoughtStreaming: true,
          });
        } else if (streamKind === "llm_summary") {
          streamMessageIds.current.set(streamId, messageId);
          appendMessage({
            kind: "assistant",
            id: messageId,
            text: "",
            streaming: true,
          });
        }
      }

      if (e.type === "llm_stream_delta" && e.stream_id && e.delta) {
        const messageId = streamMessageIds.current.get(String(e.stream_id));
        if (!messageId) return;
        const delta = String(e.delta);

        if (streamKind === "react_thought" && showReactDetails) {
          updateMessage(messageId, (msg) => {
            if (msg.kind !== "react_turn") return msg;
            return { ...msg, thought: msg.thought + delta };
          });
        } else if (streamKind === "llm_summary") {
          updateMessage(messageId, (msg) => {
            if (msg.kind !== "assistant") return msg;
            return { ...msg, text: msg.text + delta };
          });
        }
      }

      if (e.type === "llm_stream_end" && e.stream_id) {
        const streamId = String(e.stream_id);
        const messageId = streamMessageIds.current.get(streamId);
        if (messageId) {
          if (streamKind === "react_thought" && showReactDetails) {
            updateMessage(messageId, (msg) => {
              if (msg.kind !== "react_turn") return msg;
              return { ...msg, thoughtStreaming: false };
            });
          } else if (streamKind === "llm_summary") {
            updateMessage(messageId, (msg) => {
              if (msg.kind !== "assistant") return msg;
              return { ...msg, streaming: false };
            });
          }
          streamMessageIds.current.delete(streamId);
        }
      }

      if (e.type === "react_action") {
        const iteration = Number(e.iteration ?? 0);
        const round = chatRoundRef.current;
        const action = String(e.action ?? "");
        const actionLabel = e.action_label
          ? String(e.action_label)
          : undefined;
        const actionKind = e.action_kind
          ? (String(e.action_kind) as ActionKind)
          : undefined;
        const rawInput = e.llm_action_input ?? e.action_input;
        if (e.step_id) {
          stepMasterIteration.current.set(String(e.step_id), iteration);
          stepMasterRound.current.set(String(e.step_id), round);
        }
        upsertReactAction(
          round,
          iteration,
          action,
          actionLabel,
          actionKind,
          normalizeActionInput(rawInput)
        );
      }

      if (
        e.type === "agent_react_thought" ||
        e.type === "agent_react_action" ||
        e.type === "agent_react_observation" ||
        e.type === "agent_react_finished"
      ) {
        upsertSubAgentEvent(e as Record<string, unknown>);
      }

      if (e.type === "a2ui_confirmation_required") {
        const req = e as unknown as A2UIConfirmationRequest;
        setMessages((m) => {
          const updated = m.map((msg) =>
            msg.kind === "a2ui_confirmation" && msg.status === "pending"
              ? { ...msg, status: "superseded" as const }
              : msg
          );
          return [
            ...updated,
            {
              kind: "a2ui_confirmation" as const,
              id: `a2ui-${req.confirmation_id}`,
              confirmationId: req.confirmation_id,
              request: req,
              status: "pending" as const,
            },
          ];
        });
      }

      if (e.type === "react_observation" && e.observation && showReactDetails) {
        const iteration = Number(e.iteration ?? 0);
        const round = chatRoundRef.current;
        const obs = String(e.observation);
        setMessages((m) =>
          m.map((msg) =>
            msg.kind === "react_turn" &&
            msg.round === round &&
            msg.iteration === iteration
              ? { ...msg, observation: obs }
              : msg
          )
        );
      }

      if (e.type === "master_message" && e.content && e.source === "llm_summary") {
        const content = String(e.content);
        setMessages((m) => {
          if (
            m.some(
              (msg) => msg.kind === "assistant" && msg.text.trim() === content.trim()
            )
          ) {
            return m;
          }
          return [
            ...m,
            {
              kind: "assistant" as const,
              id: `summary-${Date.now()}`,
              text: content,
            },
          ];
        });
      }

      if (e.type === "image_gen_progress") {
        const ev = e as unknown as ImageGenProgressEvent;
        const index = Number(ev.index ?? 0);
        const total = Number(ev.total ?? 0);
        const status = String(ev.status ?? "started");
        setImageGenProgress((prev) => {
          const items = [...prev.items];
          const existingIdx = items.findIndex((item) => item.index === index);
          const entry: ImageGenProgressItem = {
            index,
            sourceTextAssetId: String(ev.source_text_asset_id ?? ""),
            name: String(ev.name ?? ""),
            status:
              status === "completed"
                ? "completed"
                : status === "failed"
                  ? "failed"
                  : "started",
            url: ev.url ? String(ev.url) : undefined,
            error: ev.error ? String(ev.error) : undefined,
          };
          if (existingIdx >= 0) {
            items[existingIdx] = { ...items[existingIdx], ...entry };
          } else {
            items.push(entry);
          }
          items.sort((a, b) => a.index - b.index);
          return {
            open: true,
            stepId: String(ev.step_id ?? prev.stepId),
            total: total || prev.total,
            items,
          };
        });
        if (status === "completed") {
          void refreshBoard();
        }
        if (status === "completed" && index === total && total > 0) {
          setImageGenProgress((prev) => ({ ...prev, open: false }));
        }
      }

      if (e.type === "assets_changed") {
        refreshWorkspace();
      }
      if (e.type === "script_style_locked" && e.style_mode) {
        const mode = String(e.style_mode);
        if (mode === "dynamic_image" || mode === "ai_video") {
          setStyleMode(mode);
        }
        setStyleLocked(true);
      }
      if (e.type === "planning_started") {
        setScriptStatus("planning");
      }
      if (e.type === "plan_ready" && e.plan) {
        const plan = e.plan as PlanDocument;
        setPlanView((prev) => mergePlanDocument(prev, plan));
        setScriptStatus((prev) => (prev === "executing" ? prev : "planned"));
        refreshWorkspace();
      }
      if (e.type === "plan_updated") {
        setPlanView((prev) => {
          const next = e.plan
            ? mergePlanDocument(prev, e.plan as PlanDocument)
            : { ...prev };
          if (Array.isArray(e.plan_status_history)) {
            next.plan_status_history = e.plan_status_history as string[];
          }
          if (Array.isArray(e.last_remaining_plan)) {
            next.last_remaining_plan = e.last_remaining_plan as string[];
          }
          return next;
        });
      }
      if (e.type === "react_started" || e.type === "execution_started") {
        setScriptStatus("executing");
        setIsRunning(true);
      }
      if (e.type === "step_started") {
        setPlanView((prev) =>
          patchPlanStep(prev, String(e.step_id), { status: "running" })
        );
      }
      if (e.type === "step_awaiting_confirmation") {
        setPlanView((prev) =>
          patchPlanStep(prev, String(e.step_id), {
            status: "awaiting_confirmation",
          })
        );
      }
      if (e.type === "step_completed" || e.type === "step_resumed") {
        const outputs = e.outputs as StepOutput[] | undefined;
        setPlanView((prev) =>
          patchPlanStep(prev, String(e.step_id), {
            status: "completed",
            progress: 100,
            outputs,
          })
        );
        refreshWorkspace();
      }
      if (e.type === "step_failed") {
        setPlanView((prev) =>
          patchPlanStep(prev, String(e.step_id), {
            status: "failed",
            error: String(e.error),
          })
        );
      }
      if (e.type === "step_paused") {
        setPlanView((prev) =>
          patchPlanStep(prev, String(e.step_id), {
            status: "paused",
            error: String(e.error ?? ""),
          })
        );
      }
      if (e.type === "project_completed") {
        setScriptStatus("completed");
        setIsRunning(false);
        refreshWorkspace();
      }
      if (e.type === "execution_abort_requested") {
        beginAborting();
      }
      if (
        e.type === "execution_aborted" ||
        e.type === "execution_failed" ||
        e.type === "react_finished"
      ) {
        setIsRunning(false);
        clearAborting();
        chatAbortRef.current = null;
        if (e.type === "execution_aborted") {
          setScriptStatus("failed");
          appendSystemMessage("已中止执行。");
        }
        if (e.type === "execution_failed") {
          setScriptStatus("failed");
          setIsRunning(false);
        }
        if (e.type === "react_finished" && e.status) {
          setScriptStatus(String(e.status));
        }
        refreshWorkspace();
      }

      // image_gen 可能抛出异常终止执行，但不等同于 execution_failed 事件
      if (e.type === "step_failed" && String(e.step_id || "")) {
        // 步骤失败不一定导致整个执行终止，但 isRunning 应保持
        // 仅 step 失败明确表示生图中断时，仍然维持 isRunning 以便用户手动中止
      }
    });
  }, [
    events,
    activeConversationId,
    refreshWorkspace,
    refreshBoard,
    appendMessage,
    updateMessage,
    upsertReactAction,
    upsertSubAgentEvent,
    appendSystemMessage,
    showReactDetails,
    beginAborting,
    clearAborting,
  ]);

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
    lastEventIndex.current = events.length;
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
          ...(styleLocked ? {} : { style_mode: styleMode }),
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
      if (
        data.script?.style_mode === "dynamic_image" ||
        data.script?.style_mode === "dynamic_comic" ||
        data.script?.style_mode === "ai_video"
      ) {
        setStyleMode(data.script.style_mode);
      }
      if (data.plan) {
        setPlanView((prev) => ({
          ...planFromApi(data.plan as PlanDocument),
          plan_status_history: prev.plan_status_history,
          last_remaining_plan: prev.last_remaining_plan,
        }));
      }
      const convIdToReload =
        data.conversation_id != null
          ? String(data.conversation_id)
          : convId;
      if (convIdToReload) {
        await loadConversationMessages(convIdToReload);
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
      await refreshWorkspace();
      await loadConversations();
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

  if (loading) return <div className="loading">加载中…</div>;

  if (initError) {
    return (
      <div className="loading">
        <p>初始化失败：{initError}</p>
        <p className="muted">请先启动后端：<code>uvicorn apps.api.main:app --port 8000</code></p>
        <button type="button" onClick={() => bootstrap()}>重试</button>
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
      <header className="top-bar">
        <button type="button" className="btn-secondary btn-sm board-back-link" onClick={onBackHome}>
          ← 项目列表
        </button>
        <h1>SuperVideoGenerator</h1>
        <span className={`status-badge ${aiBadgeClass}`}>{aiBadgeText}</span>
        {isScriptMode && (
          <>
            <span className="status-badge">{scriptStatus}</span>
            {activeScriptTitle && (
              <span className="status-badge muted-badge">{activeScriptTitle}</span>
            )}
            {styleLocked && (
              <span className="status-badge style-locked">
                风格：{styleModeLabel(styleMode)}（已锁定）
              </span>
            )}
            {/* 显示 AI 配置中的图文子风格和漫画画风 */}
            {isScriptMode && aiConfig?.image?.pipeline && (
              <>
                <span className="status-badge muted-badge">
                  图文：{imageTextPresetLabel(aiConfig.image.pipeline.image_text_preset)}
                </span>
                <span className="status-badge muted-badge">
                  漫画：{comicPresetLabel(aiConfig.image.pipeline.comic_preset)}
                </span>
              </>
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
                  {isAborting ? "中止中…" : "中止执行"}
                </button>
              </>
            )}
          </>
        )}
        <ProjectSwitcher
          projectId={projectId}
          scriptId={scriptId}
          onSwitchProject={(pid) => {
            onNavigateToProject(pid, null);
            exitToProject(pid);
            setBoardTab("overview");
            setMessages([]);
            setActiveConversationId(null);
            setPlanView(emptyPlanView());
            setIsRunning(false);
            setActiveScriptTitle("");
          }}
          onEnterScript={(pid, sid, meta) => {
            if (pid === projectId && sid === scriptId && workspaceMode === "script") {
              return;
            }
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
        <div className="top-bar-spacer" />
        <button
          type="button"
          className="btn-secondary btn-config"
          onClick={onOpenAgents}
        >
          Agent 配置
        </button>
        <button
          type="button"
          className="btn-secondary btn-config"
          onClick={onOpenLogs}
        >
          查看日志
        </button>
        <button
          type="button"
          className="btn-secondary btn-config"
          onClick={onOpenSettings}
        >
          AI 配置
        </button>
      </header>

      {needsAiConfig && !llmLoading && (
        <div className="ai-config-banner">
          <p>
            尚未配置 AI 模型与 API Key，无法使用 ReAct 智能编排。
            请填写 API Key 后点击<strong>「保存配置」</strong>或<strong>「保存并返回对话」</strong>。
          </p>
          <button type="button" onClick={onOpenSettings}>去配置 AI</button>
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
          <h2>对话</h2>
          <div className="conversation-toolbar">
            <button
              type="button"
              className="btn-secondary"
              disabled={inputBlocked || !projectId || !scriptId}
              onClick={() => void startNewConversation()}
            >
              新对话
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
                <span className="locked-style">{styleModeLabel(styleMode)}（已锁定）</span>
              ) : (
                <select
                  value={styleMode}
                  disabled={inputBlocked}
                  onChange={(e) => setStyleMode(e.target.value as StyleMode)}
                >
                  <option value="dynamic_image">动态图文模式</option>
                  <option value="dynamic_comic">动态漫画模式</option>
                  <option value="ai_video">AI 视频模式</option>
                </select>
              )}
            </label>
          </div>
          <div className="chat-log">
            <ChatMessageList
              messages={messages}
              showReactDetails={showReactDetails}
              sendConfirmation={sendConfirmation}
              onA2uiSubmitted={handleA2uiSubmitted}
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
                ? "等待确认…"
                : (isRunning || scriptStatus === "executing")
                  ? "中止执行"
                  : needsAiConfig
                    ? "配置 AI"
                    : "发送"}
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
          <h2>{isScriptMode ? "剧本工作台" : "项目看板"}</h2>
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
            onRefresh={refreshWorkspace}
            onEnterScript={handleEnterScript}
            onCreateScript={handleCreateScript}
            onDeleteScript={handleDeleteScript}
            onBackToOverview={handleBackToOverview}
            projectId={projectId}
            scriptId={scriptId}
            scriptMeta={scriptMeta}
            manualEditEnabled={manualEditEnabled}
          />
        </main>
      </div>
      <ImageGenProgressModal
        open={imageGenProgress.open}
        stepId={imageGenProgress.stepId}
        total={imageGenProgress.total}
        items={imageGenProgress.items}
        onClose={() => setImageGenProgress((prev) => ({ ...prev, open: false }))}
      />
    </div>
  );
}
