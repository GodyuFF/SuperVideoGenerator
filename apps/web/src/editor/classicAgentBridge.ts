/**
 * OpenCut Classic 弹窗会话：Agent 热更新与 EditorCore 联动（Core 按需加载）。
 */

import { svfProjectKey } from "./adapter/svfProjectAdapter";
import {
  refreshSvfBridgeFromApi,
  getSvfBridgeCache,
  updateSvfBridgeCache,
} from "./opencut/svf-storage-bridge";
import { loadFromSvf } from "./adapter/svfProjectAdapter";
import { fetchSvfScriptMedia } from "./adapter/SvfMediaProvider";
import { mergeHydratedDurationsIntoMediaItems } from "./adapter/SvfMediaBridge";
import type { EditTimelineData } from "../edit/types";

const activeSessions = new Set<string>();

/** 按需加载 OpenCut EditorCore 与 wasm 时间转换。 */
async function getClassicRuntime() {
  const [coreMod, wasmMod] = await Promise.all([
    import("@opencut/core"),
    import("@opencut/wasm"),
  ]);
  return {
    EditorCore: coreMod.EditorCore,
    mediaTimeFromSeconds: wasmMod.mediaTimeFromSeconds,
    mediaTimeToSeconds: wasmMod.mediaTimeToSeconds,
  };
}

/** 注册 Classic 弹窗会话（Agent 桥接优先走 Classic）。 */
export function registerClassicAgentSession(projectId: string, scriptId: string): void {
  activeSessions.add(`${projectId}:${scriptId}`);
}

/** 注销 Classic 弹窗会话。 */
export function unregisterClassicAgentSession(projectId: string, scriptId: string): void {
  activeSessions.delete(`${projectId}:${scriptId}`);
}

/** 当前是否有 Classic 弹窗会话。 */
export function isClassicAgentSessionActive(projectId: string, scriptId: string): boolean {
  return activeSessions.has(`${projectId}:${scriptId}`);
}

/** 从 API 刷新 Classic 编辑器（保留播放头）。 */
export async function reloadClassicFromApi(
  projectId: string,
  scriptId: string,
  timeline?: EditTimelineData,
): Promise<EditTimelineData | null> {
  const { EditorCore, mediaTimeFromSeconds, mediaTimeToSeconds } = await getClassicRuntime();
  const key = svfProjectKey(projectId, scriptId);
  const editor = EditorCore.getInstance();

  // 本地未落盘改动优先 flush，避免用旧 API 覆盖刚设的倍速/音量
  if (editor.save.getIsDirty()) {
    try {
      await editor.save.flush();
    } catch (err) {
      console.warn("[classicAgentBridge] flush before reload failed", err);
    }
  }

  const playheadMs =
    mediaTimeToSeconds({ time: editor.playback.getCurrentTime() }) * 1000;

  let data = timeline;
  if (!data) {
    const tlRes = await fetch(`/api/projects/${projectId}/scripts/${scriptId}/edit-timeline`);
    if (!tlRes.ok) return null;
    data = (await tlRes.json()) as EditTimelineData;
  }

  await refreshSvfBridgeFromApi(projectId, scriptId, data);

  const cached = getSvfBridgeCache(key);
  const mediaAssets = cached?.media ?? [];
  const mediaItemsForProject = mediaAssets.length
    ? mergeHydratedDurationsIntoMediaItems(
        mediaAssets.map((a) => ({
          id: a.id,
          name: a.name,
          type: a.type,
          url: a.url,
          duration_ms: a.duration ? a.duration * 1000 : undefined,
        })),
        mediaAssets,
      )
    : (await fetchSvfScriptMedia(projectId, scriptId)).map((r) => ({
        id: r.id,
        name: r.name,
        type: r.type,
        url: r.url,
        link: r.link,
        duration_ms: r.durationMs,
      }));
  const project = loadFromSvf(data, mediaItemsForProject, key, scriptId);
  updateSvfBridgeCache(key, data, project, mediaAssets.length ? mediaAssets : undefined);

  await editor.project.loadProject({ id: key });
  const targetMs = Math.min(playheadMs, data.duration_ms || playheadMs);
  editor.playback.seek({ time: mediaTimeFromSeconds({ seconds: targetMs / 1000 }) });

  return data;
}

/** 读取当前 bridge 中的 timeline（Classic 保存前 flush 用）。 */
export function getClassicBridgeTimeline(
  projectId: string,
  scriptId: string,
): EditTimelineData | undefined {
  return getSvfBridgeCache(svfProjectKey(projectId, scriptId))?.base;
}