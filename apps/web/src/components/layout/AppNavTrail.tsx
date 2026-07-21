/**
 * 顶栏通用导航操作：GitHub 外链、语言切换、Agent/日志/AI 配置入口。
 */

import type { MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import { LocaleSwitcher } from "../../i18n/LocaleSwitcher";
import { openInSystemBrowser } from "../../desktop/svfDesktop";
import { ThemeToggle } from "../theme/ThemeToggle";

/** 本仓库 GitHub 地址（源码 / Releases / Issues）。 */
export const GITHUB_REPO_URL = "https://github.com/GodyuFF/SuperVideoGenerator";

export interface AppNavTrailProps {
  /** 打开 Agent 配置页。 */
  onOpenAgents?: () => void;
  /** 打开交互日志页。 */
  onOpenLogs?: () => void;
  /** 打开 EditTimeline 可视化调试页。 */
  onOpenEditTimelineViz?: () => void;
  /** 打开 AI 配置页。 */
  onOpenSettings?: () => void;
}

/** 渲染顶栏右侧的标准导航按钮组。 */
export function AppNavTrail({
  onOpenAgents,
  onOpenLogs,
  onOpenEditTimelineViz,
  onOpenSettings,
}: AppNavTrailProps) {
  const { t } = useTranslation();

  /** 拦截默认导航，强制用系统浏览器打开仓库。 */
  const handleGithubClick = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    void openInSystemBrowser(GITHUB_REPO_URL);
  };

  return (
    <div className="svf-nav-actions">
      <a
        className="btn-secondary btn-config svf-github-link"
        href={GITHUB_REPO_URL}
        target="_blank"
        rel="noopener noreferrer"
        title={t("githubRepo", { ns: "nav" })}
        aria-label={t("githubRepo", { ns: "nav" })}
        onClick={handleGithubClick}
      >
        <svg
          className="svf-github-link__icon"
          viewBox="0 0 16 16"
          width="14"
          height="14"
          aria-hidden
        >
          <path
            fill="currentColor"
            d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"
          />
        </svg>
        <span>{t("github", { ns: "nav" })}</span>
      </a>
      <ThemeToggle />
      <LocaleSwitcher />
      {onOpenAgents && (
        <button type="button" className="btn-secondary btn-config" onClick={onOpenAgents}>
          {t("agentConfig", { ns: "nav" })}
        </button>
      )}
      {onOpenLogs && (
        <button type="button" className="btn-secondary btn-config" onClick={onOpenLogs}>
          {t("viewLogs", { ns: "nav" })}
        </button>
      )}
      {onOpenEditTimelineViz && (
        <button type="button" className="btn-secondary btn-config" onClick={onOpenEditTimelineViz}>
          EditTimeline 可视化
        </button>
      )}
      {onOpenSettings && (
        <button type="button" className="btn-secondary btn-config" onClick={onOpenSettings}>
          {t("aiConfig", { ns: "nav" })}
        </button>
      )}
    </div>
  );
}
