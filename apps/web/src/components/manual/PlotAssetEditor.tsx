/** 编辑剧情（plot）私有文字资产 */

import { useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";

const API = "/api";

interface PlotAssetEditorProps {
  projectId: string;
  assetId: string;
  initialName: string;
  initialText: string;
  onClose: () => void;
  onSaved: () => void;
}

export function PlotAssetEditor({
  projectId,
  assetId,
  initialName,
  initialText,
  onClose,
  onSaved,
}: PlotAssetEditorProps) {
  const { t } = useAppTranslation("common");
  const [name, setName] = useState(initialName);
  const [text, setText] = useState(initialText);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const r = await fetch(`${API}/projects/${projectId}/assets/${assetId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, content: { text } }),
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
          <h3>编辑剧情</h3>
          <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
            {t("actions.close")}
          </button>
        </header>
        {error && <p className="board-error">{error}</p>}
        <div className="asset-editor-body">
          <label className="asset-editor-field">
            <span>名称</span>
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="asset-editor-field">
            <span>正文</span>
            <textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} />
          </label>
        </div>
        <footer className="asset-editor-footer">
          <button type="button" className="btn-primary" disabled={saving} onClick={() => void save()}>
            {saving ? t("actions.saving") : t("actions.save")}
          </button>
        </footer>
      </div>
    </div>
  );
}
