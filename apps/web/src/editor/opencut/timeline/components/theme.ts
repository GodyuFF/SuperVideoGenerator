import type { TrackType } from "@opencut/timeline";

export const TIMELINE_AUDIO_WAVEFORM_COLOR = "rgba(140, 185, 220, 0.55)";

/** 时间轴 clip 分轨半透明胶片色 + 左侧类型色条（样式在 svf-opencut-theme.css）。 */
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
