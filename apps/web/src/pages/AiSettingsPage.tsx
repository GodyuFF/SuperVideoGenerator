/**
 * AI 模型配置页：服务商、模型、API Key 等。
 */

import { useEffect, useState } from "react";
import type { LLMConfig, LLMConfigPatch } from "../types";

interface AiSettingsPageProps {
  config: LLMConfig | null;
  loading: boolean;
  loadError: string | null;
  onSave: (patch: LLMConfigPatch) => Promise<LLMConfig>;
  onBack: () => void;
  onRefresh: () => void;
}

export function AiSettingsPage({
  config,
  loading,
  loadError,
  onSave,
  onBack,
  onRefresh,
}: AiSettingsPageProps) {
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [useLlmReact, setUseLlmReact] = useState(true);
  const [temperature, setTemperature] = useState(0.2);
  const [maxTokens, setMaxTokens] = useState(1024);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!config) return;
    setProvider(config.provider);
    setModel(config.model);
    setBaseUrl(config.base_url);
    setUseLlmReact(config.use_llm_react);
    setTemperature(config.temperature);
    setMaxTokens(config.max_tokens);
    setApiKey("");
  }, [config]);

  const selectedProvider = config?.available_providers.find((p) => p.id === provider);

  function handleProviderChange(id: string) {
    setProvider(id);
    const p = config?.available_providers.find((x) => x.id === id);
    if (p) setModel(p.default_model);
  }

  async function saveConfig(andBack = false) {
    setSaving(true);
    setSaveMsg(null);
    setSaveError(null);
    try {
      const patch: LLMConfigPatch = {
        provider,
        model,
        base_url: baseUrl || undefined,
        use_llm_react: useLlmReact,
        temperature,
        max_tokens: maxTokens,
      };
      if (apiKey.trim()) {
        patch.api_key = apiKey.trim();
      } else if (useLlmReact && !config?.has_api_key) {
        setSaveError("启用 LLM ReAct 时必须填写 API Key");
        setSaving(false);
        return false;
      }
      const updated = await onSave(patch);
      setSaveMsg(
        updated.llm_active
          ? "保存成功，AI 已就绪，可以返回对话。"
          : "已保存。请填写 API Key 并启用 LLM ReAct。"
      );
      setApiKey("");
      if (andBack && updated.llm_active) {
        onBack();
      }
      return true;
    } catch (err) {
      setSaveError((err as Error).message || "保存失败");
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await saveConfig(false);
  }

  async function handleSaveAndBack() {
    await saveConfig(true);
  }

  return (
    <div className="settings-page">
      <header className="top-bar settings-top-bar">
        <button type="button" className="btn-secondary" onClick={onBack}>
          返回对话
        </button>
        <h1>AI 模型配置</h1>
        {config && (
          <span
            className={`status-badge ${config.llm_active ? "ai-ready" : "ai-missing"}`}
          >
            {config.llm_active ? "AI 已配置" : "未配置 API Key"}
          </span>
        )}
      </header>

      <main className="settings-main">
        {loading && <p className="muted">加载配置中…</p>}

        {loadError && (
          <div className="settings-alert error">
            <p>{loadError}</p>
            <button type="button" onClick={onRefresh}>重试</button>
          </div>
        )}

        {!loading && config && (
          <form className="settings-form" onSubmit={handleSubmit}>
            <p className="muted settings-intro">
              ReAct 编排通过 XML 与所选大模型交互。默认 DeepSeek，可切换 OpenAI、Kimi、
              智谱、通义等 OpenAI 兼容接口。
            </p>

            <label className="settings-field">
              <span>服务商</span>
              <select
                value={provider}
                onChange={(e) => handleProviderChange(e.target.value)}
              >
                {config.available_providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}（默认 {p.default_model}）
                  </option>
                ))}
              </select>
            </label>

            <label className="settings-field">
              <span>模型名称</span>
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={selectedProvider?.default_model ?? "model-id"}
              />
            </label>

            <label className="settings-field">
              <span>API Key</span>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={
                  config.has_api_key ? "已配置（留空不修改）" : "请输入 API Key"
                }
                autoComplete="off"
              />
              <span className="field-hint">
                Key 仅保存在服务端内存，重启后端后需重新填写或通过环境变量配置
              </span>
            </label>

            <label className="settings-field">
              <span>API Base URL（可选）</span>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={config.base_url}
              />
            </label>

            <label className="settings-field checkbox-row">
              <input
                type="checkbox"
                checked={useLlmReact}
                onChange={(e) => setUseLlmReact(e.target.checked)}
              />
              <span>启用 LLM ReAct（关闭后使用规则回退，无需 Key）</span>
            </label>

            <div className="settings-row">
              <label className="settings-field">
                <span>Temperature</span>
                <input
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
                  value={temperature}
                  onChange={(e) => setTemperature(Number(e.target.value))}
                />
              </label>
              <label className="settings-field">
                <span>Max Tokens</span>
                <input
                  type="number"
                  min={256}
                  max={8192}
                  step={256}
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(Number(e.target.value))}
                />
              </label>
            </div>

            {saveMsg && <div className="settings-alert success">{saveMsg}</div>}
            {saveError && <div className="settings-alert error">{saveError}</div>}

            <div className="settings-actions">
              <button type="submit" disabled={saving}>
                {saving ? "保存中…" : "保存配置"}
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={saving}
                onClick={handleSaveAndBack}
              >
                {saving ? "保存中…" : "保存并返回对话"}
              </button>
            </div>
          </form>
        )}
      </main>
    </div>
  );
}
