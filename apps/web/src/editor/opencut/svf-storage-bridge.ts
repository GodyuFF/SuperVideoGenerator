/**

 * 将 Classic storageService 路由到 SVF edit-timeline API。

 */



import type { EditTimelineData } from "../../edit/types";

import {

  loadFromSvf,

  saveToSvf,

  parseSvfProjectKey,

  svfProjectKey,

  type ClassicProjectJson,

} from "../adapter/svfProjectAdapter";

import { fetchSvfScriptMedia } from "../adapter/SvfMediaProvider";

import {

  svfMediaItemsToAssets,

  setSvfProjectMediaCache,

  clearSvfProjectMediaCache,

  enrichMediaThumbnailsAsync,

  hydrateSvfMediaFiles,

  type SvfClassicMediaAsset,

} from "../adapter/SvfMediaBridge";



const API = "/api";



interface BridgeCacheEntry {

  project: ClassicProjectJson;

  base: EditTimelineData;

  media: SvfClassicMediaAsset[];

}



const cache = new Map<string, BridgeCacheEntry>();



let installed = false;

let saveHandler: ((timeline: EditTimelineData) => Promise<EditTimelineData | void>) | null = null;

const SAVE_DEBOUNCE_MS = 300;

const pendingSaveTimers = new Map<string, ReturnType<typeof setTimeout>>();

const pendingSaveProjects = new Map<string, ClassicProjectJson>();

let lastLoadedKey: string | null = null;

/** 活跃 EditorProvider / 预览会话引用计数（按 compositeKey）。 */
const sessionRefCounts = new Map<string, number>();

/** 注册 SVF PATCH 保存回调。 */

export function registerSvfSaveHandler(

  fn: (timeline: EditTimelineData) => Promise<EditTimelineData | void>,

) {

  saveHandler = fn;

}



/** 读取 bridge 缓存（供 Agent 热更新）。 */

export function getSvfBridgeCache(key: string): BridgeCacheEntry | undefined {

  return cache.get(key);

}



/** 更新 bridge 缓存中的 timeline 与 project。 */

export function updateSvfBridgeCache(

  key: string,

  base: EditTimelineData,

  project: ClassicProjectJson,

  media?: SvfClassicMediaAsset[],

): void {

  const hit = cache.get(key);

  if (hit) {

    hit.base = base;

    hit.project = project;

    if (media) hit.media = media;

  } else {

    cache.set(key, { project, base, media: media ?? [] });

  }

}



export interface InstallBridgeOptions {

  /** 已有 timeline 时跳过 GET。 */

  initialTimeline?: EditTimelineData;

  /** 强制刷新缓存。 */

  force?: boolean;

}



/** 安装 storageService 补丁并填充项目缓存。 */

export async function installSvfStorageBridge(

  projectId: string,

  scriptId: string,

  options: InstallBridgeOptions = {},

): Promise<void> {

  const key = svfProjectKey(projectId, scriptId);



  if (!options.force && cache.has(key) && !options.initialTimeline) {

    await ensurePatchesInstalled();

    return;

  }



  let base: EditTimelineData;

  if (options.initialTimeline) {

    base = options.initialTimeline;

  } else {

    const tlRes = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}/edit-timeline`);

    if (!tlRes.ok) throw new Error("无法加载剪辑时间轴");

    base = (await tlRes.json()) as EditTimelineData;

  }



  const mediaRecords = await fetchSvfScriptMedia(projectId, scriptId);

  const mediaContext = { projectId, scriptId };

  const mediaItems = mediaRecords.map((r) => ({

    id: r.id,

    name: r.name,

    type: r.type,

    url: r.url,

    link: r.link,

    duration_ms: r.durationMs,

    source_asset_id: r.sourceAssetId,

  }));

  const mediaAssets = svfMediaItemsToAssets(mediaItems, mediaContext);

  await hydrateSvfMediaFiles(mediaAssets, mediaContext);

  setSvfProjectMediaCache(key, mediaAssets);

  enrichMediaThumbnailsAsync(mediaAssets);



  const project = loadFromSvf(base, mediaItems, key, scriptId);

  cache.set(key, { project, base, media: mediaAssets });



  await ensurePatchesInstalled();

}



async function ensurePatchesInstalled(): Promise<void> {

  if (installed) return;

  installed = true;



  const mod = await import("@opencut/services/storage/service");

  const svc = mod.storageService as {

    loadProject: (opts: { id: string }) => Promise<{ project: ClassicProjectJson } | null>;

    saveProject: (opts: { project: ClassicProjectJson }) => Promise<void>;

    loadAllMediaAssets: (opts: { projectId: string }) => Promise<SvfClassicMediaAsset[]>;

    loadMediaAsset: (opts: {

      projectId: string;

      id: string;

    }) => Promise<SvfClassicMediaAsset | null>;

  };



  const origLoad = svc.loadProject.bind(svc);

  const origSave = svc.saveProject.bind(svc);

  const origLoadAll = svc.loadAllMediaAssets.bind(svc);

  const origLoadOne = svc.loadMediaAsset.bind(svc);



  svc.loadProject = async ({ id }) => {

    const parsed = parseSvfProjectKey(id);

    if (!parsed) return origLoad({ id });

    const hit = cache.get(id);

    if (hit) return { project: hit.project };

    await installSvfStorageBridge(parsed.projectId, parsed.scriptId);

    let again = cache.get(id);

    if (!again) {
      await installSvfStorageBridge(parsed.projectId, parsed.scriptId, { force: true });
      again = cache.get(id);
    }

    return again ? { project: again.project } : null;

  };



  svc.saveProject = async ({ project }) => {

    const id = project.metadata.id;

    const parsed = parseSvfProjectKey(id);

    if (!parsed) {

      await origSave({ project });

      return;

    }

    const hit = cache.get(id);

    if (!hit) return;



    pendingSaveProjects.set(id, project);

    const existingTimer = pendingSaveTimers.get(id);

    if (existingTimer) clearTimeout(existingTimer);



    await new Promise<void>((resolve, reject) => {

      const timer = setTimeout(() => {

        pendingSaveTimers.delete(id);

        const latestProject = pendingSaveProjects.get(id);

        pendingSaveProjects.delete(id);

        if (!latestProject) {

          resolve();

          return;

        }

        void (async () => {
          const { EditorCore } = await import("@opencut/core");
          const editor = EditorCore.getInstance();
          editor.save.pause();
          try {
            const entry = cache.get(id);
            if (!entry) {
              resolve();
              return;
            }

            entry.project = latestProject;
            const merged = saveToSvf(latestProject, entry.base);
            entry.base = merged;

            if (saveHandler) {
              const saved = await saveHandler(merged);
              if (saved?.revision != null) {
                entry.base = { ...entry.base, revision: saved.revision };
              }
            }

            resolve();
          } catch (e) {
            reject(e);
          } finally {
            editor.save.resume();
          }
        })();

      }, SAVE_DEBOUNCE_MS);

      pendingSaveTimers.set(id, timer);

    });

  };



  svc.loadAllMediaAssets = async ({ projectId }) => {

    const parsed = parseSvfProjectKey(projectId);

    if (!parsed) return origLoadAll({ projectId });

    const hit = cache.get(projectId);

    if (hit?.media.length) return hit.media;

    await installSvfStorageBridge(parsed.projectId, parsed.scriptId);

    return cache.get(projectId)?.media ?? [];

  };



  svc.loadMediaAsset = async ({ projectId, id }) => {

    const parsed = parseSvfProjectKey(projectId);

    if (!parsed) return origLoadOne({ projectId, id });

    const assets = cache.get(projectId)?.media ?? [];

    return assets.find((a) => a.id === id) ?? null;

  };

}



/** 从 API 刷新 SVF 项目缓存（Agent 热更新）。 */

export async function refreshSvfBridgeFromApi(

  projectId: string,

  scriptId: string,

  timeline?: EditTimelineData,

): Promise<void> {

  await installSvfStorageBridge(projectId, scriptId, {

    initialTimeline: timeline,

    force: true,

  });

}



/** 记录上次成功加载的 SVF 项目键（会话复用）。 */

export function markSvfProjectLoaded(key: string): void {

  lastLoadedKey = key;

}



/** 是否可 soft-reload 同一 SVF 项目。 */

export function canSoftReloadSvfProject(key: string): boolean {

  return lastLoadedKey === key && cache.has(key);

}

/** 占用 SVF 编辑器会话（预览或弹窗 mount 成功后调用）。 */
export function acquireSvfEditorSession(projectId: string, scriptId: string): string {
  const key = svfProjectKey(projectId, scriptId);
  sessionRefCounts.set(key, (sessionRefCounts.get(key) ?? 0) + 1);
  return key;
}

/** 释放 SVF 编辑器会话；引用归零时才清除 bridge 缓存。 */
export function releaseSvfEditorSession(projectId: string, scriptId: string): void {
  const key = svfProjectKey(projectId, scriptId);
  const next = (sessionRefCounts.get(key) ?? 0) - 1;
  if (next <= 0) {
    sessionRefCounts.delete(key);
    resetSvfStorageBridge(projectId, scriptId);
  } else {
    sessionRefCounts.set(key, next);
  }
}

/** 卸载 SVF 缓存（内部使用；外部应优先 releaseSvfEditorSession）。 */
export function resetSvfStorageBridge(projectId: string, scriptId: string) {

  const key = svfProjectKey(projectId, scriptId);

  cache.delete(key);

  clearSvfProjectMediaCache(key);

  if (lastLoadedKey === key) lastLoadedKey = null;

}


