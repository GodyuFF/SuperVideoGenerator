import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
} from "@opencut/components/ui/dialog";
import { useEditor } from "@opencut/editor/use-editor";
import { Loader2 } from "lucide-react";
import { useOpencutT } from "@opencut/i18n/useOpencutT";

/** 项目版本迁移进度对话框。 */
export function MigrationDialog() {
	const { tDialogs } = useOpencutT();
	const editor = useEditor();
	const migrationState = editor.project.getMigrationState();

	if (!migrationState.isMigrating) return null;

	const title = migrationState.projectName
		? tDialogs("migrationUpdatingProject")
		: tDialogs("migrationUpdatingProjects");
	const description = migrationState.projectName
		? tDialogs("migrationUpgradingSingle", {
				name: migrationState.projectName,
				from: migrationState.fromVersion,
				to: migrationState.toVersion,
			})
		: tDialogs("migrationUpgradingMultiple", {
				from: migrationState.fromVersion,
				to: migrationState.toVersion,
			});

	return (
		<Dialog open={true}>
			<DialogContent
				className="sm:max-w-md"
				onPointerDownOutside={(event) => event.preventDefault()}
				onEscapeKeyDown={(event) => event.preventDefault()}
			>
				<DialogHeader>
					<DialogTitle>{title}</DialogTitle>
					<DialogDescription>{description}</DialogDescription>
				</DialogHeader>

				<div className="flex items-center justify-center py-4">
					<Loader2 className="text-muted-foreground size-8 animate-spin" />
				</div>
			</DialogContent>
		</Dialog>
	);
}
