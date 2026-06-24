/** 哈希路由：#/settings 与主页切换，无需 react-router */

import { useCallback, useEffect, useState } from "react";

export type AppRoute = "chat" | "settings" | "agents" | "logs";

function parseHash(): AppRoute {
  const raw = window.location.hash.replace(/^#\/?/, "").trim();
  if (raw === "settings") return "settings";
  if (raw === "agents") return "agents";
  if (raw === "logs") return "logs";
  return "chat";
}

export function useAppRoute() {
  const [route, setRoute] = useState<AppRoute>(parseHash);

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
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

  return { route, navigate };
}
