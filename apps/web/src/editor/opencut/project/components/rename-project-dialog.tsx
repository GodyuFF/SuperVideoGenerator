import { Button } from "@opencut/components/ui/button";
import {
	Dialog,
	DialogBody,
	DialogContent,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@opencut/components/ui/dialog";
import { Input } from "@opencut/components/ui/input";
import { useState } from "react";
import { Label } from "@opencut/components/ui/label";
import { useOpencutT } from "@opencut/i18n/useOpencutT";

/** 重命名项目对话框。 */
export function RenameProjectDialog({
	isOpen,
	onOpenChange,
	onConfirm,
	projectName,
}: {
	isOpen: boolean;
	onOpenChange: (open: boolean) => void;
	onConfirm: (newName: string) => void;
	projectName: string;
}) {
	const { tDialogs } = useOpencutT();
	const [name, setName] = useState(projectName);

	const handleOpenChange = (open: boolean) => {
		if (open) {
			setName(projectName);
		}
		onOpenChange(open);
	};

	return (
		<Dialog open={isOpen} onOpenChange={handleOpenChange}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>{tDialogs("renameProject")}</DialogTitle>
				</DialogHeader>

				<DialogBody className="gap-3">
					<Label>{tDialogs("newName")}</Label>
					<Input
						value={name}
						onChange={(e) => setName(e.target.value)}
						onKeyDown={(e) => {
							if (e.key === "Enter") {
								e.preventDefault();
								onConfirm(name);
							}
						}}
						placeholder={tDialogs("enterNewName")}
					/>
				</DialogBody>

				<DialogFooter>
					<Button
						variant="outline"
						onClick={(e) => {
							e.preventDefault();
							e.stopPropagation();
							onOpenChange(false);
						}}
					>
						{tDialogs("cancel")}
					</Button>
					<Button onClick={() => onConfirm(name)}>{tDialogs("rename")}</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
