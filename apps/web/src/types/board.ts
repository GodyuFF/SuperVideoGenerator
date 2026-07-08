/** 看板视图类型 */

export interface BoardNode {
  id: string;
  kind: string;
  label: string;
  subtitle?: string;
  group?: string | null;
  meta?: Record<string, unknown>;
}

export interface BoardEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  label?: string;
}

export interface PipelineStepView {
  order: number;
  step_type: string;
  title: string;
  agent: string;
  status: string;
  description?: string;
}

export interface BoardView {
  kind: string;
  title: string;
  description?: string;
  nodes?: BoardNode[];
  edges?: BoardEdge[];
  items?: Record<string, unknown>[];
  pipeline?: PipelineStepView[];
  stats?: Record<string, unknown>;
}

export interface BoardKind {
  id: string;
  title: string;
}

export interface ProjectListItem {
  id: string;
  title: string;
  created_at?: string;
  script_count: number;
  scripts: { id: string; title: string; status: string }[];
}

export type BoardTabId =
  | "overview"
  | "knowledge"
  | "script_details"
  | "script"
  | "character"
  | "scene"
  | "prop"
  | "frame"
  | "storyboard"
  | "edit"
  | "media"
  | "pipeline";

export interface ScriptBoardMeta {
  has_content_md?: boolean;
  character_count?: number;
  scene_count?: number;
  prop_count?: number;
  frame_count?: number;
  shot_count?: number;
  media_count?: number;
  has_edit_timeline?: boolean;
  has_pipeline?: boolean;
}

export function visibleScriptTabs(meta: ScriptBoardMeta | null): BoardTabId[] {
  if (!meta) return [];
  const tabs: BoardTabId[] = [];
  if (meta.has_content_md) tabs.push("script");
  if ((meta.character_count ?? 0) > 0) tabs.push("character");
  if ((meta.scene_count ?? 0) > 0) tabs.push("scene");
  if ((meta.prop_count ?? 0) > 0) tabs.push("prop");
  if ((meta.frame_count ?? 0) > 0) tabs.push("frame");
  if ((meta.shot_count ?? 0) > 0) tabs.push("storyboard");
  if (meta.has_edit_timeline) tabs.push("edit");
  if ((meta.media_count ?? 0) > 0) tabs.push("media");
  if (meta.has_pipeline) tabs.push("pipeline");
  return tabs;
}

export const BOARD_TABS: { id: BoardTabId; label: string; level: 1 | 2 }[] = [
  { id: "overview", label: "整体看板", level: 1 },
  { id: "knowledge", label: "图文资产", level: 1 },
  { id: "script_details", label: "剧本详情", level: 1 },
  { id: "script", label: "剧本", level: 2 },
  { id: "character", label: "角色", level: 2 },
  { id: "scene", label: "空镜", level: 2 },
  { id: "prop", label: "物品", level: 2 },
  { id: "frame", label: "画面", level: 2 },
  { id: "storyboard", label: "分镜", level: 2 },
  { id: "edit", label: "剪辑", level: 2 },
  { id: "media", label: "媒体", level: 2 },
  { id: "pipeline", label: "生成顺序", level: 2 },
];
