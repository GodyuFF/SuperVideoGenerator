/**
 * 图文资产展示/编辑共用字段工具。
 */

import type { ImageTextAssetItem } from "./ImageTextAssetCard";
import { looksLikeMediaUrl } from "../utils/boardMediaPreview";

export const TYPE_LABEL: Record<string, string> = {
  character: "角色",
  prop: "物品",
  scene: "空镜",
  frame: "画面",
  video_clip: "视频片段",
  plot: "剧情",
};

/** 各图文资产类型的扩展属性字段。 */
export const TRAIT_FIELDS: Record<string, string[]> = {
  character: [
    "role",
    "personality",
    "age_range",
    "gender",
    "costume",
    "distinctive_features",
    "ethnicity",
    "body_type",
    "height",
    "build",
    "hair_style",
    "hair_color",
    "eye_color",
    "facial_features",
    "default_expression",
    "default_pose",
    "accessories",
    "tts_voice",
  ],
  scene: [
    "location",
    "time_of_day",
    "weather",
    "lighting",
    "mood",
    "spatial_layout",
    "architecture_style",
    "key_objects",
    "foreground",
    "background",
    "camera_angle",
    "depth_of_field",
    "color_tone",
  ],
  prop: [
    "category",
    "material",
    "size_scale",
    "usage",
    "condition",
    "shape",
    "color",
    "texture",
    "brand_style",
    "visual_details",
  ],
  /** 画面/视频精简表单不展示扩展 trait，后端字段仍可保留。 */
  frame: [],
  video_clip: [],
};

/** 图文资产共用基础字段（角色/空镜/物品创建/编辑表单）。 */
export const BASE_CONTENT_FIELDS = [
  "summary",
  "description",
  "visual_style",
  "color_palette",
  "prompt_hint",
  "notes",
] as const;

/** 画面 / 视频片段是否采用精简表单（名称·摘要·关联资产·提示词·备注）。 */
export function isSimplifiedClipAssetType(type: string): boolean {
  return type === "frame" || type === "video_clip";
}

/** 画面/视频备注眉标：供 AI 编排自用，不写入生图/生视频提示词。 */
export const CLIP_NOTES_HINT = "供 AI 编排自用，不进入提示词";

/** 画面/视频的主提示词 content 键。 */
export function promptFieldKeyForClipType(
  type: string,
): "image_prompt" | "video_prompt" | null {
  if (type === "frame") return "image_prompt";
  if (type === "video_clip") return "video_prompt";
  return null;
}

export const FIELD_LABEL: Record<string, string> = {
  summary: "摘要",
  description: "主视觉描述",
  visual_style: "画风",
  color_palette: "主色调",
  prompt_hint: "生图增强",
  notes: "创作备注",
  composition_prompt: "合成指令",
  video_prompt: "提示词",
  video_mode: "视频模式",
  camera_motion: "镜头运动",
  duration_sec: "时长（秒）",
  image_prompt: "提示词",
  negative_prompt: "负向 Prompt",
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
  tts_voice: "TTS 音色",
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

/** @deprecated 使用 FIELD_LABEL */
export const TRAIT_LABEL: Record<string, string> = FIELD_LABEL;

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

/** 从图文资产 content 解析 element_refs（画面合成引用）。 */
export function elementRefsFromItem(item: ImageTextAssetItem): Record<string, string[]> {
  const raw = item.content?.element_refs;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const out: Record<string, string[]> = {};
  for (const [key, val] of Object.entries(raw as Record<string, unknown>)) {
    if (Array.isArray(val)) {
      out[key] = val.map(String).filter(Boolean);
    }
  }
  return out;
}

/** 从图文资产 content 解析 variant_refs（关联资产 → 子形象 id）。 */
export function variantRefsFromItem(item: ImageTextAssetItem): Record<string, string> {
  const raw = item.content?.variant_refs;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const out: Record<string, string> = {};
  for (const [aid, vid] of Object.entries(raw as Record<string, unknown>)) {
    const a = String(aid ?? "").trim();
    const v = String(vid ?? "").trim();
    if (a && v) out[a] = v;
  }
  return out;
}

/** 按当前 variant_refs 解析展示用预览图（优先指定子形象）。 */
export function resolveLinkedAssetPreview(
  item: ImageTextAssetItem,
  variantId?: string | null,
): { url: string; variantLabel?: string } {
  const vid = String(variantId ?? "").trim();
  if (vid && item.variants?.length) {
    const hit = item.variants.find((v) => String(v.id ?? "") === vid);
    if (hit?.preview_url && !isPlaceholderUrl(hit.preview_url)) {
      return { url: hit.preview_url, variantLabel: hit.label || hit.kind || undefined };
    }
  }
  const primary = pickBoardPreviewFromItem(item);
  if (primary) return { url: primary };
  const imgs = assetImages(item);
  return { url: imgs[0]?.url ?? "" };
}

/** 从看板条目取主预览 URL（避免循环依赖时用内联逻辑）。 */
function pickBoardPreviewFromItem(item: ImageTextAssetItem): string {
  const previewUrl = String(item.preview_url ?? "").trim();
  if (previewUrl && !isPlaceholderUrl(previewUrl)) return previewUrl;
  for (const m of item.images ?? item.media ?? []) {
    if (m.url && !isPlaceholderUrl(m.url) && m.type !== "video" && m.type !== "final") {
      return m.url;
    }
  }
  return "";
}

export function assetImages(item: ImageTextAssetItem) {
  const fromMedia = (item.images ?? item.media ?? []).filter(
    (m) => m.url && !isPlaceholderUrl(m.url) && m.type !== "video" && m.type !== "final",
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

/** 归一化媒体 URL 键，用于去重（忽略查询串与首尾斜杠差异）。 */
function mediaUrlDedupeKey(raw: string): string {
  const u = raw.trim().replace(/\\/g, "/").toLowerCase();
  const noQuery = u.split("?")[0]?.split("#")[0] ?? u;
  return noQuery.replace(/\/+$/, "");
}

/** 从 video_clip 等文字资产解析可播放视频列表（同文件只保留一条）。 */
export function assetVideos(item: ImageTextAssetItem) {
  const fromMedia = (item.images ?? item.media ?? []).filter(
    (m) =>
      (m.type === "video" || m.type === "final") &&
      m.url &&
      !isPlaceholderUrl(m.url) &&
      looksLikeMediaUrl(m.url),
  );
  const seen = new Set<string>();
  const merged: { url: string; name?: string; id?: string; type?: string }[] = [];
  for (const vid of fromMedia) {
    const key = mediaUrlDedupeKey(vid.url!);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    merged.push(vid as { url: string; name?: string; id?: string; type?: string });
  }
  // preview 为摘要文案；仅当 media 为空时回退 preview_url，避免与 media[] 重复渲染
  if (merged.length === 0) {
    const previewUrl = String(item.preview_url ?? "").trim();
    if (previewUrl && looksLikeMediaUrl(previewUrl) && !isPlaceholderUrl(previewUrl)) {
      merged.push({ url: previewUrl, name: item.name, type: "video" });
    }
  }
  return merged;
}

/** 变体编辑视图（含生图提示词）。 */
export interface VariantEditView {
  id: string;
  kind: string;
  label: string;
  meaning: string;
  variantPrompt: string;
  imagePrompt: string;
  isPrimary: boolean;
}

/** 单资产最多形象变体数（与后端 MAX_IMAGE_VARIANTS_PER_ASSET 对齐）。 */
export const MAX_IMAGE_VARIANTS = 8;

/** 可新增的子形象 kind（不含 base）。 */
export const ADDABLE_VARIANT_KINDS = [
  "expression",
  "pose",
  "action",
  "costume",
  "other",
] as const;

/** 生成前端临时变体 id（保存时原样提交，后端可保留）。 */
export function newVariantId(): string {
  const raw =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "")
      : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  return `var_${raw.slice(0, 16)}`;
}

/** 保证列表含主形象；无则插入一条 base。 */
export function ensurePrimaryVariant(list: VariantEditView[]): VariantEditView[] {
  if (list.some((v) => v.isPrimary || v.kind === "base")) {
    return list.map((v) =>
      v.kind === "base" || v.isPrimary ? { ...v, isPrimary: true, kind: "base" } : v,
    );
  }
  return [
    {
      id: newVariantId(),
      kind: "base",
      label: "主形象",
      meaning: "设定主视觉",
      variantPrompt: "",
      imagePrompt: "",
      isPrimary: true,
    },
    ...list,
  ];
}

/** 从图文资产解析可编辑变体列表（优先 content.image_variants）。 */
export function variantsFromItem(item: ImageTextAssetItem): VariantEditView[] {
  const raw = item.content?.image_variants;
  if (Array.isArray(raw) && raw.length > 0) {
    return raw
      .map((row) => {
        if (!row || typeof row !== "object") return null;
        const r = row as Record<string, unknown>;
        const kind = String(r.kind ?? "other");
        const id = String(r.id ?? "");
        if (!id) return null;
        return {
          id,
          kind,
          label: String(r.label ?? ""),
          meaning: String(r.meaning ?? ""),
          variantPrompt: String(r.variant_prompt ?? ""),
          imagePrompt: String(r.image_prompt ?? ""),
          isPrimary: kind === "base",
        } satisfies VariantEditView;
      })
      .filter((v): v is VariantEditView => v !== null);
  }
  return (item.variants ?? [])
    .filter((v) => v.id)
    .map((v) => ({
      id: v.id!,
      kind: v.kind ?? (v.is_primary ? "base" : "other"),
      label: v.label ?? "",
      meaning: v.meaning ?? "",
      variantPrompt: v.variant_prompt ?? "",
      imagePrompt: v.image_prompt ?? "",
      isPrimary: Boolean(v.is_primary),
    }));
}
