/**

 * 剧本详情右侧抽屉：展示正文、统计与剧情段落（关系图/引用跳转入口）。

 */



import { useCallback, useEffect, useState } from "react";

import { useAppTranslation } from "../../i18n/useAppTranslation";

import { useResizableDrawerWidth } from "../../hooks/useResizableDrawerWidth";

import type { BoardView } from "../../types/board";

import { ResizableDrawerEdge } from "../layout/ResizableDrawerEdge";

import { ScriptEditorModal } from "./ScriptEditorModal";



const API = "/api";



interface ScriptDetailPayload {

  scriptId: string;

  title: string;

  status: string;

  styleMode: string;

  durationSec: number | null;

  contentMd: string;

  assetCount: number;

  mediaCount: number;

  shotCount: number;

  planDone: number;

  planTotal: number;

  plots: Array<{ id: string; name: string; preview: string }>;

}



interface ScriptDetailDrawerProps {

  projectId: string;

  /** 要展示的剧本 ID（可与当前工作台 scriptId 不同）。 */

  scriptId: string;

  /** 当前工作台剧本，用于判断是否允许编辑。 */

  activeScriptId?: string | null;

  manualEditEnabled?: boolean;

  onClose: () => void;

  onRefresh?: () => void;

  onNavigateAsset?: (id: string, kind: string) => void;

}



/** 从 script_details 看板响应解析展示载荷。 */

function parseScriptDetailsBoard(

  board: BoardView,

  fallbackScriptId: string,

): ScriptDetailPayload {

  const rows = (board.items ?? []) as Record<string, unknown>[];

  const stats = (board.stats ?? {}) as Record<string, unknown>;

  const scriptItem =

    rows.find((r) => r.script_id != null && r.type == null) ??

    rows.find((r) => r.script_id != null) ??

    rows[0];

  const plots = rows

    .filter((r) => String(r.type ?? "") === "plot")

    .map((r) => ({

      id: String(r.id ?? ""),

      name: String(r.name ?? ""),

      preview: String(r.preview ?? ""),

    }))

    .filter((p) => p.id);



  const durationRaw = scriptItem?.duration_sec ?? stats.duration_sec;

  let durationSec: number | null = null;

  if (durationRaw != null && durationRaw !== "") {

    const n = Number(durationRaw);

    if (!Number.isNaN(n)) durationSec = n;

  }



  return {

    scriptId: String(scriptItem?.script_id ?? stats.script_id ?? fallbackScriptId),

    title: String(scriptItem?.title ?? stats.title ?? fallbackScriptId),

    status: String(scriptItem?.status ?? stats.status ?? "draft"),

    styleMode: String(scriptItem?.style_mode ?? stats.style_mode ?? ""),

    durationSec,

    contentMd: String(scriptItem?.content_md ?? stats.content_md ?? ""),

    assetCount: Number(scriptItem?.asset_count ?? stats.asset_count ?? 0),

    mediaCount: Number(scriptItem?.media_count ?? stats.media_count ?? 0),

    shotCount: Number(scriptItem?.shot_count ?? stats.shot_count ?? 0),

    planDone: Number(scriptItem?.plan_steps_completed ?? stats.plan_steps_completed ?? 0),

    planTotal: Number(scriptItem?.plan_steps_total ?? stats.plan_steps_total ?? 0),

    plots,

  };

}



/** 剧本信息右侧抽屉。 */

export function ScriptDetailDrawer({

  projectId,

  scriptId,

  activeScriptId,

  manualEditEnabled = false,

  onClose,

  onRefresh,

  onNavigateAsset,

}: ScriptDetailDrawerProps) {

  const { t } = useAppTranslation(["board", "common"]);

  const [payload, setPayload] = useState<ScriptDetailPayload | null>(null);

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState<string | null>(null);

  const [editorOpen, setEditorOpen] = useState(false);



  const drawerResize = useResizableDrawerWidth({

    storageKey: "svf-script-detail-drawer-width",

    defaultWidth: 480,

    minWidth: 360,

  });



  const canEdit = Boolean(

    manualEditEnabled && activeScriptId && activeScriptId === scriptId,

  );



  /** 拉取剧本详情看板。 */

  const load = useCallback(async () => {

    setLoading(true);

    setError(null);

    try {

      const params = new URLSearchParams({ script_id: scriptId });

      const res = await fetch(

        `${API}/projects/${projectId}/board/script_details?${params}`,

      );

      if (!res.ok) {

        throw new Error(`加载剧本失败 (${res.status})`);

      }

      const board = (await res.json()) as BoardView;

      setPayload(parseScriptDetailsBoard(board, scriptId));

    } catch (err) {

      setPayload(null);

      setError(err instanceof Error ? err.message : String(err));

    } finally {

      setLoading(false);

    }

  }, [projectId, scriptId]);



  useEffect(() => {

    void load();

  }, [load]);



  useEffect(() => {

    const onKey = (e: KeyboardEvent) => {

      if (e.key === "Escape") onClose();

    };

    window.addEventListener("keydown", onKey);

    return () => window.removeEventListener("keydown", onKey);

  }, [onClose]);



  return (

    <>

      <div

        className="shot-detail-drawer__backdrop asset-editor-overlay"

        role="dialog"

        aria-modal="true"

        aria-label={t("board:scriptDrawer.title")}

        onClick={onClose}

      >

        <aside

          className={`shot-detail-drawer asset-editor-panel asset-detail-panel script-detail-drawer${drawerResize.isResizable ? " is-resizable" : ""}`}

          style={drawerResize.drawerStyle}

          onClick={(e) => e.stopPropagation()}

        >

          {drawerResize.isResizable ? (

            <ResizableDrawerEdge

              onPointerDown={drawerResize.onResizePointerDown}

              label={t("common:actions.resizeDrawer")}

            />

          ) : null}



          <header className="asset-editor-header shot-detail-drawer__header">

            <div>

              <span className="asset-type-badge">{t("board:scriptEditor.typeLabel")}</span>

              <h3>{payload?.title ?? t("board:scriptDrawer.loadingTitle")}</h3>

            </div>

            <div className="shot-detail-drawer__nav">

              {canEdit && payload ? (

                <button

                  type="button"

                  className="btn-primary btn-sm"

                  onClick={() => setEditorOpen(true)}

                >

                  {t("board:editScript")}

                </button>

              ) : null}

              <button type="button" className="btn-secondary btn-sm" onClick={onClose}>

                {t("common:actions.close")}

              </button>

            </div>

          </header>



          <div className="asset-detail-body script-detail-drawer__body">

            {loading ? <p className="muted">{t("board:loadingBoard")}</p> : null}

            {error ? <p className="form-error" role="alert">{error}</p> : null}



            {payload && !loading ? (

              <>

                <div className="script-detail-drawer__meta">

                  <span className={`board-status status-${payload.status}`}>

                    {payload.status}

                  </span>

                  {payload.styleMode ? (

                    <span className="meta-chip">{payload.styleMode}</span>

                  ) : null}

                  {payload.durationSec != null ? (

                    <span className="meta-chip">

                      {t("board:scriptDetails.durationSec", {

                        sec: String(payload.durationSec),

                      })}

                    </span>

                  ) : null}

                </div>



                <ul className="board-stats-row script-details-stats">

                  <li>

                    {t("board:scriptDetails.statAssets", {

                      count: String(payload.assetCount),

                    })}

                  </li>

                  <li>

                    {t("board:scriptDetails.statMedia", {

                      count: String(payload.mediaCount),

                    })}

                  </li>

                  <li>

                    {t("board:scriptDetails.statShots", {

                      count: String(payload.shotCount),

                    })}

                  </li>

                  <li>

                    {t("board:scriptDetails.statPlan", {

                      done: String(payload.planDone),

                      total: String(payload.planTotal),

                    })}

                  </li>

                </ul>



                <section className="script-detail-drawer__section">

                  <h4 className="script-detail-drawer__eyebrow">

                    {t("board:scriptDetails.bodyTitle")}

                  </h4>

                  {payload.contentMd.trim() ? (

                    <pre className="script-md-block script-detail-drawer__md">

                      {payload.contentMd}

                    </pre>

                  ) : (

                    <p className="muted">{t("board:scriptDetails.emptyBody")}</p>

                  )}

                </section>



                <section className="script-detail-drawer__section">

                  <h4 className="script-detail-drawer__eyebrow">

                    {t("board:scriptDetails.plotsTitle")}

                  </h4>

                  {payload.plots.length === 0 ? (

                    <p className="muted">{t("board:scriptDetails.noPlots")}</p>

                  ) : (

                    <ul className="script-detail-drawer__plot-list">

                      {payload.plots.map((plot) => (

                        <li key={plot.id}>

                          {onNavigateAsset ? (

                            <button

                              type="button"

                              className="script-detail-drawer__plot-btn"

                              onClick={() => onNavigateAsset(plot.id, "plot")}

                            >

                              <strong>{plot.name}</strong>

                              {plot.preview ? (

                                <span className="muted">{plot.preview}</span>

                              ) : null}

                            </button>

                          ) : (

                            <div className="script-detail-drawer__plot-btn script-detail-drawer__plot-btn--static">

                              <strong>{plot.name}</strong>

                              {plot.preview ? (

                                <span className="muted">{plot.preview}</span>

                              ) : null}

                            </div>

                          )}

                        </li>

                      ))}

                    </ul>

                  )}

                </section>

              </>

            ) : null}

          </div>

        </aside>

      </div>



      {editorOpen && payload && canEdit ? (

        <ScriptEditorModal

          projectId={projectId}

          scriptId={payload.scriptId}

          initialTitle={payload.title}

          initialContentMd={payload.contentMd}

          initialDurationSec={payload.durationSec}

          onClose={() => setEditorOpen(false)}

          onSaved={() => {

            void load();

            onRefresh?.();

          }}

        />

      ) : null}

    </>

  );

}


