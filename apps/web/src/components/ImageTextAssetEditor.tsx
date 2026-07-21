/**
 * 图文资产编辑表单（看板 PATCH）
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
import { AssetDetailHeader } from "./assetDetail/AssetDetailHeader";
import { AssetDetailSection } from "./assetDetail/AssetDetailSection";
import { AssetDetailShell } from "./assetDetail/AssetDetailShell";
import { AssetRefPicker } from "./board/AssetRefPicker";
import {
  ADDABLE_VARIANT_KINDS,
  CLIP_NOTES_HINT,
  elementRefsFromItem,
  ensurePrimaryVariant,
  FIELD_LABEL,
  isSimplifiedClipAssetType,
  MAX_IMAGE_VARIANTS,
  newVariantId,
  promptFieldKeyForClipType,
  TRAIT_FIELDS,
  variantsFromItem,
  variantRefsFromItem,
  type VariantEditView,
} from "./imageTextAssetShared";
import type { ImageTextAssetItem } from "./ImageTextAssetCard";

const API = "/api";

interface ImageTextAssetEditorProps {
  projectId: string;
  scriptId?: string | null;
  item: ImageTextAssetItem;
  onClose: () => void;
  onSaved: () => void;
  disabled?: boolean;
}

const VARIANT_KIND_LABEL: Record<string, string> = {
  base: "主形象",
  expression: "表情",
  pose: "姿态",
  action: "动作",
  costume: "服装",
  other: "变体",
};

/** 构建 PATCH 用 image_variants 载荷（仅文案字段，image_prompt 由后端重算）。 */
function buildImageVariantsPayload(variants: VariantEditView[]): Record<string, unknown>[] {
  return variants.map((v) => ({
    id: v.id,
    kind: v.isPrimary ? "base" : v.kind,
    label:
      v.label.trim() ||
      (v.isPrimary ? "主形象" : VARIANT_KIND_LABEL[v.kind] ?? "变体"),
    meaning: v.meaning,
    variant_prompt: v.variantPrompt.trim(),
  }));
}

const TYPE_TITLE: Record<string, string> = {
  character: "角色",
  scene: "空镜",
  prop: "物品",
  frame: "画面",
  video_clip: "视频片段",
};

/** 图文文字资产编辑弹窗（含画面 element_refs 关联）。 */
export function ImageTextAssetEditor({
  projectId,
  scriptId,
  item,
  onClose,
  onSaved,
  disabled = false,
}: ImageTextAssetEditorProps) {
  const { t } = useAppTranslation("common");
  const isSimplifiedClip = isSimplifiedClipAssetType(item.type);
  const promptFieldKey = promptFieldKeyForClipType(item.type);
  const traitKeys = isSimplifiedClip ? [] : (TRAIT_FIELDS[item.type] ?? []);
  const isVideoClip = item.type === "video_clip";
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
  const [elementRefs, setElementRefs] = useState<Record<string, string[]>>(() =>
    elementRefsFromItem(item),
  );
  const [variantRefs, setVariantRefs] = useState<Record<string, string>>(() =>
    variantRefsFromItem(item),
  );
  const [variants, setVariants] = useState<VariantEditView[]>(() =>
    item.type === "character" || item.type === "prop"
      ? ensurePrimaryVariant(variantsFromItem(item))
      : variantsFromItem(item),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ttsVoices, setTtsVoices] = useState<string[]>([]);

  useEffect(() => {
    if (item.type !== "character") return;
    let cancelled = false;
    (async () => {
      try {
        const cfgRes = await fetch(`${API}/ai/config`);
        const cfg = cfgRes.ok ? await cfgRes.json() : null;
        const provider = String(cfg?.tts?.provider ?? "edge");
        const locale = String(cfg?.tts?.default_language ?? "zh-CN");
        const params = new URLSearchParams({ provider, locale });
        const voiceRes = await fetch(`${API}/ai/tts/voices?${params}`);
        if (!voiceRes.ok || cancelled) return;
        const data = await voiceRes.json();
        setTtsVoices((data.voices as string[]) ?? []);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [item.type]);

  useEffect(() => {
    setName(item.name);
    setContent(stringFields({ ...(item.content ?? {}), ...flattenTraits(item) }));
    setPromptLocked(Boolean(item.content?.prompt_locked));
    setElementRefs(elementRefsFromItem(item));
    setVariantRefs(variantRefsFromItem(item));
    setVariants(
      item.type === "character" || item.type === "prop"
        ? ensurePrimaryVariant(variantsFromItem(item))
        : variantsFromItem(item),
    );
  }, [item]);

  const updateVariant = useCallback((id: string, patch: Partial<VariantEditView>) => {
    setVariants((prev) => prev.map((v) => (v.id === id ? { ...v, ...patch } : v)));
  }, []);

  /** 新增子形象（禁止超过上限）。 */
  const addVariant = useCallback((kind: string = "expression") => {
    setVariants((prev) => {
      if (prev.length >= MAX_IMAGE_VARIANTS) return prev;
      const kindKey = ADDABLE_VARIANT_KINDS.includes(
        kind as (typeof ADDABLE_VARIANT_KINDS)[number],
      )
        ? kind
        : "expression";
      const label = VARIANT_KIND_LABEL[kindKey] ?? "变体";
      return [
        ...prev,
        {
          id: newVariantId(),
          kind: kindKey,
          label,
          meaning: "",
          variantPrompt: "",
          imagePrompt: "",
          isPrimary: false,
        },
      ];
    });
  }, []);

  /** 删除子形象（主形象不可删）。 */
  const removeVariant = useCallback((id: string) => {
    setVariants((prev) => {
      const target = prev.find((v) => v.id === id);
      if (!target || target.isPrimary || target.kind === "base") return prev;
      return prev.filter((v) => v.id !== id);
    });
  }, []);

  const setField = useCallback((key: string, value: string) => {
    setContent((prev) => ({ ...prev, [key]: value }));
  }, []);

  const save = async (opts?: { forceRecompose?: boolean }) => {
    setSaving(true);
    setError(null);
    try {
      const bodyContent: Record<string, unknown> = {
        ...content,
        prompt_locked: promptLocked,
      };
      if (
        item.type === "frame" ||
        item.type === "video_clip" ||
        item.type === "character" ||
        item.type === "scene" ||
        item.type === "prop"
      ) {
        bodyContent.element_refs = elementRefs;
        bodyContent.variant_refs = variantRefs;
      }
      if (variants.length > 0 && item.type !== "scene" && item.type !== "frame" && !isVideoClip) {
        bodyContent.image_variants = buildImageVariantsPayload(variants);
      }
      const body: Record<string, unknown> = {
        name,
        content: bodyContent,
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

  const typeLabel = TYPE_TITLE[item.type] ?? item.type;

  return (
    <AssetDetailShell titleId="asset-editor-title" onClose={onClose}>
      <AssetDetailHeader
        typeLabel={typeLabel}
        title={name || item.name}
        titleId="asset-editor-title"
        actions={
          <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
            {t("actions.close")}
          </button>
        }
      />

      {error ? (
        <p className="board-error asset-editor-error" role="alert">
          {error}
        </p>
      ) : null}
      {disabled ? (
        <p className="muted manual-edit-banner-inline">AI 执行中，暂不可保存。</p>
      ) : null}

      <div className="asset-editor-form-body">
        <AssetDetailSection title="名称" className="asset-editor-section--name">
          <label className="asset-editor-field asset-editor-field--full">
            <span className="sr-only">名称</span>
            <input
              value={name}
              disabled={disabled}
              placeholder="资产名称"
              onChange={(e) => setName(e.target.value)}
            />
          </label>
        </AssetDetailSection>

        {isSimplifiedClip ? (
          <>
            <AssetDetailSection title="摘要">
              <label className="asset-editor-field">
                <span className="sr-only">{FIELD_LABEL.summary}</span>
                <textarea
                  rows={2}
                  disabled={disabled}
                  value={content.summary ?? ""}
                  onChange={(e) => setField("summary", e.target.value)}
                />
              </label>
            </AssetDetailSection>

            <AssetDetailSection title="关联资产">
              <AssetRefPicker
                projectId={projectId}
                scriptId={scriptId}
                ownerAssetId={item.id}
                kinds={
                  isVideoClip
                    ? ["frame"]
                    : ["scene", "character", "prop", "frame"]
                }
                value={elementRefs}
                onChange={setElementRefs}
                variantRefs={variantRefs}
                onVariantRefsChange={setVariantRefs}
                className="asset-ref-picker--editor"
              />
            </AssetDetailSection>

            {promptFieldKey ? (
              <AssetDetailSection title="提示词" className="asset-editor-section--prompt">
                <div className="asset-prompt-toolbar">
                  <label className={`asset-prompt-lock${promptLocked ? " is-locked" : ""}`}>
                    <input
                      type="checkbox"
                      disabled={disabled}
                      checked={promptLocked}
                      onChange={(e) => setPromptLocked(e.target.checked)}
                    />
                    <span className="asset-prompt-lock__label">锁定 Prompt</span>
                    <span className="asset-prompt-lock__hint">保存时不自动重算</span>
                  </label>
                </div>
                <label className="asset-editor-field asset-editor-field--prompt">
                  <span className="sr-only">{FIELD_LABEL[promptFieldKey]}</span>
                  <textarea
                    rows={5}
                    className="asset-prompt-textarea"
                    disabled={disabled}
                    value={content[promptFieldKey] ?? ""}
                    placeholder={
                      isVideoClip
                        ? "描述镜头运动、主体动作与环境变化…"
                        : "描述画面主体、环境、光线与构图…"
                    }
                    onChange={(e) => {
                      setPromptLocked(true);
                      setField(promptFieldKey, e.target.value);
                    }}
                  />
                </label>
              </AssetDetailSection>
            ) : null}

            <AssetDetailSection title="备注">
              <p className="muted asset-editor-hint">{CLIP_NOTES_HINT}</p>
              <label className="asset-editor-field">
                <span className="sr-only">备注</span>
                <textarea
                  rows={2}
                  disabled={disabled}
                  value={content.notes ?? ""}
                  placeholder="导演意图、节奏、不宜写进提示词的上下文…"
                  onChange={(e) => setField("notes", e.target.value)}
                />
              </label>
            </AssetDetailSection>
          </>
        ) : (
          <>
            <AssetDetailSection title="基础描述">
              {(["summary", "description", "notes"] as const).map((key) => (
                <label key={key} className="asset-editor-field">
                  <span className="asset-field-eyebrow">{FIELD_LABEL[key]}</span>
                  <textarea
                    rows={key === "description" ? 4 : 2}
                    disabled={disabled}
                    value={content[key] ?? ""}
                    onChange={(e) => setField(key, e.target.value)}
                  />
                </label>
              ))}
            </AssetDetailSection>

            {traitKeys.length > 0 ? (
              <AssetDetailSection title="类型属性">
                <div className="asset-editor-trait-grid">
                  {traitKeys.map((key) => (
                    <label key={key} className="asset-editor-field">
                      <span className="asset-field-eyebrow">{FIELD_LABEL[key] ?? key}</span>
                      {key === "tts_voice" && ttsVoices.length > 0 ? (
                        <select
                          disabled={disabled}
                          value={content[key] ?? ""}
                          onChange={(e) => setField(key, e.target.value)}
                        >
                          <option value="">（请选择音色）</option>
                          {ttsVoices.map((v) => (
                            <option key={v} value={v}>
                              {v}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          disabled={disabled}
                          value={content[key] ?? ""}
                          onChange={(e) => setField(key, e.target.value)}
                        />
                      )}
                    </label>
                  ))}
                </div>
              </AssetDetailSection>
            ) : null}

            <AssetDetailSection title="视觉风格">
              <div className="asset-editor-trait-grid">
                {(["visual_style", "color_palette", "prompt_hint"] as const).map((key) => (
                  <label key={key} className="asset-editor-field">
                    <span className="asset-field-eyebrow">{FIELD_LABEL[key]}</span>
                    <input
                      disabled={disabled}
                      value={content[key] ?? ""}
                      onChange={(e) => setField(key, e.target.value)}
                    />
                  </label>
                ))}
              </div>
            </AssetDetailSection>

            {(item.type === "character" || item.type === "prop") ? (
              <AssetDetailSection title="形象变体" className="asset-editor-section--variants">
                <p className="muted asset-editor-hint">
                  主形象不可删除；可添加表情/姿态等子形象。保存后子形象可单独重新生图。
                </p>
                <ul className="variant-editor-list">
                  {variants.map((v) => (
                    <li key={v.id} className="variant-editor-item">
                      <div className="variant-editor-item__head">
                        <span className="meta-chip">
                          {v.isPrimary ? "主形象" : VARIANT_KIND_LABEL[v.kind] ?? v.kind}
                        </span>
                        {v.isPrimary ? (
                          <strong>{v.label || "主形象"}</strong>
                        ) : (
                          <>
                            <label className="variant-editor-item__kind">
                              <span className="sr-only">类型</span>
                              <select
                                disabled={disabled}
                                value={
                                  ADDABLE_VARIANT_KINDS.includes(
                                    v.kind as (typeof ADDABLE_VARIANT_KINDS)[number],
                                  )
                                    ? v.kind
                                    : "other"
                                }
                                onChange={(e) =>
                                  updateVariant(v.id, {
                                    kind: e.target.value,
                                    label:
                                      v.label === VARIANT_KIND_LABEL[v.kind]
                                        ? VARIANT_KIND_LABEL[e.target.value] ?? v.label
                                        : v.label,
                                  })
                                }
                              >
                                {ADDABLE_VARIANT_KINDS.map((k) => (
                                  <option key={k} value={k}>
                                    {VARIANT_KIND_LABEL[k] ?? k}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label className="variant-editor-item__label-field">
                              <span className="sr-only">名称</span>
                              <input
                                disabled={disabled}
                                value={v.label}
                                placeholder="变体名称"
                                onChange={(e) => updateVariant(v.id, { label: e.target.value })}
                              />
                            </label>
                            <button
                              type="button"
                              className="btn-secondary btn-sm variant-editor-item__remove"
                              disabled={disabled}
                              onClick={() => removeVariant(v.id)}
                            >
                              删除
                            </button>
                          </>
                        )}
                      </div>
                      {!v.isPrimary ? (
                        <label className="asset-editor-field">
                          <span className="asset-field-eyebrow">含义</span>
                          <input
                            disabled={disabled}
                            value={v.meaning}
                            placeholder="简述该变体使用场景…"
                            onChange={(e) => updateVariant(v.id, { meaning: e.target.value })}
                          />
                        </label>
                      ) : null}
                      <label className="asset-editor-field">
                        <span className="asset-field-eyebrow">变体提示词</span>
                        <textarea
                          rows={3}
                          className="asset-prompt-textarea"
                          disabled={disabled}
                          value={v.variantPrompt}
                          placeholder="描述该变体的画面差异，如表情、姿态、动作…"
                          onChange={(e) => updateVariant(v.id, { variantPrompt: e.target.value })}
                        />
                      </label>
                      {v.imagePrompt && v.imagePrompt !== v.variantPrompt ? (
                        <p className="muted variant-editor-item__assembled">
                          已组装 Prompt：{v.imagePrompt.slice(0, 120)}
                          {v.imagePrompt.length > 120 ? "…" : ""}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
                <div className="variant-editor-actions">
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    disabled={disabled || variants.length >= MAX_IMAGE_VARIANTS}
                    onClick={() => addVariant("expression")}
                  >
                    添加子形象
                  </button>
                  {variants.length >= MAX_IMAGE_VARIANTS ? (
                    <span className="muted">最多 {MAX_IMAGE_VARIANTS} 个变体</span>
                  ) : null}
                </div>
              </AssetDetailSection>
            ) : null}

            {(["character", "scene", "prop"] as const).includes(
              item.type as "character" | "scene" | "prop",
            ) ? (
              <AssetDetailSection title="关联资产">
                <AssetRefPicker
                  projectId={projectId}
                  scriptId={scriptId}
                  ownerAssetId={item.id}
                  kinds={[item.type as "character" | "scene" | "prop"]}
                  value={elementRefs}
                  onChange={setElementRefs}
                  variantRefs={variantRefs}
                  onVariantRefsChange={setVariantRefs}
                  className="asset-ref-picker--editor"
                />
              </AssetDetailSection>
            ) : null}

            <AssetDetailSection title="生图提示词" className="asset-editor-section--prompt">
              <div className="asset-prompt-toolbar">
                <label className={`asset-prompt-lock${promptLocked ? " is-locked" : ""}`}>
                  <input
                    type="checkbox"
                    disabled={disabled}
                    checked={promptLocked}
                    onChange={(e) => setPromptLocked(e.target.checked)}
                  />
                  <span className="asset-prompt-lock__label">锁定 Prompt</span>
                  <span className="asset-prompt-lock__hint">保存时不自动重算</span>
                </label>
              </div>
              <label className="asset-editor-field asset-editor-field--prompt">
                <span className="asset-field-eyebrow">正向</span>
                <textarea
                  rows={5}
                  className="asset-prompt-textarea"
                  disabled={disabled}
                  value={content.image_prompt ?? ""}
                  placeholder="描述画面主体、环境、光线与构图…"
                  onChange={(e) => {
                    setPromptLocked(true);
                    setField("image_prompt", e.target.value);
                  }}
                />
              </label>
              <label className="asset-editor-field asset-editor-field--prompt">
                <span className="asset-field-eyebrow">负向</span>
                <textarea
                  rows={3}
                  className="asset-prompt-textarea asset-prompt-textarea--negative"
                  disabled={disabled}
                  value={content.negative_prompt ?? ""}
                  placeholder="low quality, blurry, watermark, text overlay…"
                  onChange={(e) => setField("negative_prompt", e.target.value)}
                />
              </label>
            </AssetDetailSection>
          </>
        )}
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
    </AssetDetailShell>
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
