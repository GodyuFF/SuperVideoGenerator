/** 完整对话时间线 API 响应类型 */

import type { A2UIConfirmationRequest } from "../types";
import type { ActionKind, SubAgentIteration } from "./chat";

export type A2UIHistoryStatus =
  | "pending"
  | "submitted"
  | "cancelled"
  | "expired";

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

export interface TimelineReactActionItem {
  action: string;
  action_input?: Record<string, unknown>;
  observation?: string;
}

export interface TimelineReactTurnItem {
  type: "react_turn";
  iteration: number;
  thought?: string;
  action?: string;
  action_input?: Record<string, unknown>;
  /** 同轮多 tool 并行时的明细 */
  actions?: TimelineReactActionItem[];
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
  has_more?: boolean;
  /** 本页 raw 消息窗口最早时间，供 before 游标前进。 */
  oldest_created_at?: string | null;
}

/** 对话摘要列表项 */
export interface ConversationSummary {
  id: string;
  title?: string;
  created_at?: string;
  updated_at?: string;
  message_count?: number;
  script_id?: string | null;
  last_summary?: string;
  last_round_token_usage?: { total_tokens?: number };
  /** 当前对话激活的 Skill id（跨轮保持） */
  active_skill_id?: string;
}
