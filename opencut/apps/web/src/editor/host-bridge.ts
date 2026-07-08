/**
 * OpenCut Editor → SuperVideoGenerator 宿主 postMessage 通信桥。
 * 监听宿主命令，调用编辑器 store，回传状态变更。
 */

import { useEditorStore } from "./editor-store";
import type { EditorClip, EditorEvent, HostCommand, MediaAsset } from "./types";

let bridgeInitialized = false;

export function initHostBridge() {
  if (bridgeInitialized) return;
  bridgeInitialized = true;

  const store = useEditorStore.getState;

  function send(event: EditorEvent) {
    window.parent.postMessage(
      { source: "opencut-editor", ...event },
      "*", // 宽松 origin 检查，生产环境需要收紧
    );
  }

  function handleCommand(cmd: HostCommand) {
    switch (cmd.type) {
      case "load_project": {
        const project = (cmd as Record<string, unknown>).project as Record<string, unknown> | undefined;
        if (project?.timeline) {
          const tl = project.timeline as Record<string, unknown>;
          store().setTimeline({
            durationMs: (tl.durationMs as number) || (tl.duration_ms as number) || 0,
            revision: (tl.revision as number) || 0,
            videoLayers: (tl.videoLayers as []) || (tl.video_layers as []) || [{ id: "main", name: "主画面", zIndex: 0, clips: [] }],
            audioClips: [],
            subtitleClips: [],
          });
        }
        if (project?.mediaAssets) {
          store().setMediaAssets(project.mediaAssets as MediaAsset[]);
        }
        store().setReady(true);
        send({ type: "ready" });
        break;
      }

      case "apply_action": {
        const action = cmd.action as string;
        const params = cmd.params as Record<string, unknown> | undefined;
        if (!action || !params) break;

        try {
          switch (action) {
            case "add_clip": {
              const newClip: EditorClip = {
                id: `clip_${Date.now()}`,
                track: (params.track as "video") || "video",
                startMs: params.start_ms as number || 0,
                endMs: (params.start_ms as number || 0) + (params.duration_ms as number || 3000),
                label: params.label as string || "新片段",
                assetRef: params.media_id as string,
                previewUrl: params.preview_url as string,
              };
              useEditorStore.getState().addClip(params.layer_id as string || "main", newClip);
              break;
            }
            case "update_clip":
              useEditorStore.getState().updateClip(
                params.layer_id as string || "main",
                params.clip_id as string,
                params,
              );
              break;
            case "remove_clip":
              useEditorStore.getState().removeClip(
                params.layer_id as string || "main",
                params.clip_id as string,
              );
              break;
            case "set_keyframe":
              // 关键帧数据存储到 clip 的 transform.keyframes
              useEditorStore.getState().updateClip(
                params.layer_id as string || "main",
                params.clip_id as string,
                {
                  transform: {
                    ...store().timeline.videoLayers
                      .flatMap((l) => l.clips)
                      .find((c) => c.id === params.clip_id)
                      ?.transform || { x: 0.5, y: 0.5, width: 1, height: 1, opacity: 1, rotation: 0 },
                    keyframes: [
                      ...(store().timeline.videoLayers
                        .flatMap((l) => l.clips)
                        .find((c) => c.id === params.clip_id)
                        ?.transform?.keyframes || []),
                      {
                        timeMs: (params.time_ms as number) || 0,
                        ...(params.properties as object || {}),
                      },
                    ],
                  },
                } as Partial<EditorClip>,
              );
              break;
          }
          send({
            type: "timeline_changed",
            state: store().timeline,
          });
        } catch (err) {
          send({
            type: "error",
            message: `执行 ${action} 失败: ${err instanceof Error ? err.message : String(err)}`,
          });
        }
        break;
      }

      case "seek_to": {
        store().setPlayheadMs(cmd.timeMs as number || 0);
        break;
      }

      case "play":
        store().setPlaying(true);
        break;

      case "pause":
        store().setPlaying(false);
        break;

      case "ping":
        send({ type: "pong" });
        break;
    }
  }

  window.addEventListener("message", (e: MessageEvent) => {
    const data = e.data as Record<string, unknown> | undefined;
    if (!data || data.source !== "super-video-generator") return;
    handleCommand(data as unknown as HostCommand);
  });

  // 通知宿主编辑器就绪
  send({ type: "ready" });
}
