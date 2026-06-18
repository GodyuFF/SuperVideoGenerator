/** 超级视频大师（主 Agent）显示名称 */
export const MASTER_AGENT_NAME = "超级视频大师";

export type StyleMode = "dynamic_image" | "ai_video";

/** 视频风格选项（与剧本绑定后不可修改） */
export const STYLE_MODE_LABELS: Record<StyleMode, string> = {
  dynamic_image: "动态图片模式",
  ai_video: "AI 视频模式",
};

export function styleModeLabel(mode: string | undefined): string {
  if (mode === "dynamic_image" || mode === "ai_video") {
    return STYLE_MODE_LABELS[mode];
  }
  return "未绑定";
}
