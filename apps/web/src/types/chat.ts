/** 对话面板结构化消息类型 */

export type ActionKind = "delegate" | "tool" | "finish" | "unknown";

export interface UserChatMessage {
  kind: "user";
  id: string;
  text: string;
}

export interface ReactTurnMessage {
  kind: "react_turn";
  id: string;
  iteration: number;
  thought: string;
  thoughtStreaming?: boolean;
  action?: string;
  actionLabel?: string;
  actionKind?: ActionKind;
  actionInput?: Record<string, string>;
  observation?: string;
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

export type ChatMessage =
  | UserChatMessage
  | ReactTurnMessage
  | AssistantChatMessage
  | SystemChatMessage;

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
