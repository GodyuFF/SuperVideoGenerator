/**
 * 将 API 完整时间线重建为 ChatMessageList 可渲染结构。
 */

import type { ChatMessage, ActionKind } from "../types/chat";
import type {
  ConversationTimelineItem,
  TimelineA2UIItem,
  TimelineReactTurnItem,
} from "../types/conversation";
import type { A2UIConfirmationRequest } from "../types";

function inferActionKind(action: string): ActionKind {
  if (action.startsWith("delegate_")) return "delegate";
  if (action.startsWith("tool_")) return "tool";
  if (action === "finish") return "finish";
  if (action === "ask_user_question") return "ask_user";
  return "unknown";
}

function normalizeActionInput(
  raw: Record<string, unknown> | undefined
): Record<string, string> | undefined {
  if (!raw) return undefined;
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(raw)) {
    if (value === null || value === undefined || value === "") continue;
    result[key] = typeof value === "string" ? value : JSON.stringify(value);
  }
  return Object.keys(result).length > 0 ? result : undefined;
}

function mapReactTurn(
  item: TimelineReactTurnItem,
  index: number,
  round: number
): ChatMessage {
  const action = item.action ?? "";
  return {
    kind: "react_turn",
    id: `hist-react-${round}-${item.iteration}-${index}`,
    round,
    iteration: item.iteration,
    thought: item.thought ?? "",
    action: action || undefined,
    actionKind: action ? inferActionKind(action) : undefined,
    actionInput: normalizeActionInput(item.action_input),
    observation: item.observation,
  };
}

function mapA2UI(item: TimelineA2UIItem, index: number): ChatMessage {
  const req = item.request as A2UIConfirmationRequest;
  const status =
    item.status === "submitted"
      ? "submitted"
      : item.status === "cancelled"
        ? "cancelled"
        : "pending";
  return {
    kind: "a2ui_confirmation",
    id: `hist-a2ui-${item.confirmation_id}-${index}`,
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

export function timelineToChatMessages(
  timeline: ConversationTimelineItem[]
): ChatMessage[] {
  const result: ChatMessage[] = [];
  let round = 0;
  timeline.forEach((item, index) => {
    switch (item.type) {
      case "user":
        round += 1;
        result.push({
          kind: "user",
          id: `hist-user-${index}`,
          text: item.content,
        });
        break;
      case "assistant":
        result.push({
          kind: "assistant",
          id: `hist-assistant-${index}`,
          text: item.content,
        });
        break;
      case "react_turn":
        result.push(mapReactTurn(item, index, round));
        break;
      case "sub_agent":
        result.push({
          kind: "sub_agent",
          id: `hist-sub-${item.step_id || item.agent_name}-${index}`,
          stepId: item.step_id,
          round,
          agentName: item.agent_name,
          displayName: item.display_name,
          iterations: item.iterations,
        });
        break;
      case "a2ui_confirmation":
        result.push(mapA2UI(item, index));
        break;
      default:
        break;
    }
  });
  return result;
}

export function isTimelineResponse(
  data: unknown
): data is { conversation_id: string; timeline: ConversationTimelineItem[] } {
  return (
    typeof data === "object" &&
    data !== null &&
    "timeline" in data &&
    Array.isArray((data as { timeline: unknown }).timeline)
  );
}
