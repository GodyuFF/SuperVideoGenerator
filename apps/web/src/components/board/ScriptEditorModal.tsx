/**
 * 剧本正文编辑弹窗（标题、目标时长、Markdown 正文）。
 */

import { useEffect, useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { patchScript } from "../../lib/manualAssets";
import { AssetDetailHeader } from "../assetDetail/AssetDetailHeader";
import { AssetDetailSection } from "../assetDetail/AssetDetailSection";
import { AssetDetailShell } from "../assetDetail/AssetDetailShell";

interface ScriptEditorModalProps {
  projectId: string;
  scriptId: string;
  initialTitle: string;
  initialContentMd: string;
  initialDurationSec?: number | null;
  onClose: () => void;
  onSaved: () => void;
}

/** 在 Modal 中编辑剧本元数据与 Markdown 正文。 */
export function ScriptEditorModal({
  projectId,
  scriptId,
  initialTitle,
  initialContentMd,
  initialDurationSec,
  onClose,
  onSaved,
}: ScriptEditorModalProps) {
  const { t } = useAppTranslation(["board", "common"]);
  const [title, setTitle] = useState(initialTitle);
  const [contentMd, setContentMd] = useState(initialContentMd);
  const [durationSec, setDurationSec] = useState(
    initialDurationSec != null ? String(initialDurationSec) : "",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTitle(initialTitle);
    setContentMd(initialContentMd);
    setDurationSec(initialDurationSec != null ? String(initialDurationSec) : "");
  }, [initialTitle, initialContentMd, initialDurationSec]);

  const save = async () => {
    const cleanTitle = title.trim();
    if (!cleanTitle) {
      setError(t("board:scriptEditor.titleRequired"));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const body: { title: string; content_md: string; duration_sec?: number } = {
        title: cleanTitle,
        content_md: contentMd,
      };
      const dur = parseInt(durationSec, 10);
      if (!Number.isNaN(dur) && dur > 0) body.duration_sec = dur;
      await patchScript(projectId, scriptId, body);
      onSaved();
      onClose();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const lineCount = contentMd ? contentMd.split("\n").length : 0;

  return (
    <AssetDetailShell
      titleId="script-editor-title"
      panelClassName="asset-detail-panel script-editor-panel"
      onClose={onClose}
    >
      <AssetDetailHeader
        typeLabel={t("board:scriptEditor.typeLabel")}
        title={title.trim() || initialTitle}
        titleId="script-editor-title"
        actions={
          <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
            {t("common:actions.close")}
          </button>
        }
      />

      {error ? (
        <p className="board-error asset-editor-error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="asset-editor-form-body script-editor-form">
        <AssetDetailSection title={t("board:scriptEditor.metaSection")}>
          <label className="asset-editor-field">
            <span className="asset-field-eyebrow">{t("board:scriptEditor.titleLabel")}</span>
            <input
              value={title}
              placeholder={t("board:scriptEditor.titlePlaceholder")}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label className="asset-editor-field">
            <span className="asset-field-eyebrow">{t("board:scriptEditor.durationLabel")}</span>
            <input
              type="number"
              min={1}
              value={durationSec}
              placeholder={t("board:scriptEditor.durationPlaceholder")}
              onChange={(e) => setDurationSec(e.target.value)}
            />
          </label>
        </AssetDetailSection>

        <AssetDetailSection title={t("board:scriptEditor.bodySection")}>
          <p className="muted script-editor-hint">{t("board:scriptEditor.bodyHint")}</p>
          <textarea
            className="script-md-editor script-editor-textarea"
            value={contentMd}
            rows={18}
            placeholder={t("board:scriptEditor.bodyPlaceholder")}
            onChange={(e) => setContentMd(e.target.value)}
          />
          <p className="muted script-editor-meta">
            {t("board:scriptEditor.lineCount", { count: lineCount })}
          </p>
        </AssetDetailSection>
      </div>

      <footer className="asset-editor-footer script-editor-footer">
        <button type="button" className="btn-secondary" disabled={saving} onClick={onClose}>
          {t("common:actions.cancel")}
        </button>
        <button type="button" className="btn-primary" disabled={saving} onClick={() => void save()}>
          {saving ? t("common:actions.saving") : t("common:actions.save")}
        </button>
      </footer>
    </AssetDetailShell>
  );
}
