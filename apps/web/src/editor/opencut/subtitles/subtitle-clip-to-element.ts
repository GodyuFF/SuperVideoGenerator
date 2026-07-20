import type { TrackClip } from "../../../edit/types";
import type { CanvasSize } from "../../adapter/svfTransformBridge";
import { msToTicks } from "../../adapter/svfTimeTicks";
import { clipShotMetadata } from "../../adapter/svfShotProjection";
import { buildSubtitleTextElement } from "./build-subtitle-text-element";
import {
	presetToSubtitleStyleOverrides,
	recommendSubtitleStyle,
} from "./subtitle-style-presets";
/** 将 SVF subtitle clip 转为带推荐样式的 OpenCut 文本元素。 */
export function subtitleClipToTextElement({
	clip,
	canvas,
	index,
}: {
	clip: TrackClip;
	canvas: CanvasSize;
	index: number;
}) {
	const startMs = clip.start_ms ?? 0;
	const endMs = clip.end_ms ?? startMs + 1000;
	const durationMs = Math.max(endMs - startMs, 100);
	const preset = recommendSubtitleStyle({
		width: canvas.width,
		height: canvas.height,
	});
	const built = buildSubtitleTextElement({
		index,
		caption: {
			text: clip.label || "",
			startTime: startMs / 1000,
			duration: durationMs / 1000,
			style: presetToSubtitleStyleOverrides(preset),
		},
		canvasSize: canvas,
	});

	return {
		id: clip.id || `subtitle_${startMs}`,
		name: clip.label?.slice(0, 24) || `字幕 ${index + 1}`,
		type: "text",
		duration: msToTicks(durationMs),
		startTime: msToTicks(startMs),
		trimStart: 0,
		trimEnd: 0,
		params: built.params,
		animations: [],
		metadata: {
			svf: {
				track: "subtitle",
				subtitle_style_preset: preset.placement,
			},
			edited_by: clip.metadata?.edited_by,
			user_locked: clip.metadata?.user_locked,
			...clipShotMetadata(clip),
			...(clip.metadata?.classic && typeof clip.metadata.classic === "object"
				? { classic: clip.metadata.classic }
				: {}),
		},
	};
}
