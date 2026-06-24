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
  | "storyboard"
  | "media"
  | "pipeline";

export const BOARD_TABS: { id: BoardTabId; label: string; level: 1 | 2 }[] = [
  { id: "overview", label: "整体看板", level: 1 },
  { id: "knowledge", label: "知识看板", level: 1 },
  { id: "script_details", label: "剧本详情", level: 1 },
  { id: "script", label: "剧本", level: 2 },
  { id: "character", label: "角色", level: 2 },
  { id: "scene", label: "场景", level: 2 },
  { id: "storyboard", label: "分镜", level: 2 },
  { id: "media", label: "媒体", level: 2 },
  { id: "pipeline", label: "生成顺序", level: 2 },
];
