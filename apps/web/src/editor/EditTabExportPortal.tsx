/** 将 OpenCut ExportButton 挂载到剪辑 Tab 顶栏导出槽（须在 EditorProvider 内渲染）。 */

import { createPortal } from "react-dom";
import { ExportButton } from "./opencut/components/editor/export-button";

interface EditTabExportPortalProps {
  /** 顶栏导出按钮挂载点（EditTabSimpleView / EditorStudioContent header 内空 div）。 */
  host: HTMLElement | null;
  /** 导出按钮展示场景。 */
  surface?: "cinema" | "studio";
}

/** 通过 Portal 在 SVF 顶栏展示浏览器导出控件。 */
export function EditTabExportPortal({
  host,
  surface = "cinema",
}: EditTabExportPortalProps) {
  if (!host) return null;
  return createPortal(
    <div className="edit-cinema-export-portal">
      <ExportButton surface={surface} />
    </div>,
    host,
  );
}
