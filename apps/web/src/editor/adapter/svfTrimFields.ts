/** 计算 OpenCut 媒体元素 trim 字段（与 svfProjectAdapter.clipToElement 一致）。 */

import { msToTicks } from "./svfTimeTicks";

export interface MediaTrimFields {
  trimStart: number;
  trimEnd: number;
  sourceDuration: number;
}

/** 按 clip 可见时长与源媒体全长计算 trimStart/trimEnd/sourceDuration。 */
export function computeMediaTrimFields(
  clipDurationMs: number,
  sourceDurationMs: number,
  options?: { padSourceToClip?: boolean },
): MediaTrimFields {
  const clipTicks = msToTicks(clipDurationMs);
  const sourceTicks = msToTicks(sourceDurationMs);
  if (clipTicks >= sourceTicks) {
    // 时间轴槽位长于探测源时长时，将 sourceDuration 抬到槽位，避免 OpenCut 把片段压短。
    const effectiveSource = options?.padSourceToClip ? Math.max(sourceTicks, clipTicks) : sourceTicks;
    return { trimStart: 0, trimEnd: 0, sourceDuration: effectiveSource };
  }
  return {
    trimStart: 0,
    trimEnd: sourceTicks - clipTicks,
    sourceDuration: sourceTicks,
  };
}
