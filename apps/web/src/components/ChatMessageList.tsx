/**
 * 对话消息列表：按 kind 分发 user / react_turn / a2ui / assistant / system 渲染。
 */

import { useEffect, useRef } from "react";
import { MASTER_AGENT_NAME } from "../constants";
import type { ChatMessage } from "../types/chat";
import { A2UIInlineCard } from "./A2UIInlineCard";
import { ReActTurnBlock } from "./ReActTurnBlock";
import { SubAgentBlock } from "./SubAgentBlock";

interface ChatMessageListProps {
  messages: ChatMessage[];
  /** false 时 ReAct/子 Agent 仅展示工具名称 */
  showReactDetails?: boolean;
  sendConfirmation?: (
    confirmationId: string,
    approved: boolean,
    values?: Record<string, unknown>
  ) => Promise<boolean>;
  onA2uiSubmitted?: (
    messageId: string,
    values: Record<string, unknown>,
    approved: boolean
  ) => void;
}

export function ChatMessageList({
  messages,
  showReactDetails = true,
  sendConfirmation,
  onA2uiSubmitted,
}: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const isStreaming = showReactDetails
    ? messages.some(
        (msg) =>
          (msg.kind === "assistant" && msg.streaming) ||
          (msg.kind === "react_turn" && msg.thoughtStreaming)
      )
    : messages.some((msg) => msg.kind === "assistant" && msg.streaming);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: isStreaming ? "auto" : "smooth",
      block: "end",
    });
  }, [messages, isStreaming]);

  return (
    <>
      {messages.map((msg) => {
        switch (msg.kind) {
          case "user":
            return (
              <div key={msg.id} className="chat-user">
                <span className="chat-role">你</span>
                {msg.skillId && (
                  <span className="skill-badge">Skill: {msg.skillId}</span>
                )}
                <span className="chat-user-text">{msg.text}</span>
              </div>
            );
          case "react_turn":
            return (
              <ReActTurnBlock
                key={msg.id}
                turn={msg}
                showDetails={showReactDetails}
              />
            );
          case "sub_agent":
            return (
              <SubAgentBlock
                key={msg.id}
                block={msg}
                showDetails={showReactDetails}
              />
            );
          case "a2ui_confirmation":
            if (!sendConfirmation || !onA2uiSubmitted) return null;
            return (
              <A2UIInlineCard
                key={msg.id}
                message={msg}
                sendConfirmation={sendConfirmation}
                onSubmitted={onA2uiSubmitted}
              />
            );
          case "assistant":
            return (
              <div
                key={msg.id}
                className={`chat-assistant${msg.streaming ? " streaming" : ""}`}
              >
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
            return (
              <div key={msg.id} className="chat-system">
                {msg.text}
              </div>
            );
          default:
            return null;
        }
      })}
      <div ref={bottomRef} className="chat-log-anchor" aria-hidden />
    </>
  );
}
