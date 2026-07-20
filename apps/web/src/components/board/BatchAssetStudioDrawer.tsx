/**
 * 资源列表：右侧可调宽抽屉，整表总览五类资产并批量生成/重新生成。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { useAssetGeneration } from "../../context/AssetGenerationContext";
import { useResizableDrawerWidth } from "../../hooks/useResizableDrawerWidth";
import { AssetImagePreview } from "../AssetImagePreview";
import { AssetGeneratingBadge } from "../AssetGeneratingBadge";
import { AssetRegenerateButton } from "../AssetRegenerateButton";
import { MediaPreview } from "../MediaPreview";
import { ResizableDrawerEdge } from "../layout/ResizableDrawerEdge";
import {
  BATCH_STUDIO_KINDS,
  fetchBatchStudioCatalog,
  filterBatchStudioRows,
  regenerateKindForStudioType,
  runBatchRegenerate,
  type BatchStudioAssetRow,
  type BatchStudioKind,
  type BatchStudioRowStatus,
} from "../../utils/batchAssetStudio";

type TypeFilter = BatchStudioKind | "all";
type MediaFilter = "all" | "missing" | "ready";

interface BatchAssetStudioDrawerProps {
  projectId: string;
  scriptId: string;
  manualEditEnabled?: boolean;
  onClose: () => void;
  onRefresh?: () => void;
}

/** 类型筛选 chip 顺序。 */
const TYPE_FILTERS: TypeFilter[] = ["all", ...BATCH_STUDIO_KINDS];

/** 资源列表右侧抽屉。 */
export function BatchAssetStudioDrawer({
  projectId,
  scriptId,
  manualEditEnabled = false,
  onClose,
  onRefresh,
}: BatchAssetStudioDrawerProps) {
  const { t } = useAppTranslation("board");
  const { t: tCommon } = useAppTranslation("common");
  const { markGenerating, clearGenerating, getEntry } = useAssetGeneration();
  const drawerResize = useResizableDrawerWidth({
    storageKey: "svf-batch-asset-drawer-width",
    defaultWidth: 480,
    minWidth: 360,
  });

  const [rows, setRows] = useState<BatchStudioAssetRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [mediaFilter, setMediaFilter] = useState<MediaFilter>("all");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [rowStatus, setRowStatus] = useState<Record<string, BatchStudioRowStatus>>({});
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchSummary, setBatchSummary] = useState<string | null>(null);
  const cancelRef = useRef(false);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** 节流刷新看板。 */
  const scheduleRefresh = useCallback(() => {
    if (!onRefresh) return;
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => {
      onRefresh();
      refreshTimerRef.current = null;
    }, 800);
  }, [onRefresh]);

  /** 重新拉取整表。 */
  const reloadCatalog = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const catalog = await fetchBatchStudioCatalog(projectId, scriptId);
      setRows(catalog.rows);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [projectId, scriptId]);

  useEffect(() => {
    cancelRef.current = false;
    void reloadCatalog();
    return () => {
      cancelRef.current = true;
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    };
  }, [reloadCatalog]);

  const filtered = useMemo(
    () => filterBatchStudioRows(rows, typeFilter, mediaFilter),
    [rows, typeFilter, mediaFilter],
  );

  const missingCount = useMemo(
    () => rows.filter((r) => r.missingMedia).length,
    [rows],
  );

  const progress = useMemo(() => {
    const ids = Object.keys(rowStatus);
    if (ids.length === 0) return null;
    const done = ids.filter((id) => rowStatus[id] === "done" || rowStatus[id] === "error").length;
    const running = ids.filter((id) => rowStatus[id] === "running" || rowStatus[id] === "queued").length;
    return { done, total: ids.length, running };
  }, [rowStatus]);

  /** 切换单行勾选。 */
  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  /** 全选当前筛选结果。 */
  const selectAllFiltered = () => {
    setSelectedIds(new Set(filtered.map((r) => r.id)));
  };

  /** 清空勾选。 */
  const clearSelection = () => {
    setSelectedIds(new Set());
  };

  /** 更新单行队列状态。 */
  const handleRowStatus = useCallback(
    (assetId: string, status: BatchStudioRowStatus, error?: string | null) => {
      setRowStatus((prev) => ({ ...prev, [assetId]: status }));
      setRowErrors((prev) => {
        if (!error) {
          if (!(assetId in prev)) return prev;
          const next = { ...prev };
          delete next[assetId];
          return next;
        }
        return { ...prev, [assetId]: error };
      });
    },
    [],
  );

  /** 跑批量：缺失或勾选。 */
  const runBatch = async (mode: "missing" | "selected") => {
    if (!manualEditEnabled || batchRunning) return;
    const targets =
      mode === "missing"
        ? filtered.filter((r) => r.missingMedia)
        : filtered.filter((r) => selectedIds.has(r.id));
    if (targets.length === 0) {
      setBatchSummary(
        mode === "missing"
          ? t("batchStudio.noneMissing")
          : t("batchStudio.noneSelected"),
      );
      return;
    }
    setBatchSummary(null);
    setBatchRunning(true);
    cancelRef.current = false;
    setRowStatus({});
    setRowErrors({});
    try {
      const result = await runBatchRegenerate({
        projectId,
        scriptId,
        rows: targets,
        hooks: { markGenerating, clearGenerating },
        onRowStatus: handleRowStatus,
        onItemDone: scheduleRefresh,
        shouldCancel: () => cancelRef.current,
      });
      setBatchSummary(
        t("batchStudio.batchDone", { ok: result.ok, failed: result.failed }),
      );
      await reloadCatalog();
      onRefresh?.();
    } finally {
      setBatchRunning(false);
    }
  };

  /** 类型 chip 文案。 */
  const typeLabel = (kind: TypeFilter) =>
    kind === "all" ? t("batchStudio.filterAll") : t(`tabs.${kind}`);

  /** 行状态文案。 */
  const statusLabel = (row: BatchStudioAssetRow) => {
    const st = rowStatus[row.id];
    if (st === "queued") return t("batchStudio.statusQueued");
    if (st === "running") return t("batchStudio.statusRunning");
    if (st === "done") return t("batchStudio.statusDone");
    if (st === "error") return t("batchStudio.statusError");
    return row.missingMedia
      ? t("batchStudio.statusMissing")
      : t("batchStudio.statusReady");
  };

  return (
    <div
      className="shot-detail-drawer__backdrop asset-editor-overlay batch-studio-drawer__backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={t("batchStudio.title")}
      onClick={onClose}
    >
      <aside
        className={`shot-detail-drawer asset-editor-panel asset-detail-panel batch-studio-drawer${drawerResize.isResizable ? " is-resizable" : ""}`}
        style={drawerResize.drawerStyle}
        onClick={(e) => e.stopPropagation()}
      >
        {drawerResize.isResizable ? (
          <ResizableDrawerEdge
            onPointerDown={drawerResize.onResizePointerDown}
            label={tCommon("actions.resizeDrawer")}
          />
        ) : null}

        <header className="asset-editor-header batch-studio-drawer__header">
          <div>
            <span className="asset-type-badge">{t("batchStudio.badge")}</span>
            <h3>{t("batchStudio.title")}</h3>
            <p className="muted batch-studio-drawer__stats">
              {t("batchStudio.stats", {
                missing: missingCount,
                total: rows.length,
              })}
            </p>
          </div>
          <div className="shot-detail-drawer__nav">
            <button
              type="button"
              className="btn-secondary btn-sm"
              disabled={loading || batchRunning}
              onClick={() => void reloadCatalog()}
            >
              {t("refresh")}
            </button>
            <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
              {tCommon("actions.close")}
            </button>
          </div>
        </header>

        <div className="asset-detail-body batch-studio-drawer__body">
          <div className="batch-studio-drawer__filters" role="toolbar">
            <div className="batch-studio-drawer__chips">
              {TYPE_FILTERS.map((kind) => (
                <button
                  key={kind}
                  type="button"
                  className={`meta-chip batch-studio-chip${typeFilter === kind ? " is-active" : ""}`}
                  onClick={() => setTypeFilter(kind)}
                >
                  {typeLabel(kind)}
                </button>
              ))}
            </div>
            <div className="batch-studio-drawer__chips">
              {(
                [
                  ["all", "batchStudio.mediaAll"],
                  ["missing", "batchStudio.mediaMissing"],
                  ["ready", "batchStudio.mediaReady"],
                ] as const
              ).map(([id, key]) => (
                <button
                  key={id}
                  type="button"
                  className={`meta-chip batch-studio-chip${mediaFilter === id ? " is-active" : ""}`}
                  onClick={() => setMediaFilter(id)}
                >
                  {t(key)}
                </button>
              ))}
            </div>
          </div>

          {progress && (progress.running > 0 || batchRunning) ? (
            <div
              className="batch-studio-drawer__progress"
              role="progressbar"
              aria-valuenow={progress.done}
              aria-valuemin={0}
              aria-valuemax={progress.total}
            >
              <div
                className="batch-studio-drawer__progress-bar"
                style={{
                  width: `${progress.total ? (100 * progress.done) / progress.total : 0}%`,
                }}
              />
              <span className="batch-studio-drawer__progress-label tabular-nums">
                {t("batchStudio.progress", {
                  done: progress.done,
                  total: progress.total,
                })}
              </span>
            </div>
          ) : null}

          {batchSummary ? (
            <p className="batch-studio-drawer__summary muted">{batchSummary}</p>
          ) : null}
          {loadError ? <p className="form-error">{loadError}</p> : null}
          {loading ? <p className="muted">{t("batchStudio.loading")}</p> : null}

          {!loading && filtered.length === 0 ? (
            <p className="muted">{t("batchStudio.emptyFilter")}</p>
          ) : null}

          {!loading && filtered.length > 0 ? (
            <ul className="batch-studio-drawer__list">
              {filtered.map((row) => {
                const checked = selectedIds.has(row.id);
                const genEntry = getEntry(row.id);
                const st = rowStatus[row.id];
                const err = rowErrors[row.id];
                return (
                  <li
                    key={row.id}
                    className={[
                      "batch-studio-row",
                      row.missingMedia ? "batch-studio-row--missing" : "",
                      st === "running" ? "batch-studio-row--running" : "",
                      st === "error" ? "batch-studio-row--error" : "",
                      st === "done" ? "batch-studio-row--done" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    <label className="batch-studio-row__check">
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={batchRunning}
                        onChange={() => toggleSelect(row.id)}
                      />
                    </label>
                    <div className="batch-studio-row__media">
                      {row.previewUrl ? (
                        row.type === "video_clip" ? (
                          <MediaPreview
                            kind="video"
                            url={row.previewUrl}
                            projectId={projectId}
                            scriptId={scriptId}
                            variant="thumb"
                            className="batch-studio-row__preview"
                          />
                        ) : (
                          <AssetImagePreview
                            url={row.previewUrl}
                            name={row.name}
                            size="card"
                            projectId={projectId}
                            scriptId={scriptId}
                          />
                        )
                      ) : null}
                    </div>
                    <div className="batch-studio-row__main">
                      <div className="batch-studio-row__head">
                        <span className="meta-chip">{t(`tabs.${row.type}`)}</span>
                        <strong className="batch-studio-row__name">{row.name}</strong>
                        {genEntry ? <AssetGeneratingBadge entry={genEntry} /> : null}
                      </div>
                      {row.summary ? (
                        <p className="muted batch-studio-row__summary">{row.summary}</p>
                      ) : null}
                      <p className="batch-studio-row__status tabular-nums">{statusLabel(row)}</p>
                      {err ? <p className="form-error batch-studio-row__error">{err}</p> : null}
                    </div>
                    {manualEditEnabled ? (
                      <div className="batch-studio-row__action">
                        <AssetRegenerateButton
                          projectId={projectId}
                          scriptId={scriptId}
                          assetId={row.id}
                          kind={
                            regenerateKindForStudioType(row.type) === "video"
                              ? "video"
                              : "image"
                          }
                          layout="compact"
                          disabled={batchRunning}
                          onDone={() => {
                            scheduleRefresh();
                            void reloadCatalog();
                          }}
                        />
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          ) : null}
        </div>

        <footer className="asset-editor-footer batch-studio-drawer__footer">
          <div className="batch-studio-drawer__footer-left">
            <button
              type="button"
              className="btn-secondary btn-sm"
              disabled={batchRunning || filtered.length === 0}
              onClick={selectAllFiltered}
            >
              {t("batchStudio.selectAll")}
            </button>
            <button
              type="button"
              className="btn-secondary btn-sm"
              disabled={batchRunning || selectedIds.size === 0}
              onClick={clearSelection}
            >
              {t("batchStudio.clearSelection")}
            </button>
          </div>
          <div className="batch-studio-drawer__footer-right">
            <button
              type="button"
              className="btn-secondary btn-sm"
              disabled={!manualEditEnabled || batchRunning}
              onClick={() => void runBatch("missing")}
              title={
                manualEditEnabled ? undefined : t("batchStudio.disabledHint")
              }
            >
              {t("batchStudio.generateMissing")}
            </button>
            <button
              type="button"
              className="btn-primary btn-sm"
              disabled={!manualEditEnabled || batchRunning || selectedIds.size === 0}
              onClick={() => void runBatch("selected")}
              title={
                manualEditEnabled ? undefined : t("batchStudio.disabledHint")
              }
            >
              {batchRunning
                ? t("batchStudio.batchRunning")
                : t("batchStudio.regenerateSelected")}
            </button>
          </div>
        </footer>
      </aside>
    </div>
  );
}
