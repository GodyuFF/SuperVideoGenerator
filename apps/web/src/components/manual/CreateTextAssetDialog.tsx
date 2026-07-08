/** 手动创建文字资产（剧情/角色/场景/物品） */

import { useState } from "react";
import { createTextAsset } from "../../lib/manualAssets";

const TYPE_LABEL: Record<string, string> = {
  plot: "剧情",
  character: "角色",
  scene: "空镜",
  prop: "物品",
  frame: "画面",
};

interface CreateTextAssetDialogProps {
  projectId: string;
  scriptId: string;
  assetType: string;
  onClose: () => void;
  onCreated: () => void;
}

export function CreateTextAssetDialog({
  projectId,
  scriptId,
  assetType,
  onClose,
  onCreated,
}: CreateTextAssetDialogProps) {
  const [name, setName] = useState("");
  const [summary, setSummary] = useState("");
  const [description, setDescription] = useState("");
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isPlot = assetType === "plot";

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      const content = isPlot
        ? { text: text.trim() || name.trim() }
        : { summary: summary.trim(), description: description.trim() };
      await createTextAsset(projectId, scriptId, {
        type: assetType,
        name: name.trim(),
        content,
      });
      onCreated();
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
          <h3>新建{TYPE_LABEL[assetType] ?? assetType}</h3>
          <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
            关闭
          </button>
        </header>
        {error && <p className="board-error">{error}</p>}
        <div className="asset-editor-body">
          <label className="asset-editor-field">
            <span>名称</span>
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          {isPlot ? (
            <label className="asset-editor-field">
              <span>剧情正文</span>
              <textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} />
            </label>
          ) : (
            <>
              <label className="asset-editor-field">
                <span>摘要</span>
                <input value={summary} onChange={(e) => setSummary(e.target.value)} />
              </label>
              <label className="asset-editor-field">
                <span>描述</span>
                <textarea
                  rows={4}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </label>
            </>
          )}
        </div>
        <footer className="asset-editor-footer">
          <button type="button" className="btn-primary" disabled={saving || !name.trim()} onClick={() => void submit()}>
            {saving ? "创建中…" : "创建"}
          </button>
        </footer>
      </div>
    </div>
  );
}
