/**
 * 单剧本详情看板（script_details）— 预览 + 弹窗编辑正文与剧情段落。
 */

import { useMemo, useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { deleteTextAsset } from "../../lib/manualAssets";
import { CreateTextAssetDialog } from "../manual/CreateTextAssetDialog";
import { PlotAssetEditor } from "../manual/PlotAssetEditor";
import type { BoardView } from "../../types/board";
import { ScriptEditorModal } from "./ScriptEditorModal";

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

/** 从看板 items 解析剧本主记录与剧情（plot）资产列表。 */
function parseScriptBoardItems(items: Record<string, unknown>[] | undefined) {
  const rows = items ?? [];
  const scriptItem =
    rows.find((r) => r.script_id != null && r.type == null) ??
    rows.find((r) => r.script_id != null) ??
    rows[0];
  const plotItems = rows.filter((r) => String(r.type ?? "") === "plot");
  return { scriptItem, plotItems };
}

/** 剧本详情 Tab：统计、正文预览、剧情段落与弹窗编辑入口。 */
export function ScriptDetailsBoard({
  board,
  projectId,
  scriptId,
  manualEditEnabled = false,
  onRefresh,
}: ScriptDetailsBoardProps) {
  const { t } = useAppTranslation(["board", "common"]);
  const stats = board.stats ?? {};
  const { scriptItem, plotItems } = useMemo(
    () => parseScriptBoardItems(board.items),
    [board.items],
  );

  const title = String(scriptItem?.title ?? stats.title ?? t("board:defaultScriptTitle", { suffix: "" }));
  const status = String(scriptItem?.status ?? stats.status ?? "draft");
  const styleMode = scriptItem?.style_mode ?? stats.style_mode;
  const durationSec = scriptItem?.duration_sec ?? stats.duration_sec;
  const contentMd = String(scriptItem?.content_md ?? stats.content_md ?? "").trim();
  const previewExcerpt = contentMd
    ? contentMd.length > 480
      ? `${contentMd.slice(0, 480)}…`
      : contentMd
    : "";

  const [editorOpen, setEditorOpen] = useState(false);
  const [createPlotOpen, setCreatePlotOpen] = useState(false);
  const [editingPlot, setEditingPlot] = useState<{
    id: string;
    name: string;
    text: string;
  } | null>(null);
  const [deletingPlotId, setDeletingPlotId] = useState<string | null>(null);

  const canEdit = Boolean(manualEditEnabled && projectId && scriptId);

  const handleDeletePlot = async (assetId: string) => {
    if (!projectId || !scriptId) return;
    if (!window.confirm(t("board:scriptDetails.deletePlotConfirm"))) return;
    setDeletingPlotId(assetId);
    try {
      await deleteTextAsset(projectId, scriptId, assetId);
      onRefresh?.();
    } catch (err) {
      window.alert((err as Error).message);
    } finally {
      setDeletingPlotId(null);
    }
  };

  return (
    <div className="script-details-board">
      <header className="script-details-hero">
        <div className="script-details-hero__main">
          <p className="script-details-eyebrow">{t("board:scriptEditor.typeLabel")}</p>
          <h3 className="script-details-hero__title">{title}</h3>
          <div className="script-details-hero__meta">
            <StatusBadge status={status} />
            {styleMode != null && styleMode !== "" ? (
              <span className="meta-chip">{String(styleMode)}</span>
            ) : null}
            {durationSec != null ? (
              <span className="muted script-details-duration">
                {t("board:scriptDetails.durationSec", { sec: String(durationSec) })}
              </span>
            ) : null}
          </div>
        </div>
        {canEdit ? (
          <button
            type="button"
            className="btn-primary btn-sm script-details-edit-btn"
            onClick={() => setEditorOpen(true)}
          >
            {t("board:editScript")}
          </button>
        ) : null}
      </header>

      <ul className="board-stats-row script-details-stats">
        <li>{t("board:scriptDetails.statAssets", { count: String(scriptItem?.asset_count ?? stats.asset_count ?? 0) })}</li>
        <li>{t("board:scriptDetails.statMedia", { count: String(scriptItem?.media_count ?? stats.media_count ?? 0) })}</li>
        <li>{t("board:scriptDetails.statShots", { count: String(scriptItem?.shot_count ?? stats.shot_count ?? 0) })}</li>
        <li>
          {t("board:scriptDetails.statPlan", {
            done: String(scriptItem?.plan_steps_completed ?? stats.plan_steps_completed ?? 0),
            total: String(scriptItem?.plan_steps_total ?? stats.plan_steps_total ?? 0),
          })}
        </li>
      </ul>

      <section className="script-details-content">
        <div className="script-details-content__head">
          <h4>{t("board:scriptDetails.bodyTitle")}</h4>
          {canEdit && !contentMd ? (
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => setEditorOpen(true)}
            >
              {t("board:scriptDetails.addBody")}
            </button>
          ) : null}
        </div>
        <div className="script-details-body script-details-preview">
          {contentMd ? (
            <pre className="script-md-block">{previewExcerpt}</pre>
          ) : (
            <p className="muted script-details-empty">
              {canEdit ? t("board:scriptDetails.emptyBodyEditable") : t("board:scriptDetails.emptyBody")}
            </p>
          )}
          {contentMd.length > 480 ? (
            <button
              type="button"
              className="btn-link script-details-expand"
              onClick={() => setEditorOpen(true)}
            >
              {t("board:scriptDetails.viewFull")}
            </button>
          ) : null}
        </div>
      </section>

      {(plotItems.length > 0 || canEdit) && (
        <section className="script-details-plots">
          <div className="script-details-content__head">
            <h4>{t("board:scriptDetails.plotsTitle")}</h4>
            {canEdit ? (
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => setCreatePlotOpen(true)}
              >
                {t("board:newPlot")}
              </button>
            ) : null}
          </div>
          {plotItems.length === 0 ? (
            <p className="muted">{t("board:scriptDetails.noPlots")}</p>
          ) : (
            <ul className="simple-item-list script-details-plot-list">
              {plotItems.map((raw) => {
                const id = String(raw.id);
                return (
                  <li key={id} className="simple-item-row">
                    <span className="asset-type-badge">plot</span>
                    <span className="simple-item-text">
                      {String(raw.name)} — {String(raw.preview ?? "")}
                    </span>
                    {canEdit && projectId ? (
                      <span className="simple-item-actions">
                        <button
                          type="button"
                          className="btn-secondary btn-sm"
                          onClick={() =>
                            setEditingPlot({
                              id,
                              name: String(raw.name),
                              text: String(raw.preview ?? ""),
                            })
                          }
                        >
                          {t("board:editPlot")}
                        </button>
                        <button
                          type="button"
                          className="btn-danger btn-sm"
                          disabled={deletingPlotId === id}
                          onClick={() => void handleDeletePlot(id)}
                        >
                          {deletingPlotId === id
                            ? t("common:actions.deleting")
                            : t("common:actions.delete")}
                        </button>
                      </span>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}

      {editorOpen && projectId && scriptId ? (
        <ScriptEditorModal
          projectId={projectId}
          scriptId={scriptId}
          initialTitle={title}
          initialContentMd={contentMd}
          initialDurationSec={
            typeof durationSec === "number" ? durationSec : Number(durationSec) || null
          }
          onClose={() => setEditorOpen(false)}
          onSaved={() => onRefresh?.()}
        />
      ) : null}

      {createPlotOpen && projectId && scriptId ? (
        <CreateTextAssetDialog
          projectId={projectId}
          scriptId={scriptId}
          assetType="plot"
          onClose={() => setCreatePlotOpen(false)}
          onCreated={() => onRefresh?.()}
        />
      ) : null}

      {editingPlot && projectId ? (
        <PlotAssetEditor
          projectId={projectId}
          assetId={editingPlot.id}
          initialName={editingPlot.name}
          initialText={editingPlot.text}
          onClose={() => setEditingPlot(null)}
          onSaved={() => onRefresh?.()}
        />
      ) : null}
    </div>
  );
}
