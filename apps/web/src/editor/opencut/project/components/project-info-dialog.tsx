import {
	Dialog,
	DialogBody,
	DialogContent,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@opencut/components/ui/dialog";
import type { TProjectMetadata } from "@opencut/project/types";
import { formatDate } from "@opencut/utils/date";
import { formatTimecode, mediaTimeToSeconds } from "opencut-wasm";
import { Button } from "@opencut/components/ui/button";
import { useOpencutT } from "@opencut/i18n/useOpencutT";

/** 项目信息行：标签与值并排展示。 */
function InfoRow({
	label,
	value,
}: {
	label: string;
	value: string | React.ReactNode;
}) {
	return (
		<div className="flex justify-between items-center py-0 last:pb-0">
			<span className="text-muted-foreground text-sm">{label}</span>
			<span className="text-sm font-medium">{value}</span>
		</div>
	);
}

/** 项目元信息对话框。 */
export function ProjectInfoDialog({
	isOpen,
	onOpenChange,
	project,
}: {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	project: TProjectMetadata;
}) {
	const { tDialogs } = useOpencutT();
	const durationSeconds = mediaTimeToSeconds({ time: project.duration });
	const durationFormatted =
		project.duration > 0
		? (formatTimecode({ time: project.duration, format: durationSeconds >= 3600 ? "HH:MM:SS" : "MM:SS" }) ?? "")
		: "0:00";

	return (
		<Dialog open={isOpen} onOpenChange={onOpenChange}>
			<DialogContent onOpenAutoFocus={(event) => event.preventDefault()}>
				<DialogHeader>
					<DialogTitle className="truncate max-w-[350px]">
						{project.name}
					</DialogTitle>
				</DialogHeader>

				<DialogBody className="flex flex-col">
					<InfoRow label={tDialogs("duration")} value={durationFormatted} />
					<InfoRow
						label={tDialogs("created")}
						value={formatDate({ date: project.createdAt })}
					/>
					<InfoRow
						label={tDialogs("modified")}
						value={formatDate({ date: project.updatedAt })}
					/>
					<InfoRow
						label={tDialogs("projectId")}
						value={
							<code className="text-xs bg-muted px-1.5 py-0.5 rounded">
								{project.id.slice(0, 8)}
							</code>
						}
					/>
				</DialogBody>
				<DialogFooter>
					<Button variant="outline" onClick={() => onOpenChange(false)}>
						{tDialogs("close")}
					</Button>
					<Button onClick={() => onOpenChange(false)}>{tDialogs("done")}</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
