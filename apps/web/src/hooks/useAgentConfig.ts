/** Agent 提示词工作台配置 Hook */

import { useCallback, useEffect, useState } from "react";
import { normalizeStyleModeOptions } from "../constants";
import type {
  AgentConfigPatch,
  AgentConfigResponse,
  AgentPromptResponse,
  StyleModesResponse,
  ToolsCatalogResponse,
} from "../types/agentConfig";

const API = "/api/agents";

/** 拉取与保存全局 Agent 配置、工具目录与风格列表。 */
export function useAgentConfig(_projectId: string | null) {
  const [config, setConfig] = useState<AgentConfigResponse | null>(null);
  const [toolsCatalog, setToolsCatalog] = useState<ToolsCatalogResponse | null>(null);
  const [styleModes, setStyleModes] = useState<StyleModesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [configR, toolsR, stylesR, agentsR] = await Promise.all([
        fetch(`${API}/config`),
        fetch("/api/tools"),
        fetch("/api/style-modes"),
        fetch(API),
      ]);
      if (!configR.ok) throw new Error(await configR.text());
      const globalData = await configR.json();
      const toolsData = toolsR.ok ? await toolsR.json() : { agents: {} };
      const stylesData = stylesR.ok ? await stylesR.json() : { style_modes: [] };
      const agentsData = agentsR.ok ? await agentsR.json() : { agents: [] };
      setConfig({
        prompt_profiles: globalData.prompt_profiles ?? {},
        custom_profiles: globalData.custom_profiles ?? [],
        style_modes: globalData.style_modes ?? [],
        prompt_content: globalData.prompt_content ?? {},
        tool_overrides: globalData.tool_overrides ?? {},
        custom_agents: globalData.custom_agents ?? [],
        profile_agents: globalData.profile_agents ?? {},
        tool_overrides_by_profile: globalData.tool_overrides_by_profile ?? {},
        available_profiles: globalData.available_profiles ?? [],
        config_path: globalData.config_path,
        agents: agentsData.agents ?? [],
      });
      setToolsCatalog(toolsData);
      setStyleModes({
        style_modes: normalizeStyleModeOptions(stylesData.style_modes ?? []),
      });
    } catch (err) {
      setError((err as Error).message || "加载 Agent 配置失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const update = useCallback(
    async (patch: AgentConfigPatch) => {
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
    },
    [refresh],
  );

  const fetchPrompt = useCallback(
    async (agent: string, profile: string): Promise<AgentPromptResponse> => {
      const r = await fetch(`${API}/${encodeURIComponent(agent)}/prompt?profile=${encodeURIComponent(profile)}`);
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || "加载提示词失败");
      }
      return r.json();
    },
    [],
  );

  const resetPromptOverride = useCallback(
    async (agent: string, profile: string) => {
      const r = await fetch(
        `${API}/${encodeURIComponent(agent)}/prompt/${encodeURIComponent(profile)}`,
        { method: "DELETE" },
      );
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || "重置失败");
      }
      await refresh();
      return r.json();
    },
    [refresh],
  );

  const fetchAgentsForProfile = useCallback(async (profile: string): Promise<AgentConfigResponse["agents"]> => {
    const r = await fetch(`${API}?profile=${encodeURIComponent(profile)}`);
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.detail || "加载 Agent 列表失败");
    }
    const data = await r.json();
    return data.agents ?? [];
  }, []);

  const restoreBuiltinProfile = useCallback(
    async (profileId: string) => {
      const r = await fetch(`${API}/profiles/${encodeURIComponent(profileId)}/restore`, {
        method: "POST",
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || "恢复失败");
      }
      await refresh();
      return r.json();
    },
    [refresh],
  );

  const restoreAllBuiltinProfiles = useCallback(async () => {
    const r = await fetch(`${API}/config/restore-builtin-profiles`, { method: "POST" });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.detail || "恢复失败");
    }
    await refresh();
    return r.json();
  }, [refresh]);

  return {
    config,
    toolsCatalog,
    styleModes,
    loading,
    error,
    refresh,
    update,
    fetchPrompt,
    resetPromptOverride,
    fetchAgentsForProfile,
    restoreBuiltinProfile,
    restoreAllBuiltinProfiles,
  };
}

/** 仅拉取视频风格列表（Workbench 用）。 */
export function useStyleModes() {
  const [modes, setModes] = useState<StyleModesResponse["style_modes"]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch("/api/style-modes");
        if (r.ok) {
          const data = await r.json();
          if (!cancelled) setModes(normalizeStyleModeOptions(data.style_modes ?? []));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { modes, loading };
}
