import { Suspense, lazy, useMemo } from "react";
import { Separator } from "@opencut/components/ui/separator";
import { type Tab, useAssetsPanelStore } from "@opencut/components/editor/panels/assets/assets-panel-store";
import { TabBar } from "./tabbar";
import { MediaView } from "./views/assets";
import { SettingsView } from "./views/settings";

const Captions = lazy(() =>
	import("@opencut/subtitles/components/assets-view").then((m) => ({ default: m.Captions })),
);
const SoundsView = lazy(() =>
	import("@opencut/sounds/components/assets-view").then((m) => ({ default: m.SoundsView })),
);
const StickersView = lazy(() =>
	import("@opencut/stickers/components/assets-view").then((m) => ({ default: m.StickersView })),
);
const TextView = lazy(() =>
	import("@opencut/text/components/assets-view").then((m) => ({ default: m.TextView })),
);
const EffectsView = lazy(() =>
	import("@opencut/effects/components/assets-view").then((m) => ({ default: m.EffectsView })),
);

function LazyTabPanel({ children }: { children: React.ReactNode }) {
	return (
		<Suspense fallback={<p className="text-muted-foreground p-4 text-sm">加载面板…</p>}>
			{children}
		</Suspense>
	);
}

/** 素材侧栏：各 Tab 懒加载以降低 Classic 首包体积。 */
export function AssetsPanel() {
	const { activeTab } = useAssetsPanelStore();

	const viewMap: Record<Tab, React.ReactNode> = useMemo(
		() => ({
			media: <MediaView />,
			sounds: (
				<LazyTabPanel>
					<SoundsView />
				</LazyTabPanel>
			),
			text: (
				<LazyTabPanel>
					<TextView />
				</LazyTabPanel>
			),
			stickers: (
				<LazyTabPanel>
					<StickersView />
				</LazyTabPanel>
			),
			effects: (
				<LazyTabPanel>
					<EffectsView />
				</LazyTabPanel>
			),
			transitions: (
				<div className="text-muted-foreground p-4">
					Transitions view coming soon...
				</div>
			),
			captions: (
				<LazyTabPanel>
					<Captions />
				</LazyTabPanel>
			),
			adjustment: (
				<div className="text-muted-foreground p-4">
					Adjustment view coming soon...
				</div>
			),
			settings: <SettingsView />,
		}),
		[],
	);


	return (
		<div className="panel bg-background flex h-full rounded-sm border overflow-hidden">
			<TabBar />
			<Separator orientation="vertical" />
			<div className="flex-1 overflow-hidden">{viewMap[activeTab]}</div>
		</div>
	);
}
