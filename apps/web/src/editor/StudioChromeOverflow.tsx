/** 专业剪辑顶栏「更多」溢出菜单：次要操作收纳。 */

import { useEffect, useRef, useState } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
import { ShortcutsDialog } from "./opencut/actions/components/shortcuts-dialog";

interface StudioChromeOverflowProps {
  /** 是否显示「新标签页打开」。 */
  showOpenInNewTab: boolean;
  /** 打开新标签页。 */
  onOpenInNewTab: () => void;
  /** 导出 Premiere 工程包。 */
  onExportNle: () => void;
  /** NLE 导出进行中。 */
  exportingNle: boolean;
  /** NLE 导出是否可用。 */
  nleExportEnabled: boolean;
  /** 放弃修改并关闭。 */
  onCancel: () => void;
}

/** 专业剪辑顶栏溢出菜单，收纳 NLE 导出、新标签页与快捷键。 */
export function StudioChromeOverflow({
  showOpenInNewTab,
  onOpenInNewTab,
  onExportNle,
  exportingNle,
  nleExportEnabled,
  onCancel,
}: StudioChromeOverflowProps) {
  const { t } = useAppTranslation(["editor", "common", "nav", "opencut"]);
  const [open, setOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const closeAnd = (action: () => void) => {
    setOpen(false);
    action();
  };

  return (
    <>
      <div className="svf-studio-overflow" ref={rootRef}>
        <button
          type="button"
          className="btn-secondary btn-sm"
          aria-expanded={open}
          aria-haspopup="menu"
          onClick={() => setOpen((value) => !value)}
        >
          {t("editor:studioMore")}
        </button>
        {open && (
          <div className="svf-studio-overflow-menu" role="menu">
            <button
              type="button"
              role="menuitem"
              className="svf-studio-overflow-item"
              disabled={exportingNle || !nleExportEnabled}
              onClick={() => closeAnd(onExportNle)}
            >
              {exportingNle
                ? t("editor:exportNleExporting")
                : t("editor:studioExportNlePremiere")}
            </button>
            {showOpenInNewTab && (
              <button
                type="button"
                role="menuitem"
                className="svf-studio-overflow-item"
                onClick={() => closeAnd(onOpenInNewTab)}
              >
                {t("nav:openInNewTab")}
              </button>
            )}
            <button
              type="button"
              role="menuitem"
              className="svf-studio-overflow-item"
              onClick={() => closeAnd(() => setShortcutsOpen(true))}
            >
              {t("opencutDialogs:shortcuts")}
            </button>
            <div className="svf-studio-overflow-divider" role="separator" />
            <button
              type="button"
              role="menuitem"
              className="svf-studio-overflow-item svf-studio-overflow-item--danger"
              onClick={() => closeAnd(onCancel)}
            >
              {t("common:actions.cancel")}
            </button>
          </div>
        )}
      </div>
      <ShortcutsDialog isOpen={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </>
  );
}
