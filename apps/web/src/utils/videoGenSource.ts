/**
 * AI 视频生成参考源选择：仅剧本画面（frame）。
 */

/** 视频生成参考源选择（提交 regenerate API 的 video 字段）。 */
export interface VideoGenSourceSelection {
  subShotIdx?: number;
  sourceFrameAssetIds: string[];
  /** @deprecated 保留类型兼容，前端不再收集或序列化。 */
  sourceVideoClipAssetIds?: string[];
  /** @deprecated 保留类型兼容，前端不再收集或序列化。 */
  sourceMediaIds?: string[];
  /** @deprecated 保留类型兼容，前端不再收集或序列化。 */
  sourceElementRefs?: Record<string, string[]>;
  /** 强制 img2video / keyframes；留空则按参考图数量推断。 */
  videoMode?: "img2video" | "keyframes";
}

/** 空参考源选择。 */
export function emptyVideoGenSource(subShotIdx = 0): VideoGenSourceSelection {
  return {
    subShotIdx,
    sourceFrameAssetIds: [],
  };
}

/** 是否至少选择了一张画面参考。 */
export function hasVideoGenSource(selection: VideoGenSourceSelection): boolean {
  return selection.sourceFrameAssetIds.length > 0;
}

/** 转为 regenerate API 的 video 请求体（仅提交画面 ID 与可选 videoMode）。 */
export function videoGenSourceToApiBody(
  selection: VideoGenSourceSelection,
): Record<string, unknown> | undefined {
  if (!hasVideoGenSource(selection)) return undefined;
  const body: Record<string, unknown> = {
    sub_shot_idx: selection.subShotIdx ?? 0,
    source_frame_asset_ids: selection.sourceFrameAssetIds,
  };
  if (selection.videoMode) {
    body.video_mode = selection.videoMode;
  }
  return body;
}

/** 统计已选画面参考数量。 */
export function countVideoGenSources(selection: VideoGenSourceSelection): number {
  return selection.sourceFrameAssetIds.length;
}
