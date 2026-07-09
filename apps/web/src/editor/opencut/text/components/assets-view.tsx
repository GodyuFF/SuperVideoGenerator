import { DraggableItem } from "@opencut/components/editor/panels/assets/draggable-item";
import { PanelView } from "@opencut/components/editor/panels/assets/views/base-panel";
import { useEditor } from "@opencut/editor/use-editor";
import { DEFAULTS } from "@opencut/timeline/defaults";
import { buildTextElement } from "@opencut/timeline/element-utils";
import type { MediaTime } from "@opencut/wasm";
import { useOpencutT } from "@opencut/i18n/useOpencutT";

/** 文字素材面板：拖放默认文字到时间轴。 */
export function TextView() {
	const { tAssets, tDialogs } = useOpencutT();
	const editor = useEditor();
	const defaultText = tDialogs("defaultText");

	const handleAddToTimeline = ({ currentTime }: { currentTime: MediaTime }) => {
		const activeScene = editor.scenes.getActiveScene();
		if (!activeScene) return;

		const element = buildTextElement({
			raw: DEFAULTS.text.element,
			startTime: currentTime,
		});

		editor.timeline.insertElement({
			element,
			placement: { mode: "auto" },
		});
	};

	return (
		<PanelView title={tAssets("tabs.text")}>
			<DraggableItem
				name={defaultText}
				preview={
					<div className="bg-accent flex size-full items-center justify-center rounded">
						<span className="text-xs select-none">{defaultText}</span>
					</div>
				}
				dragData={{
					id: "temp-text-id",
					type: DEFAULTS.text.element.type,
					name: DEFAULTS.text.element.name,
					content: defaultText,
				}}
				aspectRatio={1}
				onAddToTimeline={handleAddToTimeline}
				shouldShowLabel={false}
			/>
		</PanelView>
	);
}
