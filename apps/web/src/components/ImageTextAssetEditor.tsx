/**
 * 图文资产编辑表单（看板 PATCH）
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
import type { ImageTextAssetItem } from "./ImageTextAssetCard";

const API = "/api";

const TRAIT_FIELDS: Record<string, string[]> = {
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
};

const FIELD_LABEL: Record<string, string> = {
  summary: "摘要",
  description: "主视觉描述",
  prompt_hint: "生图增强",
  visual_style: "画风",
  color_palette: "主色调",
  notes: "创作备注",
  image_prompt: "生图 Prompt",
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

interface ImageTextAssetEditorProps {
  projectId: string;
  item: ImageTextAssetItem;
  onClose: () => void;
  onSaved: () => void;
  disabled?: boolean;
}

export function ImageTextAssetEditor({
  projectId,
  item,
  onClose,
  onSaved,
  disabled = false,
}: ImageTextAssetEditorProps) {
  const { t } = useAppTranslation("common");
  const traitKeys = TRAIT_FIELDS[item.type] ?? [];
  const initialContent = useMemo(
    () => ({ ...(item.content ?? {}), ...flattenTraits(item) }),
    [item]
  );

  const [name, setName] = useState(item.name);
  const [content, setContent] = useState<Record<string, string>>(() =>
    stringFields(initialContent)
  );
  const [promptLocked, setPromptLocked] = useState(
    Boolean(item.content?.prompt_locked)
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setName(item.name);
    setContent(stringFields({ ...(item.content ?? {}), ...flattenTraits(item) }));
    setPromptLocked(Boolean(item.content?.prompt_locked));
  }, [item]);

  const setField = useCallback((key: string, value: string) => {
    setContent((prev) => ({ ...prev, [key]: value }));
  }, []);

  const save = async (opts?: { forceRecompose?: boolean }) => {
    setSaving(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        name,
        content: {
          ...content,
          prompt_locked: promptLocked,
        },
        prompt_locked: promptLocked,
        force_recompose_prompt: Boolean(opts?.forceRecompose),
      };
      const r = await fetch(`${API}/projects/${projectId}/assets/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        throw new Error(String(data.detail ?? `保存失败 (${r.status})`));
      }
      onSaved();
      onClose();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="asset-editor-overlay" role="dialog" aria-modal="true">
      <div className="asset-editor-panel">
        <header className="asset-editor-header">
          <h3>编辑{item.type === "character" ? "角色" : item.type === "scene" ? "空镜" : "物品"}</h3>
          <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
            {t("actions.close")}
          </button>
        </header>

        {error && <p className="board-error">{error}</p>}
        {disabled && (
          <p className="muted manual-edit-banner-inline">AI 执行中，暂不可保存。</p>
        )}

        <div className="asset-editor-body">
          <label className="asset-editor-field">
            <span>名称</span>
            <input value={name} disabled={disabled} onChange={(e) => setName(e.target.value)} />
          </label>

          <fieldset className="asset-editor-section">
            <legend>基础描述</legend>
            {(["summary", "description", "notes"] as const).map((key) => (
              <label key={key} className="asset-editor-field">
                <span>{FIELD_LABEL[key]}</span>
                <textarea
                  rows={key === "description" ? 4 : 2}
                  disabled={disabled}
                  value={content[key] ?? ""}
                  onChange={(e) => setField(key, e.target.value)}
                />
              </label>
            ))}
          </fieldset>

          <fieldset className="asset-editor-section">
            <legend>类型属性</legend>
            {traitKeys.map((key) => (
              <label key={key} className="asset-editor-field">
                <span>{FIELD_LABEL[key] ?? key}</span>
                <input
                  disabled={disabled}
                  value={content[key] ?? ""}
                  onChange={(e) => setField(key, e.target.value)}
                />
              </label>
            ))}
          </fieldset>

          <fieldset className="asset-editor-section">
            <legend>视觉风格</legend>
            {(["visual_style", "color_palette", "prompt_hint"] as const).map((key) => (
              <label key={key} className="asset-editor-field">
                <span>{FIELD_LABEL[key]}</span>
                <input
                  disabled={disabled}
                  value={content[key] ?? ""}
                  onChange={(e) => setField(key, e.target.value)}
                />
              </label>
            ))}
          </fieldset>

          <fieldset className="asset-editor-section">
            <legend>生图 Prompt</legend>
            <label className="asset-editor-field checkbox-row">
              <input
                type="checkbox"
                disabled={disabled}
                checked={promptLocked}
                onChange={(e) => setPromptLocked(e.target.checked)}
              />
              <span>锁定 Prompt（保存时不自动重算）</span>
            </label>
            <label className="asset-editor-field">
              <span>{FIELD_LABEL.image_prompt}</span>
              <textarea
                rows={4}
                disabled={disabled}
                value={content.image_prompt ?? ""}
                onChange={(e) => {
                  setPromptLocked(true);
                  setField("image_prompt", e.target.value);
                }}
              />
            </label>
            <label className="asset-editor-field">
              <span>{FIELD_LABEL.negative_prompt}</span>
              <textarea
                rows={2}
                disabled={disabled}
                value={content.negative_prompt ?? ""}
                onChange={(e) => setField("negative_prompt", e.target.value)}
              />
            </label>
          </fieldset>
        </div>

        <footer className="asset-editor-footer">
          <button
            type="button"
            className="btn-secondary"
            disabled={saving || disabled}
            onClick={() => save({ forceRecompose: true })}
          >
            {t("actions.regeneratePrompt")}
          </button>
          <button type="button" className="btn-primary" disabled={saving || disabled} onClick={() => save()}>
            {saving ? t("actions.saving") : t("actions.save")}
          </button>
        </footer>
      </div>
    </div>
  );
}

function flattenTraits(item: ImageTextAssetItem): Record<string, string> {
  const out: Record<string, string> = {};
  if (item.traits) {
    for (const [k, v] of Object.entries(item.traits)) {
      out[k] = v;
    }
  }
  return out;
}

function stringFields(raw: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(raw)) {
    if (typeof v === "string") out[k] = v;
    else if (typeof v === "number") out[k] = String(v);
  }
  return out;
}
