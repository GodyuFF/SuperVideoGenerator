/**
 * 应用根：项目首页 ↔ 工作台 ↔ 配置/日志页（哈希路由）。
 */

import { useEffect } from "react";
import { useAppRoute } from "./hooks/useAppRoute";
import { useAiConfig } from "./hooks/useAiConfig";
import { AgentSettingsPage } from "./pages/AgentSettingsPage";
import { AiSettingsPage } from "./pages/AiSettingsPage";
import { LogsPage } from "./pages/LogsPage";
import { ProjectHomePage } from "./pages/ProjectHomePage";
import { Workbench } from "./pages/Workbench";

export default function App() {
  const { route, projectId, scriptId, navigate, navigateHome, navigateToProject, navigateToLogs } =
    useAppRoute();
  const ai = useAiConfig();

  useEffect(() => {
    if (route === "home" || route === "project") {
      ai.refresh();
    }
  }, [route]); // eslint-disable-line react-hooks/exhaustive-deps

  if (route === "agents") {
    return <AgentSettingsPage onBack={() => navigate("home")} />;
  }

  if (route === "settings") {
    return (
      <AiSettingsPage
        config={ai.config}
        loading={ai.loading}
        loadError={ai.error}
        onSave={ai.update}
        onBack={() => navigate("home")}
        onRefresh={ai.refresh}
      />
    );
  }

  if (route === "logs") {
    return (
      <LogsPage
        scriptId={scriptId}
        projectId={projectId}
        onBack={() => {
          if (projectId && scriptId) navigateToProject(projectId, scriptId);
          else if (projectId) navigateToProject(projectId);
          else navigateHome();
        }}
      />
    );
  }

  if (route === "project" && projectId) {
    return (
      <Workbench
        routeProjectId={projectId}
        routeScriptId={scriptId}
        aiConfig={ai.config}
        llmLoading={ai.loading}
        needsAiConfig={ai.needsAiConfig}
        onOpenSettings={() => navigate("settings")}
        onOpenAgents={() => navigate("agents")}
        onOpenLogs={() => navigateToLogs(projectId, scriptId)}
        onBackHome={navigateHome}
        onNavigateToProject={navigateToProject}
      />
    );
  }

  return (
    <ProjectHomePage
      onOpenProject={(id) => navigateToProject(id)}
      onOpenSettings={() => navigate("settings")}
      onOpenAgents={() => navigate("agents")}
      onOpenLogs={() => navigateToLogs()}
    />
  );
}
