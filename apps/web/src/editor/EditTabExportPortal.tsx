/** 将 OpenCut ExportButton 挂载到剪辑 Tab / 工作室顶栏导出槽（须在 EditorProvider 内渲染）。 */

import { useLayoutEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  ExportButton,
  type ExportButtonSurface,
} from "./opencut/components/editor/export-button";

interface EditTabExportPortalProps {
  /** 顶栏导出按钮挂载点（EditTabSimpleView / EditorStudioContent header 内空 div）。 */
  host: HTMLElement | null;
  /** 导出按钮展示场景。 */
  surface?: ExportButtonSurface;
}

/**
 * 通过 Portal 在 SVF 顶栏展示浏览器导出控件。
 * 在 React 管理的 slot 内再挂一层非 Fiber 子节点作为 Portal 容器，
 * 避免 Portal 卸载与 slot host 的 removeChild 顺序冲突。
 */
export function EditTabExportPortal({
  host,
  surface = "cinema",
}: EditTabExportPortalProps) {
  const [portalMount, setPortalMount] = useState<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    if (!host) {
      setPortalMount(null);
      return;
    }

    const mount = document.createElement("div");
    mount.className = "edit-cinema-export-portal-mount";
    host.appendChild(mount);
    setPortalMount(mount);

    return () => {
      // 先让后续 commit 把 Portal 从该 mount 卸下；DOM 节点在微任务中再摘除。
      setPortalMount(null);
      queueMicrotask(() => {
        mount.remove();
      });
    };
  }, [host]);

  if (!portalMount) return null;

  return createPortal(
    <div className="edit-cinema-export-portal">
      <ExportButton surface={surface} />
    </div>,
    portalMount,
  );
}
