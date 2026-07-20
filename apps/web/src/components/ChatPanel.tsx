/**
 * 对话面板子树：仅订阅 chatStore，隔离 Workbench 其它状态更新。
 */

import { useCallback } from "react";
import { ChatMessageList } from "./ChatMessageList";
import { useChatStore } from "../stores/chatStore";
import type { A2UIConfirmAck } from "../types";
import type { ChatMessage } from "../types/chat";

interface ChatPanelProps {
  showReactDetails?: boolean;
  sendConfirmation?: (
    confirmationId: string,
    approved: boolean,
    values?: Record<string, unknown>,
  ) => Promise<A2UIConfirmAck>;
  onA2uiSubmitted?: (
    messageId: string,
    values: Record<string, unknown>,
    approved: boolean,
  ) => void;
  /** 加载更早消息（分页）。 */
  hasMoreMessages?: boolean;
  loadingEarlier?: boolean;
  onLoadEarlier?: () => void;
}

/** 工作台对话消息区域。 */
export function ChatPanel({
  showReactDetails = true,
  sendConfirmation,
  onA2uiSubmitted,
  hasMoreMessages = false,
  loadingEarlier = false,
  onLoadEarlier,
}: ChatPanelProps) {
  const messages = useChatStore((s) => s.messages);
  const updateMessage = useChatStore((s) => s.updateMessage);

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
      onA2uiSubmitted?.(messageId, values, approved);
    },
    [updateMessage, onA2uiSubmitted],
  );

  /** 将 pending 确认标为 expired，解锁输入。 */
  const handleA2uiExpired = useCallback(
    (messageId: string) => {
      updateMessage(messageId, (msg) => {
        if (msg.kind !== "a2ui_confirmation" || msg.status !== "pending") {
          return msg;
        }
        return { ...msg, status: "expired" };
      });
    },
    [updateMessage],
  );

  return (
    <>
      {hasMoreMessages && onLoadEarlier && (
        <div className="chat-load-earlier">
          <button
            type="button"
            className="btn-secondary btn-sm"
            disabled={loadingEarlier}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              if (!loadingEarlier) onLoadEarlier();
            }}
          >
            {loadingEarlier ? "加载中…" : "加载更早消息"}
          </button>
        </div>
      )}
      <ChatMessageList
        messages={messages}
        showReactDetails={showReactDetails}
        sendConfirmation={sendConfirmation}
        onA2uiSubmitted={handleA2uiSubmitted}
        onA2uiExpired={handleA2uiExpired}
      />
    </>
  );
}

/** 从 store 读取消息（供 Workbench 非 UI 逻辑）。 */
export function getChatMessages(): ChatMessage[] {
  return useChatStore.getState().messages;
}
