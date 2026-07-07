/** 统一 AI 配置：拉取与更新 /api/ai/config */

import { useCallback, useEffect, useState } from "react";
import { formatApiError } from "./useApi";
import type { AiConfig, AiConfigPatch } from "../types";

const API = "/api/ai";

export function useAiConfig() {
  const [config, setConfig] = useState<AiConfig | null>(null);
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
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const update = useCallback(async (patch: AiConfigPatch) => {
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
    const data = (await r.json()) as AiConfig;
    setConfig(data);
    return data;
  }, []);

  const isAiReady = Boolean(config?.llm.llm_active);
  const needsAiConfig = Boolean(
    !loading && config?.llm.use_llm_react && !config?.llm.has_api_key
  );

  return { config, loading, error, refresh, update, isAiReady, needsAiConfig };
}

/** @deprecated 使用 useAiConfig */
export const useLlmConfig = useAiConfig;
