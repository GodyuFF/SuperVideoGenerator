/**
 * 应用根：项目首页 ↔ 工作台 ↔ 配置/日志页（哈希路由）。
 */

import type { ReactNode } from "react";
import { useEffect } from "react";
import { useAppRoute } from "./hooks/useAppRoute";
import { useAiConfig } from "./hooks/useAiConfig";
import { AgentSettingsPage } from "./pages/AgentSettingsPage";
import { AiSettingsPage } from "./pages/AiSettingsPage";
import { LogsPage } from "./pages/LogsPage";
import { EditorStudioPage } from "./pages/EditorStudioPage";
import { ProjectHomePage } from "./pages/ProjectHomePage";
import { Workbench } from "./pages/Workbench";

import { LocaleProvider } from "./i18n/LocaleProvider";
import { SvfThemeProvider } from "./components/theme/SvfThemeProvider";

export default function App() {
  const { route, projectId, scriptId, navigate, navigateHome, navigateToProject, navigateToEditor, navigateToLogs } =
    useAppRoute();
  const ai = useAiConfig();

  useEffect(() => {
    if (route === "home" || route === "project") {
      ai.refresh();
    }
  }, [route]); // eslint-disable-line react-hooks/exhaustive-deps

  let content: ReactNode;

  if (route === "agents") {
    content = <AgentSettingsPage onBack={() => navigate("home")} />;
  } else if (route === "settings") {
    content = (
      <AiSettingsPage
        config={ai.config}
        loading={ai.loading}
        loadError={ai.error}
        onSave={ai.update}
        onBack={() => navigate("home")}
        onRefresh={ai.refresh}
      />
    );
  } else if (route === "logs") {
    content = (
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
  } else if (route === "edit" && projectId && scriptId) {
    content = (
      <EditorStudioPage
        projectId={projectId}
        scriptId={scriptId}
        onExit={() => navigateToProject(projectId, scriptId)}
      />
    );
  } else if (route === "project" && projectId) {
    content = (
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
  } else {
    content = (
      <ProjectHomePage
        onOpenProject={(id) => navigateToProject(id)}
        onOpenSettings={() => navigate("settings")}
        onOpenAgents={() => navigate("agents")}
        onOpenLogs={() => navigateToLogs()}
      />
    );
  }

  return (
    <SvfThemeProvider>
      <LocaleProvider>{content}</LocaleProvider>
    </SvfThemeProvider>
  );
}
