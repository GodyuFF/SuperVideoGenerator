/** 完整 OpenCut Classic Shell：顶栏 + 四区布局 + 可选引导。 */

import { ClassicEditorLayout, DegradedRendererBanner } from "./ClassicEditorLayout";
import { SvfEditorHeader } from "./SvfEditorHeader";
import { TooltipProvider } from "@opencut/components/ui/tooltip";
import { Onboarding } from "@opencut/components/editor/onboarding";
import { useSvfOpencutThemeScope } from "./useSvfOpencutThemeScope";
import { useResolvedSvfTheme } from "../../hooks/useResolvedSvfTheme";

interface SvfClassicEditorShellProps {
  onDone: () => void;
  displayName?: string;
  chromeMode?: "embedded" | "standalone";
}

/** SVF 弹窗内完整 Classic 编辑器外壳（含 TooltipProvider 与主题）。 */
export function SvfClassicEditorShell({
  onDone,
  displayName,
  chromeMode = "standalone",
}: SvfClassicEditorShellProps) {
  useSvfOpencutThemeScope(true);
  const themeClass = useResolvedSvfTheme();

  return (
    <TooltipProvider delayDuration={300}>
      <div
        className={`svf-opencut-theme opencut-classic-root ${themeClass} flex h-full min-h-0 w-full flex-col overflow-hidden`}
      >
        <DegradedRendererBanner />
        {chromeMode !== "standalone" && (
          <SvfEditorHeader onDone={onDone} displayName={displayName} chromeMode={chromeMode} />
        )}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <ClassicEditorLayout embedded />
        </div>
        <Onboarding />
      </div>
    </TooltipProvider>
  );
}
