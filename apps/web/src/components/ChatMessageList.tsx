/**
 * 对话消息列表：按 kind 分发 user / react_turn / assistant / system 渲染。
 */

import { MASTER_AGENT_NAME } from "../constants";
import type { ChatMessage } from "../types/chat";
import { ReActTurnBlock } from "./ReActTurnBlock";

interface ChatMessageListProps {
  messages: ChatMessage[];
}

export function ChatMessageList({ messages }: ChatMessageListProps) {
  return (
    <>
      {messages.map((msg) => {
        switch (msg.kind) {
          case "user":
            return (
              <div key={msg.id} className="chat-user">
                <span className="chat-role">你</span>
                <span className="chat-user-text">{msg.text}</span>
              </div>
            );
          case "react_turn":
            return <ReActTurnBlock key={msg.id} turn={msg} />;
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
    </>
  );
}
