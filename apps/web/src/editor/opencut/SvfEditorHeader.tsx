/** SVF 定制版 OpenCut EditorHeader：保留导出/快捷键，替换退出为完成关闭。 */

import { useState } from "react";
import { Button } from "@opencut/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@opencut/components/ui/dropdown-menu";
import { ExportButton } from "@opencut/components/editor/export-button";
import { useEditor } from "@opencut/editor/use-editor";
import { CommandIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { ShortcutsDialog } from "@opencut/actions/components/shortcuts-dialog";
import { useOpencutT } from "@opencut/i18n/useOpencutT";
import { LocaleSwitcher } from "../../i18n/LocaleSwitcher";
import { ThemeToggle } from "../../components/theme/ThemeToggle";
import { useTranslation } from "react-i18next";

interface SvfEditorHeaderProps {
  /** 完成并关闭弹窗。 */
  onDone: () => void;
  /** 只读展示的剧本/项目名称。 */
  displayName?: string;
  /** standalone：外层 SVF chrome 已提供导出/完成，隐藏重复按钮。 */
  chromeMode?: "embedded" | "standalone";
}

/** SVF 弹窗内 Classic 顶栏。 */
export function SvfEditorHeader({
  onDone,
  displayName,
  chromeMode = "standalone",
}: SvfEditorHeaderProps) {
  const { tDialogs } = useOpencutT();
  const { t: tEditor } = useTranslation("editor");
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const activeProject = useEditor((e) => e.project.getActiveOrNull());
  const title = displayName || activeProject?.metadata.name || tEditor("proEditorFallback");

  return (
    <>
      <header className="bg-background svf-editor-header flex h-[3.4rem] shrink-0 items-center justify-between border-b px-3 pt-0.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="svf-studio-chrome-rec" aria-hidden />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="text-xs">
                {tDialogs("menu")}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="svf-editor-overlay-content z-[10001] w-44">
              <DropdownMenuItem
                onClick={() => setShortcutsOpen(true)}
                icon={<HugeiconsIcon icon={CommandIcon} />}
              >
                {tDialogs("shortcuts")}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onDone}>{tDialogs("doneClose")}</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <span className="truncate text-[0.9rem] font-medium" title={title}>
            {title}
          </span>
        </div>
        <nav className="flex items-center gap-2">
          <ThemeToggle />
          <LocaleSwitcher className="locale-switcher locale-switcher--compact" />
          <ExportButton />
          {chromeMode !== "standalone" && (
            <Button type="button" size="sm" variant="secondary" onClick={onDone}>
              {tDialogs("done")}
            </Button>
          )}
        </nav>
      </header>
      <ShortcutsDialog
        isOpen={shortcutsOpen}
        onOpenChange={setShortcutsOpen}
      />
    </>
  );
}
