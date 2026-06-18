/** LLM 配置：拉取与更新 /api/llm/config */

import { useCallback, useEffect, useState } from "react";
import { formatApiError } from "./useApi";
import type { LLMConfig, LLMConfigPatch } from "../types";

const API = "/api/llm";

export function useLlmConfig() {
  const [config, setConfig] = useState<LLMConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const r = await fetch(`${API}/config`);
      if (!r.ok) {
        const err = (await r.json().catch(() => null)) as Record<string, unknown> | null;
        throw new Error(formatApiError(err, r.statusText));
      }
      setConfig(await r.json());
    } catch (e) {
      setError((e as Error).message || "加载 AI 配置失败");
      // 保留已有配置，避免保存后刷新失败又变回「未配置」
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const update = useCallback(async (patch: LLMConfigPatch) => {
    setError(null);
    const r = await fetch(`${API}/config`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (!r.ok) {
      const err = (await r.json().catch(() => null)) as Record<string, unknown> | null;
      throw new Error(formatApiError(err, r.statusText));
    }
    const data = (await r.json()) as LLMConfig;
    setConfig(data);
    return data;
  }, []);

  const isAiReady = Boolean(config?.llm_active);
  // 仅在确认加载完成且缺少 Key 时拦截对话
  const needsAiConfig = Boolean(
    !loading && config?.use_llm_react && !config?.has_api_key
  );

  return { config, loading, error, refresh, update, isAiReady, needsAiConfig };
}
