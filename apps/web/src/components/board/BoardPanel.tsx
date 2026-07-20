/**
 * 看板 Tab 容器与各类型看板渲染
 */

import { lazy, memo, startTransition, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { GraphBoard } from "./GraphBoard";
import { MediaBoard } from "./MediaBoard";
import { KnowledgeBoard } from "./KnowledgeBoard";
import { ImageTextAssetCard, type ImageTextAssetItem } from "../ImageTextAssetCard";
import { ImageTextAssetDetailModal } from "../ImageTextAssetDetailModal";
import { ImageTextAssetEditor } from "../ImageTextAssetEditor";
import { MediaAssetDetailModal, type MediaAssetItem } from "../MediaAssetDetailModal";
import { EditTimelineBoard } from "./EditTimelineBoard";
import { EditTabSimpleView } from "../../editor/EditTabSimpleView";
import { useEditTimeline } from "../../edit/useEditTimeline";
import { ScriptDetailsBoard } from "./ScriptDetailsBoard";
import { ScriptDetailDrawer } from "./ScriptDetailDrawer";
import { BatchAssetStudioDrawer } from "./BatchAssetStudioDrawer";
import {
  GenerationQueueDrawer,
  GenerationQueueOpenButton,
} from "../GenerationQueueDrawer";
import { ShotDetailDrawer, type ShotDetailItem } from "./ShotDetailDrawer";
import { StoryboardBoard } from "./StoryboardBoard";
import {
  buildShotDetailItem,
  parseStoryboardShot,
  parseStoryboardShots,
} from "./storyboardShared";
import type { StyleVideoGenMode } from "../../utils/shotSegmentUtils";
import { buildEditTimelineStripSummary } from "../../utils/editTimelineSummary";
import {
  BOARD_TABS,
  boardMatchesTab,
  visibleScriptTabs,
  type BoardNode,
  type BoardTabId,
  type BoardView,
  type ScriptBoardMeta,
} from "../../types/board";
import type { WorkspaceMode } from "../../lib/localProjects";
import { ManualEditBanner } from "../manual/ManualEditBanner";
import { CreateTextAssetDialog } from "../manual/CreateTextAssetDialog";
import { deleteTextAsset } from "../../lib/manualAssets";
import { fetchBoardTextAssetItem } from "../../lib/fetchBoardTextAsset";
import { useVideoPlan } from "../../hooks/useVideoPlan";
import {
  buildMinimalShotPayload,
  shotCameraMotion,
  shotVoiceText,
} from "../../utils/shotTrackUtils";

const EditorStudioModal = lazy(() =>
  import("../../editor/EditorStudioModal").then((m) => ({ default: m.EditorStudioModal })),
);

interface BoardPanelProps {
  workspaceMode: WorkspaceMode;
  activeTab: BoardTabId;
  onTabChange: (tab: BoardTabId) => void;
  board: BoardView | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onEnterScript?: (scriptId: string) => void;
  onCreateScript?: (title: string) => void | Promise<void>;
  onDeleteScript?: (scriptId: string) => void | Promise<void>;
  onBackToOverview?: () => void;
  projectId?: string | null;
  scriptId?: string | null;
  scriptMeta?: ScriptBoardMeta | null;
  manualEditEnabled?: boolean;
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`board-status status-${status}`}>{status}</span>;
}

/** 项目整体看板：按创建顺序展示带编号的剧本卡片。 */
function OverviewBoard({
  board,
  onEnterScript,
  onCreateScript,
  onDeleteScript,
}: {
  board: BoardView;
  onEnterScript?: (id: string) => void;
  onCreateScript?: (title: string) => void | Promise<void>;
  onDeleteScript?: (id: string) => void | Promise<void>;
}) {
  const { t } = useAppTranslation(["board", "common"]);
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const items = board.items ?? [];

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const title = newTitle.trim() || t("board:defaultScriptTitle", { suffix: Date.now().toString().slice(-4) });
    if (!onCreateScript) return;
    setCreating(true);
    try {
      await onCreateScript(title);
      setNewTitle("");
    } finally {
      setCreating(false);
    }
  }

  return (
    <>
      {onCreateScript && (
        <form className="overview-create-script" onSubmit={(e) => void handleCreate(e)}>
          <input
            type="text"
            value={newTitle}
            placeholder={t("board:newScriptPlaceholder")}
            disabled={creating}
            onChange={(e) => setNewTitle(e.target.value)}
          />
          <button type="submit" className="btn-secondary btn-sm" disabled={creating}>
            {creating ? t("common:actions.creating") : t("board:newScript")}
          </button>
        </form>
      )}

      {items.length === 0 ? (
        <p className="muted">{t("board:noScripts")}</p>
      ) : (
        <div className="board-cards">
          {items.map((raw) => {
            const item = raw as Record<string, unknown>;
            const sid = String(item.script_id ?? "");
            return (
              <article
                key={sid}
                className={`board-card board-card-clickable ${item.is_active ? "active" : ""}`}
                role="button"
                tabIndex={0}
                onClick={() => sid && onEnterScript?.(sid)}
                onKeyDown={(e) => {
                  if ((e.key === "Enter" || e.key === " ") && sid) {
                    e.preventDefault();
                    onEnterScript?.(sid);
                  }
                }}
              >
                <header>
                  <div className="board-card-title-row">
                    <span className="board-script-index" aria-label={t("board:scriptIndex", { index: Number(item.script_index ?? item.order ?? 0) })}>
                      {t("board:scriptIndex", {
                        index: Number(item.script_index ?? item.order ?? 0) || "—",
                      })}
                    </span>
                    <strong>{String(item.title)}</strong>
                  </div>
                  <StatusBadge status={String(item.status)} />
                </header>
                <p className="muted board-preview">
                  {String(item.content_preview || t("board:noContentPreview"))}
                </p>
                <ul className="board-stats-row">
                  <li>资产 {String(item.asset_count)}</li>
                  <li>媒体 {String(item.media_count)}</li>
                  <li>分镜 {String(item.shot_count)}</li>
                  <li>
                    进度 {String(item.plan_steps_completed)}/{String(item.plan_steps_total)}
                  </li>
                </ul>
                {onEnterScript && sid && (
                  <div className="board-card-actions">
                    <button
                      type="button"
                      className="btn-secondary btn-sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        onEnterScript(sid);
                      }}
                    >
                      {t("board:enterScript")}
                    </button>
                    {onDeleteScript && (
                      <button
                        type="button"
                        className="btn-danger btn-sm"
                        disabled={deletingId === sid}
                        onClick={(e) => {
                          e.stopPropagation();
                          void (async () => {
                            setDeletingId(sid);
                            try {
                              await onDeleteScript(sid);
                            } finally {
                              setDeletingId(null);
                            }
                          })();
                        }}
                      >
                        {deletingId === sid ? t("common:actions.deleting") : t("common:actions.delete")}
                      </button>
                    )}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </>
  );
}

const API = "/api";

const TEXT_ASSET_KINDS = new Set([
  "plot",
  "character",
  "scene",
  "prop",
  "frame",
  "video_clip",
  "narration",
]);
const MEDIA_ASSET_KINDS = new Set(["image", "audio", "video", "final"]);

function CharacterSceneBoard({
  board,
  kind,
  projectId,
  scriptId,
  onEdit,
  onDelete,
  onCreate,
  onOpenBatchStudio,
  manualEditEnabled,
  onNavigateAsset,
  onRegenerated,
}: {
  board: BoardView;
  kind: "character" | "scene" | "prop" | "frame" | "video_clip";
  projectId?: string | null;
  scriptId?: string | null;
  onEdit?: (item: ImageTextAssetItem) => void;
  onDelete?: (item: ImageTextAssetItem) => void;
  onCreate?: (kind: "character" | "scene" | "prop" | "frame" | "video_clip") => void;
  onOpenBatchStudio?: () => void;
  manualEditEnabled?: boolean;
  onNavigateAsset?: (id: string, kind: string) => void;
  onRegenerated?: () => void;
}) {
  const { t } = useAppTranslation(["board", "common"]);
  const items = board.items ?? [];
  const empty =
    kind === "character"
      ? t("board:emptyCharacter")
      : kind === "scene"
        ? t("board:emptyScene")
        : kind === "frame"
          ? t("board:emptyFrame")
          : kind === "video_clip"
            ? t("board:emptyVideoClip")
            : t("board:emptyProp");
  if (items.length === 0 && !manualEditEnabled && !onOpenBatchStudio) {
    return <p className="muted">{empty}</p>;
  }
  return (
    <div className="character-scene-board">
      {(onOpenBatchStudio || (manualEditEnabled && projectId && scriptId && onCreate)) && (
        <div className="board-toolbar">
          {onOpenBatchStudio ? (
            <button type="button" className="btn-secondary btn-sm" onClick={onOpenBatchStudio}>
              {t("board:batchStudio.open")}
            </button>
          ) : null}
          {manualEditEnabled && projectId && scriptId && onCreate ? (
            <button type="button" className="btn-secondary btn-sm" onClick={() => onCreate(kind)}>
              {kind === "character"
                ? t("board:newCharacterShort")
                : kind === "scene"
                  ? t("board:newSceneShort")
                  : kind === "frame"
                    ? t("board:newFrameShort")
                    : kind === "video_clip"
                      ? t("board:newVideoClipShort")
                      : t("board:newPropShort")}
            </button>
          ) : null}
        </div>
      )}
      {items.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <div className="board-cards character-cards">
          {items.map((raw) => {
            const item = raw as unknown as ImageTextAssetItem;
            return (
              <ImageTextAssetCard
                key={item.id}
                item={item}
                projectId={projectId}
                scriptId={scriptId}
                onEdit={projectId && manualEditEnabled ? onEdit : undefined}
                onDelete={projectId && manualEditEnabled ? onDelete : undefined}
                manualEditEnabled={manualEditEnabled}
                onNavigateAsset={onNavigateAsset}
                onRegenerated={onRegenerated}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function StoryboardBoardPanel({
  board,
  projectId,
  scriptId,
  manualEditEnabled,
  onOpenShot,
  onApplyOps,
  onBoardRefresh,
  saving,
}: {
  board: BoardView;
  projectId?: string | null;
  scriptId?: string | null;
  manualEditEnabled?: boolean;
  onOpenShot?: (shot: ShotDetailItem) => void;
  onApplyOps?: (ops: import("../../types/videoPlan").VideoPlanOp[]) => Promise<void>;
  onBoardRefresh?: () => void;
  saving?: boolean;
}) {
  return (
    <StoryboardBoard
      board={board}
      projectId={projectId}
      scriptId={scriptId}
      manualEditEnabled={manualEditEnabled}
      saving={saving}
      onOpenShot={onOpenShot}
      onApplyOps={onApplyOps}
      onBoardRefresh={onBoardRefresh}
    />
  );
}

function PipelineBoard({ board }: { board: BoardView }) {
  const pipeline = board.pipeline ?? [];
  const extraItems = board.items ?? [];
  return (
    <div className="pipeline-board">
      <p className="muted">{board.description}</p>
      <h4>本对话已执行步骤（{String(board.stats?.style_mode ?? "storybook")}）</h4>
      {pipeline.length === 0 ? (
        <p className="muted">尚未委派子 Agent；发送创意后将按实际执行顺序展示。</p>
      ) : (
        <ol className="pipeline-master">
          {pipeline.map((step) => (
            <li key={step.step_type} className={`pipeline-step status-${step.status}`}>
              <span className="pipeline-order">{step.order}</span>
              <div>
                <strong>{step.title}</strong>
                <span className="muted"> · {step.agent}</span>
                <p className="muted">{step.description}</p>
              </div>
              <StatusBadge status={step.status} />
            </li>
          ))}
        </ol>
      )}
      {extraItems.length > 0 && (
        <>
          <h4>当前状态摘要</h4>
          <ol className="pipeline-sub">
            {extraItems.map((raw, i) => {
              const s = raw as Record<string, unknown>;
              return (
                <li key={String(s.kind ?? i)}>
                  {String(s.title ?? "")}
                </li>
              );
            })}
          </ol>
        </>
      )}
    </div>
  );
}

function BoardContent({
  activeTab,
  board,
  onEnterScript,
  onCreateScript,
  onDeleteScript,
  projectId,
  scriptId,
  scriptMeta,
  onEdit,
  onDelete,
  onCreateAsset,
  onOpenBatchStudio,
  onRefresh,
  manualEditEnabled,
  onNavigateAsset,
  onOpenShot,
  onOpenMedia,
  onGraphNodeClick,
  storyboardApplyOps,
  storyboardSaving,
}: {
  activeTab: BoardTabId;
  board: BoardView;
  onEnterScript?: (id: string) => void;
  onCreateScript?: (title: string) => void | Promise<void>;
  onDeleteScript?: (id: string) => void | Promise<void>;
  projectId?: string | null;
  scriptId?: string | null;
  scriptMeta?: ScriptBoardMeta | null;
  onEdit?: (item: ImageTextAssetItem) => void;
  onDelete?: (item: ImageTextAssetItem) => void;
  onCreateAsset?: (kind: "character" | "scene" | "prop" | "frame" | "video_clip") => void;
  onOpenBatchStudio?: () => void;
  onRefresh?: () => void;
  manualEditEnabled?: boolean;
  onNavigateAsset?: (id: string, kind: string) => void;
  onOpenShot?: (shot: ShotDetailItem) => void;
  onOpenMedia?: (item: MediaAssetItem) => void;
  onGraphNodeClick?: (node: BoardNode) => void;
  storyboardApplyOps?: (ops: import("../../types/videoPlan").VideoPlanOp[]) => Promise<void>;
  storyboardSaving?: boolean;
}) {
  switch (activeTab) {
    case "overview":
      return (
        <OverviewBoard
          board={board}
          onEnterScript={onEnterScript}
          onCreateScript={onCreateScript}
          onDeleteScript={onDeleteScript}
        />
      );
    case "knowledge":
      return (
        <KnowledgeBoard
          board={board}
          projectId={projectId}
          scriptId={scriptId}
          onEdit={onEdit}
          onDelete={onDelete}
          manualEditEnabled={manualEditEnabled}
          onNavigateAsset={onNavigateAsset}
          onRegenerated={onRefresh}
        />
      );
    case "script_details":
      return (
        <ScriptDetailsBoard
          board={board}
          projectId={projectId}
          scriptId={scriptId}
          manualEditEnabled={manualEditEnabled}
          onRefresh={onRefresh}
        />
      );
    case "character":
      return (
        <CharacterSceneBoard
          board={board}
          kind="character"
          projectId={projectId}
          scriptId={scriptId}
          onEdit={onEdit}
          onDelete={onDelete}
          onCreate={onCreateAsset}
          onOpenBatchStudio={onOpenBatchStudio}
          manualEditEnabled={manualEditEnabled}
          onNavigateAsset={onNavigateAsset}
          onRegenerated={onRefresh}
        />
      );
    case "scene":
      return (
        <CharacterSceneBoard
          board={board}
          kind="scene"
          projectId={projectId}
          scriptId={scriptId}
          onEdit={onEdit}
          onDelete={onDelete}
          onCreate={onCreateAsset}
          onOpenBatchStudio={onOpenBatchStudio}
          manualEditEnabled={manualEditEnabled}
          onNavigateAsset={onNavigateAsset}
          onRegenerated={onRefresh}
        />
      );
    case "prop":
      return (
        <CharacterSceneBoard
          board={board}
          kind="prop"
          projectId={projectId}
          scriptId={scriptId}
          onEdit={onEdit}
          onDelete={onDelete}
          onCreate={onCreateAsset}
          onOpenBatchStudio={onOpenBatchStudio}
          manualEditEnabled={manualEditEnabled}
          onNavigateAsset={onNavigateAsset}
          onRegenerated={onRefresh}
        />
      );
    case "frame":
      return (
        <CharacterSceneBoard
          board={board}
          kind="frame"
          projectId={projectId}
          scriptId={scriptId}
          onEdit={onEdit}
          onDelete={onDelete}
          onCreate={onCreateAsset}
          onOpenBatchStudio={onOpenBatchStudio}
          manualEditEnabled={manualEditEnabled}
          onNavigateAsset={onNavigateAsset}
          onRegenerated={onRefresh}
        />
      );
    case "video_clip":
      return (
        <CharacterSceneBoard
          board={board}
          kind="video_clip"
          projectId={projectId}
          scriptId={scriptId}
          onEdit={onEdit}
          onDelete={onDelete}
          onCreate={onCreateAsset}
          onOpenBatchStudio={onOpenBatchStudio}
          manualEditEnabled={manualEditEnabled}
          onNavigateAsset={onNavigateAsset}
          onRegenerated={onRefresh}
        />
      );
    case "storyboard":
      return (
        <StoryboardBoardPanel
          board={board}
          projectId={projectId}
          scriptId={scriptId}
          manualEditEnabled={manualEditEnabled}
          onOpenShot={onOpenShot}
          onApplyOps={storyboardApplyOps}
          onBoardRefresh={onRefresh}
          saving={storyboardSaving}
        />
      );
    case "edit":
      return <EditTimelineBoard board={board} />;
    case "media":
      return (
        <MediaBoard
          board={board}
          projectId={projectId}
          scriptId={scriptId}
          onOpenMedia={onOpenMedia}
        />
      );
    case "pipeline":
      return <PipelineBoard board={board} />;
    case "graph":
      return (
        <div className="board-graph-tab">
          <GraphBoard
            nodes={board.nodes ?? []}
            edges={board.edges ?? []}
            onOpenDetail={onGraphNodeClick}
          />
        </div>
      );
    default:
      return null;
  }
}

export const BoardPanel = memo(function BoardPanel({
  workspaceMode,
  activeTab,
  onTabChange,
  board,
  loading,
  error,
  onRefresh,
  onEnterScript,
  onCreateScript,
  onDeleteScript,
  onBackToOverview,
  projectId,
  scriptId,
  scriptMeta,
  manualEditEnabled = false,
}: BoardPanelProps) {
  const { t } = useAppTranslation(["board", "common"]);
  const [editing, setEditing] = useState<ImageTextAssetItem | null>(null);
  const [createAssetKind, setCreateAssetKind] = useState<
    "character" | "scene" | "prop" | "frame" | "video_clip" | null
  >(null);
  const [editStudioOpen, setEditStudioOpen] = useState(false);
  const [navTextDetail, setNavTextDetail] = useState<ImageTextAssetItem | null>(null);
  const [mediaDetail, setMediaDetail] = useState<MediaAssetItem | null>(null);
  const [shotDetail, setShotDetail] = useState<ShotDetailItem | null>(null);
  const [scriptDetailId, setScriptDetailId] = useState<string | null>(null);
  const [batchStudioOpen, setBatchStudioOpen] = useState(false);
  const isProjectMode = workspaceMode === "project";
  const isEditTab = !isProjectMode && activeTab === "edit" && Boolean(projectId && scriptId);
  const isStoryboardTab =
    !isProjectMode && activeTab === "storyboard" && Boolean(projectId && scriptId);
  const needVideoPlan =
    Boolean(projectId && scriptId) && (isStoryboardTab || Boolean(shotDetail));
  const hasEditTimeline = Boolean(scriptMeta?.has_edit_timeline);
  const needEditTimelineForShot =
    Boolean(projectId && scriptId) && Boolean(shotDetail) && hasEditTimeline;
  const editTimelineApi = useEditTimeline(projectId ?? "", scriptId ?? "", {
    enabled: isEditTab || needEditTimelineForShot,
  });
  const editTimelineSummary = useMemo(
    () =>
      hasEditTimeline
        ? buildEditTimelineStripSummary(editTimelineApi.timeline)
        : null,
    [hasEditTimeline, editTimelineApi.timeline],
  );
  const videoPlanApi = useVideoPlan(projectId, scriptId, {
    enabled: needVideoPlan,
  });
  const projectTabs = BOARD_TABS.filter((t) => t.id === "overview" || t.id === "knowledge");
  const visibleSecondaryIds = useMemo(
    () => new Set(visibleScriptTabs(scriptMeta ?? null)),
    [scriptMeta]
  );
  const scriptSecondaryTabs = BOARD_TABS.filter(
    (t) => t.level === 2 && visibleSecondaryIds.has(t.id)
  );
  const visibleTabs = isProjectMode
    ? projectTabs
    : [
        ...BOARD_TABS.filter((t) => t.id === "script_details"),
        ...scriptSecondaryTabs,
      ];

  useEffect(() => {
    if (isProjectMode) return;
    if (activeTab === "script_details") return;
    /** meta 尚未拉取或看板仍在切换加载中时，勿因 visibleSecondaryIds 为空误跳回详情 Tab。 */
    if (loading || !scriptMeta) return;
    if (!visibleSecondaryIds.has(activeTab)) {
      onTabChange("script_details");
    }
  }, [isProjectMode, activeTab, visibleSecondaryIds, onTabChange, loading, scriptMeta]);

  const boardReady = Boolean(board && boardMatchesTab(board, activeTab));

  const handleDeleteAsset = async (item: ImageTextAssetItem) => {
    if (!projectId || !scriptId || !manualEditEnabled) return;
    if (!window.confirm(`确定删除「${item.name}」？`)) return;
    try {
      await deleteTextAsset(projectId, scriptId, item.id);
      onRefresh();
    } catch (err) {
      window.alert((err as Error).message);
    }
  };

  /** 在图文/媒体/分镜详情间跳转：先关闭当前弹层，再按 kind 打开目标详情。 */
  const handleNavigateAsset = useCallback(
    async (assetId: string, kind: string) => {
      if (!projectId) return;
      setEditing(null);
      setNavTextDetail(null);
      setMediaDetail(null);
      setShotDetail(null);
      setScriptDetailId(null);

      let resolvedKind = kind;
      let name = assetId;
      try {
        const r = await fetch(`${API}/projects/${projectId}/assets/${assetId}/lineage`);
        if (r.ok) {
          const view = (await r.json()) as { asset?: { kind?: string; name?: string } };
          resolvedKind = view.asset?.kind ?? kind;
          name = view.asset?.name ?? assetId;
        }
      } catch {
        // 谱系拉取失败时仍用传入 kind 打开详情
      }

      const k = resolvedKind.replace(/^text_/, "");
      if (k === "script") {
        setScriptDetailId(assetId);
      } else if (k === "shot") {
        let shot: ShotDetailItem = { id: assetId, order: 0, time_label: name };
        if (scriptId) {
          try {
            const params = new URLSearchParams({ script_id: scriptId });
            const r = await fetch(
              `${API}/projects/${projectId}/board/storyboard?${params}`,
            );
            if (r.ok) {
              const b = (await r.json()) as BoardView;
              const found = (b.items ?? []).find(
                (it) => String((it as Record<string, unknown>).id) === assetId,
              );
              if (found) {
                shot = buildShotDetailItem(
                  parseStoryboardShot(
                    found as Record<string, unknown>,
                    0,
                    {
                      edit: t("board:storyboard.timelineEdit"),
                      plan: t("board:storyboard.timelinePlan"),
                    },
                  ),
                );
              }
            }
          } catch {
            // 使用最小 shot 占位
          }
        }
        setShotDetail(shot);
      } else if (MEDIA_ASSET_KINDS.has(k)) {
        let media: MediaAssetItem = { id: assetId, type: k, name };
        if (scriptId) {
          try {
            const params = new URLSearchParams({ script_id: scriptId });
            const r = await fetch(`${API}/projects/${projectId}/board/media?${params}`);
            if (r.ok) {
              const b = (await r.json()) as BoardView;
              const found = (b.items ?? []).find(
                (it) => String((it as Record<string, unknown>).id) === assetId,
              );
              if (found) {
                media = found as unknown as MediaAssetItem;
              }
            }
          } catch {
            // 使用最小 media 占位
          }
        }
        setMediaDetail(media);
      } else if (TEXT_ASSET_KINDS.has(k)) {
        let item: ImageTextAssetItem = { id: assetId, type: k, name };
        if (scriptId) {
          try {
            if (k === "plot") {
              const params = new URLSearchParams({ script_id: scriptId });
              const r = await fetch(
                `${API}/projects/${projectId}/board/script_details?${params}`,
              );
              if (r.ok) {
                const b = (await r.json()) as BoardView;
                const found = (b.items ?? []).find(
                  (it) =>
                    String((it as Record<string, unknown>).id) === assetId &&
                    String((it as Record<string, unknown>).type ?? "") === "plot",
                );
                if (found) {
                  const row = found as Record<string, unknown>;
                  item = {
                    id: assetId,
                    type: "plot",
                    name: String(row.name ?? name),
                    summary: String(row.preview ?? ""),
                    preview: String(row.preview ?? ""),
                    content: { text: String(row.preview ?? "") },
                  };
                }
              }
            } else {
              const full = await fetchBoardTextAssetItem(projectId, scriptId, assetId, k);
              if (full) item = full;
            }
          } catch {
            // 看板补全失败时仍用桩数据打开详情
          }
        }
        setNavTextDetail(item);
      }
    },
    [projectId, scriptId, t],
  );

  const handleGraphNodeClick = useCallback(
    (node: BoardNode) => {
      void handleNavigateAsset(node.id, node.kind);
    },
    [handleNavigateAsset],
  );

  const storyboardShotList = useMemo(() => {
    if (
      activeTab !== "storyboard" ||
      board?.kind !== "storyboard" ||
      !board?.items?.length
    ) {
      return [];
    }
    const timelineLabels = {
      edit: t("board:storyboard.timelineEdit"),
      plan: t("board:storyboard.timelinePlan"),
    };
    return parseStoryboardShots(board, timelineLabels).map(buildShotDetailItem);
  }, [activeTab, board, t]);

  const styleVideoModes = useMemo((): StyleVideoGenMode[] => {
    const raw = board?.stats?.video_modes;
    if (!Array.isArray(raw)) return [];
    return raw.filter(
      (m): m is StyleVideoGenMode =>
        m === "text2video" || m === "img2video" || m === "keyframes",
    );
  }, [board?.stats?.video_modes]);

  /** 看板刷新后同步抽屉内镜头摘要（保存编辑后元数据即时更新）。 */
  useEffect(() => {
    if (!shotDetail) return;
    const updated = storyboardShotList.find((s) => s.id === shotDetail.id);
    if (!updated) return;
    setShotDetail((prev) => {
      if (!prev || prev.id !== updated.id) return prev;
      return updated;
    });
  }, [storyboardShotList, shotDetail?.id]);

  const handleOpenShot = useCallback((shot: ShotDetailItem) => {
    setEditing(null);
    setNavTextDetail(null);
    setMediaDetail(null);
    setScriptDetailId(null);
    setShotDetail(shot);
  }, []);

  const handleOpenMedia = useCallback((item: MediaAssetItem) => {
    setEditing(null);
    setNavTextDetail(null);
    setShotDetail(null);
    setScriptDetailId(null);
    setMediaDetail(item);
  }, []);

  const handleStoryboardApplyOps = useCallback(
    async (ops: import("../../types/videoPlan").VideoPlanOp[]) => {
      await videoPlanApi.applyOps(ops);
      onRefresh();
    },
    [videoPlanApi, onRefresh],
  );

  const handleDeleteShot = useCallback(
    async (shotId: string) => {
      await videoPlanApi.applyOps([{ op: "delete", shot_id: shotId }]);
      onRefresh();
    },
    [videoPlanApi, onRefresh],
  );

  const handleSplitShot = useCallback(
    async (shotId: string) => {
      const data = await videoPlanApi.fetchVideoPlan();
      const planShot = data?.shots?.find((s) => s.id === shotId);
      const narr = planShot ? shotVoiceText(planShot) : "";
      const totalMs = planShot?.duration_ms ?? 3000;
      const halfMs = Math.max(500, Math.floor(totalMs / 2));
      const mid = Math.max(1, Math.ceil(narr.length / 2));
      const motion = planShot ? shotCameraMotion(planShot) : "static";
      const order = planShot?.order ?? 0;
      await videoPlanApi.applyOps([
        {
          op: "split",
          shot_id: shotId,
          new_shots: [
            buildMinimalShotPayload(order, halfMs, narr.slice(0, mid), motion),
            buildMinimalShotPayload(order + 1, totalMs - halfMs, narr.slice(mid), motion),
          ],
        },
      ]);
      onRefresh();
    },
    [videoPlanApi, onRefresh],
  );

  return (
    <div className="board-panel">
      <div className="board-tab-bar">
        {!isProjectMode && onBackToOverview && (
          <button type="button" className="board-back-link btn-secondary btn-sm" onClick={onBackToOverview}>
            {t("board:backOverview")}
          </button>
        )}
        <div className="board-tab-list">
          {visibleTabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`board-tab ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => onTabChange(tab.id)}
            >
              {t(`board:tabs.${tab.id}`)}
            </button>
          ))}
        </div>
        <div className="board-tab-actions">
          {!isProjectMode && projectId && scriptId ? (
            <>
              <GenerationQueueOpenButton />
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => setBatchStudioOpen(true)}
              >
                {t("board:batchStudio.open")}
              </button>
            </>
          ) : null}
          {!isEditTab && (
            <button type="button" className="btn-secondary btn-sm board-refresh" onClick={onRefresh}>
              {t("board:refresh")}
            </button>
          )}
        </div>
      </div>

      <div className="board-content">
        {(loading || !boardReady) && !isEditTab && <p className="muted">加载看板…</p>}
        {error && !isEditTab && <p className="board-error">{error}</p>}
        {!isProjectMode && !isEditTab && <ManualEditBanner visible={!manualEditEnabled} />}
        {isEditTab && projectId && scriptId && (
          <EditTabSimpleView
            projectId={projectId}
            scriptId={scriptId}
            timelineApi={editTimelineApi}
            onStudioOpenChange={setEditStudioOpen}
            studioOpen={editStudioOpen}
          />
        )}
        {!loading && boardReady && board && !isEditTab && (
          <>
            {board.description && <p className="muted board-desc">{board.description}</p>}
            <BoardContent
              activeTab={activeTab}
              board={board}
              onEnterScript={onEnterScript}
              onCreateScript={isProjectMode ? onCreateScript : undefined}
              onDeleteScript={isProjectMode ? onDeleteScript : undefined}
              projectId={projectId}
              scriptId={scriptId}
              scriptMeta={scriptMeta}
              onEdit={manualEditEnabled ? setEditing : undefined}
              onDelete={manualEditEnabled ? handleDeleteAsset : undefined}
              onCreateAsset={manualEditEnabled ? setCreateAssetKind : undefined}
              onOpenBatchStudio={() => setBatchStudioOpen(true)}
              onRefresh={onRefresh}
              manualEditEnabled={manualEditEnabled}
              onNavigateAsset={handleNavigateAsset}
              onOpenShot={handleOpenShot}
              onOpenMedia={handleOpenMedia}
              onGraphNodeClick={handleGraphNodeClick}
              storyboardApplyOps={
                manualEditEnabled ? handleStoryboardApplyOps : undefined
              }
              storyboardSaving={videoPlanApi.saving}
            />
          </>
        )}
      </div>

      {editing && projectId && (
        <ImageTextAssetEditor
          projectId={projectId}
          scriptId={scriptId}
          item={editing}
          disabled={!manualEditEnabled}
          onClose={() => setEditing(null)}
          onSaved={onRefresh}
        />
      )}

      {createAssetKind && projectId && scriptId && (
        <CreateTextAssetDialog
          projectId={projectId}
          scriptId={scriptId}
          assetType={createAssetKind}
          onClose={() => setCreateAssetKind(null)}
          onCreated={onRefresh}
        />
      )}

      {editStudioOpen && projectId && scriptId && (
        <Suspense fallback={null}>
          <EditorStudioModal
            projectId={projectId}
            scriptId={scriptId}
            timelineApi={editTimelineApi}
            onClose={(_saved) => {
              // 低优先级卸载全屏编辑器，避免与 Tab 预览重建争抢主线程。
              startTransition(() => {
                setEditStudioOpen(false);
              });
              // flushSave 已 PATCH 并更新 timeline 状态；预览由 timeline revision 指纹触发单次 soft-reload。
            }}
          />
        </Suspense>
      )}

      {navTextDetail && projectId && (
        <ImageTextAssetDetailModal
          item={navTextDetail}
          projectId={projectId}
          scriptId={scriptId}
          onClose={() => setNavTextDetail(null)}
          onNavigateAsset={handleNavigateAsset}
          manualEditEnabled={manualEditEnabled}
          onRegenerated={onRefresh}
        />
      )}

      {mediaDetail && projectId && (
        <MediaAssetDetailModal
          item={mediaDetail}
          projectId={projectId}
          scriptId={scriptId}
          onClose={() => setMediaDetail(null)}
          onNavigateAsset={handleNavigateAsset}
          manualEditEnabled={manualEditEnabled}
          onRegenerated={onRefresh}
        />
      )}

      {shotDetail && projectId && (
        <ShotDetailDrawer
          shot={shotDetail}
          projectId={projectId}
          scriptId={scriptId}
          allShots={storyboardShotList}
          manualEditEnabled={manualEditEnabled}
          planLoading={videoPlanApi.loading}
          getShotById={videoPlanApi.getShotById}
          fetchVideoPlan={videoPlanApi.fetchVideoPlan}
          patchShot={manualEditEnabled ? videoPlanApi.patchShot : undefined}
          syncFromTts={manualEditEnabled ? videoPlanApi.syncFromTts : undefined}
          analyzeAvSync={videoPlanApi.analyzeAvSync}
          applyAvSyncAction={
            manualEditEnabled ? videoPlanApi.applyAvSyncAction : undefined
          }
          onDeleteShot={manualEditEnabled ? handleDeleteShot : undefined}
          onSplitShot={manualEditEnabled ? handleSplitShot : undefined}
          onSaved={onRefresh}
          onClose={() => setShotDetail(null)}
          onNavigateAsset={handleNavigateAsset}
          onSelectShot={setShotDetail}
          onOpenEditTimeline={
            hasEditTimeline
              ? () => {
                  setShotDetail(null);
                  onTabChange("edit");
                }
              : undefined
          }
          hasEditTimeline={hasEditTimeline}
          editTimelineSummary={editTimelineSummary}
          styleVideoModes={styleVideoModes}
        />
      )}

      {scriptDetailId && projectId ? (
        <ScriptDetailDrawer
          projectId={projectId}
          scriptId={scriptDetailId}
          activeScriptId={scriptId}
          manualEditEnabled={manualEditEnabled}
          onClose={() => setScriptDetailId(null)}
          onRefresh={onRefresh}
          onNavigateAsset={handleNavigateAsset}
        />
      ) : null}

      {batchStudioOpen && projectId && scriptId ? (
        <BatchAssetStudioDrawer
          projectId={projectId}
          scriptId={scriptId}
          manualEditEnabled={manualEditEnabled}
          onClose={() => setBatchStudioOpen(false)}
          onRefresh={onRefresh}
        />
      ) : null}

      <GenerationQueueDrawer />
    </div>
  );
});
