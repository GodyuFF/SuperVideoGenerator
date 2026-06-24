/**
 * Agent 配置页：按模式管理各子 Agent 提示词，查看工具列表。
 */

import { useEffect, useState } from "react";
import { useAgentConfig } from "../hooks/useAgentConfig";
import { useProject } from "../hooks/useApi";
import type { AgentInfo } from "../types/agents";

interface AgentSettingsPageProps {
  onBack: () => void;
}

export function AgentSettingsPage({ onBack }: AgentSettingsPageProps) {
  const { projectId } = useProject();
  const { config, loading, error, refresh, update } = useAgentConfig(projectId);
  const [profiles, setProfiles] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!config) return;
    const next: Record<string, string> = {};
    for (const agent of config.agents) {
      next[agent.name] =
        config.prompt_profiles[agent.name] ?? agent.prompt_profile ?? "default";
    }
    setProfiles(next);
  }, [config]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaveMsg(null);
    setSaveError(null);
    try {
      await update({ prompt_profiles: profiles });
      setSaveMsg("Agent 提示词模式已保存。");
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function renderAgentCard(agent: AgentInfo) {
    const isOpen = expanded === agent.name;
    return (
      <article key={agent.name} className="agent-card">
        <header className="agent-card-header">
          <div>
            <strong>{agent.display_name}</strong>
            <span className="muted agent-id">{agent.name}</span>
          </div>
          <label className="agent-profile-select">
            <span>提示词模式</span>
            <select
              value={profiles[agent.name] ?? "default"}
              onChange={(e) =>
                setProfiles((p) => ({ ...p, [agent.name]: e.target.value }))
              }
            >
              {(config?.available_profiles ?? []).map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
        </header>

        <div className="agent-prompt-preview">
          <span className="field-label">当前生效 role_prompt</span>
          <p>{agent.effective_role_prompt}</p>
          {agent.action_hint && (
            <p className="muted action-hint">行动补充：{agent.action_hint}</p>
          )}
        </div>

        <button
          type="button"
          className="btn-secondary agent-tools-toggle"
          onClick={() => setExpanded(isOpen ? null : agent.name)}
        >
          {isOpen ? "收起工具" : `查看工具（${agent.tools.length}）`}
        </button>

        {isOpen && (
          <ul className="agent-tools-list">
            {agent.tools.map((tool) => (
              <li key={tool.name}>
                <code>{tool.name}</code>
                <span>{tool.description}</span>
                {tool.action && (
                  <span className="muted tool-action">→ {tool.action}</span>
                )}
              </li>
            ))}
          </ul>
        )}

        <div className="agent-pipeline muted">
          行动流水线：{agent.action_pipeline.join(" → ")}
        </div>
      </article>
    );
  }

  return (
    <div className="settings-page">
      <header className="top-bar settings-top-bar">
        <button type="button" className="btn-secondary" onClick={onBack}>
          返回对话
        </button>
        <h1>Agent 配置</h1>
      </header>

      <main className="settings-main agent-settings-main">
        {loading && <p className="muted">加载中…</p>}

        {error && (
          <div className="settings-alert error">
            <p>{error}</p>
            <button type="button" onClick={refresh}>重试</button>
          </div>
        )}

        {!loading && config && (
          <form className="settings-form" onSubmit={handleSave}>
            <p className="muted settings-intro">
              为每个子 Agent 选择提示词模式。动态图片 / AI 视频模式会在执行时自动匹配对应提示词；
              也可在此强制指定全局默认模式。
            </p>

            <div className="agent-cards">{config.agents.map(renderAgentCard)}</div>

            {saveMsg && <div className="settings-alert success">{saveMsg}</div>}
            {saveError && <div className="settings-alert error">{saveError}</div>}

            <div className="settings-actions">
              <button type="submit" disabled={saving}>
                {saving ? "保存中…" : "保存 Agent 配置"}
              </button>
            </div>
          </form>
        )}
      </main>
    </div>
  );
}
