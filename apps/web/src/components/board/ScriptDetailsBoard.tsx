/**
 * 单剧本详情看板（script_details）— 支持人工编辑正文
 */

import { useEffect, useState } from "react";
import { patchScript } from "../../lib/manualAssets";
import type { BoardView } from "../../types/board";

function StatusBadge({ status }: { status: string }) {
  return <span className={`board-status status-${status}`}>{status}</span>;
}

interface ScriptDetailsBoardProps {
  board: BoardView;
  projectId?: string | null;
  scriptId?: string | null;
  manualEditEnabled?: boolean;
  onRefresh?: () => void;
}

export function ScriptDetailsBoard({
  board,
  projectId,
  scriptId,
  manualEditEnabled = false,
  onRefresh,
}: ScriptDetailsBoardProps) {
  const stats = board.stats ?? {};
  const item = (board.items ?? [])[0] as Record<string, unknown> | undefined;
  const title = String(item?.title ?? stats.title ?? "未命名剧本");
  const status = String(item?.status ?? stats.status ?? "draft");
  const styleMode = item?.style_mode ?? stats.style_mode;
  const durationSec = item?.duration_sec ?? stats.duration_sec;
  const contentMd = String(item?.content_md ?? stats.content_md ?? "").trim();

  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(title);
  const [draftContent, setDraftContent] = useState(contentMd);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraftTitle(title);
    setDraftContent(contentMd);
  }, [title, contentMd]);

  const canEdit = Boolean(manualEditEnabled && projectId && scriptId);

  const save = async () => {
    if (!projectId || !scriptId) return;
    setSaving(true);
    setError(null);
    try {
      await patchScript(projectId, scriptId, {
        title: draftTitle.trim(),
        content_md: draftContent,
      });
      setEditing(false);
      onRefresh?.();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="script-details-board">
      <header className="script-details-header">
        <div>
          {editing ? (
            <input
              className="script-details-title-input"
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
            />
          ) : (
            <h3>{title}</h3>
          )}
          <StatusBadge status={status} />
          {styleMode != null && styleMode !== "" && (
            <span className="muted script-details-style">{String(styleMode)}</span>
          )}
          {durationSec != null && (
            <span className="muted"> · {String(durationSec)} 秒</span>
          )}
        </div>
        {canEdit && (
          <div className="script-details-actions">
            {editing ? (
              <>
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  disabled={saving}
                  onClick={() => {
                    setEditing(false);
                    setDraftTitle(title);
                    setDraftContent(contentMd);
                  }}
                >
                  取消
                </button>
                <button
                  type="button"
                  className="btn-primary btn-sm"
                  disabled={saving}
                  onClick={() => void save()}
                >
                  {saving ? "保存中…" : "保存"}
                </button>
              </>
            ) : (
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => setEditing(true)}
              >
                编辑剧本
              </button>
            )}
          </div>
        )}
      </header>

      {error && <p className="board-error">{error}</p>}

      <ul className="board-stats-row script-details-stats">
        <li>资产 {String(item?.asset_count ?? stats.asset_count ?? 0)}</li>
        <li>媒体 {String(item?.media_count ?? stats.media_count ?? 0)}</li>
        <li>分镜 {String(item?.shot_count ?? stats.shot_count ?? 0)}</li>
        <li>
          进度 {String(item?.plan_steps_completed ?? stats.plan_steps_completed ?? 0)}/
          {String(item?.plan_steps_total ?? stats.plan_steps_total ?? 0)}
        </li>
      </ul>

      <section className="script-details-content">
        <h4>剧本正文</h4>
        {editing ? (
          <textarea
            className="script-md-editor"
            rows={14}
            value={draftContent}
            onChange={(e) => setDraftContent(e.target.value)}
          />
        ) : contentMd ? (
          <pre className="script-md-block">{contentMd}</pre>
        ) : (
          <p className="muted">暂无正文{canEdit ? "，点击「编辑剧本」添加。" : "。"}</p>
        )}
      </section>
    </div>
  );
}
