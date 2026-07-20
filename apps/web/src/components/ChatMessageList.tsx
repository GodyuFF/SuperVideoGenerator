/**
 * 对话消息列表：按 kind 分发渲染；长对话虚拟化以降低 DOM 压力。
 */

import { memo, useEffect, useRef } from "react";
import { Virtuoso } from "react-virtuoso";
import { MASTER_AGENT_NAME } from "../constants";
import { logPerf } from "../lib/perfLog";
import type { A2UIConfirmAck } from "../types";
import type { ChatMessage } from "../types/chat";
import { A2UIInlineCard } from "./A2UIInlineCard";
import { ReActTurnBlock } from "./ReActTurnBlock";
import { SubAgentBlock } from "./SubAgentBlock";

const VIRTUALIZE_THRESHOLD = 30;

interface ChatMessageListProps {
  messages: ChatMessage[];
  /** false 时 ReAct/子 Agent 仅展示工具名称 */
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
  onA2uiExpired?: (messageId: string) => void;
}

/** 渲染单条聊天消息。 */
function ChatMessageRow({
  msg,
  showReactDetails,
  sendConfirmation,
  onA2uiSubmitted,
  onA2uiExpired,
}: {
  msg: ChatMessage;
  showReactDetails: boolean;
  sendConfirmation?: ChatMessageListProps["sendConfirmation"];
  onA2uiSubmitted?: ChatMessageListProps["onA2uiSubmitted"];
  onA2uiExpired?: ChatMessageListProps["onA2uiExpired"];
}) {
  switch (msg.kind) {
    case "user":
      return (
        <div className="chat-user">
          <span className="chat-role">你</span>
          {msg.skillId && <span className="skill-badge">Skill: {msg.skillId}</span>}
          <span className="chat-user-text">{msg.text}</span>
        </div>
      );
    case "react_turn":
      return <ReActTurnBlock turn={msg} showDetails={showReactDetails} />;
    case "sub_agent":
      return <SubAgentBlock block={msg} showDetails={showReactDetails} />;
    case "a2ui_confirmation":
      if (!sendConfirmation || !onA2uiSubmitted) return null;
      return (
        <A2UIInlineCard
          message={msg}
          sendConfirmation={sendConfirmation}
          onSubmitted={onA2uiSubmitted}
          onExpired={onA2uiExpired}
        />
      );
    case "assistant":
      return (
        <div className={`chat-assistant${msg.streaming ? " streaming" : ""}`}>
          <span className="chat-role">{MASTER_AGENT_NAME}</span>
          <div className="chat-assistant-body">
            {msg.text}
            {msg.streaming && !msg.text && (
              <span className="chat-assistant-placeholder">正在生成回复…</span>
            )}
          </div>
        </div>
      );
    case "system":
      return <div className="chat-system">{msg.text}</div>;
    default:
      return null;
  }
}

export const ChatMessageList = memo(function ChatMessageList({
  messages,
  showReactDetails = true,
  sendConfirmation,
  onA2uiSubmitted,
  onA2uiExpired,
}: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRafRef = useRef<number | null>(null);
  const lastMessageIdRef = useRef<string | null>(null);
  const renderCountRef = useRef(0);

  const isStreaming = showReactDetails
    ? messages.some(
        (msg) =>
          (msg.kind === "assistant" && msg.streaming) ||
          (msg.kind === "react_turn" && msg.thoughtStreaming),
      )
    : messages.some((msg) => msg.kind === "assistant" && msg.streaming);

  const lastId = messages.length > 0 ? messages[messages.length - 1]?.id ?? null : null;
  const useVirtual = messages.length >= VIRTUALIZE_THRESHOLD;

  useEffect(() => {
    renderCountRef.current += 1;
    if (renderCountRef.current % 10 === 0) {
      logPerf("workbench", "ChatMessageList_render", {
        count: renderCountRef.current,
        message_count: messages.length,
        virtualized: useVirtual,
      });
    }
  });

  useEffect(() => {
    if (useVirtual) return;
    if (lastId === lastMessageIdRef.current && !isStreaming) return;
    lastMessageIdRef.current = lastId;
    if (scrollRafRef.current !== null) {
      cancelAnimationFrame(scrollRafRef.current);
    }
    scrollRafRef.current = requestAnimationFrame(() => {
      scrollRafRef.current = null;
      bottomRef.current?.scrollIntoView({
        behavior: isStreaming ? "auto" : "smooth",
        block: "end",
      });
    });
    return () => {
      if (scrollRafRef.current !== null) {
        cancelAnimationFrame(scrollRafRef.current);
        scrollRafRef.current = null;
      }
    };
  }, [messages, isStreaming, lastId, useVirtual]);

  if (useVirtual) {
    return (
      <Virtuoso
        className="chat-virtuoso"
        data={messages}
        computeItemKey={(_, msg) => msg.id}
        followOutput={isStreaming ? "smooth" : false}
        increaseViewportBy={{ top: 200, bottom: 400 }}
        itemContent={(_, msg) => (
          <div className="chat-virtuoso-item">
            <ChatMessageRow
              msg={msg}
              showReactDetails={showReactDetails}
              sendConfirmation={sendConfirmation}
              onA2uiSubmitted={onA2uiSubmitted}
              onA2uiExpired={onA2uiExpired}
            />
          </div>
        )}
      />
    );
  }

  return (
    <>
      {messages.map((msg) => (
        <ChatMessageRow
          key={msg.id}
          msg={msg}
          showReactDetails={showReactDetails}
          sendConfirmation={sendConfirmation}
          onA2uiSubmitted={onA2uiSubmitted}
          onA2uiExpired={onA2uiExpired}
        />
      ))}
      <div ref={bottomRef} className="chat-log-anchor" aria-hidden />
    </>
  );
});
