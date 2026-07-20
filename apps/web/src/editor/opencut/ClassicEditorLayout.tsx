/** Classic 编辑器主布局（移植自 opencut-classic EditorLayout）。 */



import {

  ResizablePanelGroup,

  ResizablePanel,

  ResizableHandle,

} from "@opencut/components/ui/resizable";

import { AssetsPanel } from "@opencut/components/editor/panels/assets";

import { PropertiesPanel } from "@opencut/components/editor/panels/properties";

import { Timeline } from "@opencut/timeline/components";

import { PreviewPanel } from "@opencut/preview/components";

import { usePanelStore } from "@opencut/editor/panel-store";

import { usePasteMedia } from "@opencut/media/use-paste-media";

import { useMemo, useState } from "react";

import { useResolvedSvfTheme } from "../../hooks/useResolvedSvfTheme";

import { useEditor } from "@opencut/editor/use-editor";

import {
  getSvfProjectMediaCache,
  getMediaHydrationIssues,
  listMediaHydrationMessageKeys,
} from "../adapter/SvfMediaBridge";

import { useAppTranslation } from "../../i18n/useAppTranslation";

import {

  createPreviewOverlayControl,

  isPreviewOverlayVisible,

  mergePreviewOverlaySources,

} from "@opencut/preview/overlays";

import { usePreviewStore } from "@opencut/preview/preview-store";

import { getGuidePreviewOverlaySource } from "@opencut/guides";

import {

  bookmarkNotesPreviewOverlay,

  getBookmarkPreviewOverlaySource,

} from "@opencut/timeline/bookmarks/index";



interface ClassicEditorLayoutProps {

  /** 嵌入 SVF Shell 时不重复外层容器样式。 */

  embedded?: boolean;

}



/** OpenCut Classic 四区布局。 */

export function ClassicEditorLayout({ embedded = false }: ClassicEditorLayoutProps) {

  usePasteMedia();

  const themeClass = useResolvedSvfTheme();

  const { panels, setPanel } = usePanelStore();

  const activeScene = useEditor((editor) => editor.scenes.getActiveSceneOrNull());

  const currentTime = useEditor((editor) => editor.playback.getCurrentTime());

  const activeGuide = usePreviewStore((state) => state.activeGuide);

  const overlays = usePreviewStore((state) => state.overlays);

  const setOverlayVisibility = usePreviewStore((state) => state.setOverlayVisibility);

  const showBookmarkNotes = isPreviewOverlayVisible({

    overlay: bookmarkNotesPreviewOverlay,

    overlays,

  });



  const overlaySource = useMemo(

    () =>

      mergePreviewOverlaySources({

        sources: [

          getGuidePreviewOverlaySource({ guideId: activeGuide }),

          activeScene

            ? getBookmarkPreviewOverlaySource({

                bookmarks: activeScene.bookmarks,

                time: currentTime,

                isVisible: showBookmarkNotes,

              })

            : {

                definitions: [bookmarkNotesPreviewOverlay],

                instances: [],

              },

        ],

      }),

    [activeGuide, activeScene, currentTime, showBookmarkNotes],

  );



  const overlayControls = useMemo(

    () =>

      overlaySource.definitions.map((overlay) =>

        createPreviewOverlayControl({ overlay, overlays }),

      ),

    [overlaySource.definitions, overlays],

  );



  const layout = (

    <ResizablePanelGroup

      direction="vertical"

      className="size-full gap-[0.18rem]"

      onLayout={(sizes) => {

        const mainSize = sizes[0] ?? panels.mainContent;

        const timelineSize = sizes[1] ?? panels.timeline;

        if (Math.abs(mainSize - panels.mainContent) > 0.05) {

          setPanel({ panel: "mainContent", size: mainSize });

        }

        if (Math.abs(timelineSize - panels.timeline) > 0.05) {

          setPanel({ panel: "timeline", size: timelineSize });

        }

      }}

    >

      <ResizablePanel defaultSize={panels.mainContent} minSize={30} maxSize={85} className="min-h-0">

        <ResizablePanelGroup

          direction="horizontal"

          className="size-full gap-[0.19rem] px-3"

          onLayout={(sizes) => {

            const toolsSize = sizes[0] ?? panels.tools;

            const previewSize = sizes[1] ?? panels.preview;

            const propertiesSize = sizes[2] ?? panels.properties;

            if (Math.abs(toolsSize - panels.tools) > 0.05) {

              setPanel({ panel: "tools", size: toolsSize });

            }

            if (Math.abs(previewSize - panels.preview) > 0.05) {

              setPanel({ panel: "preview", size: previewSize });

            }

            if (Math.abs(propertiesSize - panels.properties) > 0.05) {

              setPanel({ panel: "properties", size: propertiesSize });

            }

          }}

        >

          <ResizablePanel defaultSize={panels.tools} minSize={15} maxSize={40} className="min-w-0">

            <AssetsPanel />

          </ResizablePanel>

          <ResizableHandle withHandle />

          <ResizablePanel defaultSize={panels.preview} minSize={30} className="min-h-0 min-w-0 flex-1">

            <PreviewPanel

              overlayControls={overlayControls}

              overlayInstances={overlaySource.instances}

              onOverlayVisibilityChange={setOverlayVisibility}

            />

          </ResizablePanel>

          <ResizableHandle withHandle />

          <ResizablePanel defaultSize={panels.properties} minSize={15} maxSize={40} className="min-w-0">

            <PropertiesPanel />

          </ResizablePanel>

        </ResizablePanelGroup>

      </ResizablePanel>

      <ResizableHandle withHandle />

      <ResizablePanel defaultSize={panels.timeline} minSize={15} maxSize={70} className="min-h-0 px-3 pb-3">

        <Timeline />

      </ResizablePanel>

    </ResizablePanelGroup>

  );



  if (embedded) {

    return (
      <div className="flex h-full min-h-0 w-full flex-col">
        <MediaHydrationBanner />
        <div className="min-h-0 min-w-0 flex-1">{layout}</div>
      </div>
    );

  }



  return (

    <div className={`svf-opencut-theme opencut-classic-root ${themeClass} flex h-full min-h-[480px] w-full flex-col overflow-hidden`}>

      <DegradedRendererBanner />
      <MediaHydrationBanner />

      <div className="min-h-0 min-w-0 flex-1">{layout}</div>

    </div>

  );

}



/** 视频/音频媒体水合失败提示条。 */
export function MediaHydrationBanner() {
  const { t } = useAppTranslation("editor");
  const projectId = useEditor((editor) => editor.project.getActiveOrNull()?.metadata.id);
  const messageKeys = useMemo(() => {
    if (!projectId) return [];
    const issues = getMediaHydrationIssues(getSvfProjectMediaCache(projectId));
    return listMediaHydrationMessageKeys(issues);
  }, [projectId]);
  if (messageKeys.length === 0) return null;
  return (
    <div
      className="svf-media-hydration-warn border-b px-3 py-2 text-sm space-y-1"
      role="alert"
    >
      {messageKeys.map((key) => (
        <div key={key}>{t(key)}</div>
      ))}
    </div>
  );
}



/** WASM 降级提示条。 */

export function DegradedRendererBanner() {

  const isDegraded = useEditor((e) => e.renderer.isDegraded);

  const [dismissed, setDismissed] = useState(false);

  if (!isDegraded || dismissed) return null;

  return (

    <div className="bg-accent border-b flex h-9 items-center justify-center gap-2 text-xs text-muted-foreground">

      <span>建议使用 Chrome 以获得最佳 OpenCut 预览体验。</span>

      <button type="button" className="text-xs underline" onClick={() => setDismissed(true)}>

        关闭

      </button>

    </div>

  );

}


