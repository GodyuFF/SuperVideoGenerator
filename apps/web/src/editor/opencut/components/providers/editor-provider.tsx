import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { EditorCore } from "@opencut/core";
import { useEditor } from "@opencut/editor/use-editor";
import { useKeybindingsListener } from "@opencut/actions/use-keybindings";
import { useKeybindingsStore } from "@opencut/actions/keybindings-store";
import { useTimelineStore } from "@opencut/timeline/timeline-store";
import { useEditorActions } from "@opencut/actions/use-editor-actions";
import { loadFontAtlas } from "@opencut/fonts/google-fonts";
import {
	initializeGpuRenderer,
	isGpuAvailable,
} from "@opencut/services/renderer/gpu-renderer";
import { useOpencutT } from "@opencut/i18n/useOpencutT";

interface EditorProviderProps {
	projectId: string;
	children: React.ReactNode;
	/** SVF 弹窗嵌入模式：不跳转 /projects，紧凑 loading。 */
	embedded?: boolean;
	/** 跳过 OPFS 存储迁移（SVF 项目由 bridge 托管）。 */
	skipStorageMigration?: boolean;
}

export function EditorProvider({
	projectId,
	children,
	embedded = false,
	skipStorageMigration = false,
}: EditorProviderProps) {
	const { tDialogs } = useOpencutT();
	const activeProject = useEditor((e) => e.project.getActiveOrNull());
	const projectLoading = useEditor((e) => e.project.getIsLoading());
	const router = useRouter();
	const [isLoading, setIsLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const { setLoadingProject } = useKeybindingsStore();

	const showLoadingShell = isLoading || projectLoading;

	useEffect(() => {
		setLoadingProject(showLoadingShell);
	}, [showLoadingShell, setLoadingProject]);

	useEffect(() => {
		let alive = true;
		const editor = EditorCore.getInstance();

		const loadProject = async (allowRetry: boolean) => {
			try {
				setIsLoading(true);
				setError(null);
				await initializeGpuRenderer();
				if (!alive) return;
				editor.renderer.setDegraded(!isGpuAvailable());
				await editor.project.loadProject({ id: projectId });
				if (!alive) return;
				loadFontAtlas();
			} catch (err) {
				if (!alive) return;

				const isNotFound =
					err instanceof Error &&
					(err.message.includes("not found") ||
						err.message.includes("does not exist"));

				if (isNotFound && embedded && skipStorageMigration && allowRetry) {
					await new Promise((resolve) => setTimeout(resolve, 300));
					if (alive) {
						await loadProject(false);
					}
					return;
				}

				if (isNotFound && !embedded && !skipStorageMigration) {
					try {
						const newProjectId = await editor.project.createNewProject({
							name: "Untitled Project",
						});
						router.replace(`/editor/${newProjectId}`);
					} catch (_createErr) {
						setError(tDialogs("failedCreateProject"));
					}
				} else if (isNotFound) {
					setError(tDialogs("projectNotFound"));
				} else {
					const wasmPanic = (window as Window & { __wasmPanic?: string })
						.__wasmPanic;
					if (wasmPanic) {
						delete (window as Window & { __wasmPanic?: string }).__wasmPanic;
						setError(wasmPanic);
					} else {
						setError(
							err instanceof Error
								? err.message
								: tDialogs("failedLoadProject"),
						);
					}
				}
			} finally {
				if (alive) {
					setIsLoading(false);
				}
			}
		};

		void loadProject(true);

		return () => {
			alive = false;
		};
		// router 为稳定单例，勿加入依赖以免 loadProject notify 触发重复加载
	}, [projectId, embedded, skipStorageMigration]);

	const loadingShellClass = embedded
		? "bg-background flex h-full w-full items-center justify-center"
		: "bg-background flex h-screen w-screen items-center justify-center";

	if (error) {
		return (
			<div className={loadingShellClass}>
				<div className="flex flex-col items-center gap-4">
					<p className="text-destructive text-sm">{error}</p>
					{embedded && skipStorageMigration && (
						<p className="muted text-sm">{tDialogs("embeddedRetryHint")}</p>
					)}
				</div>
			</div>
		);
	}

	if (showLoadingShell) {
		return (
			<div className={loadingShellClass}>
				<div className="flex flex-col items-center gap-4">
					<Loader2 className="text-muted-foreground size-8 animate-spin" />
					<p className="text-muted-foreground text-sm">
						{embedded
							? tDialogs("loadingEmbedded")
							: tDialogs("loadingProject")}
					</p>
				</div>
			</div>
		);
	}

	if (!activeProject) {
		return (
			<div className={loadingShellClass}>
				<div className="flex flex-col items-center gap-4">
					<Loader2 className="text-muted-foreground size-8 animate-spin" />
					<p className="text-muted-foreground text-sm">
						{tDialogs("exitingProject")}
					</p>
				</div>
			</div>
		);
	}

	return (
		<>
			<EditorRuntimeBindings />
			{children}
		</>
	);
}

function EditorRuntimeBindings() {
	const editor = useEditor();
	const rippleEditingEnabled = useTimelineStore(
		(state) => state.rippleEditingEnabled,
	);

	useEffect(() => {
		editor.command.isRippleEnabled = rippleEditingEnabled;
	}, [editor, rippleEditingEnabled]);

	useEffect(() => {
		const handleBeforeUnload = (event: BeforeUnloadEvent) => {
			if (!editor.save.getIsDirty()) return;
			event.preventDefault();
			(event as unknown as { returnValue: string }).returnValue = "";
		};

		window.addEventListener("beforeunload", handleBeforeUnload);
		return () => window.removeEventListener("beforeunload", handleBeforeUnload);
	}, [editor]);

	useEditorActions();
	useKeybindingsListener();
	return null;
}
