/**
 * 看板 Tab 容器与各类型看板渲染
 */

import { GraphBoard } from "./GraphBoard";
import type { BoardTabId, BoardView } from "../../types/board";
import { BOARD_TABS } from "../../types/board";

interface BoardPanelProps {
  activeTab: BoardTabId;
  onTabChange: (tab: BoardTabId) => void;
  board: BoardView | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onSelectScript?: (scriptId: string) => void;
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`board-status status-${status}`}>{status}</span>;
}

function OverviewBoard({
  board,
  onSelectScript,
}: {
  board: BoardView;
  onSelectScript?: (id: string) => void;
}) {
  const items = board.items ?? [];
  if (items.length === 0) {
    return <p className="muted">暂无剧本，请新建项目或发送对话开始生成。</p>;
  }
  return (
    <div className="board-cards">
      {items.map((raw) => {
        const item = raw as Record<string, unknown>;
        const sid = String(item.script_id ?? "");
        return (
          <article
            key={sid}
            className={`board-card ${item.is_active ? "active" : ""}`}
          >
            <header>
              <strong>{String(item.title)}</strong>
              <StatusBadge status={String(item.status)} />
            </header>
            <p className="muted board-preview">{String(item.content_preview || "暂无正文")}</p>
            <ul className="board-stats-row">
              <li>资产 {String(item.asset_count)}</li>
              <li>媒体 {String(item.media_count)}</li>
              <li>分镜 {String(item.shot_count)}</li>
              <li>
                进度 {String(item.plan_steps_completed)}/{String(item.plan_steps_total)}
              </li>
            </ul>
            {onSelectScript && sid && (
              <button type="button" className="btn-secondary btn-sm" onClick={() => onSelectScript(sid)}>
                切换到此剧本
              </button>
            )}
          </article>
        );
      })}
    </div>
  );
}

function KnowledgeBoard({ board }: { board: BoardView }) {
  const items = board.items ?? [];
  const stats = board.stats ?? {};
  return (
    <>
      <div className="board-stats-chips">
        {Object.entries(stats).map(([k, v]) => (
          <span key={k} className="stat-chip">{k}: {String(v)}</span>
        ))}
      </div>
      <ul className="knowledge-list">
        {items.map((raw) => {
          const item = raw as Record<string, unknown>;
          const media = (item.media as { url?: string; name?: string }[]) ?? [];
          return (
            <li key={String(item.id)} className="knowledge-item">
              <span className="asset-type-badge">{String(item.type)}</span>
              <strong>{String(item.name)}</strong>
              <p>{String(item.preview || "")}</p>
              {media.length > 0 && (
                <div className="thumb-row">
                  {media.map((m) =>
                    m.url ? (
                      <a key={m.url} href={m.url} target="_blank" rel="noreferrer" className="thumb-link">
                        {m.name ?? "图片"}
                      </a>
                    ) : null
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}

function CharacterSceneBoard({ board, kind }: { board: BoardView; kind: "character" | "scene" }) {
  const items = board.items ?? [];
  const empty = kind === "character" ? "暂无角色资产" : "暂无场景资产";
  if (items.length === 0) return <p className="muted">{empty}</p>;
  const bodyKey = kind === "character" ? "appearance" : "description";
  return (
    <div className="board-cards character-cards">
      {items.map((raw) => {
        const item = raw as Record<string, unknown>;
        const images = (item.images as { url?: string; name?: string }[]) ?? [];
        return (
          <article key={String(item.id)} className="board-card character-card">
            <h4>{String(item.name)}</h4>
            <p>{String(item[bodyKey] || "")}</p>
            {images.length > 0 ? (
              <div className="character-images">
                {images.map((img) =>
                  img.url ? (
                    <figure key={img.url}>
                      <img src={img.url} alt={img.name ?? ""} loading="lazy" />
                      <figcaption>{img.name}</figcaption>
                    </figure>
                  ) : null
                )}
              </div>
            ) : (
              <p className="muted">尚未生成关联图片</p>
            )}
          </article>
        );
      })}
    </div>
  );
}

function ScriptBoard({ board }: { board: BoardView }) {
  const stats = board.stats ?? {};
  const content = String(stats.content_md ?? "");
  return (
    <div className="script-board">
      <div className="script-board-meta">
        <span>{String(stats.title ?? "")}</span>
        <StatusBadge status={String(stats.status ?? "draft")} />
        {stats.style_mode != null && stats.style_mode !== "" && (
          <span className="muted">{String(stats.style_mode)}</span>
        )}
      </div>
      {content ? (
        <pre className="script-md-block">{content}</pre>
      ) : (
        <p className="muted">剧本正文将在 script_agent 执行 parse_brief 后显示。</p>
      )}
      {(board.items ?? []).length > 0 && (
        <>
          <h4>私有文字资产</h4>
          <ul className="simple-item-list">
            {(board.items ?? []).map((raw) => {
              const item = raw as Record<string, unknown>;
              return (
                <li key={String(item.id)}>
                  <span className="asset-type-badge">{String(item.type)}</span>
                  {String(item.name)} — {String(item.preview ?? "")}
                </li>
              );
            })}
          </ul>
        </>
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
      {items.map((raw) => {
        const shot = raw as Record<string, unknown>;
        return (
          <li key={String(shot.id)} className="shot-item">
            <div className="shot-header">
              <span className="shot-order">镜 {Number(shot.order) + 1}</span>
              <span className="shot-meta">
                {Number(shot.duration_ms) / 1000}s · {String(shot.camera_motion)}
              </span>
            </div>
            <p className="shot-narration">{String(shot.narration_text)}</p>
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
          <h4>{type}（{group.length}）</h4>
          <ul className="media-output-list">
            {group.map((raw) => {
              const m = raw as Record<string, unknown>;
              return (
                <li key={String(m.id)} className="media-output-item">
                  <strong>{String(m.name)}</strong>
                  {m.url ? (
                    <a href={String(m.url)} target="_blank" rel="noreferrer">{String(m.url)}</a>
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
  onSelectScript,
}: {
  activeTab: BoardTabId;
  board: BoardView;
  onSelectScript?: (id: string) => void;
}) {
  switch (activeTab) {
    case "overview":
      return <OverviewBoard board={board} onSelectScript={onSelectScript} />;
    case "knowledge":
      return <KnowledgeBoard board={board} />;
    case "script_details":
      // Two-stage: first load scripts via overview data, selection is local (no global scriptId change)
      return <OverviewBoard board={board} onSelectScript={onSelectScript} />;
    case "script":
      return <ScriptBoard board={board} />;
    case "character":
      return <CharacterSceneBoard board={board} kind="character" />;
    case "scene":
      return <CharacterSceneBoard board={board} kind="scene" />;
    case "storyboard":
      return <StoryboardBoard board={board} />;
    case "media":
      return <MediaBoard board={board} />;
    case "pipeline":
      return <PipelineBoard board={board} />;
    default:
      return null;
  }
}

export function BoardPanel({
  activeTab,
  onTabChange,
  board,
  loading,
  error,
  onRefresh,
  onSelectScript,
}: BoardPanelProps) {
  const level1 = BOARD_TABS.filter((t) => t.level === 1 && ["overview", "knowledge", "script_details"].includes(t.id));
  const level2 = BOARD_TABS.filter((t) => t.level === 2);

  return (
    <div className="board-panel">
      <div className="board-tab-bar">
        <div className="board-tab-group">
          <span className="board-tab-group-label">层级 1</span>
          {level1.map((t) => (
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
        <div className="board-tab-group">
          <span className="board-tab-group-label">层级 2</span>
          {level2.map((t) => (
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
        {!loading && board && (
          <>
            {board.description && <p className="muted board-desc">{board.description}</p>}
            <BoardContent
              activeTab={activeTab}
              board={board}
              onSelectScript={onSelectScript}
            />
          </>
        )}
      </div>
    </div>
  );
}
