/**
 * 将 API 完整时间线重建为 ChatMessageList 可渲染结构。
 */

import type { ChatMessage, ActionKind, ReactTurnMessage } from "../types/chat";
import type {
  ConversationTimelineItem,
  TimelineA2UIItem,
  TimelineReactTurnItem,
} from "../types/conversation";
import type { A2UIConfirmationRequest } from "../types";

/** 从时间线条目取 created_at（缺省为空串）。 */
function itemCreatedAt(item: ConversationTimelineItem): string {
  return "created_at" in item && item.created_at ? String(item.created_at) : "";
}

/** 本页时间线中最早的 created_at，作分页 before 回退游标。 */
export function earliestCreatedAtFromTimeline(
  timeline: ConversationTimelineItem[],
): string | null {
  let min: string | null = null;
  for (const item of timeline) {
    const t = itemCreatedAt(item);
    if (!t) continue;
    if (!min || t < min) min = t;
  }
  return min;
}

function inferActionKind(action: string): ActionKind {
  if (action === "delegate_agent" || action.startsWith("delegate_")) return "delegate";
  if (action.startsWith("tool_")) return "tool";
  if (action === "finish") return "finish";
  if (action === "ask_user_question") return "ask_user";
  return "unknown";
}

/** 规范化 action_input 为字符串字典。 */
function normalizeActionInput(
  raw: Record<string, unknown> | undefined,
): Record<string, string> | undefined {
  if (!raw) return undefined;
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(raw)) {
    if (value === null || value === undefined || value === "") continue;
    result[key] = typeof value === "string" ? value : JSON.stringify(value);
  }
  return Object.keys(result).length > 0 ? result : undefined;
}

/** 将时间线 ReAct 轮次映射为前端消息。 */
function mapReactTurn(
  item: TimelineReactTurnItem,
  index: number,
  round: number,
): ChatMessage {
  const action = item.action ?? "";
  const batchActions =
    item.actions && item.actions.length > 1
      ? item.actions.map((a) => ({
          action: a.action,
          actionInput: normalizeActionInput(a.action_input),
          observation: a.observation,
        }))
      : undefined;
  const created = itemCreatedAt(item) || `idx-${index}`;
  return {
    kind: "react_turn",
    id: `hist-react-${created}-${item.iteration}`,
    round,
    iteration: item.iteration,
    thought: item.thought ?? "",
    action: batchActions?.[0]?.action ?? (action || undefined),
    actionKind: action ? inferActionKind(action) : undefined,
    actionInput:
      normalizeActionInput(item.action_input) ?? batchActions?.[0]?.actionInput,
    actions: batchActions,
    observation: item.observation,
  };
}

/** 将时间线 A2UI 确认映射为前端消息。 */
function mapA2UI(item: TimelineA2UIItem, index: number): ChatMessage {
  const req = item.request as A2UIConfirmationRequest;
  const status =
    item.status === "submitted"
      ? "submitted"
      : item.status === "cancelled"
        ? "cancelled"
        : item.status === "expired"
          ? "expired"
          : "pending";
  const created = itemCreatedAt(item) || `idx-${index}`;
  return {
    kind: "a2ui_confirmation",
    id: `hist-a2ui-${item.confirmation_id}-${created}`,
    confirmationId: item.confirmation_id,
    request: {
      ...req,
      type: "a2ui_confirmation_required",
      confirmation_id: item.confirmation_id,
    },
    status,
    submittedValues: item.submitted_values,
  };
}

/** 合并同一 round/iteration 的两条 ReAct 轮次，保留字段更完整的一条。 */
function mergeReactTurn(a: ReactTurnMessage, b: ReactTurnMessage): ReactTurnMessage {
  const pickLonger = (left?: string, right?: string): string | undefined => {
    const l = left?.trim() ?? "";
    const r = right?.trim() ?? "";
    if (!l) return right;
    if (!r) return left;
    return r.length > l.length ? right : left;
  };
  return {
    ...a,
    thought: pickLonger(a.thought, b.thought) ?? "",
    action: a.action || b.action,
    actionLabel: a.actionLabel || b.actionLabel,
    actionKind: a.actionKind || b.actionKind,
    actionInput: a.actionInput ?? b.actionInput,
    observation: pickLonger(a.observation, b.observation),
  };
}

/** React 去重键：历史消息用稳定 id，实时 WS 仍用 round:iteration。 */
function reactDedupeKey(msg: ReactTurnMessage): string {
  if (msg.id.startsWith("hist-")) return msg.id;
  return `${msg.round}:${msg.iteration}`;
}

/** 去除时间线重建后可能重复的 ReAct 轮次与助手摘要。 */
export function dedupeChatMessages(messages: ChatMessage[]): ChatMessage[] {
  const result: ChatMessage[] = [];
  const reactIndexByKey = new Map<string, number>();
  const assistantTexts = new Set<string>();
  const seenIds = new Set<string>();

  for (const msg of messages) {
    if (msg.id && seenIds.has(msg.id)) continue;
    if (msg.id) seenIds.add(msg.id);

    if (msg.kind === "react_turn") {
      const key = reactDedupeKey(msg);
      const existingIdx = reactIndexByKey.get(key);
      if (existingIdx !== undefined) {
        const existing = result[existingIdx];
        if (existing.kind === "react_turn") {
          result[existingIdx] = mergeReactTurn(existing, msg);
        }
        continue;
      }
      reactIndexByKey.set(key, result.length);
      result.push(msg);
      continue;
    }

    if (msg.kind === "assistant") {
      const text = msg.text.trim();
      if (text) {
        if (assistantTexts.has(text)) continue;
        assistantTexts.add(text);
      }
    }

    result.push(msg);
  }

  return result;
}

/**
 * 按用户消息顺序重算 round，避免分页拼接后 round 从 1 重起导致 ReAct 误合并。
 */
export function reassignChatRounds(messages: ChatMessage[]): ChatMessage[] {
  let round = 0;
  return messages.map((msg) => {
    if (msg.kind === "user") {
      round += 1;
      return msg;
    }
    if (msg.kind === "react_turn" || msg.kind === "sub_agent") {
      return { ...msg, round };
    }
    return msg;
  });
}

/** 将 API timeline 转为 ChatMessage[]（单页；round 仅页内相对值，拼接后须 reassign）。 */
export function timelineToChatMessages(
  timeline: ConversationTimelineItem[],
): ChatMessage[] {
  const result: ChatMessage[] = [];
  let round = 0;
  timeline.forEach((item, index) => {
    const created = itemCreatedAt(item) || `idx-${index}`;
    switch (item.type) {
      case "user":
        round += 1;
        result.push({
          kind: "user",
          id: `hist-user-${created}-${round}`,
          text: item.content,
        });
        break;
      case "assistant":
        result.push({
          kind: "assistant",
          id: `hist-assistant-${created}`,
          text: item.content,
        });
        break;
      case "react_turn":
        result.push(mapReactTurn(item, index, round));
        break;
      case "sub_agent":
        result.push({
          kind: "sub_agent",
          id: `hist-sub-${item.step_id || item.agent_name}-${created}`,
          stepId: item.step_id,
          round,
          agentName: item.agent_name,
          displayName: item.display_name,
          iterations: (item.iterations || []).map((it) => {
            const raw = it as unknown as Record<string, unknown>;
            const ai =
              normalizeActionInput(raw.action_input as Record<string, unknown> | undefined) ??
              it.actionInput;
            const batchRaw = raw.actions;
            const actions =
              Array.isArray(batchRaw) && batchRaw.length > 1
                ? batchRaw.map((entry) => {
                    const rec = entry as Record<string, unknown>;
                    return {
                      action: String(rec.action ?? ""),
                      actionInput: normalizeActionInput(
                        rec.action_input as Record<string, unknown> | undefined,
                      ),
                      observation: rec.observation ? String(rec.observation) : undefined,
                    };
                  })
                : undefined;
            return { ...it, actionInput: ai, actions };
          }),
        });
        break;
      case "a2ui_confirmation":
        result.push(mapA2UI(item, index));
        break;
      default:
        break;
    }
  });
  return dedupeChatMessages(result);
}

/** 判断响应是否为完整时间线结构。 */
export function isTimelineResponse(
  data: unknown,
): data is {
  conversation_id: string;
  timeline: ConversationTimelineItem[];
  has_more?: boolean;
  oldest_created_at?: string | null;
} {
  return (
    typeof data === "object" &&
    data !== null &&
    "timeline" in data &&
    Array.isArray((data as { timeline: unknown }).timeline)
  );
}
