/** 主画面层 clip 排序：与 core/edit/compose.py _clip_export_order_key 对齐。 */

import type { TrackClip } from "../../edit/types";

/** 导出/预览共用的主层 clip 排序键。 */
export function clipExportOrderKey(clip: TrackClip): [number, number, number] {
  let order = -1;
  const refs = clip.source_refs as Record<string, unknown> | undefined;
  const shotOrder = refs?.video_plan_shot_order;
  if (shotOrder != null) {
    order = Number(shotOrder);
  } else {
    const raw = clip.metadata?.video_plan_shot_order ?? clip.metadata?.order;
    if (raw != null) {
      const parsed = Number(raw);
      order = Number.isFinite(parsed) ? parsed : -1;
    }
  }
  const start = clip.start_ms ?? 0;
  const end = clip.end_ms ?? start;
  return [order >= 0 ? order : 10_000, start, end];
}

/** 按导出顺序对主层 clips 排序（稳定、可复现）。 */
export function sortClipsForExport(clips: TrackClip[]): TrackClip[] {
  return [...clips].sort((a, b) => {
    const ka = clipExportOrderKey(a);
    const kb = clipExportOrderKey(b);
    if (ka[0] !== kb[0]) return ka[0] - kb[0];
    if (ka[1] !== kb[1]) return ka[1] - kb[1];
    return ka[2] - kb[2];
  });
}
