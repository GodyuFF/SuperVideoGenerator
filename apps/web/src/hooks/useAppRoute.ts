/** 哈希路由：首页 / 项目 / 设置页 */

import { useCallback, useEffect, useState } from "react";

export type AppRoute = "home" | "project" | "settings" | "agents" | "logs";

export interface AppRouteState {
  route: AppRoute;
  projectId: string | null;
  scriptId: string | null;
}

function parseHash(): AppRouteState {
  const raw = window.location.hash.replace(/^#\/?/, "").trim();
  if (raw === "settings") {
    return { route: "settings", projectId: null, scriptId: null };
  }
  if (raw === "agents") {
    return { route: "agents", projectId: null, scriptId: null };
  }
  const scriptLogsMatch = raw.match(/^project\/([^/]+)\/script\/([^/]+)\/logs$/);
  if (scriptLogsMatch) {
    return {
      route: "logs",
      projectId: decodeURIComponent(scriptLogsMatch[1]),
      scriptId: decodeURIComponent(scriptLogsMatch[2]),
    };
  }
  const projectLogsMatch = raw.match(/^project\/([^/]+)\/logs$/);
  if (projectLogsMatch) {
    return {
      route: "logs",
      projectId: decodeURIComponent(projectLogsMatch[1]),
      scriptId: null,
    };
  }
  if (raw === "logs") {
    return { route: "logs", projectId: null, scriptId: null };
  }
  const projectMatch = raw.match(/^project\/([^/]+)(?:\/script\/([^/]+))?$/);
  if (projectMatch) {
    return {
      route: "project",
      projectId: decodeURIComponent(projectMatch[1]),
      scriptId: projectMatch[2] ? decodeURIComponent(projectMatch[2]) : null,
    };
  }
  return { route: "home", projectId: null, scriptId: null };
}

function projectHash(projectId: string, scriptId?: string | null): string {
  if (scriptId) {
    return `#/project/${encodeURIComponent(projectId)}/script/${encodeURIComponent(scriptId)}`;
  }
  return `#/project/${encodeURIComponent(projectId)}`;
}

export function useAppRoute() {
  const [state, setState] = useState<AppRouteState>(parseHash);

  useEffect(() => {
    const onHash = () => setState(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const navigate = useCallback((target: AppRoute) => {
    const hash =
      target === "settings"
        ? "#/settings"
        : target === "agents"
          ? "#/agents"
          : target === "logs"
            ? "#/logs"
            : "#/";
    window.location.hash = hash;
  }, []);

  const navigateHome = useCallback(() => {
    window.location.hash = "#/";
  }, []);

  const navigateToProject = useCallback(
    (projectId: string, scriptId?: string | null) => {
      window.location.hash = projectHash(projectId, scriptId);
    },
    []
  );

  const navigateToLogs = useCallback(
    (projectId?: string | null, scriptId?: string | null) => {
      if (projectId && scriptId) {
        window.location.hash = `#/project/${encodeURIComponent(projectId)}/script/${encodeURIComponent(scriptId)}/logs`;
      } else if (projectId) {
        window.location.hash = `#/project/${encodeURIComponent(projectId)}/logs`;
      } else {
        window.location.hash = "#/logs";
      }
    },
    []
  );

  return {
    ...state,
    navigate,
    navigateHome,
    navigateToProject,
    navigateToLogs,
  };
}
