/** 手动创建文字资产（剧情/角色/场景/物品/画面），支持全字段填写或摘要 AI 生成。 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { createTextAsset, generateTextAssetDraft } from "../../lib/manualAssets";
import { AssetRefPicker } from "../board/AssetRefPicker";
import {
  BASE_CONTENT_FIELDS,
  CLIP_NOTES_HINT,
  FIELD_LABEL,
  isSimplifiedClipAssetType,
  promptFieldKeyForClipType,
  TRAIT_FIELDS,
  TYPE_LABEL,
} from "../imageTextAssetShared";

const API = "/api";

const IMAGE_TEXT_TYPES = new Set(["character", "scene", "prop", "frame", "video_clip"]);

interface CreateTextAssetDialogProps {
  projectId: string;
  scriptId: string;
  assetType: string;
  onClose: () => void;
  onCreated: (asset?: {
    id?: string;
    name?: string;
    primary_media_id?: string;
    preview?: string;
  }) => void;
}

/** 收集当前表单中已填写的 content 字段，作为 AI 生成 hints。 */
function collectHints(
  content: Record<string, string>,
  elementRefs: Record<string, string[]>,
  variantRefs: Record<string, string>,
): Record<string, unknown> {
  const hints: Record<string, unknown> = {};
  for (const [key, val] of Object.entries(content)) {
    if (val.trim()) hints[key] = val.trim();
  }
  const hasRefs = Object.values(elementRefs).some((ids) => ids.length > 0);
  if (hasRefs) hints.element_refs = elementRefs;
  if (Object.keys(variantRefs).length > 0) hints.variant_refs = variantRefs;
  return hints;
}

/** 将 AI 或用户输入的 content 合并进表单 state。 */
function mergeContentFields(
  prev: Record<string, string>,
  incoming: Record<string, unknown>,
): Record<string, string> {
  const next = { ...prev };
  for (const [key, val] of Object.entries(incoming)) {
    if (key === "element_refs" || key === "image_variants" || key === "variant_refs") continue;
    if (typeof val === "string") next[key] = val;
  }
  return next;
}

/** 新建图文/剧情资产弹窗。 */
export function CreateTextAssetDialog({
  projectId,
  scriptId,
  assetType,
  onClose,
  onCreated,
}: CreateTextAssetDialogProps) {
  const { t } = useAppTranslation("common");
  const isPlot = assetType === "plot";
  const isImageText = IMAGE_TEXT_TYPES.has(assetType);
  const isSimplifiedClip = isSimplifiedClipAssetType(assetType);
  const promptFieldKey = promptFieldKeyForClipType(assetType);

  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [content, setContent] = useState<Record<string, string>>({});
  const [elementRefs, setElementRefs] = useState<Record<string, string[]>>({});
  const [variantRefs, setVariantRefs] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ttsVoices, setTtsVoices] = useState<string[]>([]);

  const traitKeys = isSimplifiedClip ? [] : (TRAIT_FIELDS[assetType] ?? []);

  const summaryForAi = useMemo(() => {
    const s = (content.summary ?? "").trim();
    if (s) return s;
    return name.trim();
  }, [content.summary, name]);

  useEffect(() => {
    if (assetType !== "character") return;
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
  }, [assetType]);

  const setField = useCallback((key: string, value: string) => {
    setContent((prev) => ({ ...prev, [key]: value }));
  }, []);

  const runAiGenerate = async () => {
    if (!summaryForAi) {
      setError("请先填写摘要或名称，再使用 AI 生成");
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      const hints = collectHints(content, elementRefs, variantRefs);
      const draft = await generateTextAssetDraft(projectId, scriptId, {
        asset_type: assetType,
        summary: summaryForAi,
        name: name.trim(),
        hints: Object.keys(hints).length > 0 ? hints : undefined,
      });
      if (draft.name?.trim()) setName(draft.name.trim());
      if (draft.content && typeof draft.content === "object") {
        setContent((prev) => mergeContentFields(prev, draft.content));
        const refs = draft.content.element_refs;
        if (refs && typeof refs === "object" && !Array.isArray(refs)) {
          const parsed: Record<string, string[]> = {};
          for (const [key, val] of Object.entries(refs as Record<string, unknown>)) {
            if (Array.isArray(val)) parsed[key] = val.map(String).filter(Boolean);
          }
          if (Object.keys(parsed).length > 0) setElementRefs(parsed);
        }
        const vrefs = draft.content.variant_refs;
        if (vrefs && typeof vrefs === "object" && !Array.isArray(vrefs)) {
          const parsed: Record<string, string> = {};
          for (const [aid, vid] of Object.entries(vrefs as Record<string, unknown>)) {
            const a = String(aid ?? "").trim();
            const v = String(vid ?? "").trim();
            if (a && v) parsed[a] = v;
          }
          if (Object.keys(parsed).length > 0) setVariantRefs(parsed);
        }
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setGenerating(false);
    }
  };

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      const bodyContent = isPlot
        ? { text: text.trim() || name.trim() }
        : isSimplifiedClip
          ? {
              summary: (content.summary ?? "").trim(),
              notes: (content.notes ?? "").trim(),
              ...(promptFieldKey
                ? { [promptFieldKey]: (content[promptFieldKey] ?? "").trim() }
                : {}),
              element_refs: elementRefs,
              variant_refs: variantRefs,
            }
          : { ...content };
      const created = (await createTextAsset(projectId, scriptId, {
        type: assetType,
        name: name.trim(),
        content: bodyContent,
      })) as {
        id?: string;
        name?: string;
        primary_media_id?: string;
        preview?: string;
      };
      onCreated(created);
      onClose();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const typeLabel = TYPE_LABEL[assetType] ?? assetType;

  // 挂到 body，避免嵌在分镜抽屉 .asset-detail-panel 内时底栏样式泄漏
  return createPortal(
    <div className="asset-editor-overlay" role="dialog" aria-modal="true">
      <div className="asset-editor-panel asset-editor-panel--wide">
        <header className="asset-editor-header">
          <h3>新建{typeLabel}</h3>
          <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
            {t("actions.close")}
          </button>
        </header>
        {error && <p className="board-error">{error}</p>}
        <div className="asset-editor-body asset-editor-form-body">
          <label className="asset-editor-field">
            <span>名称</span>
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>

          {isPlot ? (
            <label className="asset-editor-field">
              <span>剧情正文</span>
              <textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} />
            </label>
          ) : isSimplifiedClip ? (
            <>
              <div className="create-asset-ai-row">
                <p className="muted create-asset-ai-hint">
                  可填写摘要与提示词，或只填摘要后「AI 一键生成」补全。
                </p>
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  disabled={generating || !summaryForAi}
                  onClick={() => void runAiGenerate()}
                >
                  {generating ? "AI 生成中…" : "AI 一键生成"}
                </button>
              </div>
              <label className="asset-editor-field">
                <span>{FIELD_LABEL.summary}</span>
                <textarea
                  rows={2}
                  value={content.summary ?? ""}
                  onChange={(e) => setField("summary", e.target.value)}
                />
              </label>
              <div className="asset-editor-section-block">
                <h4 className="asset-editor-section-title">关联资产</h4>
                <AssetRefPicker
                  projectId={projectId}
                  scriptId={scriptId}
                  kinds={["scene", "character", "prop", "frame"]}
                  value={elementRefs}
                  onChange={setElementRefs}
                  variantRefs={variantRefs}
                  onVariantRefsChange={setVariantRefs}
                  className="asset-ref-picker--editor"
                />
              </div>
              {promptFieldKey ? (
                <label className="asset-editor-field">
                  <span>{FIELD_LABEL[promptFieldKey]}</span>
                  <textarea
                    rows={5}
                    value={content[promptFieldKey] ?? ""}
                    onChange={(e) => setField(promptFieldKey, e.target.value)}
                    placeholder={
                      assetType === "video_clip"
                        ? "描述镜头运动、主体动作与环境变化…"
                        : "描述画面主体、环境、光线与构图…"
                    }
                  />
                </label>
              ) : null}
              <label className="asset-editor-field">
                <span>备注</span>
                <span className="muted create-asset-ai-hint">{CLIP_NOTES_HINT}</span>
                <textarea
                  rows={2}
                  value={content.notes ?? ""}
                  onChange={(e) => setField("notes", e.target.value)}
                  placeholder="导演意图、节奏、不宜写进提示词的上下文…"
                />
              </label>
            </>
          ) : isImageText ? (
            <>
              <div className="create-asset-ai-row">
                <p className="muted create-asset-ai-hint">
                  可填写全部字段，或只填摘要后点击「AI 一键生成」补全（使用已配置的 LLM 模型）。
                </p>
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  disabled={generating || !summaryForAi}
                  onClick={() => void runAiGenerate()}
                >
                  {generating ? "AI 生成中…" : "AI 一键生成"}
                </button>
              </div>

              {BASE_CONTENT_FIELDS.map((key) => (
                <label key={key} className="asset-editor-field">
                  <span>{FIELD_LABEL[key] ?? key}</span>
                  <textarea
                    rows={key === "description" ? 4 : key === "summary" ? 2 : 2}
                    value={content[key] ?? ""}
                    onChange={(e) => setField(key, e.target.value)}
                  />
                </label>
              ))}

              {traitKeys.length > 0 ? (
                <div className="asset-editor-trait-grid">
                  {traitKeys.map((key) => (
                    <label key={key} className="asset-editor-field">
                      <span>{FIELD_LABEL[key] ?? key}</span>
                      {key === "tts_voice" && ttsVoices.length > 0 ? (
                        <select
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
                          value={content[key] ?? ""}
                          onChange={(e) => setField(key, e.target.value)}
                        />
                      )}
                    </label>
                  ))}
                </div>
              ) : null}
            </>
          ) : null}
        </div>
        <footer className="asset-editor-footer">
          <button
            type="button"
            className="btn-primary"
            disabled={saving || !name.trim()}
            onClick={() => void submit()}
          >
            {saving ? t("actions.creating") : t("actions.create")}
          </button>
        </footer>
      </div>
    </div>,
    document.body,
  );
}
