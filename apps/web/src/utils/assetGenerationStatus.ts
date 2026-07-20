/**
 * 资产生成进度：合并 image_gen_progress / tts_gen_progress 等 WS 事件。
 */

import type { WsEvent } from "../types";

/** 生成任务类型。 */
export type AssetGenerationKind = "image" | "tts" | "video" | "frame";

/** 进行中的生成状态。 */
export type AssetGenerationPhase = "generating" | "failed";

/** 单目标（资产 ID 或镜头 ID）的生成状态。 */
export interface AssetGenerationEntry {
  scriptId: string;
  targetId: string;
  kind: AssetGenerationKind;
  phase: AssetGenerationPhase;
  label?: string;
}

export type AssetGenerationMap = Record<string, AssetGenerationEntry>;

/** 空生成状态表。 */
export function emptyAssetGenerationMap(): AssetGenerationMap {
  return {};
}

/** 写入或更新某目标的生成状态。 */
export function setAssetGenerating(
  map: AssetGenerationMap,
  entry: Omit<AssetGenerationEntry, "phase"> & { phase?: AssetGenerationPhase },
): AssetGenerationMap {
  const targetId = entry.targetId.trim();
  if (!targetId) return map;
  return {
    ...map,
    [targetId]: {
      scriptId: entry.scriptId,
      targetId,
      kind: entry.kind,
      phase: entry.phase ?? "generating",
      label: entry.label,
    },
  };
}

/** 清除某目标的生成状态。 */
export function clearAssetGenerating(
  map: AssetGenerationMap,
  targetId: string,
): AssetGenerationMap {
  const key = targetId.trim();
  if (!key || !(key in map)) return map;
  const next = { ...map };
  delete next[key];
  return next;
}

/** 批量清除多个目标。 */
export function clearAssetGeneratingMany(
  map: AssetGenerationMap,
  targetIds: string[],
): AssetGenerationMap {
  let next = map;
  for (const id of targetIds) {
    next = clearAssetGenerating(next, id);
  }
  return next;
}

/** 判断事件是否属于当前剧本。 */
function eventMatchesScript(event: WsEvent, scriptId?: string | null): boolean {
  const evScript = String(event.script_id ?? "");
  if (!scriptId) return true;
  if (!evScript) return true;
  return evScript === scriptId;
}

/** 将 WebSocket 事件合并进生成状态表。 */
export function reduceAssetGenerationFromWs(
  map: AssetGenerationMap,
  event: WsEvent,
  scriptId?: string | null,
): AssetGenerationMap {
  if (!eventMatchesScript(event, scriptId)) return map;

  const type = String(event.type ?? "");

  if (type === "image_gen_progress") {
    const assetId = String(event.source_text_asset_id ?? "").trim();
    if (!assetId) return map;
    const status = String(event.status ?? "started");
    const evScript = String(event.script_id ?? scriptId ?? "");
    if (status === "started") {
      return setAssetGenerating(map, {
        scriptId: evScript,
        targetId: assetId,
        kind: "image",
        label: String(event.name ?? ""),
      });
    }
    if (status === "failed") {
      return setAssetGenerating(map, {
        scriptId: evScript,
        targetId: assetId,
        kind: "image",
        phase: "failed",
        label: String(event.name ?? ""),
      });
    }
    return clearAssetGenerating(map, assetId);
  }

  if (type === "tts_gen_progress") {
    const shotId = String(event.shot_id ?? "").trim();
    if (!shotId) return map;
    const status = String(event.status ?? "started");
    const evScript = String(event.script_id ?? scriptId ?? "");
    if (status === "started") {
      return setAssetGenerating(map, {
        scriptId: evScript,
        targetId: shotId,
        kind: "tts",
        label: String(event.label ?? ""),
      });
    }
    if (status === "failed") {
      return setAssetGenerating(map, {
        scriptId: evScript,
        targetId: shotId,
        kind: "tts",
        phase: "failed",
      });
    }
    return clearAssetGenerating(map, shotId);
  }

  if (type === "assets_changed") {
    const assetId = String(event.asset_id ?? "").trim();
    const shotId = String(event.shot_id ?? "").trim();
    let next = map;
    if (assetId) {
      next = clearAssetGenerating(next, assetId);
    }
    if (shotId) {
      next = clearAssetGenerating(next, shotId);
    }
    const action = String(event.action ?? "");
    if (action.includes("tts") && assetId) {
      next = clearAssetGenerating(next, assetId);
    }
    const shotIds = event.shot_ids;
    if (Array.isArray(shotIds)) {
      for (const sid of shotIds) {
        const id = String(sid ?? "").trim();
        if (id) next = clearAssetGenerating(next, id);
      }
    }
    if (
      assetId &&
      (action === "generate_images" ||
        action === "regenerate_image" ||
        action.includes("image"))
    ) {
      next = clearAssetGenerating(next, assetId);
    }
    return next;
  }

  return map;
}

/** 读取某目标在当前剧本下是否处于生成中。 */
export function getAssetGenerationEntry(
  map: AssetGenerationMap,
  targetId: string | null | undefined,
  scriptId?: string | null,
): AssetGenerationEntry | null {
  const key = String(targetId ?? "").trim();
  if (!key) return null;
  const entry = map[key];
  if (!entry) return null;
  if (scriptId && entry.scriptId && entry.scriptId !== scriptId) return null;
  return entry;
}

/** 判断分镜镜头是否有关联生成任务（TTS/画面/视频或 frame 文字资产）。 */
export function getShotGenerationEntry(
  map: AssetGenerationMap,
  shot: { id: string; asset_refs?: Record<string, string[]> },
  scriptId?: string | null,
): AssetGenerationEntry | null {
  const byShot = getAssetGenerationEntry(map, shot.id, scriptId);
  if (byShot) return byShot;
  const refs = shot.asset_refs ?? {};
  const frameIds = refs.frame ?? refs.frames ?? [];
  for (const fid of frameIds) {
    const entry = getAssetGenerationEntry(map, fid, scriptId);
    if (entry?.kind === "image" || entry?.kind === "frame") return entry;
  }
  return null;
}

/** 合并多个候选 ID，返回首个进行中的条目。 */
export function getFirstGeneratingEntry(
  map: AssetGenerationMap,
  targetIds: Array<string | null | undefined>,
  scriptId?: string | null,
): AssetGenerationEntry | null {
  for (const id of targetIds) {
    const entry = getAssetGenerationEntry(map, id, scriptId);
    if (entry?.phase === "generating") return entry;
  }
  return null;
}

function hasRealImageUrl(raw: Record<string, unknown>): boolean {
  const url = String(raw.preview_url ?? raw.url ?? "").trim();
  if (!url) return false;
  const lower = url.toLowerCase();
  if (lower.includes("example.com")) return false;
  if (lower.startsWith("/assets/")) return false;
  if (lower.startsWith("placeholder:")) return false;
  return true;
}

function textAssetHasImage(raw: Record<string, unknown>): boolean {
  if (hasRealImageUrl(raw)) return true;
  const images = raw.images ?? raw.media;
  if (Array.isArray(images)) {
    for (const img of images) {
      if (img && typeof img === "object" && hasRealImageUrl(img as Record<string, unknown>)) {
        return true;
      }
    }
  }
  const variants = raw.variants;
  if (Array.isArray(variants)) {
    for (const variant of variants) {
      if (variant && typeof variant === "object" && hasRealImageUrl(variant as Record<string, unknown>)) {
        return true;
      }
    }
  }
  return false;
}

/** 看板数据刷新后剔除已落盘资产上的陈旧「生成中」状态。 */
export function pruneAssetGenerationFromBoard(
  map: AssetGenerationMap,
  scriptId: string | null | undefined,
  board: { items?: Record<string, unknown>[] } | null | undefined,
): AssetGenerationMap {
  const items = board?.items ?? [];
  if (!items.length) return map;

  let next = map;
  const frameIdsWithPreview = new Set<string>();

  for (const raw of items) {
    const id = String(raw.id ?? "").trim();
    if (!id) continue;

    if (hasRealImageUrl(raw) || String(raw.frame_preview_url ?? "").trim()) {
      const entry = getAssetGenerationEntry(next, id, scriptId);
      if (entry?.phase === "generating" && (entry.kind === "image" || entry.kind === "frame")) {
        next = clearAssetGenerating(next, id);
      }
    }

    const ttsUrl = String(raw.tts_audio_url ?? "").trim();
    if (ttsUrl) {
      const entry = getAssetGenerationEntry(next, id, scriptId);
      if (entry?.phase === "generating" && entry.kind === "tts") {
        next = clearAssetGenerating(next, id);
      }
    }

    if (textAssetHasImage(raw)) {
      next = clearAssetGenerating(next, id);
    }

    if (String(raw.frame_preview_url ?? "").trim()) {
      const refs = raw.asset_refs;
      if (refs && typeof refs === "object") {
        const frameRefs = (refs as Record<string, unknown>).frame ?? (refs as Record<string, unknown>).frames;
        if (Array.isArray(frameRefs)) {
          for (const fid of frameRefs) {
            const frameId = String(fid ?? "").trim();
            if (frameId) frameIdsWithPreview.add(frameId);
          }
        }
      }
      const entry = getAssetGenerationEntry(next, id, scriptId);
      if (entry?.phase === "generating" && (entry.kind === "frame" || entry.kind === "image")) {
        next = clearAssetGenerating(next, id);
      }
    }
  }

  for (const frameId of frameIdsWithPreview) {
    next = clearAssetGenerating(next, frameId);
  }

  return next;
}
