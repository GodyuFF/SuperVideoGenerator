/** 对话面板结构化消息类型 */

import type { A2UIConfirmationRequest } from "../types";

export type ActionKind = "delegate" | "tool" | "finish" | "ask_user" | "unknown";

export interface UserChatMessage {
  kind: "user";
  id: string;
  text: string;
  skillId?: string;
}

/** 同轮 ReAct 中的单条 tool 行动（batch 时使用）。 */
export interface ReactTurnActionItem {
  action: string;
  actionInput?: Record<string, string>;
  observation?: string;
}

export interface ReactTurnMessage {
  kind: "react_turn";
  id: string;
  /** 用户第几轮发言（同一 conversation 内 monotonic） */
  round: number;
  iteration: number;
  thought: string;
  thoughtStreaming?: boolean;
  action?: string;
  actionLabel?: string;
  actionKind?: ActionKind;
  actionInput?: Record<string, string>;
  /** 同轮并行多个 tool 时的明细（单 tool 时仍用 action/actionInput） */
  actions?: ReactTurnActionItem[];
  observation?: string;
}

export interface SubAgentIteration {
  iteration: number;
  thought?: string;
  action?: string;
  actionInput?: Record<string, string>;
  /** 同轮并行多个 tool 时的明细 */
  actions?: ReactTurnActionItem[];
  observation?: string;
}

export interface SubAgentTurnMessage {
  kind: "sub_agent";
  id: string;
  stepId: string;
  /** 所属主编排轮次（与用户发言轮次对齐） */
  round: number;
  agentName: string;
  displayName: string;
  iterations: SubAgentIteration[];
  finished?: { iterations: number; outputCount: number };
}

export interface AssistantChatMessage {
  kind: "assistant";
  id: string;
  text: string;
  streaming?: boolean;
}

export interface SystemChatMessage {
  kind: "system";
  id: string;
  text: string;
}

export type A2UIConfirmationStatus =
  | "pending"
  | "submitted"
  | "cancelled"
  | "superseded"
  | "expired";

export interface A2UIChatMessage {
  kind: "a2ui_confirmation";
  id: string;
  confirmationId: string;
  request: A2UIConfirmationRequest;
  status: A2UIConfirmationStatus;
  submittedValues?: Record<string, unknown>;
}

export type ChatMessage =
  | UserChatMessage
  | ReactTurnMessage
  | SubAgentTurnMessage
  | AssistantChatMessage
  | SystemChatMessage
  | A2UIChatMessage;

/** 将 WebSocket 事件中的 action_input 规范为字符串键值对 */
export function normalizeActionInput(
  raw: unknown
): Record<string, string> | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (value === null || value === undefined || value === "") continue;
    result[key] = typeof value === "string" ? value : JSON.stringify(value);
  }
  return Object.keys(result).length > 0 ? result : undefined;
}
