/** 超级视频大师（主 Agent）显示名称 */
export const MASTER_AGENT_NAME = "超级视频大师";

export type StyleMode = "dynamic_image" | "dynamic_comic" | "ai_video";

/** 视频风格选项（与剧本绑定后不可修改） */
export const STYLE_MODE_LABELS: Record<StyleMode, string> = {
  dynamic_image: "动态图文模式",
  dynamic_comic: "动态漫画模式",
  ai_video: "AI 视频模式",
};

export type ImageSourceMode = "generate" | "search" | "user_choice";

export const IMAGE_SOURCE_LABELS: Record<ImageSourceMode, string> = {
  generate: "AI 批量生图",
  search: "搜索配图",
  user_choice: "执行时弹窗选择",
};

export function styleModeLabel(mode: string | undefined): string {
  if (mode === "dynamic_image" || mode === "dynamic_comic" || mode === "ai_video") {
    return STYLE_MODE_LABELS[mode];
  }
  return "未绑定";
}

export function usesImageTextPipeline(mode: string | undefined): boolean {
  return mode === "dynamic_image" || mode === "dynamic_comic";
}

export type ImageTextPreset = "explainer" | "report" | "lecture";
export type ComicPreset = "manga" | "webtoon" | "ink";

const IMAGE_TEXT_PRESET_LABELS: Record<ImageTextPreset, string> = {
  explainer: "科普讲解",
  report: "汇报",
  lecture: "课程讲座",
};

const COMIC_PRESET_LABELS: Record<ComicPreset, string> = {
  manga: "日漫",
  webtoon: "条漫",
  ink: "水墨",
};

export function imageTextPresetLabel(preset: string | undefined): string {
  if (preset === "explainer" || preset === "report" || preset === "lecture") {
    return IMAGE_TEXT_PRESET_LABELS[preset];
  }
  return preset || "默认";
}

export function comicPresetLabel(preset: string | undefined): string {
  if (preset === "manga" || preset === "webtoon" || preset === "ink") {
    return COMIC_PRESET_LABELS[preset];
  }
  return preset || "默认";
}
