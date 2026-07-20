/** 资产谱系 API 类型（与 core/assets/lineage.py 对齐） */

export interface AssetDescriptor {
  id: string;
  kind: string;
  name: string;
  project_id: string;
  script_id?: string | null;
  storage?: string;
  status?: string | null;
}

export interface LineageEdge {
  id: string;
  relation: string;
  source: AssetDescriptor;
  target: AssetDescriptor;
  context?: Record<string, unknown>;
}

export interface AssetLineageView {
  asset: AssetDescriptor;
  outgoing: LineageEdge[];
  incoming: LineageEdge[];
}

export const RELATION_LABEL: Record<string, string> = {
  uses: "引用",
  generates: "生成",
  derived_from: "派生",
  rag_reuse: "RAG 复用",
  voice_of: "音色绑定",
  shot_ref: "分镜引用",
  element_ref: "画面合成",
  contains: "包含",
  has_plan: "分镜计划",
  has_plot: "剧情",
};

export const KIND_LABEL: Record<string, string> = {
  project: "项目",
  script: "剧本",
  video_plan: "计划稿",
  shot: "镜头",
  plot: "剧情",
  character: "角色",
  scene: "空镜",
  prop: "物品",
  frame: "画面",
  narration: "旁白",
  image: "图片",
  audio: "音频",
  video: "视频",
  final: "成片",
};
