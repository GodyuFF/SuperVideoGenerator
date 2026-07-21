import type { TrackType } from "@opencut/timeline";

export const TIMELINE_AUDIO_WAVEFORM_COLOR = "rgba(186, 220, 245, 0.88)";
/** 视频轨底部嵌入音频能量条颜色（略淡于独立音频轨）。 */
export const TIMELINE_VIDEO_AUDIO_RAIL_COLOR = "rgba(160, 205, 235, 0.7)";

/** 时间轴 clip 分轨胶片底 + 左侧类型色条（样式在 svf-opencut-theme.css）。 */
const CLIP_BASE = "svf-timeline-clip";

export const TIMELINE_TRACK_THEME: Record<
	TrackType,
	{
		elementClassName: string;
		waveformColor?: string;
	}
> = {
	video: { elementClassName: `${CLIP_BASE} svf-timeline-clip--video` },
	text: { elementClassName: `${CLIP_BASE} svf-timeline-clip--text` },
	audio: {
		elementClassName: `${CLIP_BASE} svf-timeline-clip--audio`,
		waveformColor: TIMELINE_AUDIO_WAVEFORM_COLOR,
	},
	graphic: { elementClassName: `${CLIP_BASE} svf-timeline-clip--graphic` },
	effect: { elementClassName: `${CLIP_BASE} svf-timeline-clip--effect` },
} as const;

export const SELECTED_TRACK_ROW_CLASS = "bg-accent/50";
export const DEFAULT_TIMELINE_BOOKMARK_COLOR = "var(--svf-info, #6b9fd4)";

/** 按轨道类型返回 clip 容器 class。 */
export function getTimelineElementClassName({
	type,
}: {
	type: TrackType;
}): string {
	return TIMELINE_TRACK_THEME[type].elementClassName.trim();
}
