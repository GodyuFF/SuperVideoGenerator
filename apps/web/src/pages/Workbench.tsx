/**
 * 工作台：对话 + 剧本资产（主页）。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { A2UIModal } from "../components/A2UIModal";
import { MASTER_AGENT_NAME, styleModeLabel, type StyleMode } from "../constants";
import { formatApiError, useProject, useWebSocket } from "../hooks/useApi";
import type { LLMConfig, PlanStep, TextAsset, WsEvent } from "../types";

const API = "/api";

type GenerationMode = "auto" | "cost_confirm";

interface ScriptMeta {
  style_mode?: string;
  style_locked?: boolean;
  status?: string;
}

interface WorkbenchProps {
  llmConfig: LLMConfig | null;
  llmLoading: boolean;
  needsAiConfig: boolean;
  onOpenSettings: () => void;
}

export function Workbench({
  llmConfig,
  llmLoading,
  needsAiConfig,
  onOpenSettings,
}: WorkbenchProps) {
  const { projectId, scriptId, loading, initError, bootstrap } = useProject();
  const { events, pendingConfirmation, sendConfirmation } = useWebSocket(
    projectId,
    scriptId
  );
  const [messages, setMessages] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [assets, setAssets] = useState<TextAsset[]>([]);
  const [planSteps, setPlanSteps] = useState<PlanStep[]>([]);
  const [scriptStatus, setScriptStatus] = useState("draft");
  const [generationMode, setGenerationMode] = useState<GenerationMode>("cost_confirm");
  const [styleMode, setStyleMode] = useState<StyleMode>("dynamic_image");
  const [styleLocked, setStyleLocked] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const lastEventIndex = useRef(0);

  const loadScript = useCallback(async () => {
    if (!projectId || !scriptId) return;
    const r = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}`);
    if (!r.ok) return;
    const script = (await r.json()) as ScriptMeta;
    if (script.status) setScriptStatus(script.status);
    if (script.style_mode === "dynamic_image" || script.style_mode === "ai_video") {
      setStyleMode(script.style_mode);
    }
    setStyleLocked(Boolean(script.style_locked));
  }, [projectId, scriptId]);

  useEffect(() => {
    loadScript();
  }, [loadScript]);

  const refreshAssets = useCallback(async () => {
    if (!projectId || !scriptId) return;
    const r = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}/assets`);
    if (r.ok) setAssets(await r.json());
  }, [projectId, scriptId]);

  useEffect(() => {
    const newEvents = events.slice(lastEventIndex.current);
    lastEventIndex.current = events.length;

    newEvents.forEach((e) => {
      if (e.type === "master_message" && e.content) {
        const name = String(e.agent_name ?? MASTER_AGENT_NAME);
        setMessages((m) => [...m, `${name}: ${String(e.content)}`]);
      }
      if (e.type === "script_style_locked" && e.style_mode) {
        const mode = String(e.style_mode);
        if (mode === "dynamic_image" || mode === "ai_video") {
          setStyleMode(mode);
        }
        setStyleLocked(true);
        setMessages((m) => [
          ...m,
          `[系统] 视频风格已绑定：${styleModeLabel(mode)}（不可修改）`,
        ]);
      }
      if (e.type === "planning_started") {
        setScriptStatus("planning");
      }
      if (e.type === "plan_ready" && e.plan) {
        const plan = e.plan as { steps: PlanStep[] };
        setPlanSteps(plan.steps ?? []);
        setScriptStatus((prev) => (prev === "executing" ? prev : "planned"));
      }
      if (e.type === "react_started" || e.type === "execution_started") {
        setScriptStatus("executing");
      }
      if (e.type === "step_started") {
        setPlanSteps((steps) =>
          steps.map((s) =>
            s.id === e.step_id ? { ...s, status: "running" } : s
          )
        );
      }
      if (e.type === "step_completed") {
        setPlanSteps((steps) =>
          steps.map((s) =>
            s.id === e.step_id ? { ...s, status: "completed" } : s
          )
        );
        refreshAssets();
      }
      if (e.type === "step_failed") {
        setPlanSteps((steps) =>
          steps.map((s) =>
            s.id === e.step_id
              ? { ...s, status: "failed", error: String(e.error) }
              : s
          )
        );
      }
      if (e.type === "project_completed") {
        setScriptStatus("completed");
        setIsRunning(false);
      }
      if (e.type === "execution_failed") {
        setScriptStatus("failed");
        setIsRunning(false);
      }
      if (e.type === "step_awaiting_confirmation") {
        setMessages((m) => [
          ...m,
          `[待确认] 视频生成费用 $${Number(e.estimated_cost_usd).toFixed(2)}`,
        ]);
      }
      if (e.type === "interaction_log" && e.record) {
        const rec = e.record as { kind?: string; summary?: string; source?: string };
        if (rec.kind === "react_rule_fallback") {
          setMessages((m) => [
            ...m,
            `[系统] ${String(rec.summary ?? "规则回退，未调用真实 LLM")}`,
          ]);
        }
      }
    });
  }, [events, refreshAssets]);

  const [interactionStats, setInteractionStats] = useState<{
    llm_real_calls: number;
    react_rule_fallback: number;
    agent_mock_action: number;
  } | null>(null);

  const refreshInteractionStats = useCallback(async () => {
    if (!scriptId) return;
    const r = await fetch(`${API}/interactions/stats?script_id=${scriptId}`);
    if (r.ok) setInteractionStats(await r.json());
  }, [scriptId]);

  useEffect(() => {
    refreshInteractionStats();
  }, [refreshInteractionStats, isRunning]);

  function promptConfigureAi() {
    setMessages((m) => [
      ...m,
      "[系统] 请先配置 AI 模型与 API Key 后再开始对话。",
    ]);
    onOpenSettings();
  }

  async function sendChat() {
    const text = input.trim();
    if (!text || isRunning) return;

    if (needsAiConfig) {
      promptConfigureAi();
      return;
    }

    let pid = projectId;
    let sid = scriptId;
    if (!pid || !sid) {
      try {
        const ids = await bootstrap();
        if (!ids) return;
        pid = ids.projectId;
        sid = ids.scriptId;
      } catch (e) {
        setMessages((m) => [
          ...m,
          `${MASTER_AGENT_NAME}: 无法连接服务（${(e as Error).message}）`,
        ]);
        return;
      }
    }

    setMessages((m) => [...m, `你: ${text}`]);
    setInput("");
    setIsRunning(true);
    lastEventIndex.current = 0;

    const postChat = async (p: string, s: string) =>
      fetch(`${API}/projects/${p}/scripts/${s}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          generation_mode: generationMode,
          ...(styleLocked ? {} : { style_mode: styleMode }),
        }),
      });

    try {
      let r = await postChat(pid, sid);

      if (r.status === 404) {
        const ids = await bootstrap();
        if (ids) {
          pid = ids.projectId;
          sid = ids.scriptId;
          r = await postChat(pid, sid);
          setMessages((m) => [
            ...m,
            "[系统] 已重新连接服务并创建新剧本，继续执行…",
          ]);
        }
      }

      if (!r.ok) {
        const err = (await r.json().catch(() => null)) as Record<string, unknown> | null;
        setMessages((m) => [
          ...m,
          `${MASTER_AGENT_NAME}: 执行失败（${formatApiError(err, r.statusText)}）`,
        ]);
        setIsRunning(false);
        return;
      }
      const data = await r.json();
      if (data.script?.status) setScriptStatus(data.script.status);
      if (data.script?.style_locked) setStyleLocked(true);
      if (
        data.script?.style_mode === "dynamic_image" ||
        data.script?.style_mode === "ai_video"
      ) {
        setStyleMode(data.script.style_mode);
      }
      if (data.plan?.steps) setPlanSteps(data.plan.steps);
      await refreshAssets();
      await refreshInteractionStats();
      setIsRunning(false);
    } catch {
      setMessages((m) => [
        ...m,
        `${MASTER_AGENT_NAME}: 网络错误，请确认后端已启动（端口 8000）。`,
      ]);
      setIsRunning(false);
    }
  }

  if (loading) return <div className="loading">加载中…</div>;

  if (initError) {
    return (
      <div className="loading">
        <p>初始化失败：{initError}</p>
        <p className="muted">请先启动后端：<code>uvicorn apps.api.main:app --port 8000</code></p>
        <button type="button" onClick={() => bootstrap()}>重试</button>
      </div>
    );
  }

  const aiBadgeClass = needsAiConfig ? "ai-missing" : "ai-ready";
  const aiBadgeText = llmLoading
    ? "AI 检查中…"
    : needsAiConfig
      ? "未配置 AI"
      : llmConfig?.llm_active
        ? `AI: ${llmConfig.provider_label}`
        : "规则模式";

  return (
    <div className="workbench">
      <header className="top-bar">
        <h1>SuperVideoGenerator</h1>
        <span className={`status-badge ${aiBadgeClass}`}>{aiBadgeText}</span>
        <span className="status-badge">{scriptStatus}</span>
        {styleLocked && (
          <span className="status-badge style-locked">
            风格：{styleModeLabel(styleMode)}（已锁定）
          </span>
        )}
        {isRunning && (
          <span className="status-badge running">{MASTER_AGENT_NAME} 执行中…</span>
        )}
        <div className="top-bar-spacer" />
        <button
          type="button"
          className="btn-secondary btn-config"
          onClick={onOpenSettings}
        >
          AI 配置
        </button>
      </header>

      {needsAiConfig && !llmLoading && (
        <div className="ai-config-banner">
          <p>
            尚未配置 AI 模型与 API Key，无法使用 ReAct 智能编排。
            请填写 API Key 后点击<strong>「保存配置」</strong>或<strong>「保存并返回对话」</strong>。
          </p>
          <button type="button" onClick={onOpenSettings}>去配置 AI</button>
        </div>
      )}

      {llmLoading && (
        <div className="ai-config-banner loading-banner">
          <p>正在检查 AI 配置…</p>
        </div>
      )}

      <div className="main-split">
        <aside className="chat-panel">
          <h2>对话</h2>
          <p className="muted chat-hint">
            首次发送将绑定视频风格并生成剧本；风格锁定后不可更改。
          </p>
          <div className="config-bar">
            <label>
              生成模式
              <select
                value={generationMode}
                disabled={isRunning}
                onChange={(e) =>
                  setGenerationMode(e.target.value as GenerationMode)
                }
              >
                <option value="cost_confirm">费用确认模式</option>
                <option value="auto">自动生成模式</option>
              </select>
            </label>
            <label>
              视频风格
              {styleLocked ? (
                <span className="locked-style">{styleModeLabel(styleMode)}（已锁定）</span>
              ) : (
                <select
                  value={styleMode}
                  disabled={isRunning}
                  onChange={(e) => setStyleMode(e.target.value as StyleMode)}
                >
                  <option value="dynamic_image">动态图片模式</option>
                  <option value="ai_video">AI 视频模式</option>
                </select>
              )}
            </label>
          </div>
          <div className="chat-log">
            {messages.map((msg, i) => (
              <div key={i} className="chat-line">{msg}</div>
            ))}
          </div>
          <div className="chat-input-row">
            <input
              value={input}
              disabled={isRunning || needsAiConfig || llmLoading}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                needsAiConfig
                  ? "请先配置 AI 模型…"
                  : "描述你的视频创意…"
              }
              onKeyDown={(e) => {
                if (e.key === "Enter" && !isRunning) {
                  if (needsAiConfig) promptConfigureAi();
                  else sendChat();
                }
              }}
            />
            <button
              type="button"
              onClick={needsAiConfig ? promptConfigureAi : sendChat}
              disabled={isRunning || llmLoading || (!needsAiConfig && !input.trim())}
            >
              {isRunning ? "执行中…" : needsAiConfig ? "配置 AI" : "发送"}
            </button>
          </div>
          <div className="event-log">
            <h3>事件日志（含子 Agent ReAct）</h3>
            {events.slice(-12).map((e, i) => (
              <div key={i} className="event-line">
                {e.type === "interaction_log"
                  ? `📋 ${String((e.record as { summary?: string })?.summary ?? e.type)}`
                  : e.type === "agent_react_thought" || e.type === "agent_react_action"
                    ? `${String(e.agent_display_name ?? e.agent_name)} · ${String(e.type)}`
                    : String(e.type)}
              </div>
            ))}
          </div>
        </aside>

        <main className="script-panel">
          <h2>剧本与资产</h2>
          <section className="plan-section">
            <h3>执行计划（{MASTER_AGENT_NAME} 自动编排）</h3>
            {planSteps.length === 0 && (
              <p className="muted">发送对话后，{MASTER_AGENT_NAME} 将在此展示子 Agent 执行进度</p>
            )}
            <ul className="plan-list">
              {planSteps.map((step) => (
                <li key={step.id} className={`plan-item status-${step.status}`}>
                  <span className="step-type">{step.type}</span>
                  <span>{step.title}</span>
                  <span className="step-status">{step.status}</span>
                  {step.error && <span className="step-error">{step.error}</span>}
                </li>
              ))}
            </ul>
          </section>
          <section className="interaction-section">
            <h3>接口交互记录（持久化）</h3>
            <button type="button" onClick={refreshInteractionStats}>刷新统计</button>
            {interactionStats && (
              <p className="muted interaction-stats">
                真实 LLM 调用：<strong>{interactionStats.llm_real_calls}</strong>
                · 规则回退：<strong>{interactionStats.react_rule_fallback}</strong>
                · Mock 动作：<strong>{interactionStats.agent_mock_action}</strong>
              </p>
            )}
            {interactionStats && interactionStats.llm_real_calls === 0 && (
              <p className="warn-text">
                本次剧本尚无真实 LLM 调用记录，可能在使用规则回退。请确认 API Key 已保存。
              </p>
            )}
          </section>
          <section className="asset-section">
            <h3>资产库</h3>
            <button type="button" onClick={refreshAssets}>刷新</button>
            {assets.length === 0 && <p className="muted">子 Agent 执行后显示资产</p>}
            <ul className="asset-list">
              {assets.map((a) => (
                <li key={a.id} className="asset-item">
                  <code>{a.id}</code>
                  <strong>{a.name}</strong>
                  <span className="asset-type">{a.type}</span>
                  <span className="asset-scope">{a.scope}</span>
                </li>
              ))}
            </ul>
          </section>
        </main>
      </div>

      {pendingConfirmation && (
        <A2UIModal
          request={pendingConfirmation}
          onConfirm={(values) =>
            sendConfirmation(pendingConfirmation.confirmation_id, true, values)
          }
          onCancel={() =>
            sendConfirmation(pendingConfirmation.confirmation_id, false)
          }
        />
      )}
    </div>
  );
}
