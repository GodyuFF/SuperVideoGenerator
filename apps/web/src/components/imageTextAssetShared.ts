/**
 * 图文资产展示/编辑共用字段工具。
 */

import type { ImageTextAssetItem } from "./ImageTextAssetCard";

export const TYPE_LABEL: Record<string, string> = {
  character: "角色",
  prop: "物品",
  scene: "空镜",
  frame: "画面",
};

export const TRAIT_LABEL: Record<string, string> = {
  role: "角色定位",
  personality: "性格",
  age_range: "年龄",
  gender: "性别",
  costume: "服装",
  distinctive_features: "标志特征",
  ethnicity: "族裔/人种",
  body_type: "体型",
  height: "身高",
  build: "体格",
  hair_style: "发型",
  hair_color: "发色",
  eye_color: "瞳色",
  facial_features: "面部特征",
  default_expression: "默认表情",
  default_pose: "默认姿态",
  accessories: "配饰",
  location: "地点",
  time_of_day: "时段",
  weather: "天气",
  lighting: "光线",
  mood: "氛围",
  spatial_layout: "空间布局",
  architecture_style: "建筑风格",
  key_objects: "关键物体",
  foreground: "前景",
  background: "背景",
  camera_angle: "机位角度",
  depth_of_field: "景深",
  color_tone: "色调",
  category: "类别",
  material: "材质",
  size_scale: "尺寸",
  usage: "用途",
  condition: "状态",
  shape: "形状",
  color: "颜色",
  texture: "纹理",
  brand_style: "品牌风格",
  visual_details: "视觉细节",
};

export function isPlaceholderUrl(url: string | undefined): boolean {
  if (!url?.trim()) return true;
  const u = url.trim().toLowerCase();
  return u.includes("example.com") || u.startsWith("/assets/");
}

export function traitEntries(item: ImageTextAssetItem): [string, string][] {
  const fromTraits = item.traits ?? {};
  const content = item.content ?? {};
  const keys = new Set([...Object.keys(fromTraits), ...Object.keys(TRAIT_LABEL)]);
  const out: [string, string][] = [];
  for (const key of keys) {
    if (!(key in TRAIT_LABEL)) continue;
    const val = String(fromTraits[key] ?? content[key] ?? "").trim();
    if (val && val !== "未指定") out.push([key, val]);
  }
  return out;
}

export function fieldFromItem(item: ImageTextAssetItem, key: string): string {
  const top = (item as unknown as Record<string, unknown>)[key];
  if (typeof top === "string" && top.trim()) return top.trim();
  const c = item.content?.[key];
  return typeof c === "string" ? c.trim() : "";
}

export function assetImages(item: ImageTextAssetItem) {
  const fromMedia = (item.images ?? item.media ?? []).filter(
    (m) => m.url && !isPlaceholderUrl(m.url),
  );
  const fromVariants = (item.variants ?? [])
    .filter((v) => v.preview_url && !isPlaceholderUrl(v.preview_url))
    .map((v) => ({ url: v.preview_url!, name: v.label ?? "" }));
  const seen = new Set<string>();
  const merged: { url: string; name?: string; id?: string; type?: string }[] = [];
  for (const img of [...fromMedia, ...fromVariants]) {
    const key = img.url!;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(img as { url: string; name?: string; id?: string; type?: string });
  }
  return merged;
}
