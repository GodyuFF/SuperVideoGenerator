/** Agent 提示词模式配置 */

import { useCallback, useEffect, useState } from "react";
import type { AgentConfigPatch, AgentConfigResponse } from "../types/agents";

const API = "/api/agents";

export function useAgentConfig(projectId: string | null) {
  const [config, setConfig] = useState<AgentConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (projectId) params.set("project_id", projectId);
      const qs = params.toString();
      const r = await fetch(`${API}${qs ? `?${qs}` : ""}`);
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      const globalR = await fetch(`${API}/config`);
      const globalData = globalR.ok ? await globalR.json() : {};
      setConfig({
        prompt_profiles: globalData.prompt_profiles ?? {},
        available_profiles: data.available_profiles ?? globalData.available_profiles ?? [],
        agents: data.agents ?? [],
      });
    } catch (err) {
      setError((err as Error).message || "加载 Agent 配置失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const update = useCallback(async (patch: AgentConfigPatch) => {
    const r = await fetch(`${API}/config`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.detail || "保存失败");
    }
    await refresh();
    return r.json();
  }, [refresh]);

  return { config, loading, error, refresh, update };
}
