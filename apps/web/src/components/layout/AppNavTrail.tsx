/**
 * 顶栏通用导航操作：语言切换、Agent/日志/AI 配置入口。
 */

import { useTranslation } from "react-i18next";
import { LocaleSwitcher } from "../../i18n/LocaleSwitcher";
import { ThemeToggle } from "../theme/ThemeToggle";

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

  return (
    <div className="svf-nav-actions">
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
