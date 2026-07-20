/**
 * AI 视频生成参考源选择：画面 / 落盘图片 / 角色·场景·道具元素。
 */

/** 视频生成参考源选择（提交 regenerate API 的 video 字段）。 */
export interface VideoGenSourceSelection {
  subShotIdx?: number;
  sourceFrameAssetIds: string[];
  sourceVideoClipAssetIds: string[];
  sourceMediaIds: string[];
  sourceElementRefs: Record<string, string[]>;
  /** 强制 img2video / keyframes；留空则按参考图数量推断。 */
  videoMode?: "img2video" | "keyframes";
}

/** 空参考源选择。 */
export function emptyVideoGenSource(subShotIdx = 0): VideoGenSourceSelection {
  return {
    subShotIdx,
    sourceFrameAssetIds: [],
    sourceVideoClipAssetIds: [],
    sourceMediaIds: [],
    sourceElementRefs: {},
  };
}

/** 是否至少选择了一类参考源。 */
export function hasVideoGenSource(selection: VideoGenSourceSelection): boolean {
  if (
    selection.sourceFrameAssetIds.length ||
    selection.sourceVideoClipAssetIds.length ||
    selection.sourceMediaIds.length
  ) {
    return true;
  }
  return Object.values(selection.sourceElementRefs).some((ids) => ids.length > 0);
}

/** 转为 regenerate API 的 video 请求体。 */
export function videoGenSourceToApiBody(
  selection: VideoGenSourceSelection,
): Record<string, unknown> | undefined {
  if (!hasVideoGenSource(selection)) return undefined;
  const body: Record<string, unknown> = {
    sub_shot_idx: selection.subShotIdx ?? 0,
  };
  if (selection.sourceFrameAssetIds.length) {
    body.source_frame_asset_ids = selection.sourceFrameAssetIds;
  }
  if (selection.sourceVideoClipAssetIds.length) {
    body.source_video_clip_asset_ids = selection.sourceVideoClipAssetIds;
  }
  if (selection.sourceMediaIds.length) {
    body.source_media_ids = selection.sourceMediaIds;
  }
  if (Object.keys(selection.sourceElementRefs).length) {
    body.source_element_refs = selection.sourceElementRefs;
  }
  if (selection.videoMode) {
    body.video_mode = selection.videoMode;
  }
  return body;
}

/** 统计已选参考源数量。 */
export function countVideoGenSources(selection: VideoGenSourceSelection): number {
  let n =
    selection.sourceFrameAssetIds.length +
    selection.sourceVideoClipAssetIds.length +
    selection.sourceMediaIds.length;
  for (const ids of Object.values(selection.sourceElementRefs)) {
    n += ids.length;
  }
  return n;
}
