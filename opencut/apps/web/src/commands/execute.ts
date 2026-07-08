/** Agent 命令执行器 */

import { useEditorStore } from "../editor/editor-store";
import type { EditorClip, HostCommand } from "../editor/types";

/**
 * 执行 Agent 发送的编辑命令。
 * 在 host-bridge 中被调用。
 */
export function executeAgentCommand(cmd: HostCommand) {
  const { action, params } = cmd as { action?: string; params?: Record<string, unknown> };
  if (!action) return;

  const store = useEditorStore.getState();

  switch (action) {
    case "add_clip": {
      const layerId = (params?.layer_id as string) || store.timeline.videoLayers[0]?.id || "main";
      const clip: EditorClip = {
        id: `agent_${Date.now()}`,
        track: "video",
        startMs: (params?.start_ms as number) || 0,
        endMs: ((params?.start_ms as number) || 0) + ((params?.duration_ms as number) || 3000),
        label: (params?.label as string) || "Agent 片段",
        assetRef: params?.media_id as string,
      };
      store.addClip(layerId, clip);
      store.setSelectedClipId(clip.id);
      break;
    }

    case "update_clip": {
      const targetLayer = store.timeline.videoLayers.find((l) =>
        l.clips.some((c) => c.id === params?.clip_id),
      );
      if (targetLayer) {
        store.updateClip(targetLayer.id, params?.clip_id as string, params as Partial<EditorClip>);
      }
      break;
    }

    case "remove_clip": {
      const targetLayer = store.timeline.videoLayers.find((l) =>
        l.clips.some((c) => c.id === params?.clip_id),
      );
      if (targetLayer) {
        store.removeClip(targetLayer.id, params?.clip_id as string);
      }
      break;
    }

    case "set_keyframe": {
      // 由 host-bridge 直接处理
      break;
    }

    case "export": {
      // 导出由宿主处理，编辑器仅发出通知
      break;
    }
  }
}
