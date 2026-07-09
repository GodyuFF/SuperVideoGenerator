import { Button } from "@opencut/components/ui/button";
import {
	Dialog,
	DialogBody,
	DialogContent,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@opencut/components/ui/dialog";
import { useStoragePersistence } from "@opencut/services/storage/use-storage-persistence";
import { useOpencutT } from "@opencut/i18n/useOpencutT";

/** 浏览器持久化存储授权对话框。 */
export function StoragePersistenceDialog() {
	const { tDialogs } = useOpencutT();
	const { showDialog, onConfirm, onDismiss } = useStoragePersistence();

	return (
		<Dialog open={showDialog} onOpenChange={(open) => !open && onDismiss()}>
			<DialogContent className="sm:max-w-md">
				<DialogHeader>
					<DialogTitle>{tDialogs("storageDontLoseTitle")}</DialogTitle>
				</DialogHeader>
				<DialogBody>
					<p className="text-base text-muted-foreground">
						{tDialogs("storageDontLoseBody1")}
					</p>
					<p className="text-base text-muted-foreground">
						{tDialogs("storageDontLoseBody2")}
					</p>
				</DialogBody>
				<DialogFooter>
					<Button variant="outline" onClick={onDismiss}>
						{tDialogs("storageNotNow")}
					</Button>
					<Button onClick={onConfirm}>{tDialogs("storageAllow")}</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
