/**
 * 实际生成提示词预览：标题旁小眼睛 + 按需拉取完整 prompt 弹层。
 */

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Eye } from "lucide-react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { AssetDetailShell } from "./AssetDetailShell";

const API = "/api";

/** GET .../resolved-prompt 响应。 */
export interface ResolvedPromptPayload {
  asset_id: string;
  asset_type: string;
  kind: string;
  authored_prompt: string;
  resolved_prompt: string;
  negative_prompt: string;
  differs_from_authored: boolean;
}

interface ResolvedPromptPreviewProps {
  /** 项目 ID；缺失时不渲染。 */
  projectId?: string | null;
  /** 文字资产 ID。 */
  assetId: string;
  /** 有存档提示词或关联 refs 时为 true。 */
  enabled: boolean;
}

/** 提示词区块旁的眼睛按钮；点击后展示实际生成用完整提示词。 */
export function ResolvedPromptPreview({
  projectId,
  assetId,
  enabled,
}: ResolvedPromptPreviewProps) {
  const { t } = useAppTranslation("common");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ResolvedPromptPayload | null>(null);
  const [copied, setCopied] = useState(false);

  /** 关闭弹层并清除复制态。 */
  const handleClose = useCallback(() => {
    setOpen(false);
    setCopied(false);
  }, []);

  /** 拉取实际生成提示词。 */
  const load = useCallback(async () => {
    if (!projectId || !assetId) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(
        `${API}/projects/${projectId}/assets/${encodeURIComponent(assetId)}/resolved-prompt`,
      );
      if (!r.ok) {
        const detail = await r.text();
        throw new Error(detail || `HTTP ${r.status}`);
      }
      const body = (await r.json()) as ResolvedPromptPayload;
      setData(body);
    } catch (e) {
      setData(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId, assetId]);

  useEffect(() => {
    if (!open) return;
    void load();
  }, [open, load]);

  /** 资产切换时丢弃缓存。 */
  useEffect(() => {
    setData(null);
    setError(null);
    setOpen(false);
  }, [assetId, projectId]);

  /** 复制 resolved_prompt 到剪贴板。 */
  const handleCopy = useCallback(async () => {
    const text = data?.resolved_prompt?.trim();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }, [data]);

  if (!enabled || !projectId) return null;

  return (
    <>
      <button
        type="button"
        className="resolved-prompt-eye-btn"
        aria-label={t("resolvedPrompt.viewAria")}
        title={t("resolvedPrompt.viewAria")}
        onClick={() => setOpen(true)}
      >
        <Eye size={14} strokeWidth={1.75} aria-hidden />
      </button>

      {open
        ? createPortal(
            <AssetDetailShell
              titleId="resolved-prompt-title"
              panelClassName="asset-detail-panel resolved-prompt-panel"
              onClose={handleClose}
            >
              <div className="resolved-prompt-panel__header">
                <h3 id="resolved-prompt-title" className="resolved-prompt-panel__title">
                  {t("resolvedPrompt.title")}
                </h3>
                <div className="resolved-prompt-panel__actions">
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    disabled={!data?.resolved_prompt || loading}
                    onClick={() => void handleCopy()}
                  >
                    {copied ? t("resolvedPrompt.copied") : t("actions.copy")}
                  </button>
                  <button type="button" className="btn-secondary btn-sm" onClick={handleClose}>
                    {t("actions.close")}
                  </button>
                </div>
              </div>

              <div className="resolved-prompt-panel__body">
                {loading ? <p className="muted">{t("actions.loading")}</p> : null}
                {error ? (
                  <div className="resolved-prompt-panel__error" role="alert">
                    <p>{t("resolvedPrompt.loadFailed")}</p>
                    <p className="muted">{error}</p>
                    <button
                      type="button"
                      className="btn-secondary btn-sm"
                      onClick={() => void load()}
                    >
                      {t("actions.retry")}
                    </button>
                  </div>
                ) : null}
                {!loading && !error && data ? (
                  <>
                    <p className="muted resolved-prompt-panel__hint">
                      {data.differs_from_authored
                        ? t("resolvedPrompt.hintDiffers")
                        : t("resolvedPrompt.hintSame")}
                    </p>
                    <pre className="prompt-pre resolved-prompt-panel__pre">
                      {data.resolved_prompt || t("resolvedPrompt.empty")}
                    </pre>
                    {data.negative_prompt ? (
                      <p className="muted resolved-prompt-panel__negative">
                        <strong>{t("resolvedPrompt.negativeLabel")}</strong>
                        {data.negative_prompt}
                      </p>
                    ) : null}
                  </>
                ) : null}
              </div>
            </AssetDetailShell>,
            document.body,
          )
        : null}
    </>
  );
}
