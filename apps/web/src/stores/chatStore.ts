/**
 * 工作台对话消息 Zustand Store：隔离聊天 WS 更新，避免 Workbench 整页重渲染。
 */

import { create } from "zustand";
import type {
  ActionKind,
  ChatMessage,
  ReactTurnActionItem,
  SubAgentTurnMessage,
} from "../types/chat";
import { normalizeActionInput } from "../types/chat";

/** 从 WS payload 解析同轮多 action 列表。 */
function parseBatchActions(raw: unknown): ReactTurnActionItem[] | undefined {
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

interface ChatStoreState {
  messages: ChatMessage[];
  setMessages: (updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => void;
  appendMessage: (message: ChatMessage) => void;
  updateMessage: (id: string, updater: (msg: ChatMessage) => ChatMessage) => void;
  upsertReactAction: (
    round: number,
    iteration: number,
    action: string,
    actionLabel: string | undefined,
    actionKind: ActionKind | undefined,
    actionInput: Record<string, string> | undefined,
    actions?: ReactTurnActionItem[],
  ) => void;
  upsertSubAgentEvent: (
    e: Record<string, unknown>,
    chatRound: number,
    stepMasterIteration: Map<string, number>,
    stepMasterRound: Map<string, number>,
  ) => void;
  resetMessages: () => void;
}

/** 工作台对话消息全局 Store。 */
export const useChatStore = create<ChatStoreState>((set) => ({
  messages: [],

  setMessages(updater) {
    set((state) => ({
      messages: typeof updater === "function" ? updater(state.messages) : updater,
    }));
  },

  appendMessage(message) {
    set((state) => ({ messages: [...state.messages, message] }));
  },

  updateMessage(id, updater) {
    set((state) => ({
      messages: state.messages.map((msg) => (msg.id === id ? updater(msg) : msg)),
    }));
  },

  upsertReactAction(round, iteration, action, actionLabel, actionKind, actionInput, actions) {
    set((state) => {
      const m = state.messages;
      const idx = m.findIndex(
        (msg) =>
          msg.kind === "react_turn" && msg.round === round && msg.iteration === iteration,
      );
      const primary = actions?.[0];
      const resolvedAction = action || primary?.action || "";
      const resolvedInput = actionInput ?? primary?.actionInput;
      if (idx === -1) {
        return {
          messages: [
            ...m,
            {
              kind: "react_turn" as const,
              id: `turn-${round}-${iteration}-${Date.now()}`,
              round,
              iteration,
              thought: "",
              action: resolvedAction,
              actionLabel,
              actionKind,
              actionInput: resolvedInput,
              actions,
            },
          ],
        };
      }
      return {
        messages: m.map((msg, i) =>
          i === idx && msg.kind === "react_turn"
            ? {
                ...msg,
                action: resolvedAction || msg.action,
                actionLabel: actionLabel ?? msg.actionLabel,
                actionKind: actionKind ?? msg.actionKind,
                actionInput: resolvedInput ?? msg.actionInput,
                actions: actions ?? msg.actions,
              }
            : msg,
        ),
      };
    });
  },

  upsertSubAgentEvent(e, chatRound, stepMasterIteration, stepMasterRound) {
    const stepId = e.step_id ? String(e.step_id) : "";
    if (!stepId) return;
    const eventType = String(e.type ?? "");
    const iteration = Number(e.iteration ?? 0);
    const round = chatRound;

    set((state) => {
      let m = state.messages;
      let idx = m.findIndex(
        (msg) => msg.kind === "sub_agent" && msg.stepId === stepId && msg.round === round,
      );

      if (idx === -1) {
        const masterIter = stepMasterIteration.get(stepId);
        const masterRound = stepMasterRound.get(stepId);
        const insertAt =
          masterIter !== undefined && masterRound !== undefined
            ? m.findIndex(
                (msg) =>
                  msg.kind === "react_turn" &&
                  msg.round === masterRound &&
                  msg.iteration === masterIter,
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
      if (block.kind !== "sub_agent") return state;

      const updated: SubAgentTurnMessage = { ...block };

      if (eventType === "agent_react_finished") {
        updated.finished = {
          iterations: Number(e.iterations ?? iteration),
          outputCount: Number(e.output_count ?? 0),
        };
        return { messages: m.map((msg, i) => (i === idx ? updated : msg)) };
      }

      const iterIdx = updated.iterations.findIndex((it) => it.iteration === iteration);
      const iter =
        iterIdx >= 0 ? { ...updated.iterations[iterIdx] } : { iteration };

      if (eventType === "agent_react_thought" && e.thought) {
        iter.thought = String(e.thought);
      }
      if (eventType === "agent_react_action_batch") {
        const batchActions = parseBatchActions(e.actions);
        if (batchActions) {
          iter.actions = batchActions;
          iter.action = batchActions[0]?.action ?? "";
          iter.actionInput = batchActions[0]?.actionInput;
        }
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
      }

      if (iterIdx >= 0) {
        updated.iterations = updated.iterations.map((it, i) =>
          i === iterIdx ? iter : it,
        );
      } else {
        updated.iterations = [...updated.iterations, iter];
      }

      if (e.agent_name) updated.agentName = String(e.agent_name);
      if (e.agent_display_name) {
        updated.displayName = String(e.agent_display_name);
      }

      return { messages: m.map((msg, i) => (i === idx ? updated : msg)) };
    });
  },

  resetMessages() {
    set({ messages: [] });
  },
}));
