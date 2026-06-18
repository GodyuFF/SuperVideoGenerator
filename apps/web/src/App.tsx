/**
 * 应用根：主页对话 ↔ AI 配置页（哈希路由 #/settings）。
 */

import { useEffect } from "react";
import { useAppRoute } from "./hooks/useAppRoute";
import { useLlmConfig } from "./hooks/useLlmConfig";
import { AiSettingsPage } from "./pages/AiSettingsPage";
import { Workbench } from "./pages/Workbench";

export default function App() {
  const { route, navigate } = useAppRoute();
  const llm = useLlmConfig();

  // 从配置页返回时刷新 AI 状态
  useEffect(() => {
    if (route === "chat") {
      llm.refresh();
    }
  }, [route]); // eslint-disable-line react-hooks/exhaustive-deps

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

  return (
    <Workbench
      llmConfig={llm.config}
      llmLoading={llm.loading}
      needsAiConfig={llm.needsAiConfig}
      onOpenSettings={() => navigate("settings")}
    />
  );
}
