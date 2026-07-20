import type { SubtitleStyleOverrides } from "./types";

/** 与 core/edit/subtitle_style.py `OPENCUT_FONT_SIZE_SCALE_REFERENCE` 一致。 */
export const OPENCUT_FONT_SIZE_SCALE_REFERENCE = 90;

export interface SubtitleStylePreset {
	canvasWidth: number;
	canvasHeight: number;
	orientation: "landscape" | "portrait" | "square";
	placement: "bottom_center";
	maxCharsPerLine: number;
	ass: {
		alignment: number;
		fontSizePx: number;
		marginVPx: number;
		outlinePx: number;
	};
	opencut: SubtitleStyleOverrides & {
		maxLineWidthRatio: number;
	};
	guidanceZh: string;
}

function orientation({
	width,
	height,
}: {
	width: number;
	height: number;
}): SubtitleStylePreset["orientation"] {
	if (width > height * 1.1) {
		return "landscape";
	}
	if (height > width * 1.1) {
		return "portrait";
	}
	return "square";
}

/** 按画布尺寸推荐字幕样式（与 Python subtitle_style.recommend_subtitle_style 对齐）。 */
export function recommendSubtitleStyle({
	width,
	height,
}: {
	width: number;
	height: number;
}): SubtitleStylePreset {
	const canvasW = Math.max(Math.round(width), 1);
	const canvasH = Math.max(Math.round(height), 1);
	const orient = orientation({ width: canvasW, height: canvasH });

	let fontRatio = 0.039;
	let marginRatio = 0.08;
	let maxWidthRatio = 0.85;
	let maxCharsPerLine = 18;
	if (orient === "portrait") {
		fontRatio = 0.044;
		marginRatio = 0.1;
		maxWidthRatio = 0.9;
		maxCharsPerLine = 14;
	} else if (orient === "square") {
		fontRatio = 0.04;
		marginRatio = 0.08;
		maxWidthRatio = 0.85;
		maxCharsPerLine = 16;
	}

	const fontSizePx = Math.max(28, Math.min(72, Math.round(canvasH * fontRatio)));
	const marginVPx = Math.max(32, Math.min(200, Math.round(canvasH * marginRatio)));
	const marginVerticalRatio = Math.round((marginVPx / canvasH) * 10_000) / 10_000;
	const fontSizeRatio = Math.round((fontSizePx / canvasH) * 10_000) / 10_000;
	const opencutFontSize =
		Math.round((fontSizePx / canvasH) * OPENCUT_FONT_SIZE_SCALE_REFERENCE * 100) /
		100;

	return {
		canvasWidth: canvasW,
		canvasHeight: canvasH,
		orientation: orient,
		placement: "bottom_center",
		maxCharsPerLine,
		ass: {
			alignment: 2,
			fontSizePx,
			marginVPx,
			outlinePx: 2,
		},
		opencut: {
			fontSize: opencutFontSize,
			fontSizeRatioOfPlayHeight: fontSizeRatio,
			textAlign: "center",
			fontWeight: "bold",
			color: "#ffffff",
			placement: {
				verticalAlign: "bottom",
				marginVerticalRatio,
			},
			maxLineWidthRatio: maxWidthRatio,
		},
		guidanceZh: `成片 ${canvasW}×${canvasH}（${orient}）：字幕须底部居中，禁止画面正中；字号约 ${fontSizePx}px，底边距约 ${(marginVerticalRatio * 100).toFixed(1)}%。`,
	};
}

/** 将预设转为 buildSubtitleTextElement 可用的 style 覆盖。 */
export function presetToSubtitleStyleOverrides(
	preset: SubtitleStylePreset,
): SubtitleStyleOverrides {
	return {
		fontSize: preset.opencut.fontSize,
		fontSizeRatioOfPlayHeight: preset.opencut.fontSizeRatioOfPlayHeight,
		textAlign: preset.opencut.textAlign,
		fontWeight: preset.opencut.fontWeight,
		color: preset.opencut.color,
		placement: preset.opencut.placement,
	};
}
