/** 时间轴 clip 按像素宽度的展示密度档位。 */
export type ClipDisplayTier = "bar" | "compact" | "full";

/** 相邻 clip 之间的视觉缝隙（像素），不改变时间轴 duration；设为 0 使条块完整占满时间范围。 */
export const CLIP_VISUAL_GAP_PX = 0;

/** 极窄块阈值：仅显示类型色条，不渲染文字。 */
const BAR_MAX_WIDTH_PX = 14;

/** 紧凑块阈值：显示序号或省略号，不显示完整标签。 */
const COMPACT_MAX_WIDTH_PX = 40;

/** 按 clip 渲染宽度返回展示档位。 */
export function getClipDisplayTier(widthPx: number): ClipDisplayTier {
	if (widthPx < BAR_MAX_WIDTH_PX) return "bar";
	if (widthPx < COMPACT_MAX_WIDTH_PX) return "compact";
	return "full";
}

/** 扣除视觉缝隙后的 clip 容器宽度（至少 1px）。 */
export function getClipVisualWidth(widthPx: number): number {
	return Math.max(1, widthPx - CLIP_VISUAL_GAP_PX);
}
