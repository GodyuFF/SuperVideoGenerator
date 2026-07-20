import type { EditorCore } from "@opencut/core";
import type {
	TProject,
	TProjectMetadata,
	TProjectSortKey,
	TProjectSortOption,
	TProjectSettings,
	TTimelineViewState,
} from "@opencut/project/types";

/** 判断时间轴视图状态是否等价，避免重复 notify 引发 React 更新风暴。 */
function isTimelineViewStateEqual({
	current,
	next,
}: {
	current: TTimelineViewState;
	next: TTimelineViewState;
}): boolean {
	return (
		current.zoomLevel === next.zoomLevel &&
		current.scrollLeft === next.scrollLeft &&
		Object.is(current.playheadTime, next.playheadTime)
	);
}
import type { ExportOptions, ExportResult, ExportState } from "@opencut/export";
import { storageService } from "@opencut/services/storage/service";
import { toast } from "sonner";
import { generateUUID } from "@opencut/utils/id";
import { UpdateProjectSettingsCommand } from "@opencut/commands/project";
import { DEFAULT_BACKGROUND_COLOR } from "@opencut/background/color";
import { DEFAULT_CANVAS_SIZE } from "@opencut/canvas/sizes";
import { DEFAULT_FPS } from "@opencut/fps/defaults";
import { buildDefaultScene, getProjectDurationFromScenes } from "@opencut/timeline/scenes";
import { buildScene } from "@opencut/services/renderer/scene-builder";
import { CanvasRenderer } from "@opencut/services/renderer/canvas-renderer";
import { CURRENT_PROJECT_VERSION } from "@opencut/services/storage/constants";
import { loadFonts } from "@opencut/fonts/google-fonts";
import { DEFAULTS } from "@opencut/timeline/defaults";
import { getElementFontFamilies } from "@opencut/timeline/element-utils";
import { getRaisedProjectFpsForImportedMedia } from "@opencut/fps/utils";
import type { MediaAsset } from "@opencut/media/types";
import { isSvfProjectKey } from "@opencut/svf-integration";

export class ProjectManager {
	private active: TProject | null = null;
	private savedProjects: TProjectMetadata[] = [];
	private isLoading = true;
	private isInitialized = false;
	private invalidProjectIds = new Set<string>();
	private listeners = new Set<() => void>();
	private exportState: ExportState = {
		isExporting: false,
		progress: 0,
		result: null,
	};
	private exportCancelRequested = false;
	private loadProjectInFlight: Promise<void> | null = null;
	private loadProjectInFlightId: string | null = null;

	constructor(private editor: EditorCore) {}

	async createNewProject({ name }: { name: string }): Promise<string> {
		const mainScene = buildDefaultScene({ name: "Main scene", isMain: true });
		const newProject: TProject = {
			metadata: {
				id: generateUUID(),
				name,
				duration: getProjectDurationFromScenes({ scenes: [mainScene] }),
				createdAt: new Date(),
				updatedAt: new Date(),
			},
			scenes: [mainScene],
			currentSceneId: mainScene.id,
			settings: {
				fps: DEFAULT_FPS,
				canvasSize: DEFAULT_CANVAS_SIZE,
				canvasSizeMode: "preset",
				lastCustomCanvasSize: null,
				originalCanvasSize: null,
				background: {
					type: "color",
					color: DEFAULT_BACKGROUND_COLOR,
				},
			},
			version: CURRENT_PROJECT_VERSION,
		};

		this.active = newProject;
		this.notify();

		this.editor.media.clearAllAssets();
		this.editor.scenes.initializeScenes({
			scenes: newProject.scenes,
			currentSceneId: newProject.currentSceneId,
		});

		try {
			await storageService.saveProject({ project: newProject });
			this.updateMetadata(newProject);

			return newProject.metadata.id;
		} catch (error) {
			toast.error("Failed to save new project");
			throw error;
		}
	}

	async loadProject({ id }: { id: string }): Promise<void> {
		if (this.loadProjectInFlight && this.loadProjectInFlightId === id) {
			return this.loadProjectInFlight;
		}

		const run = this.loadProjectInternal({ id });
		this.loadProjectInFlight = run;
		this.loadProjectInFlightId = id;
		try {
			await run;
		} finally {
			if (this.loadProjectInFlightId === id) {
				this.loadProjectInFlight = null;
				this.loadProjectInFlightId = null;
			}
		}
	}

	/** 实际执行项目加载，避免并发 loadProject 互相 clearScenes 导致卡死。 */
	private async loadProjectInternal({ id }: { id: string }): Promise<void> {
		this.isLoading = true;
		this.notify();

		this.editor.save.pause();

		try {
			const result = await storageService.loadProject({ id });
			if (!result) {
				throw new Error(`Project with id ${id} not found`);
			}

      const project = result.project;

      // 原子切换场景，避免 clearScenes 造成 active=null 窗口期
      this.editor.scenes.initializeScenes({
        scenes: project.scenes ?? [],
        currentSceneId: project.currentSceneId,
      });

      let activeProject = project;
      if (isSvfProjectKey(id)) {
        const scenes = this.editor.scenes.getScenes();
        const sceneDuration = getProjectDurationFromScenes({ scenes });
        if (sceneDuration > 0 && sceneDuration !== project.metadata.duration) {
          activeProject = {
            ...project,
            metadata: {
              ...project.metadata,
              duration: sceneDuration,
            },
          };
        }
      }

      this.active = activeProject;
			this.notify();

			this.editor.media.clearAllAssets();
			await this.editor.media.loadProjectMedia({ projectId: id });

			// 字体预加载不阻塞首屏（Google Fonts 在部分网络环境下会永久 pending）
			void loadFonts({
				families: [
					...new Set(
						(project.scenes ?? []).flatMap((scene) =>
							getElementFontFamilies({ tracks: scene.tracks }),
						),
					),
				],
			}).catch((error) => {
				console.warn("Font preload failed:", error);
			});

			// SVF 项目由 bridge 托管，跳过缩略图生成与即时保存，避免 load→save→notify 循环。
			if (!project.metadata.thumbnail && !isSvfProjectKey(id)) {
				try {
					const didUpdateThumbnail = await this.updateThumbnailFromTimeline();
					if (didUpdateThumbnail) {
						await this.saveCurrentProject();
					}
				} catch (error) {
					console.error("Failed to generate project thumbnail:", error);
				}
			}
		} catch (error) {
			console.error("Failed to load project:", error);
			this.editor.scenes.clearScenes();
			this.active = null;
			this.notify();
			throw error;
		} finally {
			this.isLoading = false;
			this.notify();
			this.editor.save.resume();
		}
	}

	async saveCurrentProject(): Promise<void> {
		if (!this.active) return;

		try {
			const scenes = this.editor.scenes.getScenes();
			const updatedProject = {
				...this.active,
				scenes,
				metadata: {
					...this.active.metadata,
					duration: getProjectDurationFromScenes({ scenes }),
					updatedAt: new Date(),
				},
			};

			await storageService.saveProject({ project: updatedProject });
			this.active = updatedProject;
			this.updateMetadata(updatedProject);
		} catch (error) {
			console.error("Failed to save project:", error);
		}
	}

	async export({ options }: { options: ExportOptions }): Promise<ExportResult> {
		this.exportCancelRequested = false;
		this.exportState = { isExporting: true, progress: 0, result: null };
		this.notify();

		const result = await this.editor.renderer.exportProject({
			options,
			onProgress: ({ progress }) => {
				this.exportState = { ...this.exportState, progress };
				this.notify();
			},
			onCancel: () => this.exportCancelRequested,
		});

		this.exportState = {
			isExporting: false,
			progress: this.exportState.progress,
			result,
		};
		this.notify();

		return result;
	}

	cancelExport(): void {
		this.exportCancelRequested = true;
	}

	clearExportState(): void {
		this.exportState = { isExporting: false, progress: 0, result: null };
		this.notify();
	}

	getExportState(): ExportState {
		return this.exportState;
	}

	async loadAllProjects(): Promise<void> {
		if (!this.isInitialized) {
			this.isLoading = true;
			this.notify();
		}

		try {
			const metadata = await storageService.loadAllProjectsMetadata();
			this.savedProjects = metadata;
			this.notify();
		} catch (error) {
			console.error("Failed to load projects:", error);
		} finally {
			this.isLoading = false;
			this.isInitialized = true;
			this.notify();
		}
	}

	async deleteProjects({ ids }: { ids: string[] }): Promise<void> {
		const uniqueIds = Array.from(new Set(ids));
		if (uniqueIds.length === 0) return;

		try {
			await Promise.all(
				uniqueIds.map((id) =>
					Promise.all([
						storageService.deleteProjectMedia({ projectId: id }),
						storageService.deleteProject({ id }),
					]),
				),
			);

			const idSet = new Set(uniqueIds);
			this.savedProjects = this.savedProjects.filter(
				(project) => !idSet.has(project.id),
			);

			const shouldClearActive =
				this.active && idSet.has(this.active.metadata.id);

			if (shouldClearActive) {
				this.active = null;
				this.editor.media.clearAllAssets();
				this.editor.scenes.clearScenes();
			}

			this.notify();
		} catch (error) {
			console.error("Failed to delete projects:", error);
		}
	}

	closeProject(): void {
		this.active = null;
		this.notify();

		this.editor.media.clearAllAssets();
		this.editor.scenes.clearScenes();
	}

	async renameProject({
		id,
		name,
	}: {
		id: string;
		name: string;
	}): Promise<void> {
		try {
			const result = await storageService.loadProject({ id });
			if (!result) {
				toast.error("Project not found", {
					description: "Please try again",
				});
				return;
			}

			const updatedProject: TProject = {
				...result.project,
				metadata: {
					...result.project.metadata,
					name,
					updatedAt: new Date(),
				},
			};

			await storageService.saveProject({ project: updatedProject });

			if (this.active?.metadata.id === id) {
				this.active = updatedProject;
				this.notify();
			}

			this.updateMetadata(updatedProject);
		} catch (error) {
			console.error("Failed to rename project:", error);
			toast.error("Failed to rename project", {
				description:
					error instanceof Error ? error.message : "Please try again",
			});
		}
	}

	async duplicateProjects({ ids }: { ids: string[] }): Promise<string[]> {
		const uniqueIds = Array.from(new Set(ids));
		if (uniqueIds.length === 0) return [];

		try {
			const getDuplicateBaseName = ({ name }: { name: string }) => {
				const match = name.match(/^\((\d+)\)\s+(.+)$/);
				const number = match ? Number.parseInt(match[1], 10) : null;
				const baseName = match ? match[2] : name;
				return { baseName, number };
			};

			const loadResults = await Promise.all(
				uniqueIds.map(async (projectId) => {
					const result = await storageService.loadProject({ id: projectId });
					return { projectId, project: result?.project ?? null };
				}),
			);

			const missingProjectIds = loadResults
				.filter((result) => !result.project)
				.map((result) => result.projectId);

			if (missingProjectIds.length > 0) {
				toast.error(
					missingProjectIds.length === 1
						? "Project not found"
						: "Projects not found",
					{
						description:
							missingProjectIds.length === 1
								? "Please try again"
								: "Some projects could not be found",
					},
				);
				throw new Error(`Projects not found: ${missingProjectIds.join(", ")}`);
			}

			const projectsToDuplicate = loadResults.flatMap((result) =>
				result.project ? [result.project] : [],
			);

			const maxNumberByBaseName = new Map<string, number>();

			for (const project of this.savedProjects) {
				const { baseName, number } = getDuplicateBaseName({
					name: project.name,
				});

				if (number === null) continue;

				const currentMax = maxNumberByBaseName.get(baseName);
				if (currentMax === undefined || number > currentMax) {
					maxNumberByBaseName.set(baseName, number);
				}
			}

			const nextNumberByBaseName = new Map<string, number>();
			for (const [baseName, maxNumber] of maxNumberByBaseName) {
				nextNumberByBaseName.set(baseName, maxNumber + 1);
			}

			const duplicationPlans = projectsToDuplicate.map((project) => {
				const { baseName } = getDuplicateBaseName({
					name: project.metadata.name,
				});
				const nextNumber = nextNumberByBaseName.get(baseName) ?? 1;
				nextNumberByBaseName.set(baseName, nextNumber + 1);

				const newProjectId = generateUUID();
				const newProject: TProject = {
					...project,
					metadata: {
						...project.metadata,
						id: newProjectId,
						name: `(${nextNumber}) ${baseName}`,
						createdAt: new Date(),
						updatedAt: new Date(),
					},
				};

				return {
					newProjectId,
					newProject,
					sourceProjectId: project.metadata.id,
				};
			});

			await Promise.all(
				duplicationPlans.map(({ newProject }) =>
					storageService.saveProject({ project: newProject }),
				),
			);

			await Promise.all(
				duplicationPlans.map(async ({ sourceProjectId, newProjectId }) => {
					const sourceMediaAssets = await storageService.loadAllMediaAssets({
						projectId: sourceProjectId,
					});

					await Promise.all(
						sourceMediaAssets.map((mediaAsset) =>
							storageService.saveMediaAsset({
								projectId: newProjectId,
								mediaAsset,
							}),
						),
					);
				}),
			);

			for (const { newProject } of duplicationPlans) {
				this.updateMetadata(newProject);
			}

			return duplicationPlans.map((plan) => plan.newProjectId);
		} catch (error) {
			console.error("Failed to duplicate projects:", error);
			toast.error("Failed to duplicate projects", {
				description:
					error instanceof Error ? error.message : "Please try again",
			});
			throw error;
		}
	}

	async updateSettings({
		settings,
		pushHistory = true,
	}: {
		settings: Partial<TProjectSettings>;
		pushHistory?: boolean;
	}): Promise<void> {
		if (!this.active) return;

		const command = new UpdateProjectSettingsCommand(settings);
		if (pushHistory) {
			this.editor.command.execute({ command });
			return;
		}

		command.execute();
	}

	ratchetFpsForImportedMedia({
		importedAssets,
	}: {
		importedAssets: Array<Pick<MediaAsset, "type" | "fps">>;
	}): import("opencut-wasm").FrameRate | null {
		if (!this.active) return null;

		const nextFps = getRaisedProjectFpsForImportedMedia({
			currentFps: this.active.settings.fps,
			importedAssets,
		});
		if (nextFps === null) return null;

		new UpdateProjectSettingsCommand({ fps: nextFps }).execute();
		return nextFps;
	}

	async updateThumbnail({ thumbnail }: { thumbnail: string }): Promise<void> {
		if (!this.active) return;
		if (this.active.metadata.thumbnail === thumbnail) return;

		const updatedProject: TProject = {
			...this.active,
			metadata: { ...this.active.metadata, thumbnail, updatedAt: new Date() },
		};
		this.active = updatedProject;
		this.updateMetadata(updatedProject);
		const projectId = this.active.metadata.id;
		if (!isSvfProjectKey(projectId)) {
			this.editor.save.markDirty();
		}
	}

	async prepareExit(): Promise<void> {
		if (!this.active) return;

		try {
			const didUpdateThumbnail = await this.updateThumbnailFromTimeline();
			if (didUpdateThumbnail) {
				await this.editor.save.flush();
			}
		} catch (error) {
			console.error("Failed to generate project thumbnail on exit:", error);
		}
	}

	getFilteredAndSortedProjects({
		searchQuery,
		sortOption,
	}: {
		searchQuery: string;
		sortOption: TProjectSortOption;
	}): TProjectMetadata[] {
		const filteredProjects = this.savedProjects.filter((project) =>
			project.name.toLowerCase().includes(searchQuery.toLowerCase()),
		);

		const [key, order] = sortOption.split("-") as [
			TProjectSortKey,
			"asc" | "desc",
		];

		const sortedProjects = [...filteredProjects].sort((a, b) => {
			const aValue = a[key];
			const bValue = b[key];

			if (order === "asc") {
				if (aValue < bValue) return -1;
				if (aValue > bValue) return 1;
				return 0;
			}
			if (aValue > bValue) return -1;
			if (aValue < bValue) return 1;
			return 0;
		});

		return sortedProjects;
	}

	isInvalidProjectId({ id }: { id: string }): boolean {
		return this.invalidProjectIds.has(id);
	}

	markProjectIdAsInvalid({ id }: { id: string }): void {
		this.invalidProjectIds.add(id);
		this.notify();
	}

	clearInvalidProjectIds(): void {
		this.invalidProjectIds.clear();
		this.notify();
	}

	getActive(): TProject {
		if (!this.active) {
			throw new Error("No active project");
		}
		return this.active;
	}

	/**
	 * for agents:
	 * in most cases, the project is guaranteed to be active, in which getActive() should be used instead.
	 * for very rare cases, this function may be used.
	 */
	getActiveOrNull(): TProject | null {
		return this.active;
	}

	getTimelineViewState(): TTimelineViewState {
		return this.active?.timelineViewState ?? DEFAULTS.timeline.viewState;
	}

	setTimelineViewState({ viewState }: { viewState: TTimelineViewState }): void {
		if (!this.active) return;
		const current = this.getTimelineViewState();
		const next = viewState ?? DEFAULTS.timeline.viewState;
		if (isTimelineViewStateEqual({ current, next })) {
			return;
		}
		this.active = {
			...this.active,
			timelineViewState: next,
		};
		this.editor.save.markDirty();
		this.notify();
	}

	getSavedProjects(): TProjectMetadata[] {
		return this.savedProjects;
	}

	getIsLoading(): boolean {
		return this.isLoading;
	}

	getIsInitialized(): boolean {
		return this.isInitialized;
	}

	setActiveProject({ project }: { project: TProject }): void {
		this.active = project;
		this.notify();
	}

	subscribe(listener: () => void): () => void {
		this.listeners.add(listener);
		return () => this.listeners.delete(listener);
	}

	private async updateThumbnailFromTimeline(): Promise<boolean> {
		if (!this.active) return false;

		const tracks = this.editor.scenes.getActiveScene().tracks;
		const mediaAssets = this.editor.media.getAssets();
		const duration = this.editor.timeline.getTotalDuration();
		const { canvasSize, background } = this.active.settings;

		const scene = buildScene({
			tracks,
			mediaAssets,
			duration: duration || 1,
			canvasSize,
			background,
		});

		const renderer = new CanvasRenderer({
			width: canvasSize.width,
			height: canvasSize.height,
			fps: this.active.settings.fps,
		});

		const tempCanvas = document.createElement("canvas");
		tempCanvas.width = canvasSize.width;
		tempCanvas.height = canvasSize.height;

		await renderer.renderToCanvas({
			node: scene,
			time: 0,
			targetCanvas: tempCanvas,
		});

		const thumbnailDataUrl = tempCanvas.toDataURL("image/png");

		await this.updateThumbnail({ thumbnail: thumbnailDataUrl });
		return true;
	}

	private updateMetadata(project: TProject): void {
		const index = this.savedProjects.findIndex(
			(p) => p.id === project.metadata.id,
		);

		if (index !== -1) {
			this.savedProjects = this.savedProjects.with(index, project.metadata);
		} else {
			this.savedProjects = [project.metadata, ...this.savedProjects];
		}

		this.notify();
	}

	private notify(): void {
		this.listeners.forEach((fn) => {
			fn();
		});
	}
}
