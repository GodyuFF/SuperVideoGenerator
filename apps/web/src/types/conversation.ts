/** 完整对话时间线 API 响应类型 */

import type { A2UIConfirmationRequest } from "../types";
import type { ActionKind, SubAgentIteration } from "./chat";

export type A2UIHistoryStatus = "pending" | "submitted" | "cancelled";

export interface TimelineUserItem {
  type: "user";
  content: string;
  created_at: string;
}

export interface TimelineAssistantItem {
  type: "assistant";
  content: string;
  created_at: string;
}

export interface TimelineReactTurnItem {
  type: "react_turn";
  iteration: number;
  thought?: string;
  action?: string;
  action_input?: Record<string, unknown>;
  observation?: string;
  created_at: string;
}

export interface TimelineSubAgentItem {
  type: "sub_agent";
  step_id: string;
  agent_name: string;
  display_name: string;
  iterations: SubAgentIteration[];
  created_at: string;
}

export interface TimelineA2UIItem {
  type: "a2ui_confirmation";
  confirmation_id: string;
  request: A2UIConfirmationRequest;
  status: A2UIHistoryStatus;
  submitted_values: Record<string, unknown>;
  created_at: string;
}

export type ConversationTimelineItem =
  | TimelineUserItem
  | TimelineAssistantItem
  | TimelineReactTurnItem
  | TimelineSubAgentItem
  | TimelineA2UIItem;

export interface ConversationTimelineResponse {
  conversation_id: string;
  timeline: ConversationTimelineItem[];
}

/** 兼容旧 API 的用户可见消息 */
export interface ConversationMessageRecord {
  role: "user" | "assistant";
  content: string;
  created_at: string;
}
