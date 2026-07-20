/** 超级视频大师（主 Agent）显示名称 */
export const MASTER_AGENT_NAME = "超级视频大师";

export type StyleMode = string;

/** 内置视频风格标签 */
export const STYLE_MODE_LABELS: Record<string, string> = {
  storybook: "故事书模式",
  ai_video: "AI 视频模式",
  frame_i2v: "画面图生视频",
};

/** 已下线的视频风格 id（历史数据迁移后不再展示）。 */
export const REMOVED_STYLE_MODE_IDS = new Set([
  "dynamic_comic",
  "marketing_video",
  "marketing",
  "dynamic_image",
]);

/** 过滤已下线风格，供 Workbench 与 Agent 配置页共用。 */
export function normalizeStyleModeOptions<T extends { id: string }>(modes: T[]): T[] {
  return modes.filter((m) => !REMOVED_STYLE_MODE_IDS.has(m.id));
}

/** 将历史/无效风格 id 规范化为可选值（默认 storybook）。 */
export function coerceStyleMode(mode: string | undefined, options?: { id: string }[]): StyleMode {
  const fallback = options?.[0]?.id ?? "storybook";
  if (!mode || REMOVED_STYLE_MODE_IDS.has(mode)) return fallback;
  if (options?.length && !options.some((o) => o.id === mode)) return fallback;
  return mode;
}

export type ImageSourceMode = "generate" | "search" | "user_choice";

export const IMAGE_SOURCE_LABELS: Record<ImageSourceMode, string> = {
  generate: "AI 批量生图",
  search: "搜索配图",
  user_choice: "执行时弹窗选择",
};

export function styleModeLabel(mode: string | undefined, labels?: Record<string, string>): string {
  if (!mode) return "未绑定";
  const normalized = REMOVED_STYLE_MODE_IDS.has(mode) ? "storybook" : mode;
  const merged = { ...STYLE_MODE_LABELS, ...labels };
  return merged[normalized] ?? normalized;
}

export function usesImageTextPipeline(mode: string | undefined): boolean {
  return mode === "storybook" || mode === "frame_i2v";
}

/** 画面图生视频模式：frame + video_clip 双轨，I2V 只认 frame。 */
export function usesFrameI2vPipeline(mode: string | undefined): boolean {
  return mode === "frame_i2v";
}

/** 可选通用提示词（随视频风格一并锁定传给 AI；未选择则不组装） */
export interface StyleHints {
  image_style?: string;
  target_duration?: string;
}

/** 可选提示词：图片风格候选（原图文/漫画预设整合为通用选项） */
export const IMAGE_STYLE_HINT_OPTIONS: string[] = [
  "科普讲解插画",
  "商务汇报风",
  "课程讲座风",
  "水彩绘本",
  "扁平插画",
  "写实摄影",
  "日漫",
  "条漫",
  "水墨",
];

/** 可选提示词：预计时长候选 */
export const TARGET_DURATION_HINT_OPTIONS: string[] = [
  "30秒",
  "60秒",
  "90秒",
  "2分钟",
  "3分钟",
  "5分钟",
];

/** 过滤空值，返回可提交的 style_hints；全部未选择时返回 null。 */
export function buildStyleHintsPayload(hints: StyleHints): StyleHints | null {
  const payload: StyleHints = {};
  if (hints.image_style?.trim()) payload.image_style = hints.image_style.trim();
  if (hints.target_duration?.trim()) payload.target_duration = hints.target_duration.trim();
  return Object.keys(payload).length > 0 ? payload : null;
}
