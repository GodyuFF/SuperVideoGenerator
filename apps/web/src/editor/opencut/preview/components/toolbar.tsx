import { useState, useEffect } from "react";
import { useEditor } from "@opencut/editor/use-editor";
import { formatTimecode } from "opencut-wasm";
import { invokeAction } from "@opencut/actions";
import { toast } from "sonner";
import { isSvfProjectKey } from "@opencut/svf-integration";
import {
  getSvfProjectMediaCache,
  isSvfMediaReadyForDecode,
} from "../../../adapter/SvfMediaBridge";
import { EditableTimecode } from "@opencut/components/editable-timecode";
import { Button } from "@opencut/components/ui/button";
import {
	FullScreenIcon,
	PauseIcon,
	PlayIcon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { Separator } from "@opencut/components/ui/separator";
import {
	Select,
	SelectTrigger,
	SelectContent,
	SelectItem,
	SelectSeparator,
} from "@opencut/components/ui/select";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@opencut/components/ui/tooltip";
import { PREVIEW_ZOOM_PRESETS } from "@opencut/preview/zoom";
import { usePreviewViewport } from "./preview-viewport";
import { useOpencutT } from "@opencut/i18n/useOpencutT";
import type { MediaTime } from "@opencut/wasm";

/** 预览区底部工具栏：时间码、播放与缩放。 */
export function PreviewToolbar({
	onToggleFullscreen,
}: {
	onToggleFullscreen: () => void;
}) {
	return (
		<TooltipProvider delayDuration={300}>
			<div className="grid grid-cols-[1fr_auto_1fr] items-center pb-3 pt-5 px-5">
				<TimecodeDisplay />
				<PlayPauseButton />
				<div className="justify-self-end flex items-center gap-2.5">
					<ZoomSelect />
					<Separator orientation="vertical" className="h-4" />
					<FullscreenButton onToggleFullscreen={onToggleFullscreen} />
				</div>
			</div>
		</TooltipProvider>
	);
}

function TimecodeDisplay() {
	const editor = useEditor();
	const totalDuration = useEditor((e) => e.timeline.getTotalDuration());
	const fps = useEditor((e) => e.project.getActive().settings.fps);
	const [currentTime, setCurrentTime] = useState<MediaTime>(() =>
		editor.playback.getCurrentTime(),
	);

	useEffect(() => {
		const unsubscribeUpdate = editor.playback.onUpdate(setCurrentTime);
		const unsubscribeSeek = editor.playback.onSeek(setCurrentTime);
		return () => {
			unsubscribeUpdate();
			unsubscribeSeek();
		};
	}, [editor.playback]);

	return (
		<div className="flex items-center">
			<EditableTimecode
				time={currentTime}
				duration={totalDuration}
				format="HH:MM:SS:FF"
				fps={fps}
				onTimeChange={({ time }) => editor.playback.seek({ time })}
				className="text-center"
			/>
			<span className="svf-preview-timecode-meta px-2 font-mono text-xs">/</span>
			<span className="svf-preview-timecode-meta font-mono text-xs">
				{formatTimecode({
					time: totalDuration,
					format: "HH:MM:SS:FF",
					rate: fps,
				})}
			</span>
		</div>
	);
}

function ZoomSelect() {
	const { tTimeline } = useOpencutT();
	const { isAtFit, zoomPercent, fitToScreen, setViewportPercent } =
		usePreviewViewport();

	const displayLabel = isAtFit ? tTimeline("fit") : `${zoomPercent}%`;

	const onValueChange = (value: string) => {
		if (value === "fit") {
			fitToScreen();
		} else {
			setViewportPercent({ percent: Number(value) });
		}
	};

	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<Select
					value={isAtFit ? "fit" : String(zoomPercent)}
					onValueChange={onValueChange}
				>
					<SelectTrigger className="tabular-nums">{displayLabel}</SelectTrigger>
					<SelectContent>
						<SelectItem value="fit">{tTimeline("fit")}</SelectItem>
						<SelectSeparator />
						{PREVIEW_ZOOM_PRESETS.map((preset) => (
							<SelectItem key={preset} value={String(preset)}>
								{preset}%
							</SelectItem>
						))}
					</SelectContent>
				</Select>
			</TooltipTrigger>
			<TooltipContent>{tTimeline("fitScreen")}</TooltipContent>
		</Tooltip>
	);
}

function PlayPauseButton() {
	const { tShortcuts } = useOpencutT();
	const isPlaying = useEditor((e) => e.playback.getIsPlaying());
	const projectKey = useEditor((e) => e.project.getActiveOrNull()?.metadata.id ?? "");
	const mediaNotReady =
		Boolean(projectKey) &&
		isSvfProjectKey(projectKey) &&
		!isSvfMediaReadyForDecode(getSvfProjectMediaCache(projectKey));

	const handleTogglePlay = () => {
		if (mediaNotReady) {
			toast.error("媒体尚未加载完成，请等待水合结束或刷新后重试。");
			return;
		}
		invokeAction("toggle-play");
	};

	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<Button
					variant="text"
					size="icon"
					disabled={mediaNotReady}
					onClick={handleTogglePlay}
				>
					<HugeiconsIcon icon={isPlaying ? PauseIcon : PlayIcon} />
				</Button>
			</TooltipTrigger>
			<TooltipContent>
				{tShortcuts("actions.toggle-play")}
			</TooltipContent>
		</Tooltip>
	);
}

function FullscreenButton({
	onToggleFullscreen,
}: {
	onToggleFullscreen: () => void;
}) {
	const { tTimeline } = useOpencutT();

	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<Button variant="text" onClick={onToggleFullscreen}>
					<HugeiconsIcon icon={FullScreenIcon} />
				</Button>
			</TooltipTrigger>
			<TooltipContent>{tTimeline("fullscreen")}</TooltipContent>
		</Tooltip>
	);
}
