/**
 * 分镜镜头详情抽屉：右侧滑出，展示完整字段与谱系；支持编辑模式。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { ResizableDrawerEdge } from "../layout/ResizableDrawerEdge";
import { AssetLineagePanel } from "../AssetLineagePanel";
import type { PatchVideoPlanShotBody, VideoPlanData, VideoPlanShot } from "../../types/videoPlan";
import { ShotMiniTimeline, type ShotSegmentSelection } from "./ShotMiniTimeline";
import { ShotSegmentEditor } from "./ShotSegmentEditor";
import { ShotSubShotCard } from "./ShotSubShotCard";
import { ShotVoiceActCard } from "./ShotVoiceActCard";
import { ShotAvSyncPanel } from "./ShotAvSyncPanel";
import {
  buildMediaDurationIndex,
  buildMediaLinkIndex,
  buildMediaMetaIndex,
  fallbackFramesFromDetail,
  fallbackVoiceActsFromDetail,
  parseSubShotsFromPlan,
  parseVoiceActsFromPlan,
  resolveShotDisplayDuration,
  resolveShotDisplayDurationFromPlan,
  type MediaMetaInfo,
} from "../../utils/shotSegmentUtils";
import { useVoiceActCharacters } from "../../hooks/useVoiceActCharacters";
import { useResizableDrawerWidth } from "../../hooks/useResizableDrawerWidth";
import {
  formatMs,
  formatShotDurationDisplay,
  type ShotDetailItem,
  type StoryboardSubtitleLine,
} from "./storyboardShared";
import type { StyleVideoGenMode } from "../../utils/shotSegmentUtils";
import { clampVisualVideoGenMode } from "../../utils/shotSegmentUtils";
import type { EditTimelineStripSummary } from "../../utils/editTimelineSummary";

export type { ShotDetailItem } from "./storyboardShared";

/** 从 video-plan 响应中解析单镜。 */
function shotFromPlanData(
  data: VideoPlanData | null | undefined,
  shotId: string,
): VideoPlanShot | undefined {
  return data?.shots?.find((s) => s.id === shotId);
}

interface ShotDetailDrawerProps {
  shot: ShotDetailItem;
  projectId: string;
  scriptId?: string | null;
  allShots?: ShotDetailItem[];
  manualEditEnabled?: boolean;
  planLoading?: boolean;
  getShotById?: (shotId: string) => VideoPlanShot | undefined;
  fetchVideoPlan?: () => Promise<VideoPlanData | null>;
  patchShot?: (
    shotId: string,
    body: PatchVideoPlanShotBody,
  ) => Promise<{ data?: VideoPlanData; sideEffects?: { tts_stale?: boolean } }>;
  syncFromTts?: () => Promise<unknown>;
  analyzeAvSync?: (opts?: {
    mode?: "analyze_only" | "hybrid" | "auto_only";
    shotIds?: string[];
  }) => Promise<Record<string, unknown>>;
  applyAvSyncAction?: (
    shotId: string,
    action: Record<string, unknown>,
  ) => Promise<Record<string, unknown>>;
  onDeleteShot?: (shotId: string) => Promise<void>;
  onSplitShot?: (shotId: string) => Promise<void>;
  onSaved?: () => void;
  onClose: () => void;
  onNavigateAsset?: (id: string, kind: string) => void;
  onSelectShot?: (shot: ShotDetailItem) => void;
  /** 跳转全片剪辑 Tab。 */
  onOpenEditTimeline?: () => void;
  /** 剧本是否已有真正的 EditTimeline。 */
  hasEditTimeline?: boolean;
  /** 全片剪辑轴迷你摘要。 */
  editTimelineSummary?: EditTimelineStripSummary | null;
  /** 当前剧本视频风格允许的 AI 生视频子模式。 */
  styleVideoModes?: StyleVideoGenMode[];
}

/** 分镜单镜详情右侧抽屉。 */
export function ShotDetailDrawer({
  shot,
  projectId,
  scriptId,
  allShots = [],
  manualEditEnabled,
  planLoading,
  getShotById,
  fetchVideoPlan,
  patchShot,
  syncFromTts,
  analyzeAvSync,
  applyAvSyncAction,
  onDeleteShot,
  onSplitShot,
  onSaved,
  onClose,
  onNavigateAsset,
  onSelectShot,
  onOpenEditTimeline,
  hasEditTimeline = false,
  editTimelineSummary = null,
  styleVideoModes = [],
}: ShotDetailDrawerProps) {
  const { t } = useAppTranslation("board");
  const { t: tCommon } = useAppTranslation("common");
  const { characters } = useVoiceActCharacters(projectId, scriptId);
  const [copyMsg, setCopyMsg] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [ttsStale, setTtsStale] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [planShot, setPlanShot] = useState<VideoPlanShot | undefined>(
    getShotById?.(shot.id),
  );
  const [segmentSel, setSegmentSel] = useState<ShotSegmentSelection>(null);
  const [mediaLinkById, setMediaLinkById] = useState<Record<string, string>>({});
  const [mediaDurationById, setMediaDurationById] = useState<Record<string, number>>({});
  const [mediaMetaById, setMediaMetaById] = useState<Record<string, MediaMetaInfo>>({});

  useEffect(() => {
    if (!scriptId) {
      setMediaLinkById({});
      setMediaDurationById({});
      setMediaMetaById({});
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch(`/api/projects/${projectId}/scripts/${scriptId}/media`);
        if (!res.ok || cancelled) return;
        const items = (await res.json()) as Array<{
          id?: string;
          link?: string;
          url?: string;
          type?: string;
          name?: string;
          duration_ms?: number | null;
        }>;
        if (!cancelled) {
          setMediaLinkById(buildMediaLinkIndex(items, projectId, scriptId));
          setMediaDurationById(buildMediaDurationIndex(items));
          setMediaMetaById(buildMediaMetaIndex(items));
        }
      } catch {
        if (!cancelled) {
          setMediaLinkById({});
          setMediaDurationById({});
          setMediaMetaById({});
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, scriptId]);

  const orderedShots = useMemo(
    () =>
      [...allShots].sort((a, b) => Number(a.order ?? 0) - Number(b.order ?? 0)),
    [allShots],
  );

  const currentIndex = useMemo(
    () => orderedShots.findIndex((s) => s.id === shot.id),
    [orderedShots, shot.id],
  );

  const prevShot = currentIndex > 0 ? orderedShots[currentIndex - 1] : null;
  const nextShot =
    currentIndex >= 0 && currentIndex < orderedShots.length - 1
      ? orderedShots[currentIndex + 1]
      : null;

  const goPrev = useCallback(() => {
    if (prevShot && onSelectShot) onSelectShot(prevShot);
  }, [prevShot, onSelectShot]);

  const goNext = useCallback(() => {
    if (nextShot && onSelectShot) onSelectShot(nextShot);
  }, [nextShot, onSelectShot]);

  useEffect(() => {
    setEditing(false);
    setTtsStale(false);
    setStatusMsg(null);
    setSegmentSel(null);
  }, [shot.id]);

  useEffect(() => {
    if (editing) return;
    const fromPlan = getShotById?.(shot.id);
    if (fromPlan) setPlanShot(fromPlan);
  }, [shot.id, getShotById, editing]);

  /** 打开抽屉或切换镜头时拉取最新 video-plan；编辑中不覆盖本地草稿。 */
  useEffect(() => {
    if (!fetchVideoPlan || !scriptId || editing) return;
    let cancelled = false;
    void fetchVideoPlan().then((data) => {
      if (cancelled) return;
      const fresh = shotFromPlanData(data, shot.id);
      if (fresh) setPlanShot(fresh);
    });
    return () => {
      cancelled = true;
    };
  }, [shot.id, scriptId, fetchVideoPlan, editing]);

  const durationMs = planShot?.duration_ms ?? shot.duration_ms ?? 3000;
  const displayInstructions =
    (planShot?.review_note ?? "").trim() || shot.display_instructions || "";

  const voiceActs = useMemo(() => {
    if (planShot) {
      return parseVoiceActsFromPlan(planShot, projectId, scriptId ?? undefined, mediaLinkById);
    }
    return fallbackVoiceActsFromDetail(shot, durationMs);
  }, [planShot, shot, projectId, scriptId, durationMs, mediaLinkById]);

  const shotFrames = useMemo(() => {
    const clamp = (frames: ReturnType<typeof parseSubShotsFromPlan>) =>
      frames.map((f) => ({
        ...f,
        videoGenMode: clampVisualVideoGenMode(f.videoGenMode, styleVideoModes),
      }));
    if (planShot) {
      return clamp(
        parseSubShotsFromPlan(
          planShot,
          projectId,
          scriptId ?? undefined,
          mediaLinkById,
          mediaMetaById,
        ),
      );
    }
    return clamp(fallbackFramesFromDetail(shot, durationMs));
  }, [planShot, shot, projectId, scriptId, durationMs, mediaLinkById, mediaMetaById, styleVideoModes]);

  const displayDuration = useMemo(() => {
    const ttsMs = shot.tts_duration_ms ?? shot.actual_duration_ms ?? 0;
    if (planShot) {
      return resolveShotDisplayDurationFromPlan(planShot, ttsMs);
    }
    if (shot.display_duration_ms != null && shot.display_duration_source) {
      return {
        startMs: 0,
        endMs: shot.display_duration_ms,
        durationMs: shot.display_duration_ms,
        source: shot.display_duration_source,
      };
    }
    return resolveShotDisplayDuration({
      duration_ms: shot.duration_ms ?? durationMs,
      tts_duration_ms: ttsMs,
    });
  }, [planShot, shot, durationMs]);

  const enterEdit = useCallback(async () => {
    let data: VideoPlanData | null = null;
    if (fetchVideoPlan) {
      data = await fetchVideoPlan();
    }
    const fresh = shotFromPlanData(data, shot.id) ?? getShotById?.(shot.id);
    if (fresh) {
      setPlanShot(fresh);
      setEditing(true);
      setStatusMsg(null);
      return;
    }
    setStatusMsg(t("storyboard.edit.planUnavailable"));
  }, [fetchVideoPlan, getShotById, shot.id, t]);

  /** 上传配音音频后刷新计划稿与媒体链接。 */
  const refreshPlanAfterAudio = useCallback(async () => {
    if (!fetchVideoPlan) return;
    const data = await fetchVideoPlan();
    const fresh = shotFromPlanData(data, shot.id);
    if (fresh) setPlanShot(fresh);
    if (!scriptId) return;
    try {
      const res = await fetch(`/api/projects/${projectId}/scripts/${scriptId}/media`);
      if (res.ok) {
        const items = (await res.json()) as Array<{
          id?: string;
          link?: string;
          url?: string;
          type?: string;
          name?: string;
          duration_ms?: number | null;
        }>;
        setMediaLinkById(buildMediaLinkIndex(items, projectId, scriptId));
        setMediaDurationById(buildMediaDurationIndex(items));
        setMediaMetaById(buildMediaMetaIndex(items));
      }
    } catch {
      /* ignore */
    }
    onSaved?.();
  }, [fetchVideoPlan, shot.id, projectId, scriptId, onSaved]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (editing) return;
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (!onSelectShot) return;
      if (e.key === "ArrowLeft") goPrev();
      if (e.key === "ArrowRight") goNext();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onSelectShot, goPrev, goNext, editing]);

  const handleCopyNarration = async () => {
    const text = voiceActs.map((a) => a.text).filter(Boolean).join("\n");
    if (!text.trim()) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopyMsg(t("storyboard.copySuccess"));
      window.setTimeout(() => setCopyMsg(null), 2000);
    } catch {
      setCopyMsg(t("storyboard.copyFailed"));
    }
  };

  const handleSave = async (body: PatchVideoPlanShotBody) => {
    if (!patchShot) return;
    setSaving(true);
    try {
      const { data, sideEffects } = await patchShot(shot.id, body);
      setTtsStale(Boolean(sideEffects?.tts_stale));
      setStatusMsg(t("storyboard.edit.saved"));
      setEditing(false);
      const fresh =
        shotFromPlanData(data, shot.id) ??
        shotFromPlanData(await fetchVideoPlan?.(), shot.id) ??
        getShotById?.(shot.id);
      if (fresh) setPlanShot(fresh);
      onSaved?.();
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleSyncTts = async () => {
    if (!syncFromTts) return;
    setSyncing(true);
    try {
      await syncFromTts();
      setTtsStale(false);
      setStatusMsg(t("storyboard.ttsStale.syncDone"));
      onSaved?.();
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncing(false);
    }
  };

  const handleDelete = async () => {
    if (!onDeleteShot) return;
    if (!window.confirm(t("storyboard.edit.deleteConfirm"))) return;
    try {
      await onDeleteShot(shot.id);
      onClose();
      onSaved?.();
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e));
    }
  };

  const handleSplit = async () => {
    if (!onSplitShot) return;
    if (!window.confirm(t("storyboard.edit.splitConfirm"))) return;
    try {
      await onSplitShot(shot.id);
      onClose();
      onSaved?.();
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e));
    }
  };

  const handleRegenDone = async () => {
    const data = fetchVideoPlan ? await fetchVideoPlan() : null;
    const fresh = shotFromPlanData(data, shot.id) ?? getShotById?.(shot.id);
    if (fresh) setPlanShot(fresh);
    onSaved?.();
  };

  const canEdit = Boolean(manualEditEnabled && scriptId && patchShot);
  const editStarting = Boolean(planLoading && !planShot);

  const drawerResize = useResizableDrawerWidth({
    storageKey: "svf.drawerWidth.shotDetail",
    defaultWidth: editing ? 560 : 420,
    minWidth: editing ? 480 : 320,
    maxWidthRatio: editing ? 0.94 : 0.92,
  });

  const shotView = useMemo((): ShotDetailItem => {
    if (!planShot) return shot;
    const ttsMs = shot.tts_duration_ms ?? shot.actual_duration_ms ?? 0;
    const display = resolveShotDisplayDurationFromPlan(planShot, ttsMs);
    const planMs = planShot.duration_ms ?? shot.duration_ms ?? 3000;
    const durationDrift =
      display.source !== "plan" &&
      display.durationMs > 0 &&
      Math.abs(display.durationMs - planMs) > 200;
    return {
      ...shot,
      duration_ms: planMs,
      display_duration_ms: display.durationMs,
      display_duration_source: display.source,
      duration_drift: durationDrift,
      display_instructions:
        (planShot.review_note ?? "").trim() || shot.display_instructions,
    };
  }, [shot, planShot]);

  const displayNum =
    shot.displayNumber ??
    (currentIndex >= 0 ? currentIndex + 1 : Number(shot.order ?? 0) + 1);

  return (
    <div
      className="shot-detail-drawer__backdrop asset-editor-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={t("storyboard.drawerTitle", { num: displayNum })}
      onClick={onClose}
    >
      <aside
        className={`shot-detail-drawer asset-editor-panel asset-detail-panel${drawerResize.isResizable ? " is-resizable" : ""}`}
        style={drawerResize.drawerStyle}
        onClick={(e) => e.stopPropagation()}
      >
        {drawerResize.isResizable ? (
          <ResizableDrawerEdge
            onPointerDown={drawerResize.onResizePointerDown}
            label={tCommon("actions.resizeDrawer")}
          />
        ) : null}
        <header className="asset-editor-header shot-detail-drawer__header">
          <div>
            <span className="asset-type-badge">{t("storyboard.shotType")}</span>
            <h3>{t("storyboard.drawerTitle", { num: displayNum })}</h3>
          </div>
          <div className="shot-detail-drawer__nav">
            {canEdit && !editing ? (
              <button
                type="button"
                className="btn-primary btn-sm"
                disabled={editStarting}
                onClick={() => void enterEdit()}
              >
                {editStarting ? t("storyboard.edit.loading") : t("storyboard.edit.start")}
              </button>
            ) : null}
            {onSelectShot ? (
              <>
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  disabled={!prevShot || editing}
                  onClick={goPrev}
                  aria-label={t("storyboard.prevShot")}
                >
                  ←
                </button>
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  disabled={!nextShot || editing}
                  onClick={goNext}
                  aria-label={t("storyboard.nextShot")}
                >
                  →
                </button>
              </>
            ) : null}
            <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
              {t("storyboard.close")}
            </button>
          </div>
        </header>

        <div className="asset-detail-body shot-detail-drawer__body">
          {(ttsStale || shot.missing_subtitle_sync) && !editing ? (
            <div className="shot-editor-banner shot-editor-banner--warn">
              <p>{t("storyboard.ttsStale.hint")}</p>
              {syncFromTts ? (
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  disabled={syncing}
                  onClick={() => void handleSyncTts()}
                >
                  {syncing ? t("storyboard.ttsStale.syncing") : t("storyboard.ttsStale.sync")}
                </button>
              ) : null}
            </div>
          ) : null}

          {statusMsg ? <p className="muted">{statusMsg}</p> : null}

          {editing && planShot && scriptId ? (
            <ShotSegmentEditor
              projectId={projectId}
              scriptId={scriptId}
              shot={planShot}
              saving={saving}
              mediaLinkById={mediaLinkById}
              mediaMetaById={mediaMetaById}
              mediaDurationById={mediaDurationById}
              onOpenEditTimeline={onOpenEditTimeline}
              hasEditTimeline={hasEditTimeline}
              editTimelineSummary={editTimelineSummary}
              onSave={handleSave}
              onCancel={() => setEditing(false)}
              styleVideoModes={styleVideoModes}
              onPlanRefresh={refreshPlanAfterAudio}
            />
          ) : (
            <>
              <ShotMiniTimeline
                durationMs={durationMs}
                displayDurationMs={displayDuration.durationMs}
                displayDurationSource={displayDuration.source}
                voiceActs={voiceActs}
                sub_shots={shotFrames}
                selected={segmentSel}
                onSelect={setSegmentSel}
              />

              {shotView.time_label || shotView.duration_ms != null ? (
                <section className="asset-detail-section shot-detail-drawer__meta-strip">
                  {shotView.time_label ? (
                    <p className="tabular-nums">{shotView.time_label}</p>
                  ) : null}
                  {shot.timeline_source_label ? (
                    <span className="storyboard-source-chip">{shot.timeline_source_label}</span>
                  ) : null}
                  {shotView.duration_ms != null ? (
                    <p
                      className={
                        shotView.duration_drift
                          ? "storyboard-table-duration storyboard-table-duration--drift"
                          : "muted storyboard-table-duration"
                      }
                    >
                      {formatShotDurationDisplay(
                        {
                          display_duration_ms: displayDuration.durationMs,
                          display_duration_source: displayDuration.source,
                        },
                        t,
                      )}
                    </p>
                  ) : null}
                  {shot.need_regen ? (
                    <span className="storyboard-status-badge storyboard-status-badge--warn">
                      {t("storyboard.badgeNeedRegen")}
                    </span>
                  ) : null}
                </section>
              ) : null}

              <ShotAvSyncPanel
                planShot={planShot}
                shotId={shot.id}
                enabled={canEdit}
                onAnalyze={analyzeAvSync}
                onApplyAction={applyAvSyncAction}
                onPatchPolicy={
                  canEdit && patchShot
                    ? async (body) => {
                        await handleSave(body);
                      }
                    : undefined
                }
              />

              <section className="asset-detail-section shot-detail-drawer__segments">
                <div className="shot-detail-drawer__section-head">
                  <h4>{t("storyboard.voiceAct.sectionTitle")}</h4>
                  {voiceActs.some((a) => a.text.trim()) ? (
                    <button
                      type="button"
                      className="btn-secondary btn-sm"
                      onClick={handleCopyNarration}
                    >
                      {t("storyboard.copyNarration")}
                    </button>
                  ) : null}
                </div>
                {copyMsg ? <p className="muted">{copyMsg}</p> : null}
                {voiceActs.length === 0 ? (
                  <p className="muted">{t("storyboard.voiceAct.empty")}</p>
                ) : (
                  <div className="shot-segment-editor__list">
                    {voiceActs.map((act, idx) => (
                      <ShotVoiceActCard
                        key={act.id}
                        act={act}
                        index={idx}
                        projectId={projectId}
                        scriptId={scriptId ?? ""}
                        shotId={shot.id}
                        selected={segmentSel?.kind === "voice" && segmentSel.id === act.id}
                        regenerateEnabled={Boolean(manualEditEnabled && scriptId)}
                        characterOptions={characters}
                        onSelect={() => setSegmentSel({ kind: "voice", id: act.id })}
                        onRegenerateDone={() => void handleRegenDone()}
                      />
                    ))}
                  </div>
                )}
              </section>

              <section className="asset-detail-section shot-detail-drawer__segments">
                <h4>{t("storyboard.subShot.sectionTitle")}</h4>
                {shotFrames.length === 0 ? (
                  <p className="muted">{t("storyboard.subShot.empty")}</p>
                ) : (
                  <div className="shot-segment-editor__list">
                    {shotFrames.map((vis, idx) => (
                      <ShotSubShotCard
                        key={vis.id}
                        visual={vis}
                        index={idx}
                        projectId={projectId}
                        scriptId={scriptId ?? ""}
                        shotId={shot.id}
                        selected={segmentSel?.kind === "visual" && segmentSel.id === vis.id}
                        regenerateEnabled={Boolean(manualEditEnabled && scriptId)}
                        onSelect={() => setSegmentSel({ kind: "visual", id: vis.id })}
                        onNavigateAsset={onNavigateAsset}
                        onRegenerateDone={() => void handleRegenDone()}
                        onOpenEditTimeline={onOpenEditTimeline}
                        hasEditTimeline={hasEditTimeline}
                        editTimelineSummary={editTimelineSummary}
                        voiceActs={voiceActs}
                        styleVideoModes={styleVideoModes}
                      />
                    ))}
                  </div>
                )}
              </section>

              {shot.subtitle_lines && shot.subtitle_lines.length > 0 ? (
                <section className="asset-detail-section">
                  <h4>{t("storyboard.sectionSubtitles")}</h4>
                  <ul className="storyboard-subtitle-lines">
                    {shot.subtitle_lines.map((line: StoryboardSubtitleLine, lineIdx: number) => {
                      const absStart = Number(line.absolute_start_ms ?? line.start_ms ?? 0);
                      const absEnd = Number(line.absolute_end_ms ?? line.end_ms ?? absStart);
                      const text = String(line.text ?? "").trim();
                      if (!text) return null;
                      const character = String(line.character ?? "").trim();
                      const color = String(line.color ?? "").trim();
                      return (
                        <li key={`${shot.id}-sub-${lineIdx}`}>
                          <span className="tabular-nums">
                            {formatMs(absStart)}–{formatMs(absEnd)}
                          </span>{" "}
                          {character ? (
                            <span className="storyboard-subtitle-character">{character}</span>
                          ) : null}{" "}
                          {color ? (
                            <span
                              className="storyboard-subtitle-swatch"
                              style={{ background: color }}
                              title={color}
                              aria-hidden
                            />
                          ) : null}{" "}
                          {text}
                        </li>
                      );
                    })}
                  </ul>
                </section>
              ) : null}

              <section className="asset-detail-section">
                <h4>{t("storyboard.sectionDisplay")}</h4>
                {displayInstructions ? (
                  <p className="storyboard-display-instructions">{displayInstructions}</p>
                ) : (
                  <p className="muted" title={t("storyboard.pendingDetailHint")}>
                    {t("storyboard.noDisplayInstructions")}
                  </p>
                )}
              </section>

              <section className="asset-detail-section">
                <h4>{t("storyboard.sectionLineage")}</h4>
                <AssetLineagePanel
                  projectId={projectId}
                  assetId={shot.id}
                  onNavigateAsset={onNavigateAsset}
                />
              </section>

              {canEdit && (onDeleteShot || onSplitShot) ? (
                <div className="shot-editor-actions">
                  {onSplitShot ? (
                    <button type="button" className="btn-secondary" onClick={() => void handleSplit()}>
                      {t("storyboard.edit.splitShot")}
                    </button>
                  ) : null}
                  {onDeleteShot ? (
                    <button type="button" className="btn-secondary" onClick={() => void handleDelete()}>
                      {t("storyboard.edit.deleteShot")}
                    </button>
                  ) : null}
                </div>
              ) : null}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
