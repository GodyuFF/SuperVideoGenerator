/**
 * 看板 Tab 容器与各类型看板渲染
 */

import { useEffect, useMemo, useState } from "react";
import { GraphBoard } from "./GraphBoard";
import { ImageTextAssetCard, type ImageTextAssetItem } from "../ImageTextAssetCard";
import { ImageTextAssetEditor } from "../ImageTextAssetEditor";
import { EditTimelineBoard } from "./EditTimelineBoard";
import { OpenCutIntegration, type OpenCutIntegrationProps } from "../../edit/opencut-integration";
import type { EditTimelineData } from "../../edit/types";
import { MediaPreview } from "../MediaPreview";
import { ScriptDetailsBoard } from "./ScriptDetailsBoard";
import { BOARD_TABS, type BoardTabId, type BoardView, type ScriptBoardMeta, visibleScriptTabs } from "../../types/board";
import type { WorkspaceMode } from "../../lib/localProjects";
import { ManualEditBanner } from "../manual/ManualEditBanner";
import { CreateTextAssetDialog } from "../manual/CreateTextAssetDialog";
import { PlotAssetEditor } from "../manual/PlotAssetEditor";
import { deleteTextAsset } from "../../lib/manualAssets";

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
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const items = board.items ?? [];

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const title = newTitle.trim() || `剧本 ${Date.now().toString().slice(-4)}`;
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
            placeholder="新剧本标题"
            disabled={creating}
            onChange={(e) => setNewTitle(e.target.value)}
          />
          <button type="submit" className="btn-secondary btn-sm" disabled={creating}>
            {creating ? "创建中…" : "＋ 新建剧本"}
          </button>
        </form>
      )}

      {items.length === 0 ? (
        <p className="muted">暂无剧本，请点击上方新建剧本。</p>
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
                  <strong>{String(item.title)}</strong>
                  <StatusBadge status={String(item.status)} />
                </header>
                <p className="muted board-preview">
                  {String(item.content_preview || "暂无正文")}
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
                      进入剧本
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
                        {deletingId === sid ? "删除中…" : "删除"}
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

function KnowledgeBoard({
  board,
  projectId,
  onEdit,
  onDelete,
  manualEditEnabled,
}: {
  board: BoardView;
  projectId?: string | null;
  onEdit?: (item: ImageTextAssetItem) => void;
  onDelete?: (item: ImageTextAssetItem) => void;
  manualEditEnabled?: boolean;
}) {
  const items = board.items ?? [];
  const stats = board.stats ?? {};
  return (
    <>
      <div className="board-stats-chips">
        {Object.entries(stats).map(([k, v]) => (
          <span key={k} className="stat-chip">
            {k}: {String(v)}
          </span>
        ))}
      </div>
      <ul className="knowledge-list">
        {items.map((raw) => {
          const item = raw as unknown as ImageTextAssetItem;
          return (
            <li key={item.id} className="knowledge-item">
              <ImageTextAssetCard
                item={item}
                onEdit={projectId && manualEditEnabled ? onEdit : undefined}
                onDelete={projectId && manualEditEnabled ? onDelete : undefined}
                manualEditEnabled={manualEditEnabled}
              />
            </li>
          );
        })}
      </ul>
    </>
  );
}

function CharacterSceneBoard({
  board,
  kind,
  projectId,
  scriptId,
  onEdit,
  onDelete,
  onCreate,
  manualEditEnabled,
}: {
  board: BoardView;
  kind: "character" | "scene" | "prop";
  projectId?: string | null;
  scriptId?: string | null;
  onEdit?: (item: ImageTextAssetItem) => void;
  onDelete?: (item: ImageTextAssetItem) => void;
  onCreate?: (kind: "character" | "scene" | "prop") => void;
  manualEditEnabled?: boolean;
}) {
  const items = board.items ?? [];
  const empty =
    kind === "character"
      ? "暂无角色资产"
      : kind === "scene"
        ? "暂无空镜资产"
        : "暂无物品资产";
  if (items.length === 0 && !manualEditEnabled) return <p className="muted">{empty}</p>;
  return (
    <div className="character-scene-board">
      {manualEditEnabled && projectId && scriptId && onCreate && (
        <div className="board-toolbar">
          <button type="button" className="btn-secondary btn-sm" onClick={() => onCreate(kind)}>
            ＋ 新建{kind === "character" ? "角色" : kind === "scene" ? "空镜" : "物品"}
          </button>
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
                onEdit={projectId && manualEditEnabled ? onEdit : undefined}
                onDelete={projectId && manualEditEnabled ? onDelete : undefined}
                manualEditEnabled={manualEditEnabled}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function ScriptBoard({
  board,
  projectId,
  scriptId,
  manualEditEnabled,
  onRefresh,
}: {
  board: BoardView;
  projectId?: string | null;
  scriptId?: string | null;
  manualEditEnabled?: boolean;
  onRefresh?: () => void;
}) {
  const [editingPlot, setEditingPlot] = useState<{
    id: string;
    name: string;
    text: string;
  } | null>(null);
  const [createPlotOpen, setCreatePlotOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const stats = board.stats ?? {};
  const content = String(stats.content_md ?? "").trim();
  const plotItems = board.items ?? [];

  const handleDeletePlot = async (assetId: string) => {
    if (!projectId || !scriptId) return;
    if (!window.confirm("确定删除该剧情资产？")) return;
    setDeletingId(assetId);
    try {
      await deleteTextAsset(projectId, scriptId, assetId);
      onRefresh?.();
    } catch (err) {
      window.alert((err as Error).message);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="script-board">
      {content ? (
        <>
          <div className="script-board-meta">
            <span>{String(stats.title ?? "")}</span>
            <StatusBadge status={String(stats.status ?? "draft")} />
            {stats.style_mode != null && stats.style_mode !== "" && (
              <span className="muted">{String(stats.style_mode)}</span>
            )}
          </div>
          <pre className="script-md-block">{content}</pre>
        </>
      ) : null}
      <div className="board-toolbar">
        {manualEditEnabled && projectId && scriptId && (
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={() => setCreatePlotOpen(true)}
          >
            ＋ 新建剧情
          </button>
        )}
      </div>
      {plotItems.length > 0 && (
        <>
          <h4>私有文字资产</h4>
          <ul className="simple-item-list">
            {plotItems.map((raw) => {
              const item = raw as Record<string, unknown>;
              const id = String(item.id);
              return (
                <li key={id} className="simple-item-row">
                  <span className="asset-type-badge">{String(item.type)}</span>
                  <span className="simple-item-text">
                    {String(item.name)} — {String(item.preview ?? "")}
                  </span>
                  {manualEditEnabled && projectId && (
                    <span className="simple-item-actions">
                      <button
                        type="button"
                        className="btn-secondary btn-sm"
                        onClick={() =>
                          setEditingPlot({
                            id,
                            name: String(item.name),
                            text: String(item.preview ?? ""),
                          })
                        }
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        className="btn-danger btn-sm"
                        disabled={deletingId === id}
                        onClick={() => void handleDeletePlot(id)}
                      >
                        {deletingId === id ? "删除中…" : "删除"}
                      </button>
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
      {!content && plotItems.length === 0 && (
        <p className="muted">暂无剧本内容。</p>
      )}

      {createPlotOpen && projectId && scriptId && (
        <CreateTextAssetDialog
          projectId={projectId}
          scriptId={scriptId}
          assetType="plot"
          onClose={() => setCreatePlotOpen(false)}
          onCreated={() => onRefresh?.()}
        />
      )}
      {editingPlot && projectId && (
        <PlotAssetEditor
          projectId={projectId}
          assetId={editingPlot.id}
          initialName={editingPlot.name}
          initialText={editingPlot.text}
          onClose={() => setEditingPlot(null)}
          onSaved={() => onRefresh?.()}
        />
      )}
    </div>
  );
}

function StoryboardBoard({ board }: { board: BoardView }) {
  const items = board.items ?? [];
  if (items.length === 0) {
    return <p className="muted">分镜计划稿将在 storyboard_agent 完成后显示。</p>;
  }
  return (
    <ol className="shot-list board-shot-list">
      {items.map((raw, index) => {
        const shot = raw as Record<string, unknown>;
        return (
          <li key={String(shot.id)} className="shot-item">
            <div className="shot-header">
              <span className="shot-order">镜 {index + 1}</span>
              <span className="shot-meta">
                {Number(shot.duration_ms) / 1000}s · {String(shot.camera_motion)}
              </span>
            </div>
            <p className="shot-narration">{String(shot.narration_text)}</p>
            {shot.tts_audio_url ? (
              <MediaPreview
                kind="audio"
                url={String(shot.tts_audio_url)}
                label="配音试听"
                className="shot-tts-preview"
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

function MediaBoard({ board }: { board: BoardView }) {
  const items = board.items ?? [];
  const byType: Record<string, typeof items> = {};
  for (const raw of items) {
    const t = String((raw as Record<string, unknown>).type);
    byType[t] = byType[t] ?? [];
    byType[t].push(raw);
  }
  if (items.length === 0) {
    return <p className="muted">媒体资产将在图片/视频/TTS/剪辑步骤完成后显示。</p>;
  }
  return (
    <div className="media-board-groups">
      {Object.entries(byType).map(([type, group]) => (
        <section key={type}>
          <h4>
            {type}（{group.length}）
          </h4>
          <ul className="media-output-list">
            {group.map((raw) => {
              const m = raw as Record<string, unknown>;
              const url = m.url ? String(m.url) : "";
              const type = String(m.type);
              return (
                <li key={String(m.id)} className="media-output-item">
                  <strong>{String(m.name)}</strong>
                  {m.shot_id ? (
                    <span className="muted"> · 镜头 {String(m.shot_id)}</span>
                  ) : null}
                  <MediaPreview kind={type} url={url} className="board-media-preview" />
                  {url ? (
                    <a href={url} target="_blank" rel="noreferrer" className="media-link">
                      打开文件
                    </a>
                  ) : (
                    <code>{String(m.id)}</code>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

function PipelineBoard({ board }: { board: BoardView }) {
  const pipeline = board.pipeline ?? [];
  const scriptSteps = board.items ?? [];
  return (
    <div className="pipeline-board">
      <h4>主编排顺序（{String(board.stats?.style_mode ?? "dynamic_image")}）</h4>
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
      {scriptSteps.length > 0 && (
        <>
          <h4>剧本 Agent 内部顺序</h4>
          <ol className="pipeline-sub">
            {scriptSteps.map((raw, i) => {
              const s = raw as Record<string, unknown>;
              return (
                <li key={String(s.step_type ?? i)}>
                  {Number(s.order)}. {String(s.title ?? s.step_type)}
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
  onRefresh,
  manualEditEnabled,
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
  onCreateAsset?: (kind: "character" | "scene" | "prop") => void;
  onRefresh?: () => void;
  manualEditEnabled?: boolean;
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
          onEdit={onEdit}
          onDelete={onDelete}
          manualEditEnabled={manualEditEnabled}
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
    case "script":
      return (
        <ScriptBoard
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
          manualEditEnabled={manualEditEnabled}
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
          manualEditEnabled={manualEditEnabled}
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
          manualEditEnabled={manualEditEnabled}
        />
      );
    case "storyboard":
      return <StoryboardBoard board={board} />;
    case "edit":
      if (projectId && scriptId) {
        return (
          <OpenCutIntegration
            project={{
              id: scriptId,
              name: (scriptMeta as Record<string, unknown>)?.title as string ?? "未命名剧本",
            }}
            className="board-edit-studio"
          />
        );
      }
      return <EditTimelineBoard board={board} />;
    case "media":
      return <MediaBoard board={board} />;
    case "pipeline":
      return <PipelineBoard board={board} />;
    default:
      return null;
  }
}

export function BoardPanel({
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
  const [editing, setEditing] = useState<ImageTextAssetItem | null>(null);
  const [createAssetKind, setCreateAssetKind] = useState<
    "character" | "scene" | "prop" | null
  >(null);
  const isProjectMode = workspaceMode === "project";
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
    if (!visibleSecondaryIds.has(activeTab)) {
      onTabChange("script_details");
    }
  }, [isProjectMode, activeTab, visibleSecondaryIds, onTabChange]);

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

  return (
    <div className="board-panel">
      <div className="board-tab-bar">
        {!isProjectMode && onBackToOverview && (
          <button type="button" className="board-back-link btn-secondary btn-sm" onClick={onBackToOverview}>
            ← 返回整体看板
          </button>
        )}
        <div className="board-tab-list">
          {visibleTabs.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`board-tab ${activeTab === t.id ? "active" : ""}`}
              onClick={() => onTabChange(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <button type="button" className="btn-secondary btn-sm board-refresh" onClick={onRefresh}>
          刷新
        </button>
      </div>

      <div className="board-content">
        {loading && <p className="muted">加载看板…</p>}
        {error && <p className="board-error">{error}</p>}
        {!isProjectMode && <ManualEditBanner visible={!manualEditEnabled} />}
        {!loading && board && (
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
              onRefresh={onRefresh}
              manualEditEnabled={manualEditEnabled}
            />
          </>
        )}
      </div>

      {editing && projectId && (
        <ImageTextAssetEditor
          projectId={projectId}
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
    </div>
  );
}
