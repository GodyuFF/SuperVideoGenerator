import { useState } from "react";
import {
	Popover,
	PopoverContent,
	PopoverTrigger,
} from "@opencut/components/ui/popover";
import { Button } from "@opencut/components/ui/button";
import { Progress } from "@opencut/components/ui/progress";
import { cn } from "@opencut/utils/ui";
import {
	getExportMimeType,
	getExportFileExtension,
	downloadBuffer,
} from "@opencut/export";
import { Check, Copy, Download, RotateCcw } from "lucide-react";
import type { ExportFormat, ExportQuality } from "@opencut/export";
import { useEditor } from "@opencut/editor/use-editor";
import { DEFAULT_EXPORT_OPTIONS } from "@opencut/export/defaults";
import { useOpencutT } from "@opencut/i18n/useOpencutT";
import { toast } from "sonner";
import { isSvfProjectKey } from "@opencut/svf-integration";
import {
	getSvfProjectMediaCache,
	hasHydrationFailures,
} from "../../../adapter/SvfMediaBridge";

/** 导出按钮展示场景：`cinema` 剪辑 Tab，`studio` 专业剪辑顶栏。 */
export type ExportButtonSurface = "studio" | "cinema";

/** 导出按钮与扁平静态弹出面板（剪辑 Tab 与专业剪辑顶栏共用）。 */
export function ExportButton({ surface = "studio" }: { surface?: ExportButtonSurface }) {
	const { tExport } = useOpencutT();
	const [isExportPopoverOpen, setIsExportPopoverOpen] = useState(false);
	const editor = useEditor();
	const activeProject = useEditor((e) => e.project.getActiveOrNull());
	const hasProject = !!activeProject;

	const handlePopoverOpenChange = ({ open }: { open: boolean }) => {
		if (!open) {
			editor.project.cancelExport();
			editor.project.clearExportState();
		}
		setIsExportPopoverOpen(open);
	};

	return (
		<Popover
			open={isExportPopoverOpen}
			onOpenChange={(open) => handlePopoverOpenChange({ open })}
		>
			<PopoverTrigger asChild>
				<button
					type="button"
					className={cn(
						"btn-secondary btn-sm svf-export-trigger",
						surface === "cinema" && "edit-cinema-export-trigger",
						!hasProject && "cursor-not-allowed opacity-50",
					)}
					disabled={!hasProject}
				>
					<Download className="size-3.5 shrink-0" aria-hidden />
					<span>{tExport("export")}</span>
				</button>
			</PopoverTrigger>
			{hasProject && (
				<ExportPopover
					onOpenChange={setIsExportPopoverOpen}
					surface={surface}
				/>
			)}
		</Popover>
	);
}

/** 导出选项弹出层：格式、质量、音频与进度反馈。 */
function ExportPopover({
	onOpenChange,
	surface = "studio",
}: {
	onOpenChange: (open: boolean) => void;
	surface?: ExportButtonSurface;
}) {
	const { tExport } = useOpencutT();
	const editor = useEditor();
	const activeProject = useEditor((e) => e.project.getActive());
	const exportState = useEditor((e) => e.project.getExportState());
	const { isExporting, progress, result: exportResult } = exportState;
	const [format, setFormat] = useState<ExportFormat>(
		DEFAULT_EXPORT_OPTIONS.format,
	);
	const [quality, setQuality] = useState<ExportQuality>(
		DEFAULT_EXPORT_OPTIONS.quality,
	);
	const [shouldIncludeAudio, setShouldIncludeAudio] = useState<boolean>(
		DEFAULT_EXPORT_OPTIONS.includeAudio ?? true,
	);

	const projectKey = activeProject?.metadata.id ?? "";
	const mediaHydrationBlocked =
		Boolean(projectKey) &&
		isSvfProjectKey(projectKey) &&
		hasHydrationFailures(getSvfProjectMediaCache(projectKey));

	const handleExport = async () => {
		if (!activeProject) return;
		if (shouldIncludeAudio && mediaHydrationBlocked) {
			toast.error(
				"音频媒体加载失败，无法导出有声成片。请检查网络后刷新剪辑助手。",
			);
			return;
		}

		const result = await editor.project.export({
			options: {
				format,
				quality,
				fps: activeProject.settings.fps,
				includeAudio: shouldIncludeAudio,
			},
		});

		if (result.cancelled) {
			editor.project.clearExportState();
			return;
		}

		if (result.success && result.buffer) {
			downloadBuffer({
				buffer: result.buffer,
				filename: `${activeProject.metadata.name}${getExportFileExtension({ format })}`,
				mimeType: getExportMimeType({ format }),
			});

			if (result.audioWarning) {
				toast.warning(result.audioWarning);
			}

			editor.project.clearExportState();
			onOpenChange(false);
		}
	};

	const handleCancel = () => {
		editor.project.cancelExport();
	};

	return (
		<PopoverContent
			className="edit-cinema-export-popover svf-editor-overlay-content z-[10001] flex w-[min(20rem,calc(100vw-2rem))] flex-col p-0"
			align="end"
			side="bottom"
			sideOffset={8}
		>
			{exportResult && !exportResult.success ? (
				<ExportError
					error={exportResult.error || tExport("unknownError")}
					onRetry={handleExport}
				/>
			) : (
				<>
					<div className="edit-cinema-export-popover-head flex items-center justify-between border-b px-3 py-2.5">
						<h3 className="text-sm font-medium">
							{isExporting
								? tExport("exportingProject")
								: tExport("exportProject")}
						</h3>
					</div>

					<div className="flex flex-col gap-4">
						{!isExporting && (
							<>
								<SvfExportOptionsForm
									surface={surface}
									format={format}
									quality={quality}
									shouldIncludeAudio={shouldIncludeAudio}
									mediaHydrationBlocked={mediaHydrationBlocked}
									onFormatChange={setFormat}
									onQualityChange={setQuality}
									onIncludeAudioChange={setShouldIncludeAudio}
								/>

								<div className="edit-cinema-export-popover-foot p-3 pt-0">
									{mediaHydrationBlocked && shouldIncludeAudio && (
										<p className="edit-cinema-export-warn mb-2 text-xs">
											音频媒体加载失败，导出将不可用。请刷新后重试。
										</p>
									)}
									<button
										type="button"
										className="btn-primary btn-sm edit-cinema-export-submit w-full"
										disabled={shouldIncludeAudio && mediaHydrationBlocked}
										onClick={() => void handleExport()}
									>
										<Download className="size-4" aria-hidden />
										{tExport("export")}
									</button>
								</div>
							</>
						)}

						{isExporting && (
							<div className="space-y-4 p-3">
								<div className="flex flex-col gap-2">
									<div className="flex items-center justify-between text-center">
										<p className="text-muted-foreground text-sm">
											{Math.round(progress * 100)}%
										</p>
										<p className="text-muted-foreground text-sm">100%</p>
									</div>
									<Progress value={progress * 100} className="w-full" />
								</div>

								<button
									type="button"
									className="btn-secondary btn-sm w-full"
									onClick={handleCancel}
								>
									{tExport("cancel")}
								</button>
							</div>
						)}
					</div>
				</>
			)}
		</PopoverContent>
	);
}

const EXPORT_FORMAT_OPTIONS: {
	value: ExportFormat;
	labelKey: "formatMp4" | "formatWebm";
}[] = [
	{ value: "mp4", labelKey: "formatMp4" },
	{ value: "webm", labelKey: "formatWebm" },
];

const EXPORT_QUALITY_OPTIONS: {
	value: ExportQuality;
	labelKey: "qualityLow" | "qualityMedium" | "qualityHigh" | "qualityVeryHigh";
	shortKey:
		| "qualityLowShort"
		| "qualityMediumShort"
		| "qualityHighShort"
		| "qualityVeryHighShort";
}[] = [
	{ value: "low", labelKey: "qualityLow", shortKey: "qualityLowShort" },
	{ value: "medium", labelKey: "qualityMedium", shortKey: "qualityMediumShort" },
	{ value: "high", labelKey: "qualityHigh", shortKey: "qualityHighShort" },
	{
		value: "very_high",
		labelKey: "qualityVeryHigh",
		shortKey: "qualityVeryHighShort",
	},
];

/** 扁平静态导出表单，使用 SVF 令牌避免 OpenCut 主题污染。 */
function SvfExportOptionsForm({
	surface,
	format,
	quality,
	shouldIncludeAudio,
	mediaHydrationBlocked,
	onFormatChange,
	onQualityChange,
	onIncludeAudioChange,
}: {
	surface: ExportButtonSurface;
	format: ExportFormat;
	quality: ExportQuality;
	shouldIncludeAudio: boolean;
	mediaHydrationBlocked: boolean;
	onFormatChange: (value: ExportFormat) => void;
	onQualityChange: (value: ExportQuality) => void;
	onIncludeAudioChange: (value: boolean) => void;
}) {
	const { tExport } = useOpencutT();
	const formatGroupName = `${surface}-export-format`;

	return (
		<div className="edit-cinema-export-form">
			<fieldset className="edit-cinema-export-field">
				<legend className="edit-cinema-export-label">{tExport("format")}</legend>
				<div className="edit-cinema-export-options">
					{EXPORT_FORMAT_OPTIONS.map((option) => {
						const selected = format === option.value;
						return (
							<label
								key={option.value}
								className={cn(
									"edit-cinema-export-option",
									selected && "edit-cinema-export-option--selected",
								)}
							>
								<input
									type="radio"
									name={formatGroupName}
									value={option.value}
									checked={selected}
									className="edit-cinema-export-sr-only"
									onChange={() => onFormatChange(option.value)}
								/>
								<span className="edit-cinema-export-option-marker" aria-hidden />
								<span className="edit-cinema-export-option-text">
									{tExport(option.labelKey)}
								</span>
							</label>
						);
					})}
				</div>
			</fieldset>

			<fieldset className="edit-cinema-export-field">
				<legend className="edit-cinema-export-label">{tExport("quality")}</legend>
				<div
					className="edit-cinema-export-segments"
					role="radiogroup"
					aria-label={tExport("quality")}
				>
					{EXPORT_QUALITY_OPTIONS.map((option) => {
						const selected = quality === option.value;
						return (
							<button
								key={option.value}
								type="button"
								role="radio"
								aria-checked={selected}
								title={tExport(option.labelKey)}
								className={cn(
									"edit-cinema-export-segment",
									selected && "edit-cinema-export-segment--selected",
								)}
								onClick={() => onQualityChange(option.value)}
							>
								{tExport(option.shortKey)}
							</button>
						);
					})}
				</div>
			</fieldset>

			<div className="edit-cinema-export-field">
				<label
					className={cn(
						"edit-cinema-export-audio",
						mediaHydrationBlocked && "edit-cinema-export-audio--blocked",
					)}
				>
					<input
						type="checkbox"
						className="edit-cinema-export-audio-input"
						checked={shouldIncludeAudio}
						onChange={(event) => onIncludeAudioChange(event.target.checked)}
					/>
					<span className="edit-cinema-export-audio-box" aria-hidden />
					<span className="edit-cinema-export-audio-text">
						{tExport("includeAudio")}
					</span>
				</label>
			</div>
		</div>
	);
}

/** 导出失败时的复制与重试操作区。 */
function ExportError({
	error,
	onRetry,
}: {
	error: string;
	onRetry: () => void;
}) {
	const { tExport } = useOpencutT();
	const [copied, setCopied] = useState(false);

	const handleCopy = async () => {
		await navigator.clipboard.writeText(error);
		setCopied(true);
		setTimeout(() => setCopied(false), 1000);
	};

	return (
		<div className="space-y-4 p-3">
			<div className="flex flex-col gap-1.5">
				<p className="edit-cinema-export-warn text-sm font-medium">
					{tExport("exportFailed")}
				</p>
				<p className="text-xs" style={{ color: "var(--svf-muted)" }}>
					{error}
				</p>
			</div>

			<div className="flex gap-2">
				<button
					type="button"
					className="btn-secondary btn-sm flex-1 text-xs"
					onClick={() => void handleCopy()}
				>
					{copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
					{tExport("copy")}
				</button>
				<button
					type="button"
					className="btn-secondary btn-sm flex-1 text-xs"
					onClick={onRetry}
				>
					<RotateCcw className="size-3.5" />
					{tExport("retry")}
				</button>
			</div>
		</div>
	);
}
