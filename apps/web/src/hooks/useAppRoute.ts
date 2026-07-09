/** 哈希路由：首页 / 项目 / 设置页 */

import { useCallback, useEffect, useState } from "react";

export type AppRoute = "home" | "project" | "edit" | "settings" | "agents" | "logs";

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
  const editMatch = raw.match(/^project\/([^/]+)\/script\/([^/]+)\/edit$/);
  if (editMatch) {
    return {
      route: "edit",
      projectId: decodeURIComponent(editMatch[1]),
      scriptId: decodeURIComponent(editMatch[2]),
    };
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

function editorHash(projectId: string, scriptId: string): string {
  return `#/project/${encodeURIComponent(projectId)}/script/${encodeURIComponent(scriptId)}/edit`;
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
    const sync = () => setState(parseHash());
    window.addEventListener("hashchange", sync);
    window.addEventListener("load", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("load", sync);
    };
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

  const navigateToEditor = useCallback((projectId: string, scriptId: string) => {
    window.location.hash = editorHash(projectId, scriptId);
  }, []);

  return {
    ...state,
    navigate,
    navigateHome,
    navigateToProject,
    navigateToEditor,
    navigateToLogs,
  };
}
