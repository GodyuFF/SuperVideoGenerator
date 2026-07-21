/**
 * 工作台 WebSocket 事件路由：chatStore / planStore 写入，Plan/生图防抖。
 */

import { useCallback, useEffect, useRef } from "react";
import type { BoardTabId } from "../types/board";
import type {
  ActionKind,
  ChatMessage,
  ReactTurnActionItem,
} from "../types/chat";
import { normalizeActionInput } from "../types/chat";
import type {
  A2UIConfirmationRequest,
  ImageGenProgressEvent,
  PlanDocument,
  StepOutput,
  WsEvent,
} from "../types";
import { coerceStyleMode, type StyleHints } from "../constants";
import { createDebouncedAsyncTask } from "../lib/asyncRefresh";
import { logPerf, recordWsEvent } from "../lib/perfLog";
import { createWsPlanThrottle } from "../lib/wsPlanThrottle";
import { useChatStore } from "../stores/chatStore";
import { usePlanStore } from "../stores/planStore";
import { mergePlanDocument, patchPlanStep } from "../utils/planLabels";
import type { AssetGenerationController } from "../context/AssetGenerationContext";
import type { GenerationQueueController } from "../context/GenerationQueueContext";

/** 生图完成后需刷新的看板 Tab。 */
const IMAGE_BOARD_TABS: BoardTabId[] = [
  "character",
  "scene",
  "prop",
  "frame",
  "video_clip",
  "storyboard",
  "media",
];

/** 推断 ReAct action 类型标签。 */
function inferActionKind(action: string): ActionKind {
  if (action === "delegate_agent" || action.startsWith("delegate_")) return "delegate";
  if (action.startsWith("tool_")) return "tool";
  if (action === "finish") return "finish";
  if (action === "ask_user_question") return "ask_user";
  return "unknown";
}

/** 从 WS payload 解析同轮多 action 列表。 */
function parseWsBatchActions(raw: unknown): ReactTurnActionItem[] | undefined {
  if (!Array.isArray(raw) || raw.length === 0) return undefined;
  const items: ReactTurnActionItem[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const rec = entry as Record<string, unknown>;
    const action = String(rec.action ?? "").trim();
    if (!action) continue;
    items.push({
      action,
      actionInput: normalizeActionInput(
        (rec.action_input ?? rec.llm_action_input) as Record<string, unknown> | undefined,
      ),
    });
  }
  return items.length > 0 ? items : undefined;
}

/** 判断是否影响对话消息列表的 WebSocket 事件。 */
function isConversationChatEvent(type: string): boolean {
  return (
    type.startsWith("llm_stream_") ||
    type === "react_action" ||
    type === "react_action_batch" ||
    type === "react_observation" ||
    type === "master_message" ||
    type.startsWith("agent_react_") ||
    type === "a2ui_confirmation_required"
  );
}

export interface UseWorkbenchWsOptions {
  showReactDetails: boolean;
  activeConversationId: string | null;
  assetGeneration: AssetGenerationController;
  generationQueue: GenerationQueueController;
  boardTabRef: React.MutableRefObject<BoardTabId>;
  chatRoundRef: React.MutableRefObject<number>;
  stepMasterIteration: React.MutableRefObject<Map<string, number>>;
  stepMasterRound: React.MutableRefObject<Map<string, number>>;
  streamMessageIds: React.MutableRefObject<Map<string, string>>;
  conversationHydratedRef: React.MutableRefObject<boolean>;
  pendingWsEventsRef: React.MutableRefObject<WsEvent[]>;
  wsChatReplayRef: React.MutableRefObject<boolean>;
  debouncedRefreshWorkspace: ReturnType<typeof createDebouncedAsyncTask>;
  debouncedRefreshWorkspaceFull: ReturnType<typeof createDebouncedAsyncTask>;
  debouncedRefreshBoard: ReturnType<typeof createDebouncedAsyncTask>;
  debouncedAssetsChanged: ReturnType<typeof createDebouncedAsyncTask>;
  scheduleBoardRefreshIfRelevant: () => void;
  appendSystemMessage: (text: string) => void;
  beginAborting: () => void;
  clearAborting: () => void;
  setScriptStatus: (status: string | ((prev: string) => string)) => void;
  setIsRunning: (running: boolean) => void;
  setStyleMode: (mode: string) => void;
  setStyleHints: (hints: StyleHints | ((prev: StyleHints) => StyleHints)) => void;
  setStyleLocked: (locked: boolean) => void;
  chatAbortRef: React.MutableRefObject<AbortController | null>;
}

/** 绑定工作台 WebSocket 处理器并返回 handleWsEvent。 */
export function useWorkbenchWs(options: UseWorkbenchWsOptions) {
  const setMessages = useChatStore((s) => s.setMessages);
  const updateMessage = useChatStore((s) => s.updateMessage);
  const upsertReactAction = useChatStore((s) => s.upsertReactAction);
  const upsertSubAgentEvent = useChatStore((s) => s.upsertSubAgentEvent);

  const setPlanViewTransition = usePlanStore((s) => s.setPlanViewTransition);
  const mergePlan = usePlanStore((s) => s.mergePlan);

  const streamDeltaBuffer = useRef(
    new Map<string, { messageId: string; streamKind: string; delta: string }>(),
  );
  const streamFlushTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const planThrottleRef = useRef(
    createWsPlanThrottle({
      onPlanApply: (updater) => setPlanViewTransition(updater),
    }),
  );

  useEffect(() => {
    planThrottleRef.current = createWsPlanThrottle({
      onPlanApply: (updater) => setPlanViewTransition(updater),
    });
    return () => planThrottleRef.current.dispose();
  }, [setPlanViewTransition]);

  const optionsRef = useRef(options);
  optionsRef.current = options;

  /** 批量刷新 LLM 流式 delta。 */
  const flushStreamDeltas = useCallback(() => {
    streamFlushTimer.current = null;
    const buffer = streamDeltaBuffer.current;
    if (buffer.size === 0) return;
    const entries = Array.from(buffer.values());
    buffer.clear();
    const showDetails = optionsRef.current.showReactDetails;
    const start = performance.now();
    setMessages((prev) => {
      let next = prev;
      let changed = false;
      for (const { messageId, streamKind, delta } of entries) {
        next = next.map((msg) => {
          if (msg.id !== messageId) return msg;
          if (streamKind === "react_thought" && showDetails && msg.kind === "react_turn") {
            changed = true;
            return { ...msg, thought: msg.thought + delta };
          }
          if (streamKind === "llm_summary" && msg.kind === "assistant") {
            changed = true;
            return { ...msg, text: msg.text + delta };
          }
          return msg;
        });
      }
      return changed ? next : prev;
    });
    logPerf("workbench", "flushStreamDeltas", {
      batch_size: entries.length,
      duration_ms: Math.round(performance.now() - start),
    });
  }, [setMessages]);

  const handleWsEvent = useCallback(
    (e: WsEvent) => {
      recordWsEvent(e.type);
      const opt = optionsRef.current;
      window.dispatchEvent(new CustomEvent("svg:ws-event", { detail: e }));

      if (
        e.type === "image_gen_progress" ||
        e.type === "tts_gen_progress" ||
        e.type === "assets_changed"
      ) {
        opt.assetGeneration.applyWsEvent(e);
      }

      if (e.type === "generation_queue_snapshot") {
        opt.generationQueue.applyWsEvent(e);
      }

      if (e.type === "image_gen_progress") {
        const ev = e as unknown as ImageGenProgressEvent;
        planThrottleRef.current.scheduleImageGenProgress(ev);
        const status = String(ev.status ?? "started");
        const index = Number(ev.index ?? 0);
        const total = Number(ev.total ?? 0);
        if (status === "completed" && index === total && total > 0) {
          if (IMAGE_BOARD_TABS.includes(opt.boardTabRef.current)) {
            opt.debouncedRefreshBoard.schedule();
          }
        }
      }

      if (e.type === "tts_gen_progress") {
        const status = String(e.status ?? "started");
        if (status === "completed" || status === "failed") {
          opt.debouncedAssetsChanged.schedule();
        }
      }

      if (e.type === "assets_changed") {
        const tab = opt.boardTabRef.current;
        if (
          tab !== "script_details" &&
          (IMAGE_BOARD_TABS.includes(tab) ||
            tab === "storyboard" ||
            tab === "pipeline" ||
            tab === "graph")
        ) {
          opt.debouncedAssetsChanged.schedule();
        }
      }

      if (e.type === "script_style_locked" && e.style_mode) {
        const mode = coerceStyleMode(String(e.style_mode));
        if (mode) opt.setStyleMode(mode);
        if (e.style_hints && typeof e.style_hints === "object") {
          const hints = e.style_hints as StyleHints;
          if (Object.keys(hints).length > 0) opt.setStyleHints(hints);
        }
        opt.setStyleLocked(true);
        if (IMAGE_BOARD_TABS.includes(opt.boardTabRef.current)) {
          opt.debouncedRefreshBoard.schedule();
        }
      }

      if (e.type === "planning_started") {
        opt.setScriptStatus("planning");
      }

      if (e.type === "plan_ready" && e.plan) {
        mergePlan(e.plan as PlanDocument);
        opt.setScriptStatus((prev) => (prev === "executing" ? prev : "planned"));
        opt.debouncedRefreshWorkspace.schedule();
      }

      if (e.type === "plan_updated") {
        planThrottleRef.current.schedulePlanUpdated({
          plan: e.plan as PlanDocument | undefined,
          runtime_summary:
            e.runtime_summary !== undefined ? String(e.runtime_summary) : undefined,
          plan_status_history: Array.isArray(e.plan_status_history)
            ? (e.plan_status_history as string[])
            : undefined,
          last_remaining_plan: Array.isArray(e.last_remaining_plan)
            ? (e.last_remaining_plan as string[])
            : undefined,
          version: typeof e.version === "number" ? e.version : undefined,
          affected_step_ids: Array.isArray(e.affected_step_ids)
            ? (e.affected_step_ids as string[])
            : undefined,
          reason: e.reason !== undefined ? String(e.reason) : undefined,
        });
      }

      if (e.type === "react_started" || e.type === "execution_started") {
        opt.setScriptStatus("executing");
        opt.setIsRunning(true);
      }

      if (e.type === "step_started") {
        setPlanViewTransition((prev) =>
          patchPlanStep(prev, String(e.step_id), { status: "running" }),
        );
      }

      if (e.type === "step_awaiting_confirmation") {
        setPlanViewTransition((prev) =>
          patchPlanStep(prev, String(e.step_id), { status: "awaiting_confirmation" }),
        );
      }

      if (e.type === "step_completed" || e.type === "step_resumed") {
        const outputs = e.outputs as StepOutput[] | undefined;
        setPlanViewTransition((prev) =>
          patchPlanStep(prev, String(e.step_id), {
            status: "completed",
            progress: 100,
            outputs,
            image_gen_progress: undefined,
          }),
        );
        opt.scheduleBoardRefreshIfRelevant();
      }

      if (e.type === "step_failed") {
        setPlanViewTransition((prev) =>
          patchPlanStep(prev, String(e.step_id), {
            status: "failed",
            error: String(e.error),
            image_gen_progress: undefined,
          }),
        );
      }

      if (e.type === "step_paused") {
        setPlanViewTransition((prev) =>
          patchPlanStep(prev, String(e.step_id), {
            status: "paused",
            error: String(e.error ?? ""),
          }),
        );
      }

      if (e.type === "project_completed") {
        opt.setScriptStatus("completed");
        opt.setIsRunning(false);
        opt.debouncedRefreshWorkspaceFull.schedule();
      }

      if (e.type === "execution_abort_requested") {
        opt.beginAborting();
      }

      if (
        e.type === "execution_aborted" ||
        e.type === "execution_failed" ||
        e.type === "react_finished"
      ) {
        opt.setIsRunning(false);
        opt.clearAborting();
        opt.chatAbortRef.current = null;
        if (e.type === "execution_aborted") {
          opt.setScriptStatus("failed");
          opt.appendSystemMessage("已中止执行。");
        }
        if (e.type === "execution_failed") {
          opt.setScriptStatus("failed");
        }
        if (e.type === "react_finished" && e.status) {
          opt.setScriptStatus(String(e.status));
        }
        opt.debouncedRefreshWorkspaceFull.schedule();
      }

      if (!isConversationChatEvent(String(e.type ?? ""))) {
        return;
      }

      const eventConvId = e.conversation_id ? String(e.conversation_id) : null;
      if (
        eventConvId &&
        opt.activeConversationId &&
        eventConvId !== opt.activeConversationId
      ) {
        return;
      }

      if (!opt.wsChatReplayRef.current && !opt.conversationHydratedRef.current) {
        opt.pendingWsEventsRef.current.push(e);
        return;
      }

      const streamKind = e.kind ? String(e.kind) : "";
      const showReactDetails = opt.showReactDetails;

      if (e.type === "llm_stream_start" && e.stream_id) {
        const streamId = String(e.stream_id);
        const messageId = `stream-${streamId}`;

        if (streamKind === "react_thought" && showReactDetails) {
          const iteration = Number(e.iteration ?? 0);
          const round = opt.chatRoundRef.current;
          setMessages((m) => {
            const existingIdx = m.findIndex(
              (msg) =>
                msg.kind === "react_turn" &&
                msg.round === round &&
                msg.iteration === iteration,
            );
            if (existingIdx >= 0) {
              const existing = m[existingIdx];
              if (existing.kind === "react_turn") {
                opt.streamMessageIds.current.set(streamId, existing.id);
                return m.map((msg, i) =>
                  i === existingIdx ? { ...existing, thoughtStreaming: true } : msg,
                );
              }
            }
            if (m.some((msg) => msg.id === messageId)) {
              opt.streamMessageIds.current.set(streamId, messageId);
              return m.map((msg) =>
                msg.id === messageId && msg.kind === "react_turn"
                  ? { ...msg, thoughtStreaming: true }
                  : msg,
              );
            }
            opt.streamMessageIds.current.set(streamId, messageId);
            return [
              ...m,
              {
                kind: "react_turn" as const,
                id: messageId,
                round,
                iteration,
                thought: "",
                thoughtStreaming: true,
              },
            ];
          });
        } else if (streamKind === "llm_summary") {
          setMessages((m) => {
            const byStreamId = m.findIndex((msg) => msg.id === messageId);
            if (byStreamId >= 0) {
              opt.streamMessageIds.current.set(streamId, messageId);
              return m.map((msg, i) =>
                i === byStreamId && msg.kind === "assistant"
                  ? { ...msg, streaming: true }
                  : msg,
              );
            }
            let trailingAssistantIdx = -1;
            for (let i = m.length - 1; i >= 0; i -= 1) {
              if (m[i]?.kind === "assistant") {
                trailingAssistantIdx = i;
                break;
              }
            }
            if (trailingAssistantIdx >= 0) {
              const trailing = m[trailingAssistantIdx];
              if (trailing.kind === "assistant") {
                if (trailing.streaming) {
                  opt.streamMessageIds.current.set(streamId, trailing.id);
                  return m;
                }
                if (!trailing.text.trim()) {
                  opt.streamMessageIds.current.set(streamId, trailing.id);
                  return m.map((msg, i) =>
                    i === trailingAssistantIdx && msg.kind === "assistant"
                      ? { ...msg, streaming: true }
                      : msg,
                  );
                }
              }
            }
            opt.streamMessageIds.current.set(streamId, messageId);
            return [
              ...m,
              {
                kind: "assistant" as const,
                id: messageId,
                text: "",
                streaming: true,
              },
            ];
          });
        }
      }

      if (e.type === "llm_stream_delta" && e.stream_id && e.delta) {
        const streamId = String(e.stream_id);
        const messageId = opt.streamMessageIds.current.get(streamId);
        if (!messageId) return;
        const delta = String(e.delta);
        const prev = streamDeltaBuffer.current.get(streamId);
        streamDeltaBuffer.current.set(streamId, {
          messageId,
          streamKind,
          delta: (prev?.delta ?? "") + delta,
        });
        if (!streamFlushTimer.current) {
          streamFlushTimer.current = setTimeout(flushStreamDeltas, 50);
        }
      }

      if (e.type === "llm_stream_end" && e.stream_id) {
        const streamId = String(e.stream_id);
        if (streamFlushTimer.current) {
          clearTimeout(streamFlushTimer.current);
          flushStreamDeltas();
        }
        const messageId = opt.streamMessageIds.current.get(streamId);
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
          opt.streamMessageIds.current.delete(streamId);
        }
      }

      if (e.type === "react_action") {
        const iteration = Number(e.iteration ?? 0);
        const round = opt.chatRoundRef.current;
        const action = String(e.action ?? "");
        const actionLabel = e.action_label ? String(e.action_label) : undefined;
        const actionKind = e.action_kind
          ? (String(e.action_kind) as ActionKind)
          : undefined;
        const rawInput = e.llm_action_input ?? e.action_input;
        if (e.step_id) {
          opt.stepMasterIteration.current.set(String(e.step_id), iteration);
          opt.stepMasterRound.current.set(String(e.step_id), round);
        }
        upsertReactAction(
          round,
          iteration,
          action,
          actionLabel,
          actionKind,
          normalizeActionInput(rawInput),
        );
      }

      if (e.type === "react_action_batch") {
        const iteration = Number(e.iteration ?? 0);
        const round = opt.chatRoundRef.current;
        const batchActions = parseWsBatchActions(e.actions);
        if (batchActions && batchActions.length > 0) {
          const primary = batchActions[0];
          upsertReactAction(
            round,
            iteration,
            primary.action,
            undefined,
            inferActionKind(primary.action),
            primary.actionInput,
            batchActions,
          );
        }
      }

      if (
        e.type === "agent_react_thought" ||
        e.type === "agent_react_action" ||
        e.type === "agent_react_action_batch" ||
        e.type === "agent_react_observation" ||
        e.type === "agent_react_finished"
      ) {
        upsertSubAgentEvent(
          e as Record<string, unknown>,
          opt.chatRoundRef.current,
          opt.stepMasterIteration.current,
          opt.stepMasterRound.current,
        );
      }

      if (e.type === "a2ui_confirmation_required") {
        const req = e as unknown as A2UIConfirmationRequest;
        setMessages((m) => {
          const updated = m.map((msg) =>
            msg.kind === "a2ui_confirmation" && msg.status === "pending"
              ? { ...msg, status: "superseded" as const }
              : msg,
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

      if (e.type === "a2ui_confirmation_expired") {
        const confirmationId = String(
          (e as Record<string, unknown>).confirmation_id ?? "",
        );
        if (confirmationId) {
          setMessages((m) =>
            m.map((msg) =>
              msg.kind === "a2ui_confirmation" &&
              msg.confirmationId === confirmationId &&
              msg.status === "pending"
                ? { ...msg, status: "expired" as const }
                : msg,
            ),
          );
        }
      }

      if (e.type === "react_observation" && e.observation && showReactDetails) {
        const iteration = Number(e.iteration ?? 0);
        const round = opt.chatRoundRef.current;
        const obs = String(e.observation);
        setMessages((m) =>
          m.map((msg) =>
            msg.kind === "react_turn" &&
            msg.round === round &&
            msg.iteration === iteration
              ? { ...msg, observation: obs }
              : msg,
          ),
        );
      }

      if (e.type === "master_message" && e.content && e.source === "llm_summary") {
        const content = String(e.content).trim();
        setMessages((m) => {
          const duplicateIdx = m.findIndex(
            (msg) => msg.kind === "assistant" && msg.text.trim() === content,
          );
          const streamingIdx = m.findIndex(
            (msg) => msg.kind === "assistant" && msg.streaming,
          );
          if (duplicateIdx >= 0) {
            if (streamingIdx >= 0 && streamingIdx !== duplicateIdx) {
              return m
                .filter((_, i) => i !== streamingIdx)
                .map((msg) =>
                  msg.kind === "assistant" && msg.text.trim() === content
                    ? { ...msg, streaming: false }
                    : msg,
                );
            }
            return m.map((msg) =>
              msg.kind === "assistant" && msg.text.trim() === content
                ? { ...msg, streaming: false }
                : msg,
            );
          }
          if (streamingIdx >= 0) {
            return m.map((msg, i) =>
              i === streamingIdx && msg.kind === "assistant"
                ? { ...msg, text: content, streaming: false }
                : msg,
            );
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
    },
    [
      flushStreamDeltas,
      mergePlan,
      patchPlanStep,
      setMessages,
      setPlanViewTransition,
      updateMessage,
      upsertReactAction,
      upsertSubAgentEvent,
    ],
  );

  const flushPlanThrottle = useCallback(() => {
    planThrottleRef.current.flush();
  }, []);

  const disposePlanThrottle = useCallback(() => {
    planThrottleRef.current.dispose();
  }, []);

  return { handleWsEvent, flushPlanThrottle, disposePlanThrottle };
}
