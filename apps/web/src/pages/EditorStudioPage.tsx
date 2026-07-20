/** 全屏独立剪辑页（哈希 #/project/.../script/.../edit）。 */

import { useEffect } from "react";
import { Toaster } from "../editor/opencut/components/ui/sonner";
import { useEditTimeline } from "../edit/useEditTimeline";
import { EditorStudioContent } from "../editor/EditorStudioContent";
import { bindEditWsEvents, unbindEditWsEvents } from "../editor/editWsBinding";
import { prefetchClassicStudio } from "../editor/classicPrefetch";
import { notifyOpenerTimelineReload } from "../editor/editorStudioUrls";

interface EditorStudioPageProps {
  projectId: string;
  scriptId: string;
  onExit: () => void;
}

/** 独立路由下的 OpenCut Classic 专业剪辑全屏页。 */
export function EditorStudioPage({ projectId, scriptId, onExit }: EditorStudioPageProps) {
  const timelineApi = useEditTimeline(projectId, scriptId, { enabled: true });

  useEffect(() => {
    void prefetchClassicStudio();
    bindEditWsEvents(projectId, scriptId);
    document.body.style.overflow = "hidden";
    document.title = `专业剪辑 · ${scriptId}`;
    return () => {
      unbindEditWsEvents(projectId, scriptId);
      document.body.style.overflow = "";
      document.title = "SuperVideoGenerator";
    };
  }, [projectId, scriptId]);

  /** 保存后通知 opener 刷新；若由新标签打开则尝试关闭窗口。 */
  const handleClose = (saved: boolean) => {
    if (saved) {
      notifyOpenerTimelineReload(scriptId);
    }
    if (window.opener && !window.opener.closed) {
      window.close();
      return;
    }
    onExit();
  };

  return (
    <div className="editor-studio-page">
      <Toaster position="top-center" style={{ zIndex: 10002 }} />
      <EditorStudioContent
        projectId={projectId}
        scriptId={scriptId}
        timelineApi={timelineApi}
        onClose={handleClose}
        showOpenInNewTab={false}
        shellClassName="editor-studio-page-shell"
      />
    </div>
  );
}
