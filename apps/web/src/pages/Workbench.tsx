/**
 * 工作台：对话 + 剧本资产（主页）。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { A2UIModal } from "../components/A2UIModal";
import { GeneratedContent } from "../components/GeneratedContent";
import { MASTER_AGENT_NAME, styleModeLabel, type StyleMode } from "../constants";
import { formatApiError, useProject, useWebSocket } from "../hooks/useApi";
import type { LLMConfig, PlanStep, StepOutput, TextAsset, VideoPlan } from "../types";

const API = "/api";

type GenerationMode = "auto" | "cost_confirm";

interface ChatLine {
  id: string;
  text: string;
  streaming?: boolean;
}

interface ScriptMeta {
  style_mode?: string;
  style_locked?: boolean;
  status?: string;
  title?: string;
  content_md?: string;
}

interface WorkbenchProps {
  llmConfig: LLMConfig | null;
  llmLoading: boolean;
  needsAiConfig: boolean;
  onOpenSettings: () => void;
  onOpenLogs: () => void;
}

export function Workbench({
  llmConfig,
  llmLoading,
  needsAiConfig,
  onOpenSettings,
  onOpenLogs,
}: WorkbenchProps) {
  const { projectId, scriptId, loading, initError, bootstrap } = useProject();
  const { events, pendingConfirmation, sendConfirmation } = useWebSocket(
    projectId,
    scriptId
  );
  const [messages, setMessages] = useState<ChatLine[]>([]);
  const [input, setInput] = useState("");
  const [assets, setAssets] = useState<TextAsset[]>([]);
  const [scriptTitle, setScriptTitle] = useState("");
  const [scriptContentMd, setScriptContentMd] = useState("");
  const [videoPlan, setVideoPlan] = useState<VideoPlan | null>(null);
  const [planSteps, setPlanSteps] = useState<PlanStep[]>([]);
  const [scriptStatus, setScriptStatus] = useState("draft");
  const [generationMode, setGenerationMode] = useState<GenerationMode>("cost_confirm");
  const [styleMode, setStyleMode] = useState<StyleMode>("dynamic_image");
  const [styleLocked, setStyleLocked] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const lastEventIndex = useRef(0);
  const streamLineIds = useRef<Map<string, string>>(new Map());

  const appendLine = useCallback((line: ChatLine) => {
    setMessages((m) => [...m, line]);
  }, []);

  const appendMasterLine = useCallback(
    (text: string, streaming = false) => {
      appendLine({
        id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        text: `${MASTER_AGENT_NAME}: ${text}`,
        streaming,
      });
    },
    [appendLine]
  );

  const loadScript = useCallback(async () => {
    if (!projectId || !scriptId) return;
    const r = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}`);
    if (!r.ok) return;
    const script = (await r.json()) as ScriptMeta;
    if (script.status) setScriptStatus(script.status);
    if (script.title) setScriptTitle(script.title);
    if (script.content_md) setScriptContentMd(script.content_md);
    if (script.style_mode === "dynamic_image" || script.style_mode === "ai_video") {
      setStyleMode(script.style_mode);
    }
    setStyleLocked(Boolean(script.style_locked));
  }, [projectId, scriptId]);

  const loadVideoPlan = useCallback(async () => {
    if (!projectId || !scriptId) return;
    const r = await fetch(
      `${API}/projects/${projectId}/scripts/${scriptId}/video-plan`
    );
    if (r.ok) {
      setVideoPlan(await r.json());
    }
  }, [projectId, scriptId]);

  const loadPlan = useCallback(async () => {
    if (!projectId || !scriptId) return;
    const r = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}/plan`);
    if (r.ok) {
      const plan = await r.json();
      if (plan.steps) setPlanSteps(plan.steps as PlanStep[]);
    }
  }, [projectId, scriptId]);

  const refreshAssets = useCallback(async () => {
    if (!projectId || !scriptId) return;
    const r = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}/assets`);
    if (r.ok) setAssets(await r.json());
  }, [projectId, scriptId]);

  const refreshGeneratedContent = useCallback(async () => {
    await loadScript();
    await refreshAssets();
    await loadVideoPlan();
    await loadPlan();
  }, [loadScript, refreshAssets, loadVideoPlan, loadPlan]);

  useEffect(() => {
    if (projectId && scriptId) {
      refreshGeneratedContent();
    }
  }, [projectId, scriptId, refreshGeneratedContent]);

  useEffect(() => {
    const newEvents = events.slice(lastEventIndex.current);
    lastEventIndex.current = events.length;

    newEvents.forEach((e) => {
      if (e.type === "llm_stream_start" && e.stream_id) {
        const streamId = String(e.stream_id);
        const lineId = `stream-${streamId}`;
        streamLineIds.current.set(streamId, lineId);
        appendLine({
          id: lineId,
          text: `${MASTER_AGENT_NAME}: `,
          streaming: true,
        });
      }
      if (e.type === "llm_stream_delta" && e.stream_id && e.delta) {
        const lineId = streamLineIds.current.get(String(e.stream_id));
        if (!lineId) return;
        const delta = String(e.delta);
        setMessages((m) =>
          m.map((line) =>
            line.id === lineId ? { ...line, text: line.text + delta } : line
          )
        );
      }
      if (e.type === "llm_stream_end" && e.stream_id) {
        const streamId = String(e.stream_id);
        const lineId = streamLineIds.current.get(streamId);
        if (lineId) {
          setMessages((m) =>
            m.map((line) =>
              line.id === lineId ? { ...line, streaming: false } : line
            )
          );
          streamLineIds.current.delete(streamId);
        }
      }
      if (e.type === "master_message" && e.content && e.source === "llm_summary") {
        const content = String(e.content);
        const full = `${String(e.agent_name ?? MASTER_AGENT_NAME)}: ${content}`;
        setMessages((m) => {
          if (m.some((line) => line.text === full)) return m;
          return [
            ...m,
            {
              id: `summary-${Date.now()}`,
              text: full,
            },
          ];
        });
      }
      if (e.type === "react_thought" && e.thought && e.visibility === "user") {
        appendMasterLine(String(e.thought));
      }
      if (e.type === "script_style_locked" && e.style_mode) {
        const mode = String(e.style_mode);
        if (mode === "dynamic_image" || mode === "ai_video") {
          setStyleMode(mode);
        }
        setStyleLocked(true);
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
        const outputs = e.outputs as StepOutput[] | undefined;
        setPlanSteps((steps) =>
          steps.map((s) =>
            s.id === e.step_id
              ? { ...s, status: "completed", outputs: outputs ?? s.outputs }
              : s
          )
        );
        refreshGeneratedContent();
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
        refreshGeneratedContent();
      }
    });
  }, [events, refreshGeneratedContent, appendLine, appendMasterLine]);

  function promptConfigureAi() {
    appendLine({
      id: `sys-${Date.now()}`,
      text: "[系统] 请先配置 AI 模型与 API Key 后再开始对话。",
    });
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
        appendMasterLine(`无法连接服务（${(e as Error).message}）`);
        return;
      }
    }

    appendLine({ id: `user-${Date.now()}`, text: `你: ${text}` });
    setInput("");
    setIsRunning(true);
    lastEventIndex.current = events.length;
    streamLineIds.current.clear();

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
      const r = await postChat(pid, sid);

      if (r.status === 404) {
        appendMasterLine(
          "剧本或项目不存在（后端可能已重启）。请点击页面刷新或重新初始化后再发送。"
        );
        setIsRunning(false);
        return;
      }

      if (!r.ok) {
        const err = (await r.json().catch(() => null)) as Record<string, unknown> | null;
        appendMasterLine(`执行失败（${formatApiError(err, r.statusText)}）`);
        setIsRunning(false);
        return;
      }
      const data = await r.json();
      if (data.script?.status) setScriptStatus(data.script.status);
      if (data.script?.title) setScriptTitle(data.script.title);
      if (data.script?.content_md) setScriptContentMd(data.script.content_md);
      if (data.script?.style_locked) setStyleLocked(true);
      if (
        data.script?.style_mode === "dynamic_image" ||
        data.script?.style_mode === "ai_video"
      ) {
        setStyleMode(data.script.style_mode);
      }
      if (data.plan?.steps) setPlanSteps(data.plan.steps);
      if (data.summary) {
        const summaryText = `${MASTER_AGENT_NAME}: ${data.summary}`;
        setMessages((m) => {
          if (m.some((line) => line.text === summaryText)) return m;
          return [
            ...m,
            { id: `summary-api-${Date.now()}`, text: summaryText },
          ];
        });
      }
      await refreshGeneratedContent();
      setIsRunning(false);
    } catch {
      appendMasterLine("网络错误，请确认后端已启动（端口 8000）。");
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
          onClick={onOpenLogs}
        >
          查看日志
        </button>
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
            {messages.map((line) => (
              <div
                key={line.id}
                className={`chat-line${line.streaming ? " streaming" : ""}`}
              >
                {line.text}
              </div>
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
                  {step.outputs && step.outputs.length > 0 && (
                    <span className="step-outputs">
                      {step.outputs.map((o) => o.label).join(" · ")}
                    </span>
                  )}
                  {step.error && <span className="step-error">{step.error}</span>}
                </li>
              ))}
            </ul>
          </section>
          <section className="generated-section">
            <div className="section-header-row">
              <h3>生成内容</h3>
              <button type="button" onClick={refreshGeneratedContent}>刷新</button>
            </div>
            <GeneratedContent
              scriptTitle={scriptTitle}
              scriptContentMd={scriptContentMd}
              assets={assets}
              videoPlan={videoPlan}
              planSteps={planSteps}
            />
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
