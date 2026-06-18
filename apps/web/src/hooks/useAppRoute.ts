/** 哈希路由：#/settings 与主页切换，无需 react-router */

import { useCallback, useEffect, useState } from "react";

export type AppRoute = "chat" | "settings";

function parseHash(): AppRoute {
  const raw = window.location.hash.replace(/^#\/?/, "").trim();
  return raw === "settings" ? "settings" : "chat";
}

export function useAppRoute() {
  const [route, setRoute] = useState<AppRoute>(parseHash);

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const navigate = useCallback((target: AppRoute) => {
    window.location.hash = target === "settings" ? "#/settings" : "#/";
  }, []);

  return { route, navigate };
}
