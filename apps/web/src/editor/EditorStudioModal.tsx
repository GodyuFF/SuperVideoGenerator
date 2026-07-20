/** 全屏专业剪辑弹窗：OpenCut Classic 完整编辑器（Portal 渲染）。 */

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { Toaster } from "@opencut/components/ui/sonner";
import { EditorStudioContent } from "./EditorStudioContent";
import type { EditTimelineApi } from "../edit/useEditTimeline";

interface EditorStudioModalProps {
  projectId: string;
  scriptId: string;
  timelineApi: EditTimelineApi;
  onClose: (saved: boolean) => void;
}

/** 专业剪辑全屏弹窗容器（挂载至 document.body）。 */
export function EditorStudioModal({
  projectId,
  scriptId,
  timelineApi,
  onClose,
}: EditorStudioModalProps) {
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  const overlay = (
    <div className="editor-studio-modal-overlay" role="dialog" aria-modal="true">
      <Toaster position="top-center" style={{ zIndex: 10002 }} />
      <div className="editor-studio-modal editor-studio-modal-fullscreen">
        <EditorStudioContent
          projectId={projectId}
          scriptId={scriptId}
          timelineApi={timelineApi}
          onClose={onClose}
          showOpenInNewTab
          shellClassName="editor-studio-modal-shell"
        />
      </div>
    </div>
  );

  return createPortal(overlay, document.body);
}
