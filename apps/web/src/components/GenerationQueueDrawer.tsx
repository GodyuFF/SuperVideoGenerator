/**
 * 生成队列右侧抽屉与看板工具条角标按钮。
 */

import { useMemo } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
import { useGenerationQueue } from "../context/GenerationQueueContext";
import { useResizableDrawerWidth } from "../hooks/useResizableDrawerWidth";
import { ResizableDrawerEdge } from "./layout/ResizableDrawerEdge";
import type { GenerationQueueJob } from "../types";

/** 取 asset_id 末尾 6 位用于行内展示。 */
function assetIdSuffix(assetId: string): string {
  const trimmed = assetId.trim();
  if (trimmed.length <= 6) return trimmed;
  return trimmed.slice(-6);
}

interface QueueJobRowProps {
  job: GenerationQueueJob;
}

/** 单条队列任务行：类型徽章、标签、资产尾号、状态与错误。 */
function QueueJobRow({ job }: QueueJobRowProps) {
  const { t } = useAppTranslation("board");
  const kindLabel =
    job.kind === "image" ? t("generationQueue.kindImage") : t("generationQueue.kindVideo");
  const statusLabel = t(`generationQueue.status.${job.status}`);
  const modifier =
    job.status === "running"
      ? "running"
      : job.status === "queued"
        ? "queued"
        : job.status === "done"
          ? "done"
          : "failed";

  return (
    <li className={`generation-queue-row generation-queue-row--${modifier}`}>
      <span className="meta-chip generation-queue-row__kind">{kindLabel}</span>
      <div className="generation-queue-row__main">
        <p className="generation-queue-row__label">{job.label}</p>
        <p className="generation-queue-row__meta tabular-nums muted">
          <span className="generation-queue-row__asset-id" title={job.asset_id}>
            …{assetIdSuffix(job.asset_id)}
          </span>
          <span className="generation-queue-row__status">{statusLabel}</span>
        </p>
        {job.error ? (
          <p className="generation-queue-row__error">{job.error}</p>
        ) : null}
      </div>
    </li>
  );
}

interface QueueSectionProps {
  title: string;
  jobs: GenerationQueueJob[];
}

/** 队列分区（进行中 / 排队中 / 最近完成）。 */
function QueueSection({ title, jobs }: QueueSectionProps) {
  return (
    <section className="asset-detail-section generation-queue-drawer__section">
      <div className="shot-detail-drawer__section-head">
        <h4>{title}</h4>
        <span className="muted tabular-nums generation-queue-drawer__section-count">
          {jobs.length}
        </span>
      </div>
      {jobs.length > 0 ? (
        <ul className="generation-queue-drawer__list">
          {jobs.map((job) => (
            <QueueJobRow key={job.id} job={job} />
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** 看板工具条「生成队列」按钮；角标 = queued + running。 */
export function GenerationQueueOpenButton() {
  const { t } = useAppTranslation("board");
  const { open, setOpen, counts, refresh } = useGenerationQueue();
  const badgeCount = counts.queued + counts.running;

  /** 打开时拉取快照，关闭时仅切换显隐。 */
  const onToggle = () => {
    const next = !open;
    setOpen(next);
    if (next) void refresh();
  };

  return (
    <button
      type="button"
      className={`btn-secondary btn-sm generation-queue-open-btn${open ? " is-active" : ""}`}
      onClick={onToggle}
      aria-expanded={open}
      aria-label={t("generationQueue.open")}
    >
      <span>{t("generationQueue.open")}</span>
      {badgeCount > 0 ? (
        <span className="generation-queue-open-btn__badge tabular-nums" aria-hidden>
          {badgeCount}
        </span>
      ) : null}
    </button>
  );
}

/** 生成队列右侧抽屉，由 GenerationQueueContext.open 控制显隐。 */
export function GenerationQueueDrawer() {
  const { t } = useAppTranslation("board");
  const { t: tCommon } = useAppTranslation("common");
  const { snapshot, open, setOpen, refresh } = useGenerationQueue();
  const drawerResize = useResizableDrawerWidth({
    storageKey: "svf-generation-queue-drawer-width",
    defaultWidth: 400,
    minWidth: 320,
  });

  const activeJobs = useMemo(() => {
    if (!snapshot?.active) return [];
    return [snapshot.active];
  }, [snapshot?.active]);

  const queuedJobs = snapshot?.queued ?? [];
  const recentJobs = snapshot?.recent ?? [];

  const isEmpty =
    !snapshot || (activeJobs.length === 0 && queuedJobs.length === 0 && recentJobs.length === 0);

  if (!open) return null;

  /** 关闭抽屉。 */
  const onClose = () => setOpen(false);

  return (
    <div
      className="shot-detail-drawer__backdrop asset-editor-overlay generation-queue-drawer__backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={t("generationQueue.title")}
      onClick={onClose}
    >
      <aside
        className={`shot-detail-drawer asset-editor-panel asset-detail-panel generation-queue-drawer${drawerResize.isResizable ? " is-resizable" : ""}`}
        style={drawerResize.drawerStyle}
        onClick={(e) => e.stopPropagation()}
      >
        {drawerResize.isResizable ? (
          <ResizableDrawerEdge
            onPointerDown={drawerResize.onResizePointerDown}
            label={tCommon("actions.resizeDrawer")}
          />
        ) : null}

        <header className="asset-editor-header generation-queue-drawer__header">
          <div>
            <span className="asset-type-badge">{t("generationQueue.badge")}</span>
            <h3>{t("generationQueue.title")}</h3>
          </div>
          <div className="shot-detail-drawer__nav">
            <button type="button" className="btn-secondary btn-sm" onClick={() => void refresh()}>
              {t("refresh")}
            </button>
            <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
              {tCommon("actions.close")}
            </button>
          </div>
        </header>

        <div className="asset-detail-body generation-queue-drawer__body">
          {isEmpty ? (
            <p className="muted generation-queue-drawer__empty">{t("generationQueue.empty")}</p>
          ) : (
            <>
              <QueueSection title={t("generationQueue.sectionActive")} jobs={activeJobs} />
              <QueueSection title={t("generationQueue.sectionQueued")} jobs={queuedJobs} />
              <QueueSection title={t("generationQueue.sectionRecent")} jobs={recentJobs} />
            </>
          )}
        </div>

        <footer className="asset-editor-footer generation-queue-drawer__footer">
          <p className="muted generation-queue-drawer__footnote">{t("generationQueue.footnote")}</p>
        </footer>
      </aside>
    </div>
  );
}
