import { Button } from "@opencut/components/ui/button";
import {
	Dialog,
	DialogBody,
	DialogContent,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@opencut/components/ui/dialog";
import { Alert, AlertDescription, AlertTitle } from "@opencut/components/ui/alert";
import { Label } from "@opencut/components/ui/label";
import { Input } from "@opencut/components/ui/input";
import { useOpencutT } from "@opencut/i18n/useOpencutT";

/** 删除项目确认对话框。 */
export function DeleteProjectDialog({
	isOpen,
	onOpenChange,
	onConfirm,
	projectNames,
}: {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	onConfirm: () => void;
	projectNames: string[];
}) {
	const { tDialogs } = useOpencutT();
	const count = projectNames.length;
	const isSingle = count === 1;
	const singleName = isSingle ? projectNames[0] : null;

	return (
		<Dialog open={isOpen} onOpenChange={onOpenChange}>
			<DialogContent
				onOpenAutoFocus={(event) => {
					event.preventDefault();
					event.stopPropagation();
				}}
			>
				<DialogHeader>
					<DialogTitle>
						{singleName
							? tDialogs("deleteProjectTitle", { name: singleName })
							: tDialogs("deleteProjectsTitle", { count })}
					</DialogTitle>
				</DialogHeader>
				<DialogBody>
					<Alert variant="destructive">
						<AlertTitle>{tDialogs("warning")}</AlertTitle>
						<AlertDescription>
							{singleName
								? tDialogs("deleteProjectWarningSingle", { name: singleName })
								: tDialogs("deleteProjectWarningMultiple", { count })}
						</AlertDescription>
					</Alert>
					<div className="flex flex-col gap-3">
						<Label className="text-xs font-semibold text-slate-500">
							{tDialogs("typeDeleteConfirm")}
						</Label>
						<Input
							type="text"
							placeholder={tDialogs("deleteConfirmPlaceholder")}
							size="lg"
							variant="destructive"
						/>
					</div>
				</DialogBody>
				<DialogFooter>
					<Button variant="outline" onClick={() => onOpenChange(false)}>
						{tDialogs("cancel")}
					</Button>
					<Button variant="destructive" onClick={onConfirm}>
						{tDialogs("deleteProject")}
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
