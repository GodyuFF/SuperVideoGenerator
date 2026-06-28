/**
 * 应用根：主页对话 ↔ AI 配置页 ↔ 日志页（哈希路由 #/settings、#/logs）。
 */

import { useEffect } from "react";
import { useAppRoute } from "./hooks/useAppRoute";
import { useLlmConfig } from "./hooks/useLlmConfig";
import { useProject } from "./hooks/useApi";
import { AgentSettingsPage } from "./pages/AgentSettingsPage";
import { AiSettingsPage } from "./pages/AiSettingsPage";
import { LogsPage } from "./pages/LogsPage";
import { Workbench } from "./pages/Workbench";

export default function App() {
  const { route, navigate } = useAppRoute();
  const llm = useLlmConfig();
  const { projectId, scriptId } = useProject();

  // 从配置页返回时刷新 AI 状态
  useEffect(() => {
    if (route === "chat") {
      llm.refresh();
    }
  }, [route]); // eslint-disable-line react-hooks/exhaustive-deps

  if (route === "agents") {
    return <AgentSettingsPage onBack={() => navigate("chat")} />;
  }

  if (route === "settings") {
    return (
      <AiSettingsPage
        config={llm.config}
        loading={llm.loading}
        loadError={llm.error}
        onSave={llm.update}
        onBack={() => navigate("chat")}
        onRefresh={llm.refresh}
      />
    );
  }

  if (route === "logs") {
    return (
      <LogsPage
        scriptId={scriptId}
        projectId={projectId}
        onBack={() => navigate("chat")}
      />
    );
  }

  return (
    <Workbench
      llmConfig={llm.config}
      llmLoading={llm.loading}
      needsAiConfig={llm.needsAiConfig}
      onOpenSettings={() => navigate("settings")}
      onOpenAgents={() => navigate("agents")}
      onOpenLogs={() => navigate("logs")}
    />
  );
}
